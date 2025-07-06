from BinaryOptionsToolsV2.pocketoption.asyncronous import PocketOptionAsync
import logging
import time
import asyncio
import aiohttp
from .trade_utils import check_payout, display_account_stats
from utils.redis_client import redis_client

# إعدادات التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('errors.log', mode='a', encoding='utf-8')]
)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger = logging.getLogger()
if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    logger.addHandler(console_handler)

async def check_internet_connection(timeout=1):
    """التحقق من الاتصال بالإنترنت مرة واحدة فقط."""
    url = 'https://po.trade'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    logging.info(f"الاتصال بالإنترنت ناجح عبر {url}")
                    return True
                else:
                    logging.error(f"فشل التحقق من الاتصال عبر {url}: استجابة غير متوقعة {response.status}")
                    print(f"⚠️ فشل التحقق من الاتصال عبر {url}: استجابة {response.status}")
    except Exception as e:
        logging.error(f"فشل التحقق من الاتصال عبر {url}: {str(e)}")
        print(f"⚠️ فشل التحقق من الاتصال عبر {url}: {str(e)}")
    return False

async def is_ws_connected(client: PocketOptionAsync):
    """التحقق من اتصال WebSocket باستخدام balance مع التخزين المؤقت."""
    try:
        # التحقق من التخزين المؤقت أولاً
        redis_key = "ws_connection_status"
        cached_status = redis_client.get_data(redis_key)
        if cached_status and cached_status.get("is_connected", False):
            logging.info("استخدام حالة اتصال WebSocket من التخزين المؤقت")
            return True

        # إذا لم يكن هناك تخزين مؤقت، نفذ طلب balance
        balance = await client.balance()
        if balance is not None and isinstance(balance, (int, float)) and balance >= 0:
            redis_client.set_data(redis_key, {"is_connected": True}, ttl=30)  # تخزين مؤقت لمدة 30 ثانية
            logging.info("اتصال WebSocket نشط")
            return True
        else:
            logging.error("فشل التحقق من اتصال WebSocket: استجابة غير صالحة من balance")
            redis_client.set_data(redis_key, {"is_connected": False}, ttl=30)
            return False
    except Exception as e:
        logging.error(f"اتصال WebSocket غير نشط: {str(e)}")
        print(f"⚠️ فشل الاتصال بـ WebSocket: {str(e)}")
        redis_client.set_data(redis_key, {"is_connected": False}, ttl=30)
        return False

