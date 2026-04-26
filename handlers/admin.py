import os
import subprocess
import logging
from datetime import datetime
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
import asyncio
# Импортируем твои настройки
from config import ADMIN_ID, REMOTE_GDRIVE, MARZBAN_DB_PATH, BOT_DB_PATH

router = Router()


# ==========================================
# 1. АДМИН-ПАНЕЛЬ (CORE CONTROL)
# ==========================================
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
    await message.answer(f"💻 <b>CORE_CONTROL (Marzban)</b>\nUptime: {uptime}\n<i>Выберите действие:</i>",
                         parse_mode="HTML", reply_markup=get_admin_kb())


@router.callback_query(F.data == "admin_refresh")
async def handle_refresh(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    uptime = subprocess.run(['uptime', '-p'], capture_output=True, text=True).stdout.strip()
    try:
        await callback.message.edit_text(f"💻 <b>CORE_CONTROL (Marzban)</b>\nUptime: {uptime}\n<i>Обновлено.</i>",
                                         parse_mode="HTML", reply_markup=get_admin_kb())
    except Exception:
        pass  # Игнорим, если текст не изменился
    finally:
        await callback.answer("Обновлено")


@router.callback_query(F.data == "admin_status")
async def handle_status(callback: types.CallbackQuery, panel):
    if callback.from_user.id != ADMIN_ID: return
    try:
        stats = await panel.get_system_stats()
        if not stats:
            await callback.answer("🔴 Ошибка: API Marzban недоступно", show_alert=True)
            return

        docker_status = "Unknown"
        try:
            docker_status = subprocess.run(['docker', 'inspect', '-f', '{{.State.Status}}', 'marzban-marzban-1'],
                                           capture_output=True, text=True).stdout.strip()
        except Exception:
            pass

        status_emoji = "🟢" if docker_status == "running" else "🟡"

        # --- ИСПРАВЛЕННЫЕ КЛЮЧИ API MARZBAN ---
        mem_used = stats.get('mem_used', 0) / (1024 ** 3)
        mem_total = stats.get('mem_total', 1) / (1024 ** 3)
        cpu = stats.get('cpu_usage', 0)
        version = stats.get('xray_version') or stats.get('version', 'Unknown')

        report = (f"{status_emoji} <b>Статус Контейнера:</b> {docker_status}\n"
                  f"🖥 <b>CPU:</b> {cpu}%\n"
                  f"💾 <b>RAM:</b> {mem_used:.2f} GB / {mem_total:.2f} GB\n"
                  f"🌐 <b>Версия:</b> {version}")

        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=get_admin_kb())
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка кода статуса: {e}")
    finally:
        await callback.answer()


@router.callback_query(F.data == "admin_users_stat")
async def handle_users_stat(callback: types.CallbackQuery, panel):
    if callback.from_user.id != ADMIN_ID: return
    try:
        users = await panel.get_all_users()
        if users is None:
            await callback.answer("❌ Ошибка получения юзеров (API).", show_alert=True)
            return

        # Marzban может отдавать list или dict {"users": [...]}
        users_list = users.get('users', []) if isinstance(users, dict) else users

        if not isinstance(users_list, list):
            await callback.answer("❌ Неверный формат данных от API.", show_alert=True)
            return

        active_count = sum(1 for u in users_list if u.get('status') == 'active')
        total_traffic = sum(u.get('used_traffic', 0) for u in users_list) / (1024 ** 3)

        report = f"👥 <b>Пользователи Marzban:</b>\n"
        report += f"Всего юзеров: {len(users_list)}\n"
        report += f"Активных: {active_count}\n"
        report += f"Суммарный трафик: {total_traffic:.2f} GB\n\n"

        top_users = sorted(users_list, key=lambda x: x.get('used_traffic', 0), reverse=True)[:5]
        report += "🏆 <b>Топ-5 по трафику:</b>\n"
        for u in top_users:
            u_traffic = u.get('used_traffic', 0) / (1024 ** 3)
            report += f"👤 <code>{u.get('username')}</code>: {u_traffic:.2f} GB\n"

        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=get_admin_kb())
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка вывода юзеров: {e}")
    finally:
        await callback.answer()


@router.callback_query(F.data == "admin_backup")
async def handle_backup(callback: types.CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID: return
    await callback.answer("⏳ Собираю базы данных, ожидай...", show_alert=False)

    try:
        date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
        temp_dir = "/tmp/vpn_backup"
        os.makedirs(temp_dir, exist_ok=True)

        status_tg = []
        status_drive = []

        # Базы для бэкапа
        tasks = [
            (MARZBAN_DB_PATH, f"marzban_{date_str}.sqlite", "📦 База данных Marzban"),
            (BOT_DB_PATH, f"vpn_service_{date_str}.db", "🤖 База данных Telegram-бота")
        ]

        for src, dest_name, caption in tasks:
            if os.path.exists(src):
                # 1. Отправка в Telegram
                try:
                    await bot.send_document(chat_id=ADMIN_ID, document=FSInputFile(src), caption=caption)
                    status_tg.append("✅")
                except Exception as e:
                    logging.error(f"TG Backup Error {src}: {e}")
                    status_tg.append("❌")

                # 2. Отправка на GDrive (если настроен rclone)
                if REMOTE_GDRIVE:
                    try:
                        tmp_file = os.path.join(temp_dir, dest_name)
                        subprocess.run(['cp', src, tmp_file])
                        subprocess.run(['rclone', 'copyto', tmp_file, f"{REMOTE_GDRIVE}/background/{dest_name}"],
                                       check=True)
                        status_drive.append("✅")
                    except Exception as e:
                        logging.error(f"Rclone Backup Error {src}: {e}")
                        status_drive.append("❌")
                else:
                    status_drive.append("⚠️ (не настроено)")
            else:
                status_tg.append("⚪️")
                status_drive.append("⚪️")

        # Очистка временной папки
        subprocess.run(['rm', '-rf', temp_dir])

        report = (f"📦 <b>Результаты Бэкапа:</b>\n\n"
                  f"<b>Telegram:</b>\nMarzban: {status_tg[0]} | Бот: {status_tg[1]}\n\n"
                  f"<b>Google Drive:</b>\nMarzban: {status_drive[0]} | Бот: {status_drive[1]}")

        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=get_admin_kb())
    except Exception as e:
        await bot.send_message(chat_id=ADMIN_ID, text=f"❌ Критическая ошибка бэкапов: {e}")
    finally:
        await callback.answer()


