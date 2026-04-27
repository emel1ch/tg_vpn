import os
from dotenv import load_dotenv
from datetime import datetime
import json      # <--- ДОБАВИТЬ
import base64    # <--- ДОБАВИТЬ

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
DB_NAME = os.getenv("DB_NAME")

PANEL_URL = os.getenv("PANEL_URL").rstrip('/')
PANEL_USER = os.getenv("PANEL_USER")
PANEL_PASSWORD = os.getenv("PANEL_PWD")
HAPP_ROUTING_LINK =os.getenv("HAPP_ROUTING_LINK").rstrip('/')

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
# --- КРИПТО КОШЕЛЬКИ (из .env) ---
CRYPTO_WALLETS = {
    "TON": os.getenv("WALLET_TON", "Кошелек не настроен"),
    "ETH": os.getenv("WALLET_ETH", "Кошелек не настроен"),
    "BTC": os.getenv("WALLET_BTC", "Кошелек не настроен"),
    "USDT_TRC20": os.getenv("WALLET_USDT_TRC20", "Кошелек не настроен"),
    "USDT_ERC20": os.getenv("WALLET_USDT_ERC20", "Кошелек не настроен"),
    "USDT_TON": os.getenv("WALLET_USDT_TON", "Кошелек не настроен"),
    "USDT_SOL": os.getenv("WALLET_USDT_SOL", "Кошелек не настроен"),
}

# --- ПУТИ К КАРТИНКАМ QR КОДОВ ---
# Назовите ваши картинки именно так и положите в папку с ботом
CRYPTO_QRS = {
    "TON": "qr_ton.jpg",
    "ETH": "qr_eth.jpg",
    "BTC": "qr_btc.jpg",
    "USDT_TRC20": "qr_usdt_trc20.jpg",
    "USDT_ERC20": "qr_usdt_erc20.jpg",
    "USDT_TON": "qr_usdt_ton.jpg",
    "USDT_SOL": "qr_usdt_sol.jpg",
}
