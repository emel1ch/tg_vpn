import os
import subprocess
import logging
import time  # ✅ ИСПРАВЛЕНО: Добавлен импорт
import asyncio
from datetime import datetime
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

# Импорт настроек (убедись, что они есть в .env и config.py)
from config import ADMIN_ID, REMOTE_GDRIVE, MARZBAN_DB_PATH, BOT_DB_PATH, INBOUND_ID

router = Router()


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ---
async def resolve_target_id(identifier: str, db):
    """Определяет ID: если в цифрах - как есть, если с @ - ищет в БД"""
    if identifier.isdigit():
        return int(identifier)

    username = identifier.replace("@", "")
    user = await db.get_user_by_username(username)
    return user['tg_id'] if user else None


# --- КЛАВИАТУРА ---
def get_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Статистика юзеров", callback_data="admin_users_stat")],
        [InlineKeyboardButton(text="📊 Статус Marzban", callback_data="admin_status")],
        [InlineKeyboardButton(text="📦 Сделать Бэкап (TG + GDrive)", callback_data="admin_backup")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_refresh")]
    ])


@router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    uptime = subprocess.run(['uptime', '-p'], capture_output=True, text=True).stdout.strip()
    await message.answer(f"💻 <b>CORE_CONTROL (Marzban)</b>\nUptime: {uptime}",
                         parse_mode="HTML", reply_markup=get_admin_kb())


@router.callback_query(F.data == "admin_status")
async def handle_status(callback: types.CallbackQuery, panel):
    try:
        stats = await panel.get_system_stats()
        if not stats:
            await callback.answer("🔴 API недоступно", show_alert=True)
            return

        docker_res = subprocess.run(['docker', 'inspect', '-f', '{{.State.Status}}', 'marzban-marzban-1'],
                                    capture_output=True, text=True).stdout.strip()

        # Правильные ключи Marzban API
        mem_used = stats.get('mem_used', 0) / (1024 ** 3)
        mem_total = stats.get('mem_total', 1) / (1024 ** 3)
        cpu = stats.get('cpu_usage', 0)
        version = stats.get('xray_version') or stats.get('version', 'Unknown')

        report = (f"<b>Статус:</b> {docker_res}\n"
                  f"🖥 <b>CPU:</b> {cpu}%\n"
                  f"💾 <b>RAM:</b> {mem_used:.2f} / {mem_total:.2f} GB\n"
                  f"🌐 <b>Версия:</b> {version}")

        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=get_admin_kb())
    except Exception as e:
        await callback.answer(f"Ошибка: {e}")
    finally:
        await callback.answer()


@router.callback_query(F.data == "admin_backup")
async def handle_backup(callback: types.CallbackQuery, bot: Bot):
    await callback.answer("⏳ Запускаю двойной бэкап...")
    try:
        date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")

        # 1. Отправка в Telegram
        for path, cap in [(MARZBAN_DB_PATH, "БД Marzban"), (BOT_DB_PATH, "БД Бота")]:
            if os.path.exists(path):
                await bot.send_document(ADMIN_ID, FSInputFile(path), caption=f"📦 {cap} ({date_str})")

        # 2. Google Drive (rclone)
        if REMOTE_GDRIVE:
            subprocess.run(['rclone', 'copy', MARZBAN_DB_PATH, f"{REMOTE_GDRIVE}/background/"], check=True)
            subprocess.run(['rclone', 'copy', BOT_DB_PATH, f"{REMOTE_GDRIVE}/background/"], check=True)
            await callback.message.answer("✅ Копии также загружены на Google Drive.")

    except Exception as e:
        await callback.message.answer(f"❌ Ошибка бэкапа: {e}")
    finally:
        await callback.answer()


@router.message(Command("sendall"))
async def cmd_sendall(message: types.Message, command: CommandObject, db, bot: Bot):
    if message.from_user.id != ADMIN_ID or not command.args: return
    users = await db.get_all_users()
    await message.answer(f"🚀 Начинаю рассылку на {len(users)} чел.")
    for uid in users:
        try:
            await bot.send_message(uid, command.args, parse_mode="HTML")
            await asyncio.sleep(0.05)
        except:
            continue
    await message.answer("✅ Рассылка окончена.")


@router.message(Command("give_sub"))
async def cmd_give_sub(message: types.Message, command: CommandObject, db, panel, bot: Bot):
    if message.from_user.id != ADMIN_ID or not command.args: return
    parts = command.args.split()
    if len(parts) != 2: return

    target_id = await resolve_target_id(parts[0], db)
    if not target_id:
        await message.reply("❌ Пользователь не найден в БД бота.")
        return

    days = int(parts[1])
    add_ms = days * 86400000

    try:
        user = await db.get_user(target_id)
        now_ms = int(time.time() * 1000)  # ✅ ОШИБКА БОЛЬШЕ НЕ ПОВТОРИТСЯ
        new_expiry = max(user['expiry_ms'] or 0, now_ms) + add_ms

        # Синхронизация с Marzban
        await panel.add_user(INBOUND_ID, f"User_{target_id}", str(target_id), new_expiry)
        await db.confirm_payment(target_id, 0, new_expiry)

        await message.reply(f"✅ Выдано {days} дн. для {target_id}")
        await bot.send_message(target_id, f"🎁 Вам начислено {days} дней подписки!")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")