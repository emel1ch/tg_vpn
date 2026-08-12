import os
import subprocess
import asyncio
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, BufferedInputFile
from aiogram.exceptions import TelegramForbiddenError
import openpyxl
from openpyxl.styles import Font
from io import BytesIO
from config import ADMIN_ID, REMOTE_GDRIVE, MARZBAN_DB_PATH, BOT_DB_PATH, INBOUND_ID,GROUP_ID

router = Router()


# ==========================================
# 0. ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ (Поиск по Username)
# ==========================================
async def resolve_target_id(identifier: str, db):
    """
    Принимает строку (ID или @username).
    Возвращает int (ID) или None, если не нашел.
    """
    # Если передали чистое число (ID)
    if identifier.isdigit():
        return int(identifier)

    # Очищаем юзернейм от @, пробелов и приводим к нижнему регистру
    clean_username = identifier.replace("@", "").strip().lower()

    # Ищем пользователя в базе (get_user_by_username тоже должен приводить к lower())
    user = await db.get_user_by_username(clean_username)
    if user:
        return user['tg_id']

    return None

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
        pass
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

        users_list = users.get('users', []) if isinstance(users, dict) else users
        if not isinstance(users_list, list):
            await callback.answer("❌ Неверный формат данных от API.", show_alert=True)
            return

        active_count = sum(1 for u in users_list if u.get('status') == 'active')
        total_traffic = sum(u.get('used_traffic', 0) for u in users_list) / (1024 ** 3)

        report = f"👥 <b>Пользователи Marzban:</b>\nВсего: {len(users_list)}\nАктивных: {active_count}\nТрафик: {total_traffic:.2f} GB\n\n🏆 <b>Топ-5:</b>\n"
        top_users = sorted(users_list, key=lambda x: x.get('used_traffic', 0), reverse=True)[:5]
        for u in top_users:
            report += f"👤 <code>{u.get('username')}</code>: {(u.get('used_traffic', 0) / (1024 ** 3)):.2f} GB\n"

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
        status_tg, status_drive = [], []

        tasks = [(MARZBAN_DB_PATH, f"marzban_{date_str}.sqlite", "📦 БД Marzban"),
                 (BOT_DB_PATH, f"vpn_service_{date_str}.db", "🤖 БД Telegram-бота")]

        for src, dest_name, caption in tasks:
            if os.path.exists(src):
                # Telegram
                try:
                    await bot.send_document(ADMIN_ID, FSInputFile(src), caption=caption)
                    status_tg.append("✅")
                except Exception:
                    status_tg.append("❌")

                # GDrive
                if REMOTE_GDRIVE:
                    try:
                        tmp_file = os.path.join(temp_dir, dest_name)
                        subprocess.run(['cp', src, tmp_file])
                        subprocess.run(['rclone', 'copyto', tmp_file, f"{REMOTE_GDRIVE}/background/{dest_name}"],
                                       check=True)
                        status_drive.append("✅")
                    except Exception:
                        status_drive.append("❌")
                else:
                    status_drive.append("⚠️")
            else:
                status_tg.append("⚪️")
                status_drive.append("⚪️")

        subprocess.run(['rm', '-rf', temp_dir])
        report = f"📦 <b>Бэкап:</b>\nTG: Marzban {status_tg[0]} | Бот {status_tg[1]}\nDrive: Marzban {status_drive[0]} | Бот {status_drive[1]}"
        await callback.message.edit_text(report, parse_mode="HTML", reply_markup=get_admin_kb())
    except Exception as e:
        await bot.send_message(ADMIN_ID, f"❌ Критическая ошибка бэкапов: {e}")


