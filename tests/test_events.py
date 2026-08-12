import aiosqlite


async def test_log_event_insert(db):
    await db.log_event(123, "trial_activated", {"foo": "bar"})

    events = await db.get_events(since_ts_ms=0)

    assert len(events) == 1
    assert events[0]["tg_id"] == 123
    assert events[0]["event_type"] == "trial_activated"
    assert events[0]["payload"] == '{"foo": "bar"}'


async def test_get_events_filters_by_period(db):
    async with aiosqlite.connect(db.db_file) as conn:
        await conn.execute(
            "INSERT INTO events (tg_id, event_type, payload, ts_ms) VALUES (?, ?, ?, ?)",
            (1, "old_event", "{}", 1000))
        await conn.execute(
            "INSERT INTO events (tg_id, event_type, payload, ts_ms) VALUES (?, ?, ?, ?)",
            (2, "new_event", "{}", 2_000_000))
        await conn.commit()

    events = await db.get_events(since_ts_ms=1_000_000)

    assert len(events) == 1
    assert events[0]["event_type"] == "new_event"


async def test_payment_created_to_approved_updates_same_row(db):
    transaction_id = await db.create_pending_transaction(555, method="sbp")

    async with aiosqlite.connect(db.db_file) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM transactions WHERE tg_id = ?", (555,))
        rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"

    await db.add_user(555, "tester", "Test", expiry_ms=0)
    await db.approve_pending_transaction(transaction_id, 555, amount=200, new_expiry_ms=999999999, approved_by=1)

    async with aiosqlite.connect(db.db_file) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM transactions WHERE tg_id = ?", (555,))
        rows = await cursor.fetchall()

    # Не должно появиться второй (дублирующей) транзакции
    assert len(rows) == 1
    assert rows[0]["id"] == transaction_id
    assert rows[0]["status"] == "approved"
    assert rows[0]["amount"] == 200
    assert rows[0]["approved_by"] == 1
