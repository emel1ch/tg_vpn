import asyncio
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, DB_NAME
from database import Database
from api_client import PanelAPI
from handlers import user, payment, admin

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    db = Database(DB_NAME)
    panel = PanelAPI()

    # Передаем зависимости
    dp["db"] = db
    dp["panel"] = panel

    dp.include_router(user.router)
    dp.include_router(payment.router)
    dp.include_router(admin.router)

    await db.create_tables()
    print("🚀 Бот Aura VPN запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())