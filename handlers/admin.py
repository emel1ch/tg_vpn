import time
import re
from aiogram import Router, types, F, Bot
from config import MONTH_MS, INBOUND_ID, GROUP_ID

router = Router()


# --- МЕХАНИКА ОДОБРЕНИЯ ОПЛАТЫ ---
@router.callback_query(F.data.startswith("pay_"))
async def process_admin_pay(callback: types.CallbackQuery, db, panel, bot: Bot):
    action, uid = callback.data.split(":")
    uid = int(uid)

    if action == "pay_yes":
        user = await db.get_user(uid)
        now_ms = int(time.time() * 1000)

        # Считаем новый срок: если подписка активна — плюсуем к ней, если нет — от текущего момента
        current_expiry = user['expiry_ms'] if user and user['expiry_ms'] else 0
        new_expiry = max(current_expiry, now_ms) + MONTH_MS

        # 1. Пробуем продлить в Marzban (используем ID как username)
        # Если юзера нет в панели (вернул 404), создаем его с новым сроком
        marzban_res = await panel.extend_user(INBOUND_ID, str(uid), f"User_{uid}", None, new_expiry)

        if not marzban_res.get("success"):
            # Если продление не вышло (юзер удален/новый), создаем заново
            await panel.add_user(INBOUND_ID, f"User_{uid}", str(uid), new_expiry)

        # 2. Обновляем локальную базу
        await db.confirm_payment(uid, 200, new_expiry)

        # 3. Уведомляем пользователя
        await bot.send_message(uid,
                               "✅ Ваша оплата принята! Подписка активирована/продлена.\n\nПроверьте статус кнопкой в меню.")
        await callback.message.edit_caption(caption=f"✅ ОДОБРЕНО для ID: {uid}")

    elif action == "pay_no":
        await bot.send_message(uid, "❌ Ваша оплата была отклонена администратором.")
        await callback.message.edit_caption(caption=f"❌ ОТКЛОНЕНО для ID: {uid}")

    await callback.answer()


# --- МЕХАНИКА ОТВЕТА ИЗ БЕСЕДЫ (REPLY) ---
@router.message(F.chat.id == GROUP_ID, F.reply_to_message)
async def admin_reply_to_user(message: types.Message, bot: Bot):
    # Ищем ID пользователя в тексте сообщения, на которое отвечаем
    # Мы специально пишем "🆔 ID: `123456789`" в каждом уведомлении
    reply_to = message.reply_to_message
    source_text = reply_to.text or reply_to.caption

    if not source_text: return

    # Ищем ID через регулярку
    match = re.search(r"ID: `(\d+)`", source_text)
    if not match: return

    user_id = int(match.group(1))

    try:
        # Пересылаем ответ админа (текст или медиа) пользователю
        await message.copy_to(user_id)
        await message.reply("✅ Ответ доставлен пользователю.")
    except Exception as e:
        await message.reply(f"❌ Ошибка отправки: {e}")