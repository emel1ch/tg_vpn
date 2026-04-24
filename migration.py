import sqlite3
import aiohttp
import asyncio
from config import PANEL_URL, PANEL_LOGIN, PANEL_PASSWORD


async def get_token():
    url = f"{PANEL_URL.rstrip('/')}/api/admin/token"
    data = {"username": PANEL_LOGIN, "password": PANEL_PASSWORD}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as resp:
            if resp.status == 200:
                res = await resp.json()
                return res['access_token']
            return None


async def start_migration():
    token = await get_token()
    if not token:
        print("❌ Ошибка авторизации в Marzban. Проверь логин/пароль в .env")
        return

    # Подключаемся к твоей БД
    conn = sqlite3.connect('vpn_service.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT tg_id, expiry_ms FROM users")
    users = cursor.fetchall()

    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        for user in users:
            tg_id = user['tg_id']
            # Переводим твои мс в секунды для Marzban
            expiry_s = int(user['expiry_ms'] / 1000) if user['expiry_ms'] > 0 else 0

            payload = {
                "username": str(tg_id),
                "proxies": {"vless": {}},
                "expire": expiry_s,
                "data_limit": 0
            }

            url = f"{PANEL_URL.rstrip('/')}/api/user"
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Сохраняем новую ссылку в базу бота
                    new_sub_url = data['subscription_url']
                    cursor.execute("UPDATE users SET sub_id = ?, uuid = ? WHERE tg_id = ?",
                                   (new_sub_url, str(tg_id), tg_id))
                    print(f"✅ Перенесен: {tg_id}")
                else:
                    print(f"⚠️ Ошибка {tg_id}: {resp.status}")

    conn.commit()
    conn.close()
    print("🚀 Миграция завершена!")


if __name__ == "__main__":
    asyncio.run(start_migration())