import asyncio
import time
from aiogram import Bot
from database import Database


async def check_expiring_subs(bot: Bot, db: Database):
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