import time
from aiogram import Router, types, F, Bot
from config import MONTH_MS, INBOUND_ID
router = Router()


@router.callback_query(F.data.startswith("pay_"))
async def process_admin_pay(callback: types.CallbackQuery, db, panel, bot: Bot):
    action, uid = callback.data.split(":")
    uid = int(uid)

    if action == "pay_yes":
        user = await db.get_user(uid)
        now_ms = int(time.time() * 1000)
        new_expiry = max(user['expiry_ms'], now_ms) + MONTH_MS

        # Продление в панели Marzban
        res = await panel.extend_user(INBOUND_ID, user['uuid'], f"ID: {uid}", user['sub_id'], new_expiry)

        if res.get("success"):
            await db.confirm_payment(uid, 200, new_expiry)
            await bot.send_message(uid, f"✅ Оплата принята! Подписка продлена.\nТвоя ссылка:\n`{user['sub_id']}`")
            await callback.message.edit_caption(caption="✅ ОДОБРЕНО")
    else:
        await bot.send_message(uid, "❌ Твоя оплата была отклонена.")
        await callback.message.edit_caption(caption="❌ ОТКЛОНЕНО")