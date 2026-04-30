import time
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
from utils.keyboards import get_main_menu, get_back_kb
from config import GROUP_ID, TRIAL_DAYS, INBOUND_ID, HAPP_ROUTING_LINK
from utils.keyboards import get_guides_kb  

router = Router()


class SupportState(StatesGroup):
    waiting_for_msg = State()


@router.message(Command("start", "menu"))
async def cmd_start(message: types.Message, command: CommandObject, state: FSMContext, db, panel, bot: Bot):
    await state.clear()
    uid = message.from_user.id
    user = await db.get_user(uid)
    args = command.args

    if not user:
        # НОВЫЙ ПОЛЬЗОВАТЕЛЬ (Регистрация с 0 временем)
        await db.add_user(uid, message.from_user.username, message.from_user.full_name, expiry_ms=0, is_active=0)
        has_used_trial = False

        welcome_text = (
            f"👋 <b>Добро пожаловать в GTN VPN!</b>\n\n"
            f"🎁 Вам доступен <b>бесплатный период на {TRIAL_DAYS} дня</b>.\n"
            f"Нажмите кнопку «🎁 Получить 3 дня (Trial)» ниже, чтобы активировать его!\n\n"
            f"⚠️ <i>Обязательно подпишитесь на Наш Канал для работы бота.</i>\n\n"
            f"🆔 Ваш ID: <code>{uid}</code>"
        )

        # Записываем реферала, но бонусы дадим только после активации триала
        if args and args.startswith("ref"):
            try:
                referrer_id = int(args.replace("ref", ""))
                if referrer_id != uid and await db.get_user(referrer_id):
                    await db.update_referrer(uid, referrer_id)
            except ValueError:
                pass
    else:
        # СТАРЫЙ ПОЛЬЗОВАТЕЛЬ
        has_used_trial = bool(user['has_used_trial']) if 'has_used_trial' in user.keys() else True
        welcome_text = (
            f"🚀 <b>Управление VPN подпиской GTN VPN</b>\n"
            f"🆔 Ваш ID: <code>{uid}</code>"
        )

    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(welcome_text, reply_markup=get_main_menu(has_used_trial), parse_mode="HTML")


@router.callback_query(F.data == "get_trial")
async def give_trial(callback: types.CallbackQuery, db, panel, bot: Bot):
    uid = callback.from_user.id
    user = await db.get_user(uid)

    if user['has_used_trial']:
        return await callback.answer("❌ Вы уже использовали пробный период!", show_alert=True)

    await callback.answer("⏳ Активируем VPN...", show_alert=False)

    now_ms = int(time.time() * 1000)
    trial_ms = TRIAL_DAYS * 24 * 60 * 60 * 1000
    expiry_ms = now_ms + trial_ms

    import aiosqlite
    # Отмечаем триал и ставим время
    async with aiosqlite.connect(db.db_file) as dbase:
        await dbase.execute("UPDATE users SET has_used_trial = 1, expiry_ms = ?, is_active = 1 WHERE tg_id = ?",
                            (expiry_ms, uid))
        await dbase.commit()

    panel_res = await panel.add_user(INBOUND_ID, None, str(uid), expiry_ms)
    if panel_res and panel_res.get("success"):
        sub_url = panel_res.get("subscription_url", "")
        if sub_url:
            await db.set_user_keys(uid, str(uid), sub_url)

    # ЛОГИКА РЕФЕРАЛОВ (срабатывает только сейчас)
    if user['referrer_id']:
        ref_id = user['referrer_id']
        ref_user = await db.get_user(ref_id)

        current_month = datetime.now().strftime("%Y-%m")
        # Проверяем лимит
        if ref_user.get('last_ref_month') != current_month:
            new_limit = ref_user.get('ref_limit', 12) + 2 if ref_user.get('last_ref_month') else 12
            async with aiosqlite.connect(db.db_file) as dbase:
                await dbase.execute("UPDATE users SET ref_limit = ?, last_ref_month = ? WHERE tg_id = ?",
                                    (new_limit, current_month, ref_id))
                await dbase.commit()
            ref_limit = new_limit
        else:
            ref_limit = ref_user.get('ref_limit', 12)

        refs_count = ref_user.get('referrals_count', 0)

        if refs_count < ref_limit:
            refs_count = await db.add_referral_count(ref_id)
            if refs_count % 2 == 0:
                curr_exp = ref_user['expiry_ms'] if ref_user['expiry_ms'] > now_ms else now_ms
                new_exp = curr_exp + (14 * 24 * 60 * 60 * 1000)
                await db.confirm_payment(ref_id, 0, new_exp)
                await panel.extend_user(INBOUND_ID, str(ref_id), None, None, new_exp)
                try:
                    await bot.send_message(ref_id,
                                           "🎉 <b>Вы пригласили 2-х друзей!</b>\nВам начислено <b>14 дней бесплатного VPN</b>!",
                                           parse_mode="HTML")
                except Exception:
                    pass
            else:
                try:
                    await bot.send_message(ref_id,
                                           f"🎁 Друг активировал триал! (<b>{refs_count}/{ref_limit}</b> в этом месяце)\n<i>Пригласите еще 1, чтобы получить 14 дней.</i>",
                                           parse_mode="HTML")
                except Exception:
                    pass

    await callback.message.edit_text(
        "✅ <b>Триал активирован!</b>\nНажмите «📊 Статус (Подписка)», чтобы получить настройки.",
        reply_markup=get_main_menu(has_used_trial=True), parse_mode="HTML")
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
async def back_to_main(callback: types.CallbackQuery, state: FSMContext, db):  # Добавили db сюда!
    await callback.answer()
    await state.clear()
    uid = callback.from_user.id

    user = await db.get_user(uid)
    has_used_trial = bool(user['has_used_trial']) if user and 'has_used_trial' in user.keys() else True

    text = (
        f"🚀 <b>Управление VPN подпиской GTN VPN</b>\n"
        f"🆔 Ваш ID: <code>{uid}</code>"
    )
    kb = get_main_menu(has_used_trial)  # Передаем аргумент

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")




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


