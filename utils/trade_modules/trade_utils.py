import re
from datetime import datetime
from BinaryOptionsToolsV2.pocketoption.asyncronous import PocketOptionAsync
import logging
import asyncio
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
logging.getLogger().addHandler(console_handler)

async def display_account_stats(martingale_strategy):
    """عرض إحصائيات الحساب باستخدام بيانات MartingaleStrategy"""
    try:
        net_profit = martingale_strategy.current_balance - martingale_strategy.initial_balance
        net_loss = martingale_strategy.initial_balance - martingale_strategy.current_balance if martingale_strategy.current_balance < martingale_strategy.initial_balance else 0.0
        print("📊 Account Stats:")
        print(f"  Wins: {martingale_strategy.wins}")
        print(f"  Profit: {net_profit:.2f}")
        print(f"  Losses: {martingale_strategy.losses}")
        print(f"  Ties: {martingale_strategy.ties}")
        print(f"  Win Rate: {(martingale_strategy.wins / martingale_strategy.total_trades * 100 if martingale_strategy.total_trades > 0 else 0.0):.2f}%")
        print(f"  Total Trades: {martingale_strategy.total_trades}")
        print(f"💰 Current Balance: {martingale_strategy.current_balance:,.2f} $")
        logging.info("تم عرض إحصائيات الحساب")
    except Exception as e:
        logging.error(f"خطأ أثناء عرض إحصائيات الحساب: {str(e)}")
        print(f"⚠️ خطأ أثناء عرض إحصائيات الحساب: {str(e)}")

def normalize_symbol(symbol: str) -> str:
    """تطبيع صيغة الرمز لضمان التوافق مع API."""
    symbol = symbol.replace(" ", "").replace("/", "").lower()
    symbol_mapping = {
        "eurusdotc": "eurusd_otc",
        "usdphpotc": "usdphp_otc",
    }
    symbol = symbol_mapping.get(symbol, symbol)
    symbol = symbol.replace("-otc", "_otc").replace("otc", "_otc")
    while "__otc" in symbol:
        symbol = symbol.replace("__otc", "_otc")
    return symbol

async def check_payout(client: PocketOptionAsync, symbol: str, min_payout: float) -> tuple:
    """التحقق من نسبة العائد مع التخزين المؤقت المحلي."""
    max_attempts = 3  # تحسين: تقليل المحاولات إلى 3
    attempt = 0
    normalized_symbol = normalize_symbol(symbol)
    symbol_variants = [
        normalized_symbol,
        normalized_symbol.replace("_otc", ""),
        normalized_symbol.replace("_otc", "-otc")
    ]

    # التحقق من التخزين المؤقت في Redis
    redis_key = f"payout_{normalized_symbol}"
    cached_payout = redis_client.get_data(redis_key)
    if cached_payout:
        logging.info(f"Using cached payout for {symbol}: {cached_payout['payout']}%")
        if cached_payout['payout'] >= min_payout:
            return cached_payout['symbol'], cached_payout['payout']
        return None, None

    while attempt < max_attempts:
        try:
            full_payout = await client.payout()
            logging.info(f"محاولة {attempt + 1}: استجابة client.payout(): {full_payout}")
            if not full_payout:
                logging.warning(f"محاولة {attempt + 1}: استجابة client.payout() فارغة")
                attempt += 1
                await asyncio.sleep(0.5)  # تحسين: تقليل النوم إلى 0.5 ثانية
                continue

            for variant in symbol_variants:
                for key in full_payout:
                    if key.lower() == variant.lower():
                        payout = float(full_payout[key])
                        logging.info(f"رمز: {key}, نسبة العائد: {payout}%, الحد الأدنى: {min_payout}%")
                        if payout >= min_payout:
                            redis_client.set_data(redis_key, {"symbol": key, "payout": payout}, ttl=180)  # تحسين: TTL إلى 3 دقائق
                            logging.info(f"رمز صالح: {key}, نسبة العائد: {payout}%")
                            return key, payout
                        else:
                            logging.warning(f"تم تخطي {key}: نسبة العائد {payout}% أقل من الحد الأدنى {min_payout}%")
                            print(f"⚠️ تم تخطي {key}: نسبة العائد {payout}% أقل من الحد الأدنى {min_payout}%")
                            return None, None
            logging.warning(f"محاولة {attempt + 1}: الرمز {symbol} غير نشط")
            print(f"⚠️ الرمز {symbol} غير نشط")
        except Exception as e:
            logging.error(f"محاولة {attempt + 1}/{max_attempts}: خطأ أثناء التحقق من العائد لـ {symbol}: {str(e)}")
            print(f"⚠️ خطأ أثناء التحقق من العائد لـ {symbol}: {str(e)}")
        attempt += 1
        await asyncio.sleep(0.5)  # تحسين: تقليل النوم إلى 0.5 ثانية

    logging.error(f"فشل التحقق من العائد لـ {symbol} بعد {max_attempts} محاولات")
    print(f"❌ فشل التحقق من العائد لـ {symbol} بعد {max_attempts} محاولات")
    return None, None

def validate_symbol(symbol: str) -> bool:
    """التحقق من أن الرمز صالح."""
    pattern = r"^[A-Z0-9]+$"
    return bool(re.match(pattern, symbol))

def validate_trade_time(trade_time: str) -> bool:
    """التحقق من أن وقت الصفقة بالتنسيق الصحيح."""
    try:
        datetime.strptime(trade_time, "%H:%M:%S")
        return True
    except ValueError:
        return False

def format_amount(amount: float) -> str:
    """تنسيق المبلغ للعرض."""
    return f"{amount:,.2f}"