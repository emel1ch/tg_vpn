import asyncio
import uuid
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardRemove, BotCommand
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiosqlite
from config import BOT_TOKEN, ADMIN_ID, DB_NAME, GROUP_ID, INBOUND_ID
from database import Database
from api_client import PanelAPI

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database(DB_NAME)
panel = PanelAPI()


class SupportState(StatesGroup):
    waiting_for_msg = State()


# --- Настройки Времени ---
TRIAL_END_MS = int(datetime(2026, 5, 4, 23, 59, 59).timestamp() * 1000)
GRACE_PERIOD_MS = 3 * 24 * 60 * 60 * 1000  # 3 дня
MONTH_MS = 30 * 24 * 60 * 60 * 1000


# --- Клавиатуры (оставлены твои) ---
def get_main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Оплата", callback_data="renew"))
    builder.row(
        InlineKeyboardButton(text="📚 Инструкции", callback_data="guides"),
        InlineKeyboardButton(text="📊 Статус", callback_data="status")
    )
    builder.row(
        InlineKeyboardButton(text="📜 Транзакции", callback_data="history"),
        InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")
    )
    builder.adjust(1, 2, 2)
    return builder.as_markup()


def get_guides_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🍏 iOS/iPad/TV", url="https://teletype.in/@emel1ch/eJMUeXbv9P3"))
    builder.row(InlineKeyboardButton(text="🤖 Android", url="https://teletype.in/@emel1ch/YVYFWWL3pcJ"))
    builder.row(InlineKeyboardButton(text="💻 Windows", url="https://teletype.in/@emel1ch/1oshgSSJjal"))
    builder.row(InlineKeyboardButton(text="💻 MacOS", url="https://teletype.in/@emel1ch/I6p31Dxnwhq"))
    builder.row(InlineKeyboardButton(text="💻 Linux", url="https://teletype.in/@emel1ch/DrBPJnR4dnT"))
    builder.row(InlineKeyboardButton(text="📺 AndroidTV", url="https://teletype.in/@emel1ch/nUHewpzq5B3"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="to_main"))
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def get_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main")]])


# --- ЕЖЕДНЕВНАЯ ПРОВЕРКА ПОДПИСОК ---
async def check_subscriptions():
    print(f"🕒 [{datetime.now().strftime('%H:%M')}] Проверка подписок...")
    users = await db.get_all_active_users()
    now_ms = int(time.time() * 1000)

    for user in users:
        uid = user['tg_id']
        expiry_ms = user['expiry_ms']
        time_left = expiry_ms - now_ms

        if 0 < time_left <= 86400000:  # За 1 день до 4 мая
            try:
                await bot.send_message(uid,
                                       "⏳ <b>Твой бесплатный период заканчивается завтра!</b>\nПродли подписку, чтобы не потерять доступ.",
                                       parse_mode="HTML")
            except:
                pass

        elif time_left <= 0 and now_ms < (expiry_ms + GRACE_PERIOD_MS):  # Начались 3 дня форы
            try:
                await bot.send_message(uid,
                                       "⚠️ <b>Официально твоя подписка истекла!</b>\nНо мы дарим тебе 3 бонусных дня форы. Интернет работает, не тяни с оплатой!",
                                       parse_mode="HTML")
            except:
                pass

        elif now_ms >= (expiry_ms + GRACE_PERIOD_MS):  # Фора кончилась, панель уже сама отрубила юзера
            await db.set_user_inactive(uid)
            try:
                await bot.send_message(uid, "🚫 <b>Доступ закрыт.</b>\nТвоя подписка полностью остановлена.",
                                       parse_mode="HTML")
            except:
                pass


# --- Хендлеры
# Настройки оплаты
PAYMENT_LINK = "https://finance.ozon.ru/apps/sbp/ozonbankpay/019db3db-f12d-7107-b6ca-a55329933289"
QR_FILE_PATH = "qr.jpg"  # Название файла с QR-кодом, который лежит в папке с ботом


