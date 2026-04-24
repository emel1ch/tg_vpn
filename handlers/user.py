import time
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove
from datetime import datetime
from utils.keyboards import get_main_menu, get_guides_kb, get_back_kb
from config import GROUP_ID, ADMIN_ID

router = Router()


class SupportState(StatesGroup):
    waiting_for_msg = State()


@router.message(Command("start", "menu"))
async def cmd_start(message: types.Message, state: FSMContext, db):
    await state.clear()
    uid = message.from_user.id
    user = await db.get_user(uid)

    # Принудительно убираем старый дашборд
    if not user:
        # Логика регистрации остается, но без выдачи старых ключей
        await db.add_user(uid, message.from_user.username, message.from_user.full_name, expiry_ms=0, is_active=0)

    await message.answer(
        "Управление VPN подпиской **Aura VPN** 🚀",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "status")
async def show_status(callback: types.CallbackQuery, db, panel):  # <-- Добавили panel
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Сначала нажми /start", show_alert=True)
        return

    now_ms = int(time.time() * 1000)
    expiry = user['expiry_ms']

    days = max(0, (expiry - now_ms) // (24 * 60 * 60 * 1000))
    status = "🟢 Активен" if expiry > now_ms else "🔴 Истек"

    text = f"📊 **Твой статус:** {status}\n📅 **Осталось дней:** {days}\n\n"

    if expiry > now_ms:
        # Стучимся в Marzban за актуальной ссылкой (по Telegram ID)
        marzban_user = await panel.get_user(str(callback.from_user.id))

        if marzban_user and 'subscription_url' in marzban_user:
            sub_url = marzban_user['subscription_url']

            # Если Marzban отдает путь без домена (начинается с /sub/)
            if not sub_url.startswith("http"):
                from config import PANEL_URL
                sub_url = f"{PANEL_URL.rstrip('/')}{sub_url}"

            # Заодно обновляем правильную ссылку в нашей БД
            await db.set_user_keys(callback.from_user.id, str(callback.from_user.id), sub_url)

            text += f"🔗 **Твоя ссылка:**\n`{sub_url}`\n\n*(Скопируй её и вставь в приложение)*"
        else:
            text += "⏳ Ошибка получения ссылки. Обратись в поддержку."

    await callback.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "support")
async def support_init(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SupportState.waiting_for_msg)
    await callback.message.edit_text("📝 Опиши свою проблему, я передам её админу.", reply_markup=get_back_kb())


@router.message(SupportState.waiting_for_msg)
async def forward_support(message: types.Message, state: FSMContext, bot: Bot):
    # Отправляем админу и в группу (для надежности)
    report = f"🆘 **Новый вопрос!**\nОт: @{message.from_user.username}\nID: `{message.from_user.id}`\n\n{message.text}"
    await bot.send_message(GROUP_ID, report, parse_mode="Markdown")
    await state.clear()
    await message.answer("✅ Отправлено! Ожидай ответа.", reply_markup=get_main_menu())


@router.callback_query(F.data == "to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    text = "Управление VPN подпиской **Aura VPN** 🚀"
    kb = get_main_menu()

    try:
        # Пробуем просто отредактировать (если это было текстовое сообщение)
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        # Если это было фото — удаляем его и шлем новое сообщение
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")