import time
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove
from datetime import datetime
from utils.keyboards import get_main_menu, get_guides_kb, get_back_kb
from config import GROUP_ID, ADMIN_ID, TRIAL_DAYS, INBOUND_ID, HAPP_ROUTING_LINK


router = Router()


class SupportState(StatesGroup):
    waiting_for_msg = State()


@router.message(Command("start", "menu"))
async def cmd_start(message: types.Message, command: CommandObject, state: FSMContext, db, panel, bot: Bot):
    await state.clear()
    uid = message.from_user.id
    user = await db.get_user(uid)
    args = command.args  # Получаем то, что написано после /start

    if not user:
        # НОВЫЙ ПОЛЬЗОВАТЕЛЬ
        now_ms = int(time.time() * 1000)
        trial_ms = TRIAL_DAYS * 24 * 60 * 60 * 1000
        expiry_ms = now_ms + trial_ms

        await db.add_user(uid, message.from_user.username, message.from_user.full_name, expiry_ms=expiry_ms,
                          is_active=1)
        # Создаем в Marzban и ловим ответ
        panel_res = await panel.add_user(INBOUND_ID, None, str(uid), expiry_ms)

        # Если успешно создалось, сразу сохраняем ссылку в БД бота
        if panel_res and panel_res.get("success"):
            sub_url = panel_res.get("subscription_url", "")
            if sub_url:
                await db.set_user_keys(uid, str(uid), sub_url)

        # --- ЛОГИКА РЕФЕРАЛОВ ---
        if args and args.startswith("ref"):
            try:
                referrer_id = int(args.replace("ref", ""))
                # Проверяем, что не пригласил сам себя и что пригласивший существует
                if referrer_id != uid and await db.get_user(referrer_id):
                    await db.update_referrer(uid, referrer_id)
                    refs_count = await db.add_referral_count(referrer_id)

                    # Если счетчик делится на 2 (2, 4, 6...), выдаем 14 дней!
                    if refs_count % 2 == 0:
                        ref_user = await db.get_user(referrer_id)
                        curr_exp = ref_user['expiry_ms'] if ref_user['expiry_ms'] > now_ms else now_ms
                        new_exp = curr_exp + (14 * 24 * 60 * 60 * 1000)

                        await db.confirm_payment(referrer_id, 0, new_exp)
                        await panel.extend_user(INBOUND_ID, str(referrer_id), None, None, new_exp)

                        try:
                            await bot.send_message(referrer_id,
                                                   "🎉 <b>Вы пригласили 2-х друзей!</b>\nВам начислено <b>14 дней бесплатного VPN</b>!",
                                                   parse_mode="HTML")
                        except Exception:
                            pass
                    else:
                        try:
                            await bot.send_message(referrer_id,
                                                   f"🎁 По вашей ссылке зарегистрировался друг! (<b>{refs_count}</b>)\n<i>Пригласите еще 1, чтобы получить 14 дней.</i>",
                                                   parse_mode="HTML")
                        except Exception:
                            pass
            except ValueError:
                pass  # Если прислали кривой ref (не число)

        welcome_text = (
            f"👋 <b>Добро пожаловать!</b>\n\n"
            f"🎁 Мы начислили вам <b>{TRIAL_DAYS} дня бесплатного доступа</b>!\n"
            f"Нажмите «📊 Статус (Подписка)», чтобы получить вашу ссылку-подписку.\n\n"
            f"🚀 <b>Управление VPN подпиской GTN VPN</b>\n"
            f"🆔 Ваш ID: <code>{uid}</code>"
        )
    else:
        # СТАРЫЙ ПОЛЬЗОВАТЕЛЬ
        welcome_text = (
            f"🚀 <b>Управление VPN подпиской GTN VPN</b>\n"
            f"🆔 Ваш ID: <code>{uid}</code>"
        )

    # Безопасная отправка меню
    try:
        await message.delete()  # Очищаем команду /start
    except Exception:
        pass
    await message.answer(welcome_text, reply_markup=get_main_menu(), parse_mode="HTML")


@router.callback_query(F.data == "status")
async def show_status(callback: types.CallbackQuery, db, panel):
    # 1. ОТЛЕПЛЯЕМ КНОПКУ СРАЗУ (чтобы не было долгих часиков)
    await callback.answer("⏳ Загружаю данные...")

    user_id = callback.from_user.id
    user_data = await db.get_user(user_id)

    if not user_data:
        return await callback.message.answer("❌ Ошибка: запустите бота через /start")

    # Идем в Marzban (если бот локально, а PANEL_URL неправильный - тут он может выдать ошибку связи)
    marzban_user = await panel.get_user(str(user_id))

    # Если юзера нет в панели, но подписка в БД активна — создаем заново
    if not marzban_user and user_data['expiry_ms'] > int(time.time() * 1000):
        await panel.add_user(1, "user", str(user_id), user_data['expiry_ms'])
        marzban_user = await panel.get_user(str(user_id))

    status = "🟢 Активен" if user_data['expiry_ms'] > int(time.time() * 1000) else "🔴 Истек"

    # Считаем дату красиво
    expiry_date = "Никогда"
    if user_data['expiry_ms'] > 0:
        expiry_date = datetime.fromtimestamp(user_data['expiry_ms'] / 1000).strftime('%d.%m.%Y %H:%M')

    text = f"📊 <b>Ваш статус:</b> {status}\n"
    text += f"⏳ <b>Истекает:</b> {expiry_date}\n\n"

    if marzban_user and 'subscription_url' in marzban_user and marzban_user['subscription_url']:
        sub_url = marzban_user['subscription_url']
        if not sub_url.startswith("http"):
            from config import PANEL_URL
            sub_url = f"{PANEL_URL.rstrip('/')}{sub_url}"

        text += (
            "➖ ➖ ➖ ➖ ➖ ➖ ➖\n\n"
            "<i>Умный обход: РФ-сайты напрямую, остальное через VPN</i>\n\n"
            "<b>Шаг 1:</b> Установи приложение Happ\n"
            f"<b>Шаг 2:</b> <a href='{HAPP_ROUTING_LINK}'>⚙️ Настроить маршрутизацию</a>\n"
            "<i>(Нажми на текст 👆, откроется Happ, профиль добавится сам)</i>\n\n"
            "<b>Шаг 3:</b> Скопируй твою подписку (нажми на ссылку 👇):\n"
            f"<code>{sub_url}</code>\n"
            "<i>Затем вставь её в Happ: кнопка «+» ➔ Import from Clipboard</i>\n\n"
            "➖ ➖ ➖ ➖ ➖ ➖ ➖\n\n"
        )
    else:
        text += "⚠️ Ссылка временно недоступна."
    # 2. БЕЗОПАСНАЯ ОТПРАВКА МЕНЮ
    try:
        await callback.message.delete()
    except Exception:
        pass  # Игнорируем ошибку удаления

    await callback.message.answer(text, reply_markup=get_back_kb(), parse_mode="HTML")

