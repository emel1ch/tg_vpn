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
        expiry_s = int(expiry_ms / 1000) if expiry_ms > 0 else 0

        payload = {
            "username": str(user_uuid),
            "proxies": {"vless": {}},
            "inbounds": {"vless": ["VLESS_TCP_TLS"]},  # Имя должно точно совпадать с панелью
            "expire": expiry_s,
            "data_limit": 0
        }

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.token}"}
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"success": True, "subscription_url": data.get('subscription_url', '')}
                elif resp.status == 409:  # Если уже есть
                    return {"success": True}
                elif resp.status == 401:  # Токен истек
                    logging.info("Токен Marzban истек при add_user. Обновляем...")
                    await self._get_token()
                    headers = {"Authorization": f"Bearer {self.token}"}
                    async with session.post(url, json=payload, headers=headers) as retry_resp:
                        if retry_resp.status == 200:
                            data = await retry_resp.json()
                            return {"success": True, "subscription_url": data.get('subscription_url', '')}
                        elif retry_resp.status == 409:
                            return {"success": True}
                return {"success": False}

    async def get_user(self, user_uuid):
        """Получает инфу о юзере напрямую из Marzban с защитой от протухшего токена"""
        if not self.token: await self._get_token()
        url = f"{self.base_url}/api/user/{user_uuid}"

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.token}"}
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 401:  # Токен истек
                    logging.info("Токен Marzban истек при get_user. Обновляем...")
                    await self._get_token()
                    headers = {"Authorization": f"Bearer {self.token}"}
                    async with session.get(url, headers=headers) as retry_resp:
                        if retry_resp.status == 200:
                            return await retry_resp.json()
                        return None
                else:
                    return None

    async def extend_user(self, inbound_id, user_uuid, user_email, sub_id, new_expiry_ms):
        """Жестко устанавливает новую дату истечения подписки в Marzban"""
        if not self.token: await self._get_token()
        url = f"{self.base_url}/api/user/{user_uuid}"
        expiry_s = int(new_expiry_ms / 1000) if new_expiry_ms > 0 else 0
        payload = {"expire": expiry_s}

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.token}"}
            async with session.put(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    return {"success": True}
                elif resp.status == 401:  # Токен истек
                    logging.info("Токен Marzban истек при extend_user. Обновляем...")
                    await self._get_token()
                    headers = {"Authorization": f"Bearer {self.token}"}
                    async with session.put(url, json=payload, headers=headers) as retry_resp:
                        if retry_resp.status == 200:
                            return {"success": True}
                        return {"success": False, "error": await retry_resp.text()}
                else:
                    return {"success": False, "error": await resp.text()}

    async def get_all_users(self):
        """Получает список всех пользователей из Marzban"""
        if not self.token: await self._get_token()
        url = f"{self.base_url}/api/users"

        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self.token}"}
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 401:  # Токен истек
                        logging.info("Токен Marzban истек при get_all_users. Обновляем...")
                        await self._get_token()
                        headers = {"Authorization": f"Bearer {self.token}"}
                        async with session.get(url, headers=headers) as retry_resp:
                            if retry_resp.status == 200:
                                return await retry_resp.json()
                    return None
        except Exception:
            return None

    async def get_system_stats(self):
        """Получает статистику системы (CPU, RAM, Версия)"""
        if not self.token: await self._get_token()
        url = f"{self.base_url}/api/system"

        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self.token}"}
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 401:  # Токен истек
                        logging.info("Токен Marzban истек при get_system_stats. Обновляем...")
                        await self._get_token()
                        headers = {"Authorization": f"Bearer {self.token}"}
                        async with session.get(url, headers=headers) as retry_resp:
                            if retry_resp.status == 200:
                                return await retry_resp.json()
                    return None
        except Exception:
            return None

    async def close(self):
        pass