@dp.callback_query(F.data == "renew")
async def renew_callback(callback: CallbackQuery):
    # 1. Собираем клавиатуру со статичной ссылкой
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Оплатить по ссылке (200₽)", url=PAYMENT_LINK)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main")]
    ])

    # 2. Отправляем заранее заготовленное фото QR-кода
    photo = FSInputFile(QR_FILE_PATH)

    await callback.message.answer_photo(
        photo=photo,
        caption=(
            "💳 **Оплата подписки (200₽/мес)**\n\n"
            "1️⃣ Отсканируй QR-код или перейди по ссылке ниже.\n"
            "2️⃣ Переведи ровно 200₽.\n"
            "3️⃣ **Обязательно отправь сюда фото чека!** 📸\n\n"
            "⏳ *После проверки чека администратором, бот автоматически выдаст тебе ключ.*"
        ),
        reply_markup=kb,
        parse_mode="Markdown"
    )

    # 3. Удаляем предыдущее текстовое меню, оставляем только красивую картинку с кнопками
    await callback.message.delete()
    await callback.answer()


@dp.message(Command("start", "menu"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id

    user = await db.get_user(uid)
    now_ms = int(time.time() * 1000)

    # === ЛОГИКА ДЛЯ НОВЫХ ПОЛЬЗОВАТЕЛЕЙ ===
    if not user:
        # 1. Если сейчас ДО 4 мая -> Выдаем триал
        if now_ms < TRIAL_END_MS:
            tmp_msg = await message.answer("🔄 Генерация акционного ключа...")
            user_uuid = str(uuid.uuid4())
            user_email = f"ID: {uid}"

            panel_expiry = TRIAL_END_MS + GRACE_PERIOD_MS
            res = await panel.add_user(INBOUND_ID, user_email, user_uuid, panel_expiry)

            if res and res.get("success"):
                await db.add_user(uid, message.from_user.username, message.from_user.full_name, TRIAL_END_MS,
                                  is_active=1)
                await db.set_user_keys(uid, user_uuid, res["sub_id"])
                await tmp_msg.delete()

                link = f"https://gtnforever.space:2096/sub/private-access-99/{res['sub_id']}"
                await message.answer(
                    f"🎉 **Твой VPN готов!**\nДоступ открыт бесплатно до 4 мая.\n\n"
                    f"🔗 **Ссылка (Happ):**\n`{link}`\n\n"
                    f"🆔 Ваш ID: `{uid}`",
                    reply_markup=get_main_menu(), parse_mode="Markdown"
                )
            else:
                await tmp_msg.edit_text("❌ Ошибка генерации. Напиши в поддержку.")
            return

        # 2. Если сейчас ПОСЛЕ 4 мая -> Просто регистрируем в БД (без выдачи ключа)
        else:
            await db.add_user(uid, message.from_user.username, message.from_user.full_name, expiry_ms=0, is_active=0)
            user = await db.get_user(uid)

    # === ЛОГИКА ДЛЯ УЖЕ СУЩЕСТВУЮЩИХ ПОЛЬЗОВАТЕЛЕЙ ===
    user = await db.get_user(uid)  # Подтягиваем свежие данные

    # Если у юзера уже сгенерирован ключ (триал или оплачено)
    if user and user['uuid']:
        text = f"Управление VPN подпиской gtn vpn 🚀\n\n🆔 Ваш ID: `{uid}`"
        await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")

    # Если ключа нет (зашел после 4 мая и еще не платил)
    else:
        text = f"Добро пожаловать в **gtn vpn**! 🚀\n\nДля получения доступа к приватному VPN необходимо оплатить подписку.\nЖми кнопку «💳 Оплата» ниже.\n\n🆔 Ваш ID: `{uid}`"
        await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")
@dp.callback_query(F.data == "to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = f"Управление VPN подпиской gtn vpn 🚀\n\n🆔 Ваш ID: `{callback.from_user.id}`"
    await callback.message.edit_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data == "guides")
async def guides_menu(callback: CallbackQuery):
    await callback.message.edit_text("📖 **Инструкции (Happ)**\n\nВыбери устройство ниже:", reply_markup=get_guides_kb(),
                                     parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data == "status")
async def status_callback(callback: types.CallbackQuery):
    uid = callback.from_user.id
    user = await db.get_user(uid)

    if not user:
        await callback.message.answer("❌ Вас нет в базе. Нажмите /start")
        await callback.answer()
        return

    now_ms = int(time.time() * 1000)
    expiry = user['expiry_ms']

    # Считаем остаток дней
    if expiry > now_ms:
        days_left = (expiry - now_ms) // (24 * 3600 * 1000)
        status_text = f"🟢 **Активен** (осталось дней: {days_left})"
    else:
        status_text = "🔴 **Отключен** (подписка закончилась)"

    # Конвертируем дату для красоты
    expiry_date = datetime.fromtimestamp(expiry / 1000).strftime('%d.%m.%Y %H:%M') if expiry > 0 else "Нет данных"

    # Формируем базовый текст
    text = (
        f"📊 **Твоя статистика:**\n\n"
        f"👤 ID: `{uid}`\n"
        f"⚡ Статус: {status_text}\n"
        f"📅 Действует до: {expiry_date}\n"
    )

    # ЕСЛИ У ЮЗЕРА ЕСТЬ КЛЮЧ И ОН АКТИВЕН — ДОБАВЛЯЕМ ССЫЛКУ В СТАТУС
    if user['sub_id'] and expiry > now_ms:
        link = f"https://gtnforever.space:2096/sub/private-access-99/{user['sub_id']}"
        text += f"\n🔗 **Твоя ссылка для подключения:**\n`{link}`\n*(Нажми на ссылку, чтобы скопировать)*"

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_menu())
    await callback.answer()


@dp.callback_query(F.data == "history")
async def history_callback(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    trans = await db.get_transactions(callback.from_user.id)

    text = f"📜 **История транзакций:**\n\nОбщая сумма: {user['total_paid'] if user else 0}₽\n\n"
    if trans:
        text += "**Последние операции:**\n"
        for i, t in enumerate(trans, 1): text += f"{i}. {t['pay_date']} — `+{t['amount']}₽`\n"
    else:
        text += "*Операций пока нет.*"
    await callback.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data == "support")
async def support_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SupportState.waiting_for_msg)
    await callback.message.edit_text("Напиши свой вопрос ниже — я перешлю его админу.", reply_markup=get_back_kb())
    await callback.answer()