@router.callback_query(F.data == "support")
async def support_init(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SupportState.waiting_for_msg)
    await callback.message.edit_text("📝 Опиши свою проблему, я передам её админу.", reply_markup=get_back_kb())


@router.message(SupportState.waiting_for_msg)
async def forward_support(message: types.Message, state: FSMContext, bot: Bot):
    await state.clear()

    # Формируем подпись (теперь она будет внутри сообщения юзера)
    user_info = f"\n\n---\n🆘 Запрос от @{message.from_user.username or 'скрыт'}\n🆔 ID: <code>{message.from_user.id}</code>"

    # Пересылаем сообщение в группу с добавленной подписью (работает и для текста, и для фото)
    if message.text:
        await bot.send_message(GROUP_ID, f"{message.text}{user_info}", parse_mode="HTML")
    elif message.photo:
        caption = message.caption if message.caption else ""
        await bot.send_photo(GROUP_ID, message.photo[-1].file_id, caption=f"{caption}{user_info}", parse_mode="HTML")
    else:
        # Для стикеров, голосовых и т.д. просто пересылаем, а потом шлем ID ответом на него
        sent_msg = await message.copy_to(GROUP_ID)
        await bot.send_message(GROUP_ID, f"☝️ ID: <code>{message.from_user.id}</code>",
                               reply_to_message_id=sent_msg.message_id, parse_mode="HTML")

    await message.answer("✅ Твой вопрос передан админу. Ожидай ответа прямо здесь.", reply_markup=get_main_menu())


@router.callback_query(F.data == "to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    uid = callback.from_user.id
    text = (
        f"🚀 <b>Управление VPN подпиской GTN VPN</b>\n"
        f"🆔 Ваш ID: <code>{uid}</code>"
    )
    kb = get_main_menu()

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


from utils.keyboards import get_guides_kb  # убедитесь, что этот импорт есть наверху


@router.callback_query(F.data == "guides")
async def show_guides(callback: types.CallbackQuery):
    await callback.answer()

    text = "📚 <b>Инструкции по настройке VPN</b>\n\nВыберите вашу платформу, чтобы посмотреть подробный гайд:"

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(text, reply_markup=get_guides_kb(), parse_mode="HTML")


@router.callback_query(F.data == "history")
async def show_history(callback: types.CallbackQuery, db):
    await callback.answer()

    user_id = callback.from_user.id
    transactions = await db.get_transactions(user_id, limit=5)

    if not transactions:
        text = "📜 <b>История транзакций пуста.</b>\nВы еще не совершали оплат."
    else:
        text = "📜 <b>Ваши последние 5 транзакций:</b>\n\n"
        for idx, t in enumerate(transactions, 1):
            text += f"{idx}. <b>{t['amount']}₽</b> — <i>{t['pay_date']}</i>\n"

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(text, reply_markup=get_back_kb(), parse_mode="HTML")


@router.callback_query(F.data == "referral_menu")
async def show_referral_menu(callback: types.CallbackQuery, db, bot: Bot):
    await callback.answer()
    uid = callback.from_user.id
    user = await db.get_user(uid)

    if not user:
        return await callback.message.answer("❌ Ошибка базы данных.")

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref{uid}"

    refs_count = user['referrals_count'] if 'referrals_count' in user.keys() else 0
    next_bonus = 2 - (refs_count % 2)  # Сколько осталось до бонуса (1 или 2)

    text = (
        f"🎁 <b>Реферальная программа</b>\n\n"
        f"Приглашайте друзей и получайте бесплатный VPN!\n"
        f"🔥 <b>За каждых 2-х друзей — мы даем 14 дней бесплатно!</b>\n\n"
        f"📊 <b>Ваша статистика:</b>\n"
        f"👥 Приглашено друзей: <b>{refs_count}</b>\n"
        f"⏳ До следующего бонуса (14 дней) осталось пригласить: <b>{next_bonus}</b> чел.\n\n"
        f"👇 <b>Ваша уникальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"<i>Нажмите на ссылку, чтобы скопировать её и отправить друзьям!</i>"
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(text, reply_markup=get_back_kb(), parse_mode="HTML")