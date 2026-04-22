import aiosqlite
from datetime import datetime

class Database:
    def __init__(self, db_file):
        self.db_file = db_file

    async def create_tables(self):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    tg_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    contact_link TEXT,
                    expiry_ms INTEGER,  -- ТЕПЕРЬ ХРАНИМ В МИЛЛИСЕКУНДАХ
                    is_active BOOLEAN DEFAULT 1,
                    total_paid INTEGER DEFAULT 0,
                    uuid TEXT,
                    sub_id TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_id INTEGER,
                    amount INTEGER,
                    pay_date TEXT
                )
            """)
            await db.commit()

    async def add_user(self, tg_id, username, full_name, expiry_ms, is_active=0):
        contact_link = f"tg://user?id={tg_id}"
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (tg_id, username, full_name, contact_link, expiry_ms, is_active) VALUES (?, ?, ?, ?, ?, ?)",
                (tg_id, username, full_name, contact_link, expiry_ms, is_active)
            )
            await db.commit()
    async def get_user(self, tg_id):
        async with aiosqlite.connect(self.db_file) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)) as cursor:
                return await cursor.fetchone()

    async def get_all_active_users(self):
        async with aiosqlite.connect(self.db_file) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE is_active = 1") as cursor:
                return await cursor.fetchall()

    async def confirm_payment(self, tg_id, amount, new_expiry_ms):
        current_date = datetime.now().strftime('%d.%m.%Y %H:%M')
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("UPDATE users SET expiry_ms = ?, is_active = 1, total_paid = total_paid + ? WHERE tg_id = ?",
                               (new_expiry_ms, amount, tg_id))
            await db.execute("INSERT INTO transactions (tg_id, amount, pay_date) VALUES (?, ?, ?)",
                               (tg_id, amount, current_date))
            await db.commit()

    async def set_user_keys(self, tg_id, user_uuid, sub_id):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("UPDATE users SET uuid = ?, sub_id = ? WHERE tg_id = ?", (user_uuid, sub_id, tg_id))
            await db.commit()

    async def set_user_inactive(self, tg_id):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("UPDATE users SET is_active = 0 WHERE tg_id = ?", (tg_id,))
            await db.commit()

    async def get_transactions(self, tg_id, limit=5):
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute("SELECT pay_date, amount FROM transactions WHERE tg_id = ? ORDER BY id DESC LIMIT ?", (tg_id, limit)) as cursor:
                return await cursor.fetchall()

    async def get_tg_id_by_username(self, username):
        clean_username = username.replace("@", "").strip()
        async with aiosqlite.connect(self.db_file) as db:
            async with db.execute("SELECT tg_id FROM users WHERE username = ? COLLATE NOCASE", (clean_username,)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else None