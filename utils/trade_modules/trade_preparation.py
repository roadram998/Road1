import asyncio
import logging
import time
from datetime import datetime, timedelta
from BinaryOptionsToolsV2.pocketoption.asyncronous import PocketOptionAsync
from .trade_utils import check_payout, validate_trade_time
import aiohttp
import pytz

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
logging.getLogger().addHandler(console_handler)

async def check_internet_connection(timeout=2, retries=2):  # تحسين: تقليل المهلة إلى 2 ثانية والمحاولات إلى 2
    """التحقق من الاتصال بالإنترنت باستخدام رابط المنصة."""
    url = 'https://pocketoption.com/en/'  # تحسين: استخدام رابط واحد
    for attempt in range(1, retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=timeout) as response:
                    if response.status == 200:
                        logging.info(f"الاتصال بالإنترنت ناجح عبر {url}")
                        return True
        except Exception as e:
            logging.error(f"محاولة {attempt}/{retries} - فشل التحقق من الاتصال عبر {url}: {str(e)}")
            print(f"⚠️ محاولة {attempt}/{retries} - فشل التحقق من الاتصال عبر {url}: {str(e)}")
            if attempt < retries:
                await asyncio.sleep(0.5)  # تحسين: تقليل النوم إلى 0.5 ثانية
    logging.error("فشل التحقق من الاتصال بالإنترنت بعد كل المحاولات")
    print("⚠️ فشل التحقق من الاتصال بالإنترنت بعد كل المحاولات")
    return False

async def prepare_trade(client: PocketOptionAsync, symbol: str, trade_time: str, direction: str, martingale_settings: dict, trade_time_exact: str = None, logger=None):
    """تحضير إشارة التداول قبل تنفيذ الصفقة."""
    start_time = time.time()
    try:
        # التحقق من الاتصال بالإنترنت
        if not await check_internet_connection():
            print("⚠️ لا يوجد اتصال بالإنترنت أثناء تحضير الصفقة")
            return None, None, None

        # التحقق من اتجاه الصفقة
        if direction not in ["call", "put"]:
            logging.error(f"اتجاه غير صالح: {direction}")
            print(f"⚠️ اتجاه غير صالح: {direction}")
            return None, None, None

        # التحقق من نسبة العائد
        min_payout = float(martingale_settings.get("payout", 70.0))
        api_symbol, payout = await check_payout(client, symbol, min_payout)
        if api_symbol is None:
            logging.info(f"تم تخطي {symbol} بسبب انخفاض نسبة العائد أو الرمز غير نشط")
            return None, None, None

        # التحقق من وقت الصفقة
        if not trade_time_exact or not validate_trade_time(trade_time_exact):
            logging.error(f"وقت الإشارة غير صالح: {trade_time_exact}")
            print(f"⚠️ وقت الإشارة غير صالح: {trade_time_exact}")
            return None, None, None

        # تحسين: تبسيط معالجة وقت الصفقة
        target_tz = pytz.timezone('America/Sao_Paulo')
        current_time = datetime.now(target_tz)
        try:
            trade_time_obj = datetime.strptime(trade_time_exact, "%H:%M:%S").replace(
                year=current_time.year, month=current_time.month, day=current_time.day
            )
            trade_time_obj = target_tz.localize(trade_time_obj)
            if trade_time_obj < current_time:
                trade_time_obj += timedelta(days=1)
        except ValueError as e:
            logging.error(f"خطأ في وقت الصفقة: {str(e)}")
            print(f"⚠️ خطأ في وقت الصفقة: {str(e)}")
            return None, None, None

        # حساب مدة الصفقة
        duration_map = {"M1": 60, "M2": 120, "M3": 180, "M5": 300, "M15": 900}
        if trade_time.startswith("M") and trade_time[1:].isdigit():
            duration = duration_map.get(trade_time.upper(), None)
            if duration is None:
                logging.error(f"مدة غير معروفة: {trade_time}")
                print(f"⚠️ مدة غير مدعومة: {trade_time}")
                return None, None, None
        else:
            time_diff = (trade_time_obj - current_time).total_seconds()
            if time_diff > 600:
                logging.warning(f"وقت الصفقة بعيد جدًا: {trade_time}, فرق الوقت: {time_diff} ثانية")
                print(f"⚠️ وقت الصفقة بعيد جدًا: {trade_time}")
                return None, None, None
            if time_diff > 0:
                logging.info(f"⏳ الانتظار {time_diff} ثانية حتى: {trade_time}")
                print(f"⏱️ الانتظار: {time_diff:.2f}")
                await asyncio.sleep(time_diff - 0.5)
            duration = int(time_diff)

        # تسجيل الإشارة
        if logger:
            logger.log_signal(symbol, trade_time, direction, signal_score=1, accepted=True)

        end_time = time.time()
        logging.info(f"Preparation time: {(end_time - start_time):.3f} seconds")
        logging.info(f"تم تحضير الصفقة: {api_symbol}, مدة: {duration} ثانية, اتجاه: {direction}")
        return api_symbol, duration, direction

    except Exception as e:
        logging.error(f"خطأ أثناء تحضير الصفقة لـ {symbol}: {str(e)}")
        print(f"⚠️ خطأ أثناء تحضير الصفقة لـ {symbol}: {str(e)}")
        return None, None, None