# ==========================================
# 2. БАН / РАЗБАН
# ==========================================
@router.message(Command("ban"))
async def cmd_ban(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return
    ip = command.args
    if not ip: return await message.reply("⚠️ Пример: <code>/ban 1.2.3.4</code>", parse_mode="HTML")
    try:
        subprocess.run(['iptables', '-A', 'INPUT', '-s', ip.strip(), '-j', 'DROP'], check=True)
        await message.reply(f"🚫 IP <code>{ip}</code> заблокирован.", parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


@router.message(Command("unban"))
async def cmd_unban(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return
    ip = command.args
    if not ip: return await message.reply("⚠️ Пример: <code>/unban 1.2.3.4</code>", parse_mode="HTML")
    try:
        subprocess.run(['iptables', '-D', 'INPUT', '-s', ip.strip(), '-j', 'DROP'], check=True)
        await message.reply(f"🕊 IP <code>{ip}</code> разблокирован.", parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


# ==========================================
# 3. РАССЫЛКА И ВЫДАЧА ПОДПИСОК
# ==========================================
# ==========================================
# 3. РАССЫЛКА И ВЫДАЧА ПОДПИСОК
# ==========================================
@router.message(Command("sendall"))
async def cmd_sendall(message: types.Message, command: CommandObject, db, bot: Bot):
    if message.from_user.id != ADMIN_ID: return
    if not command.args:
        return await message.reply("⚠️ <b>Использование:</b>\n<code>/sendall Текст рассылки</code>", parse_mode="HTML")

    users = await db.get_all_users()
    if not users: return await message.reply("❌ В базе данных пока нет пользователей.")
    msg = await message.answer(f"⏳ <b>Начинаю рассылку для {len(users)} пользователей...</b>", parse_mode="HTML")

    success, blocked, failed = 0, 0, 0
    for tg_id in users:
        try:
            await bot.send_message(chat_id=tg_id, text=command.args, parse_mode="HTML")
            success += 1
        except TelegramForbiddenError:
            blocked += 1
            await db.set_user_inactive(tg_id) # Сразу помечаем юзера как неактивного
        except Exception:
            failed += 1
        await asyncio.sleep(0.05) # Безопасная пауза от спам-блока

    await msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"✉️ Доставлено: {success}\n"
        f"🚫 Заблокировали бота: {blocked}\n"
        f"❌ Ошибок: {failed}",
        parse_mode="HTML"
    )

@router.message(Command("give_sub"))
async def cmd_give_sub(message: types.Message, command: CommandObject, db, panel, bot: Bot):
    if message.from_user.id != ADMIN_ID: return
    if not command.args:
        return await message.reply("⚠️ <b>Формат:</b>\n<code>/give_sub <ID или @username> <Дни></code>", parse_mode="HTML")

    parts = command.args.split()
    if len(parts) != 2: return await message.reply("❌ Неверный формат.")

    target_input = parts[0]
    try:
        days = int(parts[1])
    except ValueError:
        return await message.reply("❌ Количество дней должно быть числом.")

    # Используем функцию поиска ID
    target_uid = await resolve_target_id(target_input, db)
    if not target_uid:
        return await message.reply(f"❌ Пользователь <code>{target_input}</code> не найден в БД.", parse_mode="HTML")

    add_ms = days * 24 * 60 * 60 * 1000

    try:
        user = await db.get_user(target_uid)
        now_ms = int(time.time() * 1000)
        current_expiry = user['expiry_ms'] if user and user['expiry_ms'] else 0
        new_expiry = max(current_expiry, now_ms) + add_ms

        username_panel = str(target_uid) # Marzban использует ID как логин

        # Пробуем продлить
        marzban_res = await panel.extend_user(INBOUND_ID, username_panel, None, None, new_expiry)

        # Если юзера нет в панели, создаем
        if not marzban_res or not marzban_res.get("success"):
            await panel.add_user(INBOUND_ID, None, str(target_uid), new_expiry)

        await db.confirm_payment(target_uid, 0, new_expiry)
        await message.reply(f"✅ Подписка выдана для <code>{target_input}</code> (ID: {target_uid}) на {days} дн.", parse_mode="HTML")

        # Отправляем уведомление самому пользователю
        try:
            await bot.send_message(
                target_uid,
                f"🎁 <b>Вам начислена подписка!</b>\nАдминистратор выдал вам доступ на {days} дней. Проверьте /menu",
                parse_mode="HTML"
            )
        except Exception:
            pass # Если заблокировал бота, просто игнорируем

    except Exception as e:
        await message.reply(f"❌ Ошибка выдачи подписки: {e}")


from datetime import datetime


@router.message(Command("promo_may2"))
async def cmd_promo_may2(message: types.Message, db, panel, bot: Bot):
    if message.from_user.id != ADMIN_ID: return

    # Задаем жесткую дату: 2 мая 2026 года, 23:59:59
    target_date = datetime(2026, 5, 3, 23, 59, 59)
    target_ms = int(target_date.timestamp() * 1000)

    users = await db.get_all_users()
    if not users:
        return await message.reply("❌ База пуста.")

    msg = await message.answer(
        f"⏳ <b>Начинаю обновление...</b>\nСтавлю всем срок до 2 мая. Юзеров в базе: {len(users)}", parse_mode="HTML")

    success = 0
    for tg_id in users:
        try:
            # 1. Обновляем в локальной базе бота (amount=0, чтобы не портить стату)
            await db.confirm_payment(tg_id, 0, target_ms)

            username_panel = str(tg_id)

            # 2. Пробуем обновить время в Marzban
            marzban_res = await panel.extend_user(INBOUND_ID, username_panel, None, None, target_ms)

            # Если юзера нет в Marzban (вдруг удалился), создаем заново с нужным сроком
            if not marzban_res or not marzban_res.get("success"):
                await panel.add_user(INBOUND_ID, None, str(tg_id), target_ms)

            success += 1
        except Exception as e:
            print(f"Ошибка с юзером {tg_id}: {e}")

        await asyncio.sleep(0.05)  # Защита от лимитов API

    await msg.edit_text(
        f"✅ <b>Готово!</b>\nСрок подписки для {success} пользователей успешно установлен ровно до 2 мая 2026 года.",
        parse_mode="HTML")


@router.message(Command("revoke_sub"))
async def cmd_revoke_sub(message: types.Message, command: CommandObject, db, panel):
    if message.from_user.id != ADMIN_ID: return
    if not command.args:
        return await message.reply(
            "⚠️ <b>Формат:</b>\n<code>/revoke_sub <ID или @username></code>\nЭта команда обнулит время юзера и отключит ему VPN.",
            parse_mode="HTML")

    target_input = command.args.strip()
    target_uid = await resolve_target_id(target_input, db)

    if not target_uid:
        return await message.reply(f"❌ Пользователь <code>{target_input}</code> не найден в БД.", parse_mode="HTML")

    try:
        # Ставим время = 0
        await db.confirm_payment(target_uid, 0, 0)
        # Обновляем в Marzban (передаем 0, чтобы подписка истекла моментально)
        await panel.extend_user(INBOUND_ID, str(target_uid), None, None, 0)

        await message.reply(
            f"🛑 Подписка пользователя <code>{target_input}</code> (ID: {target_uid}) успешно аннулирована. VPN отключен.",
            parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


import re  # Убедитесь, что импорт re есть в начале файла


@router.message(F.chat.id == GROUP_ID, F.reply_to_message)
async def reply_from_admin(message: types.Message, bot: Bot):
    # Берем текст оригинального сообщения, на которое отвечает админ
    original_text = message.reply_to_message.text or message.reply_to_message.caption

    if not original_text:
        return  # Если оригинальное сообщение было стикером или войсом без подписи

    # Ищем в тексте строку "ID: 12345678"
    match = re.search(r"ID:\s*(\d+)", original_text)

    if match:
        user_id = int(match.group(1))

        # Формируем ответ для пользователя
        admin_response = (
            f"👨‍💻 <b>Ответ от поддержки:</b>\n\n"
            f"{message.text}"
        )

        try:
            # Отправляем ответ юзеру
            await bot.send_message(user_id, admin_response, parse_mode="HTML")

            # Ставим реакцию в админ-группе, чтобы админ понял, что ответ ушел (опционально)
            await message.react([types.ReactionTypeEmoji(emoji="👍")])

        except Exception:
            await message.reply("❌ Ошибка отправки: Пользователь заблокировал бота или удален.")


import time
from aiogram.exceptions import TelegramBadRequest


# ==========================================
# ОБРАБОТКА ОПЛАТЫ ИЗ АДМИН-ГРУППЫ
# ==========================================
@router.callback_query(F.data.startswith("pay_yes:"))
async def approve_payment(callback: types.CallbackQuery, db, panel, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⛔ Недостаточно прав", show_alert=True)
    await callback.answer("⏳ Одобряю...", show_alert=False)

    # Достаем ID пользователя из callback_data (pay_yes:12345678)
    user_id = int(callback.data.split(":")[1])

    # ВАШИ НАСТРОЙКИ (200 руб = 30 дней)
    from config import PAYMENT_PRICE
    add_ms = 30 * 24 * 60 * 60 * 1000  # 30 дней в миллисекундах

    try:
        user = await db.get_user(user_id)
        now_ms = int(time.time() * 1000)
        current_expiry = user['expiry_ms'] if user and user['expiry_ms'] else 0
        new_expiry = max(current_expiry, now_ms) + add_ms

        username_panel = str(user_id)
        from config import INBOUND_ID

        # Обновляем Marzban
        marzban_res = await panel.extend_user(INBOUND_ID, username_panel, None, None, new_expiry)
        if not marzban_res or not marzban_res.get("success"):
            await panel.add_user(INBOUND_ID, None, str(user_id), new_expiry)

        # Записываем транзакцию в БД
        await db.confirm_payment(user_id, PAYMENT_PRICE, new_expiry)

        # Обновляем сообщение в админ-чате
        try:
            await callback.message.edit_caption(
                caption=callback.message.caption + "\n\n✅ <b>ОДОБРЕНО</b>",
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            pass  # Если не получилось изменить текст, игнорируем

        # Уведомляем юзера
        try:
            await bot.send_message(
                user_id,
                "🎉 <b>Ваша оплата успешно подтверждена!</b>\nПодписка продлена на 30 дней. Проверьте /menu",
                parse_mode="HTML"
            )
        except Exception:
            pass

    except Exception as e:
        await callback.message.reply(f"❌ Ошибка при выдаче подписки: {e}")


@router.callback_query(F.data.startswith("pay_no:"))
async def reject_payment(callback: types.CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⛔ Недостаточно прав", show_alert=True)
    await callback.answer("Отклонено", show_alert=False)
    user_id = int(callback.data.split(":")[1])

    # Обновляем сообщение в админ-чате
    try:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ <b>ОТКЛОНЕНО</b>",
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass

    # Уведомляем юзера
    try:
        await bot.send_message(
            user_id,
            "❌ <b>Ваша оплата не была подтверждена.</b>\nЕсли вы уверены, что оплатили, обратитесь в Поддержку через меню бота.",
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.message(Command("export"))
async def export_excel_command(message: types.Message, db, panel):  # <--- Добавь panel сюда!
    if message.from_user.id != ADMIN_ID:
        return

    msg = await message.answer("🔄 Актуализирую данные перед выгрузкой...")

    # Быстрая фоновая синхронизация перед созданием файла
    marzban_data = await panel.get_all_users()
    if marzban_data and 'users' in marzban_data:
        for m_user in marzban_data['users']:
            if m_user.get('username').isdigit():
                tg_id = int(m_user.get('username'))
                expiry_ms = m_user.get('expire', 0) * 1000
                is_active = 1 if m_user.get('status') == 'active' else 0
                sub_url = m_user.get('subscription_url', '')

                local_user = await db.get_user(tg_id)
                if local_user:
                    await db.update_sync_data(tg_id, expiry_ms, is_active, sub_url)

    await msg.delete()  # Удаляем системное сообщение

    # Получаем 100% актуальные подписки из нашей локальной базы
    users = await db.get_active_subscriptions()

    if not users:
        await message.answer("На данный момент нет пользователей с активной подпиской.")
        return

    # Создаем виртуальный Excel файл
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Активные подписки"

    # Создаем заголовки
    headers = [
        "TG ID", "Юзернейм", "Имя", "Ссылка на чат",
        "Срок окончания", "Оплачено (Сумма)", "Рефералов", "Sub ID"
    ]
    ws.append(headers)

    # Делаем заголовки жирными
    for cell in ws[1]:
        cell.font = Font(bold=True)

    # Заполняем таблицу данными пользователей
    for u in users:
        # Переводим миллисекунды в красивую человеческую дату
        if u['expiry_ms']:
            expiry_dt = datetime.fromtimestamp(u['expiry_ms'] / 1000).strftime('%d.%m.%Y %H:%M')
        else:
            expiry_dt = "Ошибка/Безлимит"

        row = [
            u['tg_id'],
            f"@{u['username']}" if u['username'] else "Нет юзернейма",
            u['full_name'],
            u['contact_link'],
            expiry_dt,
            u['total_paid'],
            u['referrals_count'] if 'referrals_count' in u.keys() else 0, # На случай если рефералов нет
            u['sub_id']
        ]
        ws.append(row)

    # Красиво растягиваем колонки по ширине текста
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        ws.column_dimensions[column].width = max_length + 2

    # Сохраняем Excel в оперативную память
    file_bytes = BytesIO()
    wb.save(file_bytes)
    file_bytes.seek(0)

    # Формируем документ для отправки в Telegram
    date_str = datetime.now().strftime('%d_%m_%Y')
    document = BufferedInputFile(file_bytes.read(), filename=f"Active_Subs_{date_str}.xlsx")

    # Отправляем админу
    await message.answer_document(
        document,
        caption=f"📥 <b>Выгрузка завершена!</b>\n\nАктивных пользователей: <b>{len(users)} чел.</b>",
        parse_mode="HTML"
    )


@router.message(Command("sync"))
async def cmd_sync_users(message: types.Message, db, panel):
    if message.from_user.id != ADMIN_ID:
        return

    msg = await message.answer("⏳ <b>Начинаю синхронизацию с Marzban...</b>", parse_mode="HTML")
    marzban_data = await panel.get_all_users()

    if not marzban_data or 'users' not in marzban_data:
        return await msg.edit_text("❌ Ошибка: не удалось получить данные из панели Marzban.")

    added_count = 0
    updated_count = 0
    skipped_count = 0

    for m_user in marzban_data['users']:
        m_username = m_user.get('username')

        if not m_username.isdigit():
            skipped_count += 1
            continue

        tg_id = int(m_username)
        expiry_ms = m_user.get('expire', 0) * 1000
        is_active = 1 if m_user.get('status') == 'active' else 0
        sub_url = m_user.get('subscription_url', '')

        local_user = await db.get_user(tg_id)

        if not local_user:
            # Юзера нет в боте! Добавляем его
            await db.add_user(
                tg_id=tg_id, username="ImportedFromPanel", full_name="User",
                expiry_ms=expiry_ms, is_active=is_active
            )
            await db.set_user_keys(tg_id, str(tg_id), sub_url)
            added_count += 1
        else:
            # Юзер есть! Тихо обновляем ему время и статус, чтобы убить рассинхрон
            await db.update_sync_data(tg_id, expiry_ms, is_active, sub_url)
            updated_count += 1

    await msg.edit_text(
        f"✅ <b>Синхронизация успешно завершена!</b>\n\n"
        f"📥 Подтянуто новых юзеров: <b>{added_count}</b>\n"
        f"🔄 Обновлено существующих: <b>{updated_count}</b>\n"
        f"⏭ Пропущено не-TG аккаунтов: <b>{skipped_count}</b>",
        parse_mode="HTML"
    )
@router.message(Command("set_sub"))
async def cmd_set_sub(message: types.Message, command: CommandObject, db, panel):
    if message.from_user.id != ADMIN_ID: return
    if not command.args:
        return await message.reply("⚠️ <b>Формат:</b>\n<code>/set_sub <ID или @username> <Дни></code>\n"
                                   "<i>Установит срок ровно на указанное число дней от текущего момента.</i>",
                                   parse_mode="HTML")

    parts = command.args.split()
    if len(parts) != 2: return await message.reply("❌ Неверный формат.")

    target_input = parts[0]
    try:
        days = int(parts[1])
    except ValueError:
        return await message.reply("❌ Количество дней должно быть числом.")

    target_uid = await resolve_target_id(target_input, db)
    if not target_uid:
        return await message.reply(f"❌ Пользователь <code>{target_input}</code> не найден.", parse_mode="HTML")

    try:
        # Считаем время строго от "сейчас"
        now_ms = int(time.time() * 1000)
        new_expiry = now_ms + (days * 24 * 60 * 60 * 1000)

        # 1. Обновляем в локальной БД (ставим 0 в оплату, чтобы не портить статистику доходов)
        await db.confirm_payment(target_uid, 0, new_expiry)

        # 2. Обновляем в Marzban
        await panel.extend_user(INBOUND_ID, str(target_uid), None, None, new_expiry)

        await message.reply(
            f"🔧 <b>Срок исправлен!</b>\nДля <code>{target_input}</code> установлено ровно <b>{days}</b> дн. подписки.",
            parse_mode="HTML")
    except Exception as e:
        await message.reply(f"❌ Ошибка при исправлении: {e}")


@router.message(Command("give_all"))
async def cmd_give_all(message: types.Message, command: CommandObject, db, panel, bot: Bot):
    # Защита от чужих
    if message.from_user.id != ADMIN_ID:
        return

    args = command.args
    if not args or not args.isdigit():
        return await message.answer("⚠️ Использование: <code>/give_all количество_дней</code>", parse_mode="HTML")

    days = int(args)
    added_ms = days * 24 * 60 * 60 * 1000
    now_ms = int(time.time() * 1000)

    msg = await message.answer(f"⏳ Начинаю выдачу {days} дней всем пользователям...")

    import aiosqlite
    success_count = 0

    # Получаем всех пользователей из базы
    async with aiosqlite.connect(db.db_file) as dbase:
        dbase.row_factory = aiosqlite.Row
        async with dbase.execute("SELECT tg_id, expiry_ms FROM users") as cursor:
            users = await cursor.fetchall()

            for user in users:
                uid = user['tg_id']
                curr_exp = user['expiry_ms']

                # Если подписка уже кончилась, прибавляем время к текущему моменту
                new_exp = (curr_exp if curr_exp > now_ms else now_ms) + added_ms

                # Обновляем в БД (и заодно сбрасываем стадию спам-воронки отвала)
                await dbase.execute(
                    "UPDATE users SET expiry_ms = ?, is_active = 1, lapsed_reminder_stage = 0 WHERE tg_id = ?",
                    (new_exp, uid))
                await dbase.commit()

                # Обновляем в Marzban
                await panel.extend_user(INBOUND_ID, str(uid), None, None, new_exp)

                # Рассылаем уведомление
                try:
                    await bot.send_message(uid,
                                           f"🎁 <b>Подарок от администрации!</b>\nВам начислено <b>{days} дней</b> подписки!",
                                           parse_mode="HTML")
                    success_count += 1
                except Exception:
                    pass  # Пользователь мог заблокировать бота

    await msg.edit_text(f"✅ Успешно!\nВыдано <b>{days} дней</b>.\nОповещено пользователей: <b>{success_count}</b>",
                        parse_mode="HTML")