async def confirm_trade(client: PocketOptionAsync, trade_id, timeout=3):
    """تأكيد تنفيذ الصفقة."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            balance = await client.balance()
            if balance is not None and balance >= 0:
                logging.info(f"تم تأكيد الصفقة {trade_id} بنجاح")
                return True
        except Exception as e:
            logging.warning(f"فشل تأكيد الصفقة {trade_id}: {str(e)}")
        await asyncio.sleep(0.5)
    logging.error(f"لم يتم تأكيد الصفقة {trade_id} خلال {timeout} ثواني")
    print(f"⚠️ لم يتم تأكيد الصفقة {trade_id}")
    return False

async def safe_execute_trade(client: PocketOptionAsync, symbol: str, amount: float, duration_input, direction: str, min_payout: float, martingale_strategy):
    """تنفيذ الصفقة مرة واحدة مع التحقق من الاتصال والرصيد."""
    try:
        start_time_total = time.time()
        # التحقق من الاتصال بالإنترنت
        internet_start = time.time()
        if not await check_internet_connection():
            await display_account_stats(martingale_strategy)
            return None
        logging.info(f"وقت التحقق من الاتصال بالإنترنت: {(time.time() - internet_start):.3f} ثانية")

        # التحقق من اتصال WebSocket
        if not await is_ws_connected(client):
            await display_account_stats(martingale_strategy)
            return None

        # التحقق من الرصيد
        MINIMUM_TRADE_AMOUNT = 1.0
        BUFFER_AMOUNT = 0.5
        balance = await client.balance()
        if balance is None or balance < 0:
            logging.error("فشل جلب الرصيد قبل تنفيذ الصفقة")
            print("⚠️ فشل جلب الرصيد")
            await display_account_stats(martingale_strategy)
            return None
        logging.info(f"الرصيد الحالي: {balance}, المبلغ المطلوب: {amount}, الحد الأدنى: {MINIMUM_TRADE_AMOUNT}, الاحتياطي: {BUFFER_AMOUNT}")
        if balance < amount + MINIMUM_TRADE_AMOUNT + BUFFER_AMOUNT:
            logging.error(f"الرصيد غير كافٍ: {balance} < {amount + MINIMUM_TRADE_AMOUNT + BUFFER_AMOUNT}")
            print(f"⚠️ الرصيد غير كافٍ: {balance:,.2f} $")
            await display_account_stats(martingale_strategy)
            return None

        # التحقق من نسبة العائد
        api_symbol, payout = await check_payout(client, symbol, min_payout)
        if api_symbol is None:
            logging.error(f"الأصل {symbol} غير نشط أو العائد أقل من الحد الأدنى")
            print(f"⚠️ الأصل {symbol} غير نشط أو العائد أقل من الحد الأدنى")
            await display_account_stats(martingale_strategy)
            return None

        # تحويل المدة
        duration_map = {"M1": 60, "M2": 120, "M3": 180, "M5": 300, "M15": 900}
        if isinstance(duration_input, str):
            duration = duration_map.get(duration_input.upper())
            if duration is None:
                logging.error(f"مدة غير معروفة: {duration_input}")
                print(f"⚠️ مدة غير مدعومة: {duration_input}")
                await display_account_stats(martingale_strategy)
                return None
        else:
            duration = duration_input

        # التحقق من صحة المدة
        if not isinstance(duration_input, (str, int, float)):
            logging.error(f"نوع المدة غير صالح: {type(duration_input)}، القيمة: {duration_input}")
            print(f"⚠️ نوع المدة غير صالح: {duration_input}")
            await display_account_stats(martingale_strategy)
            return None
        if not isinstance(duration, (int, float)) or duration <= 0 or duration > 900:
            logging.error(f"مدة غير صالحة: {duration}")
            print(f"⚠️ مدة غير صالحة: {duration}")
            await display_account_stats(martingale_strategy)
            return None

        # تنفيذ الصفقة
        start_time = time.time()
        trade_id = None
        timeout = 60
        try:
            async with asyncio.timeout(timeout):
                if direction == "call":
                    trade_id, _ = await client.buy(api_symbol, amount, duration, check_win=False)
                elif direction == "put":
                    trade_id, _ = await client.sell(api_symbol, amount, duration, check_win=False)
                else:
                    logging.error(f"اتجاه غير صالح: {direction}")
                    print(f"⚠️ اتجاه غير صالح: {direction}")
                    await display_account_stats(martingale_strategy)
                    return None
        except asyncio.TimeoutError:
            logging.error(f"تجاوز المهلة الزمنية {timeout} ثانية أثناء تنفيذ الصفقة لـ {api_symbol}")
            print(f"❌ تجاوز المهلة الزمنية {timeout} ثانية لـ {api_symbol}")
            await display_account_stats(martingale_strategy)
            return None
        except Exception as e:
            logging.error(f"خطأ أثناء تنفيذ الصفقة لـ {api_symbol}: {str(e)}")
            print(f"❌ فشل تنفيذ الصفقة لـ {api_symbol}: {str(e)}")
            await display_account_stats(martingale_strategy)
            return None

        end_time = time.time()
        logging.info(f"تأخير تنفيذ الصفقة: {(end_time - start_time):.3f} ثانية")

        # تأكيد الصفقة
        if trade_id is not None:
            if await confirm_trade(client, trade_id):
                logging.info(f"نجاح بدء الصفقة: {api_symbol}, trade_id: {trade_id}")
                return trade_id
            else:
                logging.error(f"لم يتم تأكيد الصفقة: {api_symbol}")
                print(f"❌ لم يتم تأكيد الصفقة: {api_symbol}")
                await display_account_stats(martingale_strategy)
                return None
        else:
            logging.error(f"فشل تنفيذ الصفقة لـ {api_symbol}: لا يوجد معرف صفقة")
            print(f"❌ فشل تنفيذ الصفقة لـ {api_symbol}")
            await display_account_stats(martingale_strategy)
            return None

    except Exception as e:
        logging.error(f"خطأ عام أثناء تنفيذ الصفقة لـ {symbol}: {str(e)}")
        print(f"❌ خطأ عام أثناء تنفيذ الصفقة: {str(e)}")
        await display_account_stats(martingale_strategy)
        return None