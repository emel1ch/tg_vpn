import asyncio
import time
from aiogram import Bot
from database import Database, get_db_connection
import aiosqlite


async def check_expiring_subs(bot: Bot, db: Database,panel):
    """
    Фоновая задача, которая проверяет сроки подписок.
    Рекомендуется запускать раз в час.
    """
    while True:
        try:
            # Получаем всех активных пользователей
            users = await db.get_all_active_users()
            now_ms = int(time.time() * 1000)

            # В миллисекундах
            ONE_DAY = 24 * 60 * 60 * 1000

            for user in users:
                tg_id = user['tg_id']
                expiry_ms = user['expiry_ms']

                # Если подписка уже истекла, помечаем юзера как неактивного
                if expiry_ms > 0 and expiry_ms < now_ms:

                    # --- 🛡 ЗАЩИТА ОТ РАССИНХРОНА ---
                    # Спрашиваем у Marzban: а точно ли истекла?
                    marzban_user = await panel.get_user(str(tg_id))

                    if marzban_user and marzban_user.get('expire'):
                        marzban_expiry_ms = marzban_user['expire'] * 1000

                        # Если в панели время еще есть (лечим базу и пропускаем отключение)
                        if marzban_expiry_ms > now_ms:
                            await db.confirm_payment(tg_id, 0, marzban_expiry_ms)
                            continue  # Юзер спасен, идем к следующему
                    # --------------------------------

                    # Если и в панели пусто/истекло, тогда честно отключаем
                    await db.set_user_inactive(tg_id)
                    try:
                        await bot.send_message(
                            tg_id,
                            "🔴 <b>Ваша подписка на VPN закончилась!</b>\n"
                            "Интернет отключен. Чтобы снова пользоваться свободным интернетом, продлите подписку в меню.",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
                    continue  # Переходим к следующему юзеру

                # Сколько времени осталось (в миллисекундах)
                time_left_ms = expiry_ms - now_ms

                # Ловим промежутки для уведомлений
                # Чтобы не спамить, мы отправляем уведомление только если остаток попал
                # в "окно" (например, от 71 до 72 часов = 3 дня)
                # Поскольку цикл крутится раз в час, мы берем окно в 1.5 часа (1.5 * 3600 * 1000 = 5400000 мс)

                WINDOW = 5400000  # 1.5 часа

                days_left = None

                # Проверка за 3 дня
                if (3 * ONE_DAY) <= time_left_ms < (3 * ONE_DAY + WINDOW):
                    days_left = 3
                # Проверка за 2 дня
                elif (2 * ONE_DAY) <= time_left_ms < (2 * ONE_DAY + WINDOW):
                    days_left = 2
                # Проверка за 1 день (24 часа)
                elif (1 * ONE_DAY) <= time_left_ms < (1 * ONE_DAY + WINDOW):
                    days_left = 1

                # Если пора отправлять уведомление
                if days_left is not None:
                    try:
                        await bot.send_message(
                            tg_id,
                            f"⚠️ <b>Внимание!</b>\nВаша подписка на VPN истекает через <b>{days_left} дн.</b>!\n"
                            f"Не забудьте продлить её заранее, чтобы не остаться без связи.\n\n"
                            f"👉 Для продления нажмите «💳 Оплата» в /menu",
                            parse_mode="HTML"
                        )
                    except Exception:
                        # Юзер заблокировал бота
                        pass

                await asyncio.sleep(0.05)  # Защита от лимитов телеграма

        except Exception as e:
            print(f"[NOTIFIER ERROR] Ошибка в цикле уведомлений: {e}")

        # Засыпаем на 1 час (3600 секунд) перед следующей проверкой
        await asyncio.sleep(3600)


# Тайминги в миллисекундах (Абсолютное время от события: регистрация или конец подписки)
STAGES_MS = {
    0: 1 * 3600 * 1000,  # 1 час
    1: (1 + 6) * 3600 * 1000,  # 7 часов (+6 от пред.)
    2: (7 + 12) * 3600 * 1000,  # 19 часов (+12 от пред.)
    3: (19 + 24) * 3600 * 1000,  # 43 часа (+24 от пред.)
    4: (43 + 72) * 3600 * 1000  # 115 часов (+72 от пред.)
}

# Тексты для тех, кто НЕ ВЗЯЛ ТРИАЛ
TRIAL_TEXTS = [
    "👋 Привет! Вы зарегистрировались час назад, но так и не забрали свой бесплатный VPN на 3 дня!\nЖмите /start и забирайте подарок 🎁",
    "⏳ Прошло уже 6 часов! Ваш бесплатный триал все еще ждет вас.\nНе упускайте шанс попробовать наш VPN бесплатно 🚀",
    "🌐 Свободный интернет ждет!\nАктивируйте 3 дня бесплатного доступа прямо сейчас в главном меню /start",
    "📆 Сутки прошли, а вы еще не с нами. Попробуйте бесплатно, отменить можно в любой момент! 🛡",
    "😢 Это наше последнее напоминание...\nВаш 3-дневный триал все еще доступен, забегайте, если передумаете! /start"
]

# Тексты для тех, у кого КОНЧИЛАСЬ ПОДПИСКА
LAPSED_TEXTS = [
    "⚠️ Ваша подписка закончилась час назад!\nПродлите её прямо сейчас в меню /start, чтобы оставаться на связи 🔄",
    "Уже 6 часов без VPN... Возвращайтесь, мы скучаем!\nОплатить подписку можно в главном меню 💳",
    "🛡 Оставайтесь в безопасности! Продлите подписку и верните доступ к свободному интернету без ограничений.",
    "🚀 Сутки без подписки. Не забывайте, что с нами быстрее и безопаснее! Ждем вас обратно.",
    "💔 Прошло 3 дня с момента окончания подписки. Если захотите вернуться – мы всегда тут! /start"
]


async def start_reminder_loop(bot: Bot, db_path: str):
    """Фоновая задача для рассылки дожимов"""
    while True:
        now_ms = int(time.time() * 1000)

        async with get_db_connection(db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. ВОРОНКА ТРИАЛА (has_used_trial = 0)
            async with db.execute(
                    "SELECT tg_id, reg_time_ms, reminder_stage FROM users WHERE has_used_trial = 0") as cursor:
                async for row in cursor:
                    stage = row['reminder_stage']
                    if stage > 4:
                        continue  # Воронка пройдена полностью

                    target_time = row['reg_time_ms'] + STAGES_MS[stage]
                    if now_ms >= target_time:
                        try:
                            await bot.send_message(row['tg_id'], TRIAL_TEXTS[stage])
                        except Exception:
                            pass  # Заблокировал бота
                        # Переводим на следующую стадию даже если заблокировал (чтобы не спамить ошибки)
                        await db.execute("UPDATE users SET reminder_stage = ? WHERE tg_id = ?",
                                         (stage + 1, row['tg_id']))
                        await db.commit()

            # 2. ВОРОНКА ОТВАЛА (expiry_ms < now AND has_used_trial = 1)
            # Ищем тех, кто брал триал/покупал, но подписка истекла
            async with db.execute(
                    "SELECT tg_id, expiry_ms, lapsed_reminder_stage FROM users WHERE has_used_trial = 1 AND expiry_ms > 0 AND expiry_ms < ?",
                    (now_ms,)) as cursor:
                async for row in cursor:
                    stage = row['lapsed_reminder_stage']
                    if stage > 4:
                        continue

                    target_time = row['expiry_ms'] + STAGES_MS[stage]
                    if now_ms >= target_time:
                        try:
                            await bot.send_message(row['tg_id'], LAPSED_TEXTS[stage])
                        except Exception:
                            pass
                        await db.execute("UPDATE users SET lapsed_reminder_stage = ? WHERE tg_id = ?",
                                         (stage + 1, row['tg_id']))
                        await db.commit()

        # Пауза перед следующей проверкой (каждые 10 минут)
        await asyncio.sleep(600)


async def auto_sync_loop(db, panel):
    """Бесконечный цикл, который обновляет базу каждый час"""
    while True:
        try:
            marzban_data = await panel.get_all_users()
            if marzban_data and 'users' in marzban_data:
                for m_user in marzban_data['users']:
                    if (m_user.get('username') or '').isdigit():
                        tg_id = int(m_user.get('username'))
                        expiry_ms = m_user.get('expire', 0) * 1000
                        is_active = 1 if m_user.get('status') == 'active' else 0
                        sub_url = m_user.get('subscription_url', '')

                        local_user = await db.get_user(tg_id)
                        if local_user:
                            await db.update_sync_data(tg_id, expiry_ms, is_active, sub_url)
        except Exception as e:
            print(f"Ошибка авто-синхронизации: {e}")

        await asyncio.sleep(3600)  # Спим ровно 1 час (3600 секунд)