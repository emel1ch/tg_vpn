import time
import re
import os
import subprocess
import logging
from datetime import datetime
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import MONTH_MS, INBOUND_ID, GROUP_ID, ADMIN_ID, REMOTE_GDRIVE, MARZBAN_DB_PATH, MARZBAN_ENV_PATH

router = Router()


# ==========================================
# 1. АДМИН-ПАНЕЛЬ (CORE CONTROL)
# ==========================================
def get_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Статистика юзеров", callback_data="admin_users_stat")],
        [InlineKeyboardButton(text="📊 Статус Marzban", callback_data="admin_status")],
        [InlineKeyboardButton(text="📦 Сделать Бэкап БД", callback_data="admin_backup")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_refresh")]
    ])


@router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    uptime = subprocess.run(['uptime', '-p'], capture_output=True, text=True).stdout.strip()
    await message.answer(f"💻 <b>CORE_CONTROL (Marzban)</b>\nUptime: {uptime}\n<i>Выберите действие:</i>",
                         parse_mode="HTML", reply_markup=get_admin_kb())


@router.callback_query(F.data == "admin_refresh")
async def handle_refresh(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    uptime = subprocess.run(['uptime', '-p'], capture_output=True, text=True).stdout.strip()
    await callback.message.edit_text(f"💻 <b>CORE_CONTROL (Marzban)</b>\nUptime: {uptime}\n<i>Обновлено.</i>",
                                     parse_mode="HTML", reply_markup=get_admin_kb())


@router.callback_query(F.data == "admin_status")
async def handle_status(callback: types.CallbackQuery, panel):
    if callback.from_user.id != ADMIN_ID: return

    # Пингуем системный API Marzban
    stats = await panel.get_system_stats()

    if not stats:
        await callback.answer("🔴 Ошибка связи с панелью Marzban", show_alert=True)
        return

    # Проверяем статус докер-контейнера Marzban (опционально)
    docker_status = subprocess.run(['docker', 'inspect', '-f', '{{.State.Status}}', 'marzban-marzban-1'],
                                   capture_output=True, text=True).stdout.strip()
    status_emoji = "🟢" if docker_status == "running" else "🟡"

    mem_usage = stats.get('memory_used', 0) / (1024 ** 3)
    mem_total = stats.get('memory_total', 1) / (1024 ** 3)

    report = (f"{status_emoji} <b>Статус Контейнера:</b> {docker_status}\n"
              f"🖥 <b>CPU:</b> {stats.get('cpu_percent', 0)}%\n"
              f"💾 <b>RAM:</b> {mem_usage:.2f} GB / {mem_total:.2f} GB\n"
              f"🌐 <b>Xray Версия:</b> {stats.get('xray_version', 'Unknown')}")

    await callback.answer()
    await callback.message.edit_text(report, parse_mode="HTML", reply_markup=get_admin_kb())


@router.callback_query(F.data == "admin_users_stat")
async def handle_users_stat(callback: types.CallbackQuery, panel):
    if callback.from_user.id != ADMIN_ID: return
    await callback.message.edit_text("🔍 <b>Анализирую API Marzban...</b>", parse_mode="HTML")

    users = await panel.get_all_users()
    if not users:
        await callback.message.edit_text("❌ Ошибка получения пользователей.", reply_markup=get_admin_kb())
        return

    active_count = sum(1 for u in users if u.get('status') == 'active')
    total_traffic = sum(u.get('used_traffic', 0) for u in users) / (1024 ** 3)  # в ГБ

    report = f"👥 <b>Пользователи Marzban:</b>\n"
    report += f"Всего юзеров: {len(users)}\n"
    report += f"Активных (Status active): {active_count}\n"
    report += f"Суммарный трафик: {total_traffic:.2f} GB\n\n"

    # Выводим топ-5 по трафику (чтобы не спамить огромным сообщением)
    top_users = sorted(users, key=lambda x: x.get('used_traffic', 0), reverse=True)[:5]
    report += "🏆 <b>Топ-5 по трафику:</b>\n"
    for u in top_users:
        u_traffic = u.get('used_traffic', 0) / (1024 ** 3)
        report += f"👤 <code>{u.get('username')}</code>: {u_traffic:.2f} GB\n"

    await callback.message.edit_text(report, parse_mode="HTML", reply_markup=get_admin_kb())


@router.callback_query(F.data == "admin_backup")
async def handle_backup(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    await callback.message.edit_text("🔄 <b>Синхронизация баз Marzban с G-Drive...</b>", parse_mode="HTML")

    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    temp_dir = "/tmp/marzban_backup"
    os.makedirs(temp_dir, exist_ok=True)
    status = []

    tasks = [(MARZBAN_DB_PATH, f"background/marzban_{date_str}.sqlite"),
             (MARZBAN_ENV_PATH, f"background/env_{date_str}.txt")]

    for src, dest in tasks:
        if os.path.exists(src):
            try:
                tmp_file = os.path.join(temp_dir, os.path.basename(src))
                subprocess.run(['cp', src, tmp_file])
                subprocess.run(['rclone', 'copyto', tmp_file, f"{REMOTE_GDRIVE}/{dest}"], check=True)
                status.append("✅")
            except Exception as e:
                logging.error(f"Ошибка бэкапа {src}: {e}")
                status.append("❌")
        else:
            status.append("⚪️ (не найден)")

    subprocess.run(['rm', '-rf', temp_dir])

    report = f"📦 <b>Бэкап Marzban завершен:</b>\nБаза данных: {status[0]}\nФайл .env: {status[1]}"
    await callback.message.edit_text(report, parse_mode="HTML", reply_markup=get_admin_kb())


# ==========================================
# 2. BAN / UNBAN IP (Iptables)
# ==========================================
@router.message(Command("ban"))
async def cmd_ban(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return
    ip = command.args
    if not ip:
        await message.reply("⚠️ Укажите IP-адрес.\nПример: <code>/ban 1.2.3.4</code>", parse_mode="HTML")
        return
    try:
        subprocess.run(['iptables', '-A', 'INPUT', '-s', ip.strip(), '-j', 'DROP'], check=True)
        await message.reply(f"🚫 <b>Доступ закрыт!</b>\nIP <code>{ip}</code> заблокирован на уровне ядра.",
                            parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Ошибка выполнения: {e}")


@router.message(Command("unban"))
async def cmd_unban(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return
    ip = command.args
    if not ip:
        await message.reply("⚠️ Укажите IP-адрес.\nПример: <code>/unban 1.2.3.4</code>", parse_mode="HTML")
        return
    try:
        subprocess.run(['iptables', '-D', 'INPUT', '-s', ip.strip(), '-j', 'DROP'], check=True)
        await message.reply(f"🕊 <b>Амнистия!</b>\nБлокировка с IP <code>{ip}</code> снята.", parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Ошибка (возможно, этот IP не был в бане): {e}")


# ==========================================
# 3. МЕХАНИКА ОДОБРЕНИЯ ОПЛАТЫ (Из старого файла)
# ==========================================
@router.callback_query(F.data.startswith("pay_"))
async def process_admin_pay(callback: types.CallbackQuery, db, panel, bot: Bot):
    action, uid = callback.data.split(":")
    uid = int(uid)

    if action == "pay_yes":
        user = await db.get_user(uid)
        now_ms = int(time.time() * 1000)
        current_expiry = user['expiry_ms'] if user and user['expiry_ms'] else 0
        new_expiry = max(current_expiry, now_ms) + MONTH_MS

        marzban_res = await panel.extend_user(INBOUND_ID, str(uid), f"User_{uid}", None, new_expiry)
        if not marzban_res.get("success"):
            await panel.add_user(INBOUND_ID, f"User_{uid}", str(uid), new_expiry)

        await db.confirm_payment(uid, 200, new_expiry)
        await bot.send_message(uid,
                               "✅ Ваша оплата принята! Подписка активирована/продлена.\n\nПроверьте статус кнопкой в меню.")
        await callback.message.edit_caption(caption=f"✅ ОДОБРЕНО для ID: {uid}")

    elif action == "pay_no":
        await bot.send_message(uid, "❌ Ваша оплата была отклонена администратором.")
        await callback.message.edit_caption(caption=f"❌ ОТКЛОНЕНО для ID: {uid}")
    await callback.answer()


# ==========================================
# 4. ОТВЕТ НА ПОДДЕРЖКУ ИЗ БЕСЕДЫ
# ==========================================
@router.message(F.chat.id == GROUP_ID, F.reply_to_message)
async def admin_reply_to_user(message: types.Message, bot: Bot):
    reply_to = message.reply_to_message
    source_text = reply_to.text or reply_to.caption
    if not source_text: return

    match = re.search(r"ID: `(\d+)`", source_text)
    if not match: return
    user_id = int(match.group(1))

    try:
        await message.copy_to(user_id)
        await message.reply("✅ Ответ доставлен пользователю.")
    except Exception as e:
        await message.reply(f"❌ Ошибка отправки: {e}")