import os
import json

def format_value(value):
    """
    دالة لتنسيق القيم بحيث تُحفظ كسلسلة نصية مع الاحتفاظ بالدقة العشرية.
    """
    try:
        return str(float(value))  # الاحتفاظ بالقيمة كـ float دائمًا
    except ValueError:
        return value

def get_martingale_settings():
    print("\n⚙️ Martingale settings:")
    settings = {
        "amount": format_value(input("💵 Amount: ")),
        "multiplier": format_value(input("✖️ Multiplier: ")),
        "profit": format_value(input("🎯 Profit: ")),
        "loss": format_value(input("🛑 Loss: ")),
        "max_loss_count": format_value(input("🔢 MAX_LOSS_COUNT: ")),
        "payout": format_value(input("📉 Payout: "))
    }
    return settings

def save_martingale_settings(settings, filename="martingale_settings.txt"):
    with open(filename, "w") as f:
        for key, value in settings.items():
            f.write(f"{key}: {value}\n")

def load_martingale_settings(filename="martingale_settings.txt"):
    if os.path.exists(filename):
        settings = {}
        with open(filename, "r") as f:
            for line in f:
                key, value = line.strip().split(": ")
                try:
                    settings[key] = float(value) if key != "max_loss_count" else int(value)
                except ValueError:
                    settings[key] = value
        return settings
    return None

def save_account_data(account_type, credentials, ssid=None, filename_prefix="account_data"):
    filename = f"{filename_prefix}_{account_type.lower()}.json"
    data = {
        "account_type": account_type,
        "credentials": credentials,
        "ssid": ssid
    }
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

def load_account_data(account_type=None, filename_prefix="account_data"):
    if account_type:
        filename = f"{filename_prefix}_{account_type.lower()}.json"
        if os.path.exists(filename):
            with open(filename, "r") as f:
                return json.load(f)
    return None
