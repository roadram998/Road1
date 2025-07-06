import json
import logging
import time
import os
from seleniumwire.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from contextlib import contextmanager
from getpass import getpass
from utils.trade_modules.trade_globals import initialize_driver
from BinaryOptionsToolsV2.pocketoption.asyncronous import PocketOptionAsync
import asyncio
import msvcrt

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('errors.log', mode='a', encoding='utf-8')]
)

async def check_ssid_validity(ssid: str, demo: bool = False) -> bool:
    try:
        client = PocketOptionAsync(ssid=ssid, demo=demo)
        balance = await client.balance()
        if balance is not None and balance >= 0:
            logging.info(f"SSID {ssid} is valid")
            return True
        logging.warning(f"SSID {ssid} is invalid or balance retrieval failed")
        return False
    except Exception as e:
        logging.error(f"Failed to validate SSID {ssid}: {str(e)}")
        return False

def input_with_timeout(prompt, timeout):
    try:
        print(prompt, end='', flush=True)
        start_time = time.time()
        result = ""
        while time.time() - start_time < timeout:
            if msvcrt.kbhit():
                char = msvcrt.getch().decode('utf-8', errors='ignore')
                if char == '\r':
                    print()
                    return result
                result += char
                print(char, end='', flush=True)
            time.sleep(0.01)
        raise TimeoutException("Input timed out")
    except TimeoutException:
        print("\nInput timed out")
        raise
    except Exception as e:
        logging.error(f"Input error: {str(e)}")
        raise

@contextmanager
def get_driver():
    driver = initialize_driver()
    try:
        yield driver
    finally:
        driver.quit()
        logging.info("Browser closed successfully")
        print("Browser closed")

async def handle_captcha(driver):
    try:
        captcha = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[title*='CAPTCHA'], div[id*='captcha'], div[class*='recaptcha']"))
        )
        if captcha.is_displayed():
            print("⏳ CAPTCHA detected! Please solve it manually within 30 seconds...")
            try:
                await asyncio.to_thread(input_with_timeout, "", 30)
                WebDriverWait(driver, 30).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[title*='CAPTCHA'], div[id*='captcha'], div[class*='recaptcha']")),
                    message="CAPTCHA was not solved in time."
                )
                logging.info("CAPTCHA solved successfully")
                print("✅ CAPTCHA solved")
                return True
            except TimeoutException:
                logging.error("CAPTCHA solving timed out")
                print("❌ CAPTCHA solving timed out")
                return False
        return True
    except:
        logging.info("No CAPTCHA detected")
        print("⚠️ No CAPTCHA detected, proceeding...")
        return True

async def login(driver, email, password):
    try:
        driver.get("https://pocketoption.com/en/login")
        email_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "email"))
        )
        password_field = driver.find_element(By.NAME, "password")
        email_field.send_keys(email)
        password_field.send_keys(password)
        password_field.submit()
        logging.info("Login credentials submitted successfully")
        print("✅ Login credentials submitted")
        WebDriverWait(driver, 15).until(
            EC.url_contains("/cabinet"),
            message="Login failed: Still on login page"
        )
        logging.info("Login successful")
        print("✅ Login successful")
        return True
    except (TimeoutException, WebDriverException) as e:
        logging.error(f"Login failed: {str(e)}")
        print(f"❌ Login failed: {str(e)}")
        return False

async def extract_ssid(driver, is_demo, max_attempts=3, delay=1):
    account_type = "Real" if not is_demo else "Demo"
    url = f"https://pocketoption.com/en/cabinet/{'/demo-quick-high-low' if is_demo else ''}"
    print(f"Extracting SSID for {account_type} account...")
    
    for load_attempt in range(2):
        try:
            driver.get(url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            logging.info(f"{account_type} page loaded successfully")
            break
        except:
            logging.warning(f"Attempt {load_attempt + 1}/2: Failed to load {account_type} page, retrying...")
            print(f"⚠️ Attempt {load_attempt + 1}/2: Failed to load {account_type} page, retrying...")
            if load_attempt == 1:
                logging.error(f"Failed to load {account_type} page after retries")
                print(f"❌ Failed to load {account_type} page after retries")
                return None

    for attempt in range(max_attempts):
        try:
            driver.execute_script("window.location.reload();")
            await asyncio.sleep(1)
            for request in driver.requests:
                if request.ws_messages and "wss://" in request.url:
                    for message in request.ws_messages:
                        message_text = message.content
                        if isinstance(message_text, bytes):
                            message_text = message_text.decode('utf-8', errors='ignore')
                        if '42["auth"' in message_text or 'a:4:{' in message_text:
                            try:
                                if '42["auth"' in message_text:
                                    parsed_data = json.loads(message_text[2:])
                                    if parsed_data[0] == "auth" and parsed_data[1].get('isDemo') == (1 if is_demo else 0):
                                        ssid = message_text
                                        logging.info(f"SSID extracted for {account_type}: {ssid}")
                                        print(f"✅ SSID successfully extracted for {account_type}: {ssid}")
                                        return ssid
                                elif 'a:4:{' in message_text:
                                    if is_demo:
                                        continue  # Ignore a:4:{ format for demo account
                                    ssid = message_text
                                    logging.info(f"SSID extracted for {account_type}: {ssid}")
                                    print(f"✅ SSID successfully extracted for {account_type}: {ssid}")
                                    return ssid
                            except json.JSONDecodeError as e:
                                logging.error(f"Failed to parse WebSocket message: {str(e)}")
                                continue
                            except KeyError as e:
                                logging.error(f"Key error in WebSocket data: {str(e)}")
                                continue
            logging.warning(f"Attempt {attempt + 1}/{max_attempts}: Could not find valid {account_type} SSID")
            print(f"⚠️ Attempt {attempt + 1}/{max_attempts}: Failed to extract {account_type} SSID")
            await asyncio.sleep(delay)
        except Exception as e:
            logging.error(f"Failed to extract {account_type} SSID: {str(e)}")
            print(f"⚠️ Error extracting {account_type} SSID: {str(e)}")
            return None
    return None

async def login_to_account(email, password, demo=False):
    from utils.config_manager import load_account_data, save_account_data
    account_type = "Demo" if demo else "Real"
    saved_account_data = load_account_data(account_type)
    
    if saved_account_data and saved_account_data.get("ssid"):
        ssid = saved_account_data["ssid"]
        if await check_ssid_validity(ssid, demo):
            logging.info(f"Using cached SSID for {account_type}")
            print(f"✅ Using cached SSID for {account_type}")
            return None, ssid

    with get_driver() as driver:
        if not await login(driver, email, password):
            return None, None
        if not await handle_captcha(driver):
            return None, None
        
        # Extract SSID for both real and demo accounts
        ssid_real = await extract_ssid(driver, is_demo=False)
        ssid_demo = await extract_ssid(driver, is_demo=True)
        
        # Save both SSIDs
        if ssid_real:
            save_account_data("Real", {"email": email, "password": password}, ssid_real)
        if ssid_demo:
            save_account_data("Demo", {"email": email, "password": password}, ssid_demo)
        
        # Return the SSID for the requested account type
        ssid = ssid_demo if demo else ssid_real
        if not ssid:
            print(f"❌ Failed to extract SSID for {account_type}")
            return None, None
        return driver, ssid

def choose_account():
    print("\n🔢 Choose Account:")
    print("1️⃣  Demo")
    print("2️⃣  Real")
    print("3️⃣  Exit")
    choice = input("💥 Press to Start💥: ").strip()
    return choice