from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import PAYMENT_LINK

def get_main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Оплата", callback_data="renew"))
    builder.row(
        InlineKeyboardButton(text="📚 Инструкции", callback_data="guides"),
        InlineKeyboardButton(text="📊 Статус", callback_data="status")
    )
    builder.row(
        InlineKeyboardButton(text="📜 Транзакции", callback_data="history"),
        InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")
    )
    builder.adjust(1, 2, 2)
    return builder.as_markup()

def get_guides_kb():
    builder = InlineKeyboardBuilder()
    # Твои актуальные ссылки из main.py
    builder.row(InlineKeyboardButton(text="🍏 iOS/iPad/TV", url="https://teletype.in/@emel1ch/eJMUeXbv9P3"))
    builder.row(InlineKeyboardButton(text="🤖 Android", url="https://teletype.in/@emel1ch/YVYFWWL3pcJ"))
    builder.row(InlineKeyboardButton(text="💻 Windows", url="https://teletype.in/@emel1ch/1oshgSSJjal"))
    builder.row(InlineKeyboardButton(text="💻 MacOS", url="https://teletype.in/@emel1ch/I6p31Dxnwhq"))
    builder.row(InlineKeyboardButton(text="💻 Linux", url="https://teletype.in/@emel1ch/DrBPJnR4dnT"))
    builder.row(InlineKeyboardButton(text="📺 AndroidTV", url="https://teletype.in/@emel1ch/nUHewpzq5B3"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="to_main"))
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()

def get_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main")]])

def get_payment_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Оплатить по ссылке (200₽)", url=PAYMENT_LINK)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main")]
    ])
