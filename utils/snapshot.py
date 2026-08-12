import asyncio
import os
from datetime import datetime

import aiosqlite


async def daily_snapshot_loop(db_path: str, snapshot_dir: str = "snapshots"):
    """
    Раз в сутки делает VACUUM INTO копию боевой БД в snapshot_dir — доступ
    для аналитиков без риска заблокировать прод-БД конкурентными запросами.
    """
    os.makedirs(snapshot_dir, exist_ok=True)
    while True:
        try:
            date_str = datetime.now().strftime("%Y-%m-%d")
            snapshot_path = os.path.join(snapshot_dir, f"vpn_service_{date_str}.db")
            if not os.path.exists(snapshot_path):
                async with aiosqlite.connect(db_path) as conn:
                    await conn.execute("VACUUM INTO ?", (snapshot_path,))
        except Exception as e:
            print(f"[SNAPSHOT ERROR] Ошибка создания снапшота: {e}")

        await asyncio.sleep(24 * 60 * 60)
