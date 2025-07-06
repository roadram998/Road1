import os
import json
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneNumberInvalidError, FloodWaitError
import re
import logging

# إعدادات التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('errors.log', mode='a', encoding='utf-8')
    ]
)

def load_telegram_config():
    """تحميل بيانات Telegram من ملف التكوين إذا كان موجودًا"""
    config_file = "telegram_config.json"
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def save_telegram_config(api_id, api_hash, channel_name):
    """حفظ بيانات Telegram في ملف التكوين"""
    config_file = "telegram_config.json"
    config = {
        "api_id": api_id,
        "api_hash": api_hash,
        "channel_name": channel_name
    }
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

async def setup_telegram():
    session_file = "session_name"
    config = load_telegram_config()

    if os.path.exists(f"{session_file}.session") and config:
        api_id = config["api_id"]
        api_hash = config["api_hash"]
        channel_name = config.get("channel_name")
        client = TelegramClient(session_file, api_id, api_hash)
        await client.connect()
        if await client.is_user_authorized():
            if channel_name:
                print(f"✅ Using saved channel/group: {channel_name}")
                return client, channel_name
            else:
                print("⚠️ No channel/group specified in config, please enter one.")
        else:
            await client.disconnect()

    print("📱 Telegram connection:")
    while True:
        try:
            api_id = input("🔑 Enter API_ID: ").strip()
            api_hash = input("🔑 Enter API_HASH: ").strip()
            phone = input("📞 Enter phone number (with country code, e.g., +963912345678): ").strip()
            channel_name = input("📢 Enter channel/group username (e.g., @ChannelName): ").strip()

            if not all([api_id, api_hash, phone, channel_name]):
                print("❌ Input cannot be empty. Please try again.")
                continue
            if not api_id.isdigit():
                print("❌ API_ID must be a number. Please try again.")
                continue
            if not phone.startswith("+"):
                print("❌ Phone number must include country code (e.g., +963912345678). Please try again.")
                continue
            if not channel_name.startswith("@"):
                print("❌ Channel/group username must start with @ (e.g., @ChannelName). Please try again.")
                continue

            break
        except KeyboardInterrupt:
            print("❌ Process interrupted by user. Exiting...")
            exit()

    save_telegram_config(api_id, api_hash, channel_name)
    client = TelegramClient(session_file, api_id, api_hash)

    while True:
        try:
            await client.start(phone=phone)
            print("✅ Telegram client initialized.")
            break
        except PhoneNumberInvalidError:
            print("❌ Invalid phone number. Please try again.")
            phone = input("📞 Enter phone number (with country code, e.g., +963912345678): ").strip()
        except SessionPasswordNeededError:
            password = input("🔒 Enter your Telegram password: ").strip()
            await client.sign_in(password=password)
            print("✅ Telegram client initialized.")
            break
        except FloodWaitError as e:
            print(f"⚠️ Too many attempts. Please wait {e.seconds} seconds before trying again.")
            exit()
        except Exception as e:
            print(f"❌ Error during Telegram setup: {e}")
            print("Please try again.")
            phone = input("📞 Enter phone number (with country code, e.g., +963912345678): ").strip()

    return client, channel_name

async def listen_to_signals(client, signal_handler, channel_name):
    channels = [ch.strip() for ch in channel_name.split(",")]
    @client.on(events.NewMessage(chats=channels))
    async def handler(event):
        message_text = event.message.text
        pattern = r"💷 (\S+)\s+💎 (M\d+)\s+⌚️ (\d{2}:\d{2}:\d{2})\s+(🔼 call|🔽 put)"
        match = re.search(pattern, message_text, re.MULTILINE)
        if match:
            symbol, duration, time, direction = match.groups()
            direction = "call" if "call" in direction.lower() else "put"
            message = {
                "symbol": symbol,
                "duration": duration,
                "time": time,
                "direction": direction
            }
            await signal_handler(message)

    await client.run_until_disconnected()