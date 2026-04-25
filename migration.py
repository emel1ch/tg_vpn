import sqlite3
import aiohttp
import asyncio
# Исправлен импорт: используем PANEL_USER, как указано в твоем config.py
from config import PANEL_URL, PANEL_USER, PANEL_PASSWORD

async def get_token():
    url = f"{PANEL_URL.rstrip('/')}/api/admin/token"
    # Заменено PANEL_LOGIN на PANEL_USER
    data = {"username": PANEL_USER, "password": PANEL_PASSWORD}
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

    # Подключаемся к твоей БД бота
    conn = sqlite3.connect('vpn_service.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT tg_id, expiry_ms FROM users")
    users = cursor.fetchall()

    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        for user in users:
            tg_id = user['tg_id']
            # Переводим миллисекунды в секунды для Marzban
            expiry_s = int(user['expiry_ms'] / 1000) if user['expiry_ms'] > 0 else 0

            # Исправленный payload: добавили точную привязку к VLESS_TCP_TLS
            payload = {
                "username": str(tg_id),
                "proxies": {"vless": {}},
                "inbounds": {"vless": ["VLESS_TCP_TLS"]},
                "expire": expiry_s,
                "data_limit": 0
            }

            url = f"{PANEL_URL.rstrip('/')}/api/user"
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Сохраняем новую ссылку-подписку в базу бота
                    new_sub_url = data.get('subscription_url', '')
                    cursor.execute("UPDATE users SET sub_id = ?, uuid = ? WHERE tg_id = ?",
                                   (new_sub_url, str(tg_id), tg_id))
                    print(f"✅ Перенесен: {tg_id}")
                elif resp.status == 409:
                    print(f"⚠️ Пропущен: Юзер {tg_id} уже существует в панели Marzban.")
                else:
                    error_text = await resp.text()
                    print(f"❌ Ошибка {tg_id} (Код {resp.status}): {error_text}")

    conn.commit()
    conn.close()
    print("🚀 Миграция базы данных успешно завершена!")

if __name__ == "__main__":
    # Запуск в Windows/Linux
    asyncio.run(start_migration())