@dp.message(SupportState.waiting_for_msg)
async def handle_support(message: types.Message, state: FSMContext):
    user_mention = f"[{message.from_user.full_name}](tg://user?id={message.from_user.id})"
    await bot.send_message(ADMIN_ID,
                           f"📩 **Вопрос в техподдержку!**\nОт: {user_mention}\nID: `{message.from_user.id}`\n\n{message.text}",
                           parse_mode="Markdown")
    await message.answer("✅ Сообщение отправлено! Админ ответит в ближайшее время.", reply_markup=get_main_menu())
    await state.clear()


@dp.message(F.photo)
async def handle_photo(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Одобрить", callback_data=f"pay_yes:{message.from_user.id}")
        builder.button(text="❌ Отказать", callback_data=f"pay_no:{message.from_user.id}")
        user_mention = f"[{message.from_user.full_name}](tg://user?id={message.from_user.id})"
        await bot.send_photo(GROUP_ID, message.photo[-1].file_id,
                             caption=f"💰 **Новый чек!**\nОтправитель: {user_mention}\nID: `{message.from_user.id}`",
                             reply_markup=builder.as_markup(), parse_mode="Markdown")
        await message.answer("Чек на проверке! ✅")


@dp.callback_query(F.data.startswith("pay_"))
async def pay_confirm(callback: CallbackQuery):
    action, uid = callback.data.split(":")
    uid = int(uid)
    user_mention = f"[ID: {uid}](tg://user?id={uid})"

    if action == "pay_yes":
        user = await db.get_user(uid)
        now_ms = int(time.time() * 1000)

        # 1. ЕСЛИ КЛЮЧА ЕЩЕ НЕТ (НОВАЯ ОПЛАТА)
        if not user['uuid']:
            user_uuid = str(uuid.uuid4())
            user_email = f"ID: {uid}"
            new_db_expiry = now_ms + MONTH_MS
            new_panel_expiry = new_db_expiry + GRACE_PERIOD_MS

            res = await panel.add_user(INBOUND_ID, user_email, user_uuid, new_panel_expiry)

            if res and res.get("success"):
                await db.set_user_keys(uid, user_uuid, res["sub_id"])
                await db.confirm_payment(uid, 200, new_db_expiry)
                link = f"https://gtnforever.space:2096/sub/private-access-99/{res['sub_id']}"

                await bot.send_message(uid, f"🎉 **Оплата успешна! Твой VPN создан на 30 дней.**\n\n🔗 Твоя ссылка:\n`{link}`\n\nДля настройки используй кнопку «📚 Инструкции» в меню.", parse_mode="Markdown")
                await callback.message.edit_caption(caption=f"✅ Подписка СОЗДАНА для {user_mention}", parse_mode="Markdown")
            else:
                await callback.message.edit_caption(caption=f"❌ Ошибка API (Создание) для {user_mention}", parse_mode="Markdown")

        # 2. ЕСЛИ КЛЮЧ УЖЕ ЕСТЬ (ПРОДЛЕНИЕ)
        else:
            current_expiry = user['expiry_ms']
            new_db_expiry = now_ms + MONTH_MS if current_expiry < now_ms else current_expiry + MONTH_MS
            new_panel_expiry = new_db_expiry + GRACE_PERIOD_MS

            u_email = f"ID: {uid}"
            res = await panel.extend_user(INBOUND_ID, user['uuid'], u_email, user['sub_id'], new_panel_expiry)

            if res and res.get("success"):
                await db.confirm_payment(uid, 200, new_db_expiry)
                link = f"https://gtnforever.space:2096/sub/private-access-99/{user['sub_id']}"
                await bot.send_message(uid, f"✅ **Оплата принята! Продлено на 30 дней.**\n\n🔗 Твоя ссылка:\n`{link}`\n\nОбнови подписку в Happ.", parse_mode="Markdown")
                await callback.message.edit_caption(caption=f"✅ Подписка ПРОДЛЕНА для {user_mention}", parse_mode="Markdown")
            else:
                await callback.message.edit_caption(caption=f"❌ Ошибка API (Продление) для {user_mention}", parse_mode="Markdown")
    else:
        await bot.send_message(uid, "❌ Оплата отклонена.")
        await callback.message.edit_caption(caption=f"❌ Отказано для {user_mention}", parse_mode="Markdown")
    await callback.answer()


@dp.message(Command("give"))
async def manual_give_access(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return

    if not command.args or len(command.args.split()) != 2:
        await message.answer("Использование: `/give <ID или @username> <кол-во дней>`\nПример: `/give 123456789 60`", parse_mode="Markdown")
        return

    target, days_str = command.args.split()
    days_to_add_ms = int(days_str) * 24 * 60 * 60 * 1000

    if target.isdigit():
        uid = int(target)
    else:
        uid = await db.get_tg_id_by_username(target)
        if not uid:
            await message.answer("❌ Пользователь не найден.", parse_mode="Markdown")
            return

    user = await db.get_user(uid)
    if not user:
        await message.answer("❌ Юзер еще не нажимал /start")
        return

    now_ms = int(time.time() * 1000)

    # 1. ЕСЛИ КЛЮЧА ЕЩЕ НЕТ
    if not user['uuid']:
        user_uuid = str(uuid.uuid4())
        user_email = f"ID: {uid}"
        new_db_expiry = now_ms + days_to_add_ms
        new_panel_expiry = new_db_expiry + GRACE_PERIOD_MS

        res = await panel.add_user(INBOUND_ID, user_email, user_uuid, new_panel_expiry)

        if res and res.get("success"):
            await db.set_user_keys(uid, user_uuid, res["sub_id"])
            async with aiosqlite.connect(db.db_file) as d_conn:
                await d_conn.execute("UPDATE users SET expiry_ms = ?, is_active = 1 WHERE tg_id = ?", (new_db_expiry, uid))
                await d_conn.commit()

            link = f"https://gtnforever.space:2096/sub/private-access-99/{res['sub_id']}"
            await message.answer(f"✅ Успех! Создан ключ для `{uid}` на {days_str} дней.", parse_mode="Markdown")
            try:
                await bot.send_message(uid, f"🎁 Администратор выдал тебе доступ на {days_str} дней!\n\n🔗 **Твоя ссылка:**\n`{link}`", parse_mode="Markdown")
            except: pass
        else:
            await message.answer("❌ Ошибка API панели при создании ключа.")

    # 2. ЕСЛИ КЛЮЧ УЖЕ ЕСТЬ
    else:
        new_db_expiry = now_ms + days_to_add_ms if user['expiry_ms'] < now_ms else user['expiry_ms'] + days_to_add_ms
        new_panel_expiry = new_db_expiry + GRACE_PERIOD_MS

        res = await panel.extend_user(INBOUND_ID, user['uuid'], f"ID: {uid}", user['sub_id'], new_panel_expiry)

        if res and res.get("success"):
            async with aiosqlite.connect(db.db_file) as d_conn:
                await d_conn.execute("UPDATE users SET expiry_ms = ?, is_active = 1 WHERE tg_id = ?", (new_db_expiry, uid))
                await d_conn.commit()

            link = f"https://gtnforever.space:2096/sub/private-access-99/{user['sub_id']}"
            await message.answer(f"✅ Успех! Юзеру `{uid}` добавлено {days_str} дней.", parse_mode="Markdown")
            try:
                await bot.send_message(uid, f"🎁 Администратор продлил твою подписку на {days_str} дней!\n\n🔗 **Твоя ссылка:**\n`{link}`", parse_mode="Markdown")
            except: pass
        else:
            await message.answer("❌ Ошибка API при ручном продлении.")


@dp.message(Command("db"))
async def send_db_backup(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        db_file = FSInputFile(DB_NAME)
        await message.answer_document(
            document=db_file,
            caption=f"📦 **Бэкап базы данных**\nДата: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@dp.message(Command("sendall"))
async def mass_send(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return
    if not command.args:
        await message.answer("Использование: `/sendall <текст сообщения>`", parse_mode="Markdown")
        return

    users = await db.get_all_active_users()
    count = 0
    for u in users:
        try:
            await bot.send_message(u['tg_id'], command.args)
            count += 1
            await asyncio.sleep(0.05)
        except:
            pass

    await message.answer(f"✅ Рассылка завершена!\nДоставлено: {count} пользователям.")


# --- ЖИЗНЕННЫЙ ЦИКЛ БОТА ---
async def on_startup():
    await db.create_tables()
    print("✅ База данных подключена.")


async def on_shutdown():
    await panel.close()
    print("❌ Соединения закрыты.")


async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await bot.set_my_commands([
        BotCommand(command="start", description="🚀 Запустить бота"),
        BotCommand(command="menu", description="🏠 Главное меню")
    ])

    # Планировщик проверяет подписки 1 раз в день в 12:00
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(check_subscriptions, 'cron', hour=12, minute=0, id='check_subs', replace_existing=True)
    scheduler.start()

    print("🚀 Бот aura VPN запущен на aiosqlite!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())