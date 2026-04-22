import aiohttp
import json
import string
import random
import logging
from config import PANEL_URL, PANEL_LOGIN, PANEL_PASSWORD

def generate_sub_id(length=16):
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

class PanelAPI:
    def __init__(self):
        self.base_url = PANEL_URL
        self.username = PANEL_LOGIN
        self.password = PANEL_PASSWORD
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def login(self):
        session = await self._get_session()
        payload = {"username": self.username, "password": self.password}
        try:
            async with session.post(f"{self.base_url}/login", data=payload) as response:
                return response.status == 200
        except Exception as e:
            logging.error(f"Ошибка логина в панель: {e}")
            return False

    async def add_user(self, inbound_id, user_email, user_uuid, expiry_ms):
        session = await self._get_session()
        await self.login()
        sub_id = generate_sub_id()

        client_settings = {
            "id": user_uuid, "alterId": 0, "email": user_email, "limitIp": 2,
            "totalGB": 0, "expiryTime": expiry_ms, "enable": True,
            "tgId": "", "subId": sub_id
        }
        payload = {"id": inbound_id, "settings": json.dumps({"clients": [client_settings]})}

        async with session.post(f"{self.base_url}/panel/api/inbounds/addClient", data=payload) as resp:
            result = await resp.json()
            result["sub_id"] = sub_id
            return result

    async def extend_user(self, inbound_id, client_uuid, user_email, sub_id, new_expiry_ms):
        session = await self._get_session()
        await self.login()

        client_settings = {
            "id": client_uuid, "email": user_email, "limitIp": 2,
            "totalGB": 0, "expiryTime": new_expiry_ms, "enable": True, "subId": sub_id
        }
        payload = {"id": inbound_id, "settings": json.dumps({"clients": [client_settings]})}

        async with session.post(f"{self.base_url}/panel/api/inbounds/updateClient/{client_uuid}", data=payload) as resp:
            return await resp.json()

    async def close(self):
        if self.session:
            await self.session.close()