import asyncio
import sys
from aiogram import Bot, Dispatcher,BaseMiddleware
from config import BOT_TOKEN, DB_NAME, CHANNEL_ID
from database import Database
from api_client import PanelAPI
from handlers import user, payment, admin
from utils.notifier import auto_sync_loop  # check_expiring_subs, start_reminder_loop отключены (см. ниже)
from utils.snapshot import daily_snapshot_loop
from aiogram.types import CallbackQuery

if sys.stdout.encoding != "utf-8":
    # Локальный запуск на Windows использует кодировку консоли (cp1251) вместо
    # UTF-8, из-за чего print() с эмодзи падает с UnicodeEncodeError.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


class SubCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: CallbackQuery, data):
        bot = data.get('bot')
        user_id = event.from_user.id

        if CHANNEL_ID:
            try:
                member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
                # Если не участник и не админ
                if member.status not in ['member', 'administrator', 'creator']:
                    await event.answer("⚠️ Для использования бота подпишитесь на наш канал!", show_alert=True)
                    return  # Блокируем нажатие, дальше ничего не идет
            except Exception:
                pass  # Бот не в канале или ошибка апи
        return await handler(event, data)  # Пропускаем к родным функциям


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    db = Database(DB_NAME)
    panel = PanelAPI()

    # Передаем зависимости
    dp["db"] = db
    dp["panel"] = panel

    dp.callback_query.middleware(SubCheckMiddleware())

    dp.include_router(user.router)
    dp.include_router(payment.router)
    dp.include_router(admin.router)

    await db.create_tables()

    # asyncio.create_task(check_expiring_subs(bot, db, panel))  # отключено: все автоматические уведомления выключены
    # asyncio.create_task(start_reminder_loop(bot, db.db_file))  # отключено: все автоматические уведомления выключены
    asyncio.create_task(auto_sync_loop(db, panel))  # <--- Добавили наш часовой луп
    asyncio.create_task(daily_snapshot_loop(db.db_file))
    print("🚀 Бот GTN VPN запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())