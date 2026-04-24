import asyncio
import time
import aiosqlite
from api_client import PanelAPI
from config import DB_NAME


async def sync_users():
    panel = PanelAPI()
    now_ms = int(time.time() * 1000)

    print("⏳ Подключаемся к базе данных и панели...")

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row

        try:
            async with db.execute("SELECT * FROM users") as cursor:
                users = await cursor.fetchall()
        except Exception as e:
            print(f"❌ Ошибка чтения БД: {e}")
            return

        print(f"🔍 Найдено пользователей в базе: {len(users)}")

        for row in users:
            # Превращаем строку БД в обычный словарь Питон
            row_dict = dict(row)

            # Пытаемся вытащить ID по всем возможным названиям
            uid = row_dict.get('tg_id') or row_dict.get('user_id') or row_dict.get('id') or row_dict.get('telegram_id')
            expiry = row_dict.get('expiry_ms', 0)

            if not uid:
                print(f"❌ Не смог найти колонку с Telegram ID! Доступные колонки: {list(row_dict.keys())}")
                continue

            if expiry > now_ms:
                res = await panel.add_user(1, "user", str(uid), expiry)

                if res and res.get("success"):
                    print(f"✅ Юзер {uid} успешно восстановлен в Marzban!")
                else:
                    print(f"⚠️ Юзер {uid}: ошибка создания или уже существует.")
            else:
                print(f"💤 Юзер {uid} пропущен (подписка истекла).")


if __name__ == "__main__":
    asyncio.run(sync_users())