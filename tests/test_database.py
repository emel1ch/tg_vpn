async def test_add_and_get_user(db):
    await db.add_user(tg_id=1, username="tester", full_name="Test User", expiry_ms=0)

    user = await db.get_user(1)

    assert user is not None
    assert user["tg_id"] == 1
    assert user["username"] == "tester"
