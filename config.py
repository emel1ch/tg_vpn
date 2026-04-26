import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
DB_NAME = os.getenv("DB_NAME")

PANEL_URL = os.getenv("PANEL_URL").rstrip('/')
PANEL_USER = os.getenv("PANEL_USER")
PANEL_PASSWORD = os.getenv("PANEL_PWD")

# --- НАСТРОЙКИ CORE CONTROL (ADMIN) ---
REMOTE_GDRIVE = os.getenv("REMOTE_GDRIVE") # Оставляем Google Drive
MARZBAN_DB_PATH = os.getenv("MARZBAN_DB_PATH", "/opt/marzban/data/db.sqlite3")
# Путь к локальной базе бота (как в migration.py)
BOT_DB_PATH = os.getenv("BOT_DB_PATH", "vpn_service.db")

# Настройки времени и цен
INBOUND_ID = 1
TRIAL_DAYS = 3
MONTH_MS = 30 * 24 * 60 * 60 * 1000
PAYMENT_PRICE = 200
QR_FILE_PATH = "qr.jpg"
PAYMENT_LINK =os.getenv("PAYMENT_LINK").rstrip('/')