# ==========================================
# 2. БАН / РАЗБАН (Оставляем как было)
# ==========================================
@router.message(Command("ban"))
async def cmd_ban(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return
    ip = command.args
    if not ip:
        await message.reply("⚠️ Пример: <code>/ban 1.2.3.4</code>", parse_mode="HTML")
        return
    try:
        subprocess.run(['iptables', '-A', 'INPUT', '-s', ip.strip(), '-j', 'DROP'], check=True)
        await message.reply(f"🚫 IP <code>{ip}</code> заблокирован.", parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


@router.message(Command("unban"))
async def cmd_unban(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return
    ip = command.args
    if not ip:
        await message.reply("⚠️ Пример: <code>/unban 1.2.3.4</code>", parse_mode="HTML")
        return
    try:
        subprocess.run(['iptables', '-D', 'INPUT', '-s', ip.strip(), '-j', 'DROP'], check=True)
        await message.reply(f"🕊 IP <code>{ip}</code> разблокирован.", parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


@router.message(Command("sendall"))
async def cmd_sendall(message: types.Message, command: CommandObject, db, bot: Bot):
    if message.from_user.id != ADMIN_ID: return

    text = command.args
    if not text:
        await message.reply("⚠️ <b>Использование:</b>\n<code>/sendall Внимание! Сегодня скидки!</code>",
                            parse_mode="HTML")
        return

    users = await db.get_all_users()
    if not users:
        await message.reply("❌ В базе данных пока нет пользователей.")
        return

    msg = await message.answer(f"⏳ <b>Начинаю рассылку для {len(users)} пользователей...</b>", parse_mode="HTML")

    success = 0
    failed = 0

    for tg_id in users:
        try:
            await bot.send_message(chat_id=tg_id, text=text, parse_mode="HTML")
            success += 1
        except Exception as e:
            # Юзер мог заблокировать бота, игнорируем
            failed += 1

        # Anti-flood задержка, чтобы Telegram не забанил бота за спам
        await asyncio.sleep(0.05)

    await msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n✉️ Успешно доставлено: {success}\n❌ Заблокировали бота: {failed}",
        parse_mode="HTML")


@router.message(Command("give_sub"))
async def cmd_give_sub(message: types.Message, command: CommandObject, db, panel, bot: Bot):
    if message.from_user.id != ADMIN_ID: return

    args = command.args
    if not args:
        await message.reply(
            "⚠️ <b>Формат:</b>\n<code>/give_sub <ID_пользователя> <Дни></code>\nПример: <code>/give_sub 123456789 30</code>",
            parse_mode="HTML")
        return

    parts = args.split()
    if len(parts) != 2:
        await message.reply("❌ Неверный формат. Укажите ID и количество дней через пробел.")
        return

    try:
        target_uid = int(parts[0])
        days = int(parts[1])
    except ValueError:
        await message.reply("❌ ID и количество дней должны быть числами.")
        return

    add_ms = days * 24 * 60 * 60 * 1000

    try:
        # Логика расчета времени
        user = await db.get_user(target_uid)
        now_ms = int(time.time() * 1000)
        current_expiry = user['expiry_ms'] if user and user['expiry_ms'] else 0
        new_expiry = max(current_expiry, now_ms) + add_ms

        # Синхронизация с Marzban (Создаем или продлеваем)
        # Обрати внимание: INBOUND_ID должно импортироваться из config.py
        from config import INBOUND_ID

        username = f"User_{target_uid}"
        # Пробуем продлить (если юзер уже есть в панели)
        # Если в твоем panel_client метод называется иначе, поправим, но обычно это так:
        marzban_res = await panel.extend_user(INBOUND_ID, str(target_uid), username, None, new_expiry)

        if not marzban_res or not marzban_res.get("success"):
            # Если юзера нет в Marzban - создаем
            await panel.add_user(INBOUND_ID, username, str(target_uid), new_expiry)

        # Обновляем локальную базу
        await db.confirm_payment(target_uid, 0, new_expiry)  # Сумма 0, так как выдано админом

        await message.reply(
            f"✅ <b>Готово!</b>\nПодписка для <code>{target_uid}</code> продлена/создана на {days} дней.",
            parse_mode="HTML")

        # Пробуем обрадовать юзера
        try:
            await bot.send_message(target_uid,
                                   f"🎁 <b>Вам начислена подписка!</b>\nАдминистратор выдал вам доступ на {days} дней.",
                                   parse_mode="HTML")
        except Exception:
            pass  # Если бот заблокирован юзером

    except Exception as e:
        await message.reply(f"❌ Ошибка выдачи подписки: {e}")
