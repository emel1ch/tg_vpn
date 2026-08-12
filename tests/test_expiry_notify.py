import aiosqlite


async def test_update_expiry_notify_stage_persists(db):
    await db.add_user(1, "tester", "Test", expiry_ms=0)

    await db.update_expiry_notify_stage(1, 3)

    async with aiosqlite.connect(db.db_file) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT last_expiry_notify_days FROM users WHERE tg_id = 1")
        row = await cursor.fetchone()

    assert row["last_expiry_notify_days"] == 3


async def test_confirm_payment_resets_expiry_notify_stage(db):
    await db.add_user(1, "tester", "Test", expiry_ms=0)
    await db.update_expiry_notify_stage(1, 1)

    await db.confirm_payment(1, amount=200, new_expiry_ms=999999999)

    async with aiosqlite.connect(db.db_file) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT last_expiry_notify_days FROM users WHERE tg_id = 1")
        row = await cursor.fetchone()

    assert row["last_expiry_notify_days"] is None
