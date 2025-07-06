import os
import asyncio
import time
import threading
import sys
import platform
from datetime import datetime
import ntplib
import pytz
from utils.auth import login_to_account, choose_account
from utils.config_manager import load_account_data, save_account_data, load_martingale_settings, save_martingale_settings, get_martingale_settings
from utils.telegram_bot import setup_telegram, listen_to_signals
from utils.helpers import get_pocketoption_credentials
from utils.martingale_strategy import MartingaleStrategy
from utils.trade_modules.message_handling import handle_signal
from utils.logger import Logger
from BinaryOptionsToolsV2.pocketoption.asyncronous import PocketOptionAsync
from utils.trade_modules.trade_utils import display_account_stats

# إنشاء مجلد logs إذا لم يكن موجودًا
log_dir = "logs"
if not os.path.exists(log_dir):
    try:
        os.makedirs(log_dir)
    except Exception as e:
        print(f"⚠️ Failed to create logs directory: {str(e)}")
        sys.exit(1)

# إعداد logger
logger = Logger()

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

start_time = datetime.now()

def sync_system_time():
    try:
        client = ntplib.NTPClient()
        response = client.request('pool.ntp.org')
        ntp_time = datetime.fromtimestamp(response.tx_time, pytz.timezone('America/Sao_Paulo'))
        current_time = datetime.now(pytz.timezone('America/Sao_Paulo'))
        time_diff = abs((ntp_time - current_time).total_seconds())
        if time_diff > 1:
            logger.warning(f"System time is off by {time_diff:.2f} seconds. Consider syncing.")
            print(f"⚠️ System time is off by {time_diff:.2f} seconds. Please sync your system clock.")
    except Exception as e:
        logger.error(f"Failed to sync time with NTP: {str(e)}")
        print(f"⚠️ Failed to sync time: {str(e)}")

def print_timer(stop_event, start_time_timer):
    while not stop_event.is_set():
        elapsed_time = time.time() - start_time_timer
        sys.stdout.write(f"\r⏳ Timer: {elapsed_time:.2f} seconds")
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write("\r" + " " * 50 + "\r")
    sys.stdout.flush()

async def get_valid_balance(client, strategy, max_retries=3, retry_delay=1.5):
    for attempt in range(max_retries):
        try:
            balance = await client.balance()
            if balance is not None and balance >= 0:
                if strategy:
                    strategy.update_balance(balance)
                logger.info(f"Balance retrieved successfully: {balance:.2f}")
                return balance
            logger.warning(f"Invalid balance (attempt {attempt + 1}/{max_retries}): {balance}")
        except Exception as e:
            logger.error(f"Error fetching balance (attempt {attempt + 1}/{max_retries}): {str(e)}")
        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay)
    logger.error(f"Failed to fetch balance after {max_retries} attempts")
    return -1.0

async def keep_alive(client: PocketOptionAsync):
    while True:
        try:
            await client.payout()
            logger.info("Keep_alive request sent successfully")
        except Exception as e:
            logger.error(f"Keep_alive failed: {str(e)}")
        await asyncio.sleep(15)  # تحسين: تغيير الفاصل الزمني إلى 15 ثانية بدلاً من 10

