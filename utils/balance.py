async def get_balance(driver=None, client=None):
    """جلب الرصيد باستخدام PocketOptionAsync فقط"""
    if not client:
        return "💵 Balance: Client not available"
    try:
        balance = await client.balance()
        if balance < 0:
            raise ValueError(f"Invalid balance: {balance}")
        account_type = "Demo" if client.ssid and '"isDemo":1' in client.ssid else "Real"
        return f"💵 QT {account_type} 🔻\n    {balance:,.2f} $"
    except Exception as e:
        print(f"⚠️ Failed to fetch balance via PocketOptionAsync: {e}")
        return "💵 Balance: Not Available"
