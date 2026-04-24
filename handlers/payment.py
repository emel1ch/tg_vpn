from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from config import GROUP_ID, QR_FILE_PATH, PAYMENT_LINK
from utils.keyboards import get_payment_kb, get_main_menu
router = Router()


class PaymentState(StatesGroup):
    waiting_for_check = State()


@router.callback_query(F.data == "renew")
async def renew_init(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PaymentState.waiting_for_check)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Оплата (200₽)", url=PAYMENT_LINK)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main")]
    ])
    await callback.message.answer_photo(
        photo=FSInputFile(QR_FILE_PATH),
        caption="💳 Пришли скриншот чека после оплаты.",
        reply_markup=kb
    )
    await callback.message.delete()


@router.message(PaymentState.waiting_for_check, F.photo)
async def handle_payment_photo(message: types.Message, state: FSMContext, bot: Bot):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"pay_yes:{message.from_user.id}")
    builder.button(text="❌ Отказать", callback_data=f"pay_no:{message.from_user.id}")

    # Отправляем в GROUP_ID
    await bot.send_photo(
        GROUP_ID,
        message.photo[-1].file_id,
        caption=f"💰 **Новый чек!**\nОт: @{message.from_user.username}\nID: `{message.from_user.id}`",
        reply_markup=builder.as_markup()
    )
    await message.answer("✅ Чек на проверке!", reply_markup=get_main_menu())