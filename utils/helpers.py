from getpass import getpass

def get_pocketoption_credentials():
    print("\n🔹 PocketOption connection:")
    email = input("📧 Enter email: ").strip()
    password = getpass("🔑 Enter password: ")
    return {"email": email, "password": password}
