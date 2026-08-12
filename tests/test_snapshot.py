import sqlite3

from utils.snapshot import daily_snapshot_loop


async def test_snapshot_creates_readable_copy(db, tmp_path, monkeypatch):
    await db.add_user(42, "tester", "Test", expiry_ms=0)

    snapshot_dir = tmp_path / "snapshots"

    async def fake_sleep(_seconds):
        raise StopAsyncIteration  # прерываем бесконечный цикл после первой итерации

    monkeypatch.setattr("utils.snapshot.asyncio.sleep", fake_sleep)

    try:
        await daily_snapshot_loop(db.db_file, snapshot_dir=str(snapshot_dir))
    except StopAsyncIteration:
        pass

    files = list(snapshot_dir.glob("vpn_service_*.db"))
    assert len(files) == 1

    con = sqlite3.connect(files[0])
    try:
        cur = con.execute("SELECT tg_id FROM users WHERE tg_id = 42")
        assert cur.fetchone() == (42,)
    finally:
        con.close()
