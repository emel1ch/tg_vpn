import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
DB_NAME = os.getenv("DB_NAME")

PANEL_URL = os.getenv("PANEL_URL")
PANEL_LOGIN = os.getenv("PANEL_USER")
PANEL_PASSWORD = os.getenv("PANEL_PWD")
INBOUND_ID = 1  # ID твоего входящего подключения (посмотри в панели в списке подключений)