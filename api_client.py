import aiohttp
import logging
from config import PANEL_URL, PANEL_USER, PANEL_PASSWORD


class PanelAPI:
    def __init__(self):
        self.base_url = PANEL_URL.rstrip('/')
        self.username = PANEL_USER
        self.password = PANEL_PASSWORD
        self.token = None

    async def _get_token(self):
        url = f"{self.base_url}/api/admin/token"
        data = {"username": self.username, "password": self.password}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as resp:
                    if resp.status == 200:
                        res = await resp.json()
                        self.token = res['access_token']
                        return True
                    logging.error(f"Ошибка авторизации в Marzban: {resp.status}")
                    return False
        except Exception as e:
            logging.error(f"Ошибка связи с панелью: {e}")
            return False

    async def add_user(self, inbound_id, user_email, user_uuid, expiry_ms):
        """Создает юзера в Marzban. user_uuid = Telegram ID"""
        if not self.token: await self._get_token()

        url = f"{self.base_url}/api/user"
        headers = {"Authorization": f"Bearer {self.token}"}
        expiry_s = int(expiry_ms / 1000) if expiry_ms > 0 else 0

        payload = {
            "username": str(user_uuid),
            "expire": expiry_s,
            "data_limit": 0
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Возвращаем ссылку
                    return {"success": True, "subscription_url": data.get('subscription_url', '')}
                elif resp.status == 409:  # Если уже есть
                    return {"success": True}
                return {"success": False}

    async def get_user(self, user_uuid):
        """Получает инфу о юзере напрямую из Marzban"""
        if not self.token: await self._get_token()
        url = f"{self.base_url}/api/user/{user_uuid}"
        headers = {"Authorization": f"Bearer {self.token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None

    async def extend_user(self, inbound_id, user_uuid, user_email, sub_id, new_expiry_ms):
        if not self.token: await self._get_token()
        url = f"{self.base_url}/api/user/{user_uuid}"
        headers = {"Authorization": f"Bearer {self.token}"}
        async with aiohttp.ClientSession() as session:
            async with session.put(url, json={"expire": int(new_expiry_ms / 1000)}, headers=headers) as resp:
                return {"success": resp.status == 200}

    async def close(self):
        pass