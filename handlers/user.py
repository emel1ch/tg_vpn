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
async def show_status(callback: types.CallbackQuery, db, panel):
    user_id = callback.from_user.id
    user_data = await db.get_user(user_id)

    if not user_data:
        await callback.answer("Запустите бота через /start", show_alert=True)
        return

    # 1. Проверяем наличие юзера в панели
    marzban_user = await panel.get_user(str(user_id))

    # 2. Если юзера нет в панели (например, удалили), но подписка в БД активна — создаем заново
    if not marzban_user and user_data['expiry_ms'] > int(time.time() * 1000):
        await panel.add_user(1, "user", str(user_id), user_data['expiry_ms'])
        marzban_user = await panel.get_user(str(user_id))

    status = "🟢 Активен" if user_data['expiry_ms'] > int(time.time() * 1000) else "🔴 Истек"
    text = f"📊 **Статус:** {status}\n"

    if marzban_user and 'subscription_url' in marzban_user:
        sub_url = marzban_user['subscription_url']
        # Проверка на абсолютный путь
        if not sub_url.startswith("http"):
            from config import PANEL_URL
            sub_url = f"{PANEL_URL.rstrip('/')}{sub_url}"

        text += f"🔗 **Ваша ссылка:**\n`{sub_url}`"
    else:
        text += "⚠️ Ссылка временно недоступна."

    await callback.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="Markdown")
@router.callback_query(F.data == "support")
async def support_init(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SupportState.waiting_for_msg)
    await callback.message.edit_text("📝 Опиши свою проблему, я передам её админу.", reply_markup=get_back_kb())


@router.message(SupportState.waiting_for_msg)
async def forward_support(message: types.Message, state: FSMContext, bot: Bot):
    # Формируем "шапку" для админа
    header = f"🆘 **Новый запрос в поддержку!**\nОт: @{message.from_user.username or 'скрыт'}\n🆔 ID: `{message.from_user.id}`\n\n"

    # Сначала шлем инфо-сообщение
    await bot.send_message(GROUP_ID, header, parse_mode="Markdown")

    # Затем копируем само сообщение (текст, фото или что угодно другое)
    await message.copy_to(GROUP_ID)

    await state.clear()
    await message.answer("✅ Твой вопрос передан админу. Ожидай ответа прямо здесь.", reply_markup=get_main_menu())

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