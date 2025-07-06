from seleniumwire.webdriver import Chrome
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager
from BinaryOptionsToolsV2.pocketoption.asyncronous import PocketOptionAsync
import asyncio
import json
import os
import logging

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('errors.log', mode='a', encoding='utf-8')
    ]
)

# جلب SSID من ملفات الحساب
def get_ssid(account_type="Demo"):
    file_path = f"account_data_{account_type.lower()}.json"
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            data = json.load(f)
            return data.get("ssid")
    return None

# جلب الأصول المدعومة
async def fetch_supported_symbols(ssid):
    try:
        api = PocketOptionAsync(ssid)
        await asyncio.sleep(5)
        payout_data = await api.payout()
        symbols = list(payout_data.keys())
        logging.info(f"ℹ️ الأصول المدعومة المجلوبة: {symbols}")
        return symbols
    except Exception as e:
        logging.error(f"⚠️ فشل جلب الأصول المدعومة: {str(e)}")
        return [
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
            "AUDUSD-OTC", "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "NZDUSD-OTC",
            "AUDCAD-OTC", "GBPJPY-OTC", "CADCHF-OTC", "AUDJPY-OTC", "USDMYR-OTC",
            "USDCHF-OTC", "USDCNH-OTC", "TNDUSD-OTC", "BHDCNY-OTC", "EURHUF-OTC",
            "AUDCHF-OTC", "EURRUB-OTC", "USDPKR-OTC", "USDARS-OTC", "USDBRL-OTC",
            "USDPHP-OTC", "USDCLP-OTC", "USDCOP-OTC", "USDEGP-OTC", "USDIDR-OTC",
            "USDSGD-OTC", "USDTHB-OTC", "YERUSD-OTC", "ZARUSD-OTC", "AEDCNY-OTC",
            "AUDNZD-OTC", "CADJPY-OTC", "EURGBP-OTC", "EURJPY-OTC", "EURNZD-OTC",
            "EURTRY-OTC", "GBPAUD-OTC", "NGNUSD-OTC", "NZDJPY-OTC"
        ]

# تحديث SUPPORTED_SYMBOLS
async def initialize_supported_symbols():
    ssid = get_ssid("Demo") or get_ssid("Real")
    if ssid:
        symbols = await fetch_supported_symbols(ssid)
        logging.info(f"الأصول المدعومة بعد الجلب: {symbols}")
        return symbols
    logging.warning("⚠️ لم يتم العثور على SSID، استخدام قائمة افتراضية")
    return [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
        "AUDUSD-OTC", "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "NZDUSD-OTC",
        "AUDCAD-OTC", "GBPJPY-OTC", "CADCHF-OTC", "AUDJPY-OTC", "USDMYR-OTC",
        "USDCHF-OTC", "USDCNH-OTC", "TNDUSD-OTC", "BHDCNY-OTC", "EURHUF-OTC",
        "AUDCHF-OTC", "EURRUB-OTC", "USDPKR-OTC", "USDARS-OTC", "USDBRL-OTC",
        "USDPHP-OTC", "USDCLP-OTC", "USDCOP-OTC", "USDEGP-OTC", "USDIDR-OTC",
        "USDSGD-OTC", "USDTHB-OTC", "YERUSD-OTC", "ZARUSD-OTC", "AEDCNY-OTC",
        "AUDNZD-OTC", "CADJPY-OTC", "EURGBP-OTC", "EURJPY-OTC", "EURNZD-OTC",
        "EURTRY-OTC", "GBPAUD-OTC", "NGNUSD-OTC", "NZDJPY-OTC"
    ]

SUPPORTED_SYMBOLS = asyncio.run(initialize_supported_symbols())
logging.info(f"{SUPPORTED_SYMBOLS}")

MAX_TIME_DIFF = 600
DEFAULT_DURATION = 60
MINIMUM_PAYOUT = 70

driver = None

def initialize_driver():
    global driver
    if driver is None:
        chrome_options = ChromeOptions()
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--ignore-ssl-errors")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("disable-infobars")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-webgl")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--ignore-certificate-errors")
        service = Service(ChromeDriverManager().install())
        driver = Chrome(service=service, options=chrome_options)
    return driver

def quit_driver():
    global driver
    if driver is not None:
        driver.quit()
        driver = None