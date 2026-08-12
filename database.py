import aiosqlite
import json
from contextlib import asynccontextmanager
from datetime import datetime
import time


@asynccontextmanager
async def get_db_connection(db_file: str):
    """
    Соединение с уже настроенными PRAGMA (WAL, busy_timeout). Использовать
    в местах с длинными фоновыми циклами (notifier.py и т.п.), где несколько
    запросов идут через одно и то же соединение и риск "database is locked"
    выше, чем у коротких точечных запросов в методах Database.
    """
    async with aiosqlite.connect(db_file) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        yield conn


class Database:
    def __init__(self, db_file):
        self.db_file = db_file

    async def create_tables(self):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    tg_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    contact_link TEXT,
                    expiry_ms INTEGER,
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

            # --- МИГРАЦИЯ ДЛЯ РЕФЕРАЛОВ ---
            # Пытаемся добавить колонки. Если они уже есть, SQLite выдаст ошибку, которую мы игнорируем.
            new_columns = [
                "has_used_trial BOOLEAN DEFAULT 0",
                "reg_time_ms INTEGER DEFAULT 0",
                "reminder_stage INTEGER DEFAULT 0",
                "lapsed_reminder_stage INTEGER DEFAULT 0",
                "ref_limit INTEGER DEFAULT 12",
                "last_ref_month TEXT DEFAULT ''"
            ]
            for col in new_columns:
                try:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col}")
                except Exception:
                    pass
            try:
                await db.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER DEFAULT NULL")
            except Exception:
                pass

            try:
                await db.execute("ALTER TABLE users ADD COLUMN referrals_count INTEGER DEFAULT 0")
            except Exception:
                pass

            # Персистентный флаг для надёжных напоминаний об истечении (Фаза 3.3):
            # раньше отправка зависела от попадания в узкое "окно" при часовом цикле
            # и легко проскакивала при рестарте бота.
            try:
                await db.execute("ALTER TABLE users ADD COLUMN last_expiry_notify_days INTEGER DEFAULT NULL")
            except Exception:
                pass

            # --- АНАЛИТИЧЕСКАЯ СХЕМА (Фаза 2) ---
            await db.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT,
                    ts_ms INTEGER NOT NULL
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_events_tg_id ON events(tg_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(event_type, ts_ms)")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS referral_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER NOT NULL,
                    referee_id INTEGER NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    bonus_days INTEGER DEFAULT 0
                )
            """)

            transactions_columns = [
                "method TEXT",
                "currency TEXT",
                "status TEXT DEFAULT 'approved'",
                "approved_by INTEGER",
                "created_ts_ms INTEGER",
                "decided_ts_ms INTEGER",
            ]
            for col in transactions_columns:
                try:
                    await db.execute(f"ALTER TABLE transactions ADD COLUMN {col}")
                except Exception:
                    pass

            await db.commit()

    async def add_user(self, tg_id, username, full_name, expiry_ms, is_active=0):
        contact_link = f"tg://user?id={tg_id}"
        reg_time = int(time.time() * 1000) # ДОБАВЛЕНО
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (tg_id, username, full_name, contact_link, expiry_ms, is_active, reg_time_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (tg_id, username, full_name, contact_link, expiry_ms, is_active, reg_time)
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
            # Обнуляем стадию напоминаний об отвале и флаг напоминаний об истечении
            # (last_expiry_notify_days) — подписка продлена, старый цикл уведомлений
            # больше не актуален.
            await db.execute(
                "UPDATE users SET expiry_ms = ?, is_active = 1, total_paid = total_paid + ?, "
                "lapsed_reminder_stage = 0, last_expiry_notify_days = NULL WHERE tg_id = ?",
                (new_expiry_ms, amount, tg_id))
            await db.execute("INSERT INTO transactions (tg_id, amount, pay_date) VALUES (?, ?, ?)",
                             (tg_id, amount, current_date))
            await db.commit()

    async def update_expiry_notify_stage(self, tg_id: int, days_left: int):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("UPDATE users SET last_expiry_notify_days = ? WHERE tg_id = ?", (days_left, tg_id))
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
            # ВОТ ЭТА СТРОКА РЕШАЕТ ПРОБЛЕМУ:
            db.row_factory = aiosqlite.Row

            async with db.execute("SELECT pay_date, amount FROM transactions WHERE tg_id = ? ORDER BY id DESC LIMIT ?",
                                  (tg_id, limit)) as cursor:
                return await cursor.fetchall()

    async def get_all_users(self):
        """Получает список всех TG ID пользователей"""
        async with aiosqlite.connect(self.db_file) as db:  # ИСПРАВЛЕНО: было self.path
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT tg_id FROM users")
            rows = await cursor.fetchall()
            return [row['tg_id'] for row in rows]

    async def get_user_by_username(self, username: str):
        """Находит пользователя по юзернейму (без @)"""
        async with aiosqlite.connect(self.db_file) as db:
            db.row_factory = aiosqlite.Row
            # Очищаем от @ и приводим к нижнему регистру для надежности
            username = username.replace("@", "").strip().lower()
            # В SQL запросе тоже используем LOWER(username) на случай,
            # если в базе записано 'StealYourWifey'
            cursor = await db.execute("SELECT * FROM users WHERE LOWER(username) = ?", (username,))
            return await cursor.fetchone()

    async def add_referral_count(self, tg_id):
        """Увеличивает счетчик приглашенных у пользователя на 1 и возвращает новое значение"""
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE tg_id = ?", (tg_id,))
            await db.commit()

            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT referrals_count FROM users WHERE tg_id = ?", (tg_id,)) as cursor:
                row = await cursor.fetchone()
                return row['referrals_count'] if row else 0

    async def update_referrer(self, tg_id, referrer_id):
        """Записывает, кто пригласил этого пользователя"""
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("UPDATE users SET referrer_id = ? WHERE tg_id = ?", (referrer_id, tg_id))
            await db.commit()

    async def get_active_subscriptions(self):
        """Получает пользователей, у которых реальное время подписки еще не вышло"""
        # Берем текущее время в миллисекундах (т.к. у тебя expiry_ms)
        current_time_ms = int(time.time() * 1000)

        async with aiosqlite.connect(self.db_file) as db:
            db.row_factory = aiosqlite.Row
            # Ищем тех, у кого дата истечения больше текущей
            async with db.execute("SELECT * FROM users WHERE expiry_ms > ?", (current_time_ms,)) as cursor:
                return await cursor.fetchall()

    async def update_sync_data(self, tg_id, expiry_ms, is_active, sub_id):
        """Тихо обновляет данные пользователя при синхронизации с панелью"""
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("""
                UPDATE users
                SET expiry_ms = ?, is_active = ?, sub_id = ?
                WHERE tg_id = ?
            """, (expiry_ms, is_active, sub_id, tg_id))
            await db.commit()

    # ========================================================
    # АНАЛИТИКА (Фаза 2)
    # ========================================================

    async def log_event(self, tg_id: int, event_type: str, payload: dict | None = None):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                "INSERT INTO events (tg_id, event_type, payload, ts_ms) VALUES (?, ?, ?, ?)",
                (tg_id, event_type, json.dumps(payload or {}, ensure_ascii=False), int(time.time() * 1000))
            )
            await db.commit()

    async def log_referral_event(self, referrer_id: int, referee_id: int, bonus_days: int = 0):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                "INSERT INTO referral_events (referrer_id, referee_id, ts_ms, bonus_days) VALUES (?, ?, ?, ?)",
                (referrer_id, referee_id, int(time.time() * 1000), bonus_days)
            )
            await db.commit()

    async def get_events(self, since_ts_ms: int):
        async with aiosqlite.connect(self.db_file) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                    "SELECT tg_id, event_type, payload, ts_ms FROM events WHERE ts_ms >= ? ORDER BY ts_ms DESC",
                    (since_ts_ms,)) as cursor:
                return await cursor.fetchall()

    # --- Привязка транзакции к платежу: payment_created создаёт запись со
    # status='pending', payment_approved/payment_rejected обновляют эту же
    # запись (а не создают новую) — чтобы считать конверсию pending -> approved
    # по одной и той же транзакции. ---

    async def create_pending_transaction(self, tg_id: int, method: str | None = None, currency: str | None = None) -> int:
        async with aiosqlite.connect(self.db_file) as db:
            cursor = await db.execute(
                "INSERT INTO transactions (tg_id, amount, pay_date, method, currency, status, created_ts_ms) "
                "VALUES (?, 0, ?, ?, ?, 'pending', ?)",
                (tg_id, datetime.now().strftime('%d.%m.%Y %H:%M'), method, currency, int(time.time() * 1000))
            )
            await db.commit()
            return cursor.lastrowid

    async def approve_pending_transaction(self, transaction_id: int, tg_id: int, amount: int, new_expiry_ms: int, approved_by: int):
        current_date = datetime.now().strftime('%d.%m.%Y %H:%M')
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                "UPDATE users SET expiry_ms = ?, is_active = 1, total_paid = total_paid + ?, lapsed_reminder_stage = 0 WHERE tg_id = ?",
                (new_expiry_ms, amount, tg_id))
            await db.execute(
                "UPDATE transactions SET amount = ?, pay_date = ?, status = 'approved', approved_by = ?, decided_ts_ms = ? WHERE id = ?",
                (amount, current_date, approved_by, int(time.time() * 1000), transaction_id))
            await db.commit()

    async def reject_pending_transaction(self, transaction_id: int):
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute(
                "UPDATE transactions SET status = 'rejected', decided_ts_ms = ? WHERE id = ?",
                (int(time.time() * 1000), transaction_id))
            await db.commit()