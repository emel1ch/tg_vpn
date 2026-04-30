from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import os
from aiogram.types import FSInputFile
from config import GROUP_ID, QR_FILE_PATH, PAYMENT_LINK, CRYPTO_WALLETS, CRYPTO_QRS
from utils.keyboards import (
    get_payment_method_kb,
    get_crypto_method_kb,
    get_usdt_network_kb,
    get_payment_done_kb,
    get_main_menu
)

router = Router()


class PaymentState(StatesGroup):
    waiting_for_check = State()


# 1. Точка входа (Выбор СБП / Крипта)
@router.callback_query(F.data == "renew")
async def choose_payment_method(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    text = "💳 <b>Выберите способ оплаты (200₽ или эквивалент):</b>\n\nБанковские карты принимаются через СБП, а криптовалюта — прямым переводом."

    try:
        await callback.message.edit_text(text, reply_markup=get_payment_method_kb(), parse_mode="HTML")
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=get_payment_method_kb(), parse_mode="HTML")


# 2. Выбрали СБП (Показываем старый добрый QR)
@router.callback_query(F.data == "pay_sbp")
async def pay_via_sbp(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PaymentState.waiting_for_check)
    await callback.answer()
    kb = InlineKeyboardBuilder()
    kb.button(text="🔗 Оплатить по ссылке", url=PAYMENT_LINK)
    kb.button(text="⬅️ Назад", callback_data="renew")

    await callback.message.delete()
    await callback.message.answer_photo(
        photo=FSInputFile(QR_FILE_PATH),
        caption="🏦 <b>Оплата по СБП (200₽)</b>\n\nОплатите по QR-коду или ссылке ниже.\n\n📸 <b>Затем пришлите сюда скриншот чека.</b>",
        reply_markup=kb.adjust(1, 1).as_markup(),
        parse_mode="HTML"
    )


# 3. Выбрали Крипту (Выбор монеты)
@router.callback_query(F.data == "pay_crypto")
async def choose_crypto_coin(callback: types.CallbackQuery):
    await callback.answer()
    text = "🪙 <b>Выберите криптовалюту для оплаты:</b>\n<i>Мы рассчитаем эквивалент 200₽ в выбранной монете по текущему курсу.</i>"
    try:
        await callback.message.edit_text(text, reply_markup=get_crypto_method_kb(), parse_mode="HTML")
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=get_crypto_method_kb(), parse_mode="HTML")


# 4. Выбрали USDT (Выбор сети)
@router.callback_query(F.data == "crypto_usdt")
async def choose_usdt_network(callback: types.CallbackQuery):
    await callback.answer()
    text = "🟢 <b>USDT: Выберите сеть перевода:</b>\n⚠️ Внимательно выбирайте сеть, иначе средства будут утеряны!"
    await callback.message.edit_text(text, reply_markup=get_usdt_network_kb(), parse_mode="HTML")


# 5. Финал крипты (Выдача кошелька)
@router.callback_query(F.data.startswith("crypto_direct:"))
async def pay_crypto_direct(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(PaymentState.waiting_for_check)

    # Достаем название монеты/сети из callback (например, USDT_TRC20)
    coin_network = callback.data.split(":")[1]

    wallet = CRYPTO_WALLETS.get(coin_network, "Кошелек не настроен")
    qr_filename = CRYPTO_QRS.get(coin_network, "qr.jpg")  # Берем имя файла из конфига

    # Красивое форматирование (USDT_TRC20 -> USDT (Сеть: TRC20))
    display_name = coin_network.replace('_', ' (Сеть: ') + ')' if '_' in coin_network else coin_network

    text = (
        f"🪙 <b>Оплата в {display_name}</b>\n\n"
        f"Отправьте эквивалент <b>200₽</b> на этот кошелек:\n\n"
        f"<code>{wallet}</code>\n"
        f"<i>(нажмите на кошелек, чтобы скопировать)</i>\n\n"
        f"📸 <b>После успешного перевода пришлите сюда скриншот транзакции (чтобы был виден хэш).</b>"
    )

    await callback.message.delete()  # Удаляем меню выбора сети

    # Пытаемся отправить QR-код. Если картинки нет в папке, бот просто пришлет текст, чтобы не сломаться
    if os.path.exists(qr_filename):
        await callback.message.answer_photo(
            photo=FSInputFile(qr_filename),
            caption=text,
            reply_markup=get_payment_done_kb(),
            parse_mode="HTML"
        )
    else:
        await callback.message.answer(
            text=text + "\n\n<i>(QR-код временно недоступен, используйте адрес кошелька)</i>",
            reply_markup=get_payment_done_kb(),
            parse_mode="HTML"
        )

# 6. Обработка любого присланного чека (СБП или Крипта)
@router.message(PaymentState.waiting_for_check, F.photo)
async def handle_payment_photo(message: types.Message, state: FSMContext, bot: Bot):
    await state.clear()


    # Кнопки для админа
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"pay_yes:{message.from_user.id}")
    builder.button(text="❌ Отказать", callback_data=f"pay_no:{message.from_user.id}")

    await bot.send_photo(
        GROUP_ID,
        message.photo[-1].file_id,
        caption=f"💰 <b>Новый чек на проверку!</b>\nОт: @{message.from_user.username or 'скрыт'}\n🆔 ID: <code>{message.from_user.id}</code>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

    await message.answer("✅ Чек отправлен на проверку администратору!\nОбычно проверка занимает пару минут.",
                         reply_markup=get_main_menu())