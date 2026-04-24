import asyncio
import aiohttp
from config import PANEL_URL, PANEL_USER, PANEL_PASSWORD


async def get_token():
    url = f"{PANEL_URL.rstrip('/')}/api/admin/token"
    data = {"username": PANEL_USER, "password": PANEL_PASSWORD}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as resp:
            if resp.status == 200:
                res = await resp.json()
                return res['access_token']
            return None


async def fix_users():
    token = await get_token()
    if not token:
        print("❌ Ошибка авторизации")
        return

    headers = {"Authorization": f"Bearer {token}"}
    base_url = PANEL_URL.rstrip('/')

    async with aiohttp.ClientSession() as session:
        # 1. Получаем список всех пользователей
        async with session.get(f"{base_url}/api/users", headers=headers) as resp:
            users = await resp.json()
            # В некоторых версиях API список лежит в users['users']
            user_list = users.get('users', users)

        print(f"🔍 Найдено пользователей в панели: {len(user_list)}")

        for user in user_list:
            username = user['username']
            # 2. Обновляем каждого пользователя, принудительно включая vless
            # Пустой словарь внутри vless заставит Marzban использовать дефолты ноды
            update_payload = {
                "proxies": {"vless": {}}
            }

            async with session.put(f"{base_url}/api/user/{username}", json=update_payload,
                                   headers=headers) as update_resp:
                if update_resp.status == 200:
                    print(f"✅ Прокси активированы для: {username}")
                else:
                    print(f"❌ Ошибка при обновлении {username}: {update_resp.status}")


if __name__ == "__main__":
    asyncio.run(fix_users())