async def main():
    sync_system_time()
    saved_martingale = load_martingale_settings()
    choice = choose_account()
    if choice == "1":
        account_type = "Demo"
        demo = True
    elif choice == "2":
        account_type = "Real"
        demo = False
    elif choice == "3":
        print("👋 Exiting RoadBot...")
        logger.log_session(start_time, datetime.now(), account_type, 0.0, 0.0, 0.0, 0, 0, 0, 0, "Manual Exit")
        return
    else:
        print("❌ Invalid choice, exiting...")
        logger.log_session(start_time, datetime.now(), account_type, 0.0, 0.0, 0.0, 0, 0, 0, 0, "Invalid Choice")
        return

    saved_account_data = load_account_data(account_type)
    if saved_account_data:
        print(f"\nℹ️ Previous account type: {saved_account_data['account_type']}")
    else:
        print(f"\nℹ️ No previous {account_type} account data found, will create new...")

    if saved_martingale:
        print("\n⚙️ Loaded Martingale settings:\n")
        print(f"💵 Amount: {saved_martingale['amount']}\n")
        print(f"✖️ Multiplier: {saved_martingale['multiplier']}\n")
        print(f"🎯 Profit: {saved_martingale['profit']}\n")
        print(f"🛑 Loss: {saved_martingale['loss']}\n")
        print(f"🔢 MAX_LOSS_COUNT: {saved_martingale['max_loss_count']}\n")
        print(f"📉 Payout: {saved_martingale['payout']}\n")
    else:
        martingale_settings = get_martingale_settings()
        save_martingale_settings(martingale_settings)
        saved_martingale = martingale_settings

    telegram_client, channel_name = await setup_telegram()

    ssid = None
    client = None
    driver = None
    retry_attempts = 0
    max_attempts = 3
    martingale_strategy = None
    stop_event = None
    timer_thread = None

    while retry_attempts < max_attempts:
        try:
            if saved_account_data and saved_account_data.get("ssid"):
                ssid = saved_account_data["ssid"]
                client = PocketOptionAsync(ssid=ssid)
                stop_event = threading.Event()
                start_time_timer = time.time()
                timer_thread = threading.Thread(target=print_timer, args=(stop_event, start_time_timer))
                timer_thread.start()
                balance = await get_valid_balance(client, None)
                if balance < 0:
                    raise Exception("Invalid balance retrieved")
                martingale_strategy = MartingaleStrategy(saved_martingale, balance)
                logger.info(f"Successfully connected with cached SSID for {account_type}")
                print(f"✅ Successfully connected with cached SSID for {account_type}")
                print("🔥 Let's win 🔥")
                break
            else:
                credentials = saved_account_data.get("credentials") if saved_account_data else get_pocketoption_credentials()
                driver, ssid = await login_to_account(credentials["email"], credentials["password"], demo=demo)
                if ssid:
                    save_account_data(account_type, credentials, ssid)
                    client = PocketOptionAsync(ssid=ssid)
                    stop_event = threading.Event()
                    start_time_timer = time.time()
                    timer_thread = threading.Thread(target=print_timer, args=(stop_event, start_time_timer))
                    timer_thread.start()
                    balance = await get_valid_balance(client, None)
                    if balance < 0:
                        raise Exception("Invalid balance retrieved")
                    martingale_strategy = MartingaleStrategy(saved_martingale, balance)
                    logger.info(f"Successfully connected with new SSID for {account_type}")
                    print(f"✅ Successfully connected with new SSID for {account_type}")
                    print("🔥 Let's win 🔥")
                    break
                else:
                    raise Exception("Failed to extract SSID")

        except Exception as e:
            if stop_event and timer_thread:
                stop_event.set()
                timer_thread.join()
            if client:
                await client.disconnect()
                client = None
            if driver:
                driver.quit()
                driver = None
            retry_attempts += 1
            delay = min(2 * retry_attempts, 10)
            logger.error(f"Connection failed: {str(e)}. Retrying ({retry_attempts}/{max_attempts}) in {delay} seconds...")
            print(f"⚠️ Connection failed: {str(e)}, retrying ({retry_attempts}/{max_attempts}) in {delay} seconds...")
            await asyncio.sleep(delay)

    if stop_event and timer_thread:
        stop_event.set()
        timer_thread.join()

    if retry_attempts >= max_attempts:
        print("❌ Max retry attempts reached, exiting...")
        logger.log_session(start_time, datetime.now(), account_type, 0.0, 0.0, 0.0, 0, 0, 0, 0, "Max Retry Attempts Reached")
        if driver:
            driver.quit()
        return

    if not client or not martingale_strategy:
        print("❌ No connection to PocketOptionAsync, cannot proceed")
        logger.log_session(start_time, datetime.now(), account_type, 0.0, 0.0, 0.0, 0, 0, 0, 0, "No Connection")
        if driver:
            driver.quit()
        return

    try:
        balance = await get_valid_balance(client, martingale_strategy)
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"🤖 Account Type: {account_type}")

        await display_account_stats(martingale_strategy)

        logger.info("CONNECTED SUCCESSFUL")
        asyncio.create_task(keep_alive(client))
    except Exception as e:
        logger.error(f"Failed to fetch balance for {account_type}: {str(e)}")
        print(f"⚠️ Failed to fetch balance: {str(e)}")
        logger.log_session(start_time, datetime.now(), account_type, 0.0, 0.0, 0.0, 0, 0, 0, 0, "Failed Balance Fetch")
        if driver:
            driver.quit()
        return

    martingale_strategy.is_active = True

    async def signal_handler(message):
        if not martingale_strategy.is_active:
            logger.info("⚠️ Bot stopped, ignoring new signal")
            return
        print("🔥 Waiting for a new trade 🔥")
        await handle_signal(client, message, martingale_strategy, logger, ssid, demo)
        net_profit = martingale_strategy.current_balance - martingale_strategy.initial_balance
        net_loss = martingale_strategy.initial_balance - martingale_strategy.current_balance if martingale_strategy.current_balance < martingale_strategy.initial_balance else 0
        if (net_profit >= martingale_strategy.settings["profit"] or
            net_loss >= martingale_strategy.settings["loss"]):
            martingale_strategy.is_active = False
            limit_type = ('Profit' if net_profit >= martingale_strategy.settings["profit"]
                        else 'Loss')
            logger.info(f"🛑 Bot stopped due to reaching {limit_type} limit")
            print(f"🛑 Bot stopped due to reaching {limit_type} limit")
            final_balance = martingale_strategy.current_balance
            logger.log_session(
                start_time,
                datetime.now(),
                account_type,
                net_profit,
                net_loss,
                final_balance,
                martingale_strategy.total_trades,
                martingale_strategy.wins,
                martingale_strategy.losses,
                martingale_strategy.ties,
                f"Reached {limit_type} Limit"
            )
            await telegram_client.disconnect()

    await listen_to_signals(telegram_client, signal_handler, channel_name)

    final_balance = martingale_strategy.current_balance
    net_profit = final_balance - martingale_strategy.initial_balance
    net_loss = martingale_strategy.initial_balance - final_balance if final_balance < martingale_strategy.initial_balance else 0
    stop_reason = "Manual Exit" if martingale_strategy.is_active else "Reached Limit or Error"
    logger.log_session(
        start_time,
        datetime.now(),
        account_type,
        net_profit,
        net_loss,
        final_balance,
        martingale_strategy.total_trades,
        martingale_strategy.wins,
        martingale_strategy.losses,
        martingale_strategy.ties,
        stop_reason
    )
    if driver:
        driver.quit()
    if telegram_client:
        await telegram_client.disconnect()
    print("👋 Session ended and logged.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.log_session(start_time, datetime.now(), "Unknown", 0.0, 0.0, 0.0, 0, 0, 0, 0, "Interrupted by User")
        print("👋 Program interrupted by user, session logged.")
    except Exception as e:
        logger.log_session(start_time, datetime.now(), "Unknown", 0.0, 0.0, 0.0, 0, 0, 0, 0, f"Unexpected Error: {str(e)}")
        print(f"⚠️ Unexpected error: {str(e)}, session logged.")
