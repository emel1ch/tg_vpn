from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import CHANNEL_URL, GUIDES


def get_main_menu(has_used_trial=True):  # Добавили аргумент
    builder = InlineKeyboardBuilder()

    # Если триал еще не использован, показываем кнопку в самом верху
    if not has_used_trial:
        builder.row(InlineKeyboardButton(text="🎁 Получить 3 дня (Trial)", callback_data="get_trial"))

    builder.row(InlineKeyboardButton(text="💳 Оплата", callback_data="renew"))
    builder.row(
        InlineKeyboardButton(text="📚 Инструкции", callback_data="guides"),
        InlineKeyboardButton(text="📊 Статус (Подписка)", callback_data="status")
    )
    builder.row(
        InlineKeyboardButton(text="📜 Транзакции", callback_data="history"),
        InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")
    )
    builder.row(InlineKeyboardButton(text="💌 Пригласить друга (Бонус)", callback_data="referral_menu"))
    # Новая кнопка канала
    builder.row(InlineKeyboardButton(text="📢 Наш Канал", url=CHANNEL_URL))

    return builder.as_markup()


def get_guides_kb():
    builder = InlineKeyboardBuilder()
    # Теперь берем из .env
    if GUIDES["IOS"]: builder.row(InlineKeyboardButton(text="🍏 iOS/iPad/TV", url=GUIDES["IOS"]))
    if GUIDES["AND"]: builder.row(InlineKeyboardButton(text="🤖 Android", url=GUIDES["AND"]))
    if GUIDES["WIN"]: builder.row(InlineKeyboardButton(text="💻 Windows", url=GUIDES["WIN"]))
    if GUIDES["MAC"]: builder.row(InlineKeyboardButton(text="💻 MacOS", url=GUIDES["MAC"]))
    if GUIDES["LINUX"]: builder.row(InlineKeyboardButton(text="💻 Linux", url=GUIDES["LINUX"]))
    if GUIDES["TV"]: builder.row(InlineKeyboardButton(text="📺 AndroidTV", url=GUIDES["TV"]))

    builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="to_main"))
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()

def get_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main")]])


def get_payment_method_kb():
    """Выбор способа оплаты: СБП или Крипта"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🏦 Банковская карта (СБП)", callback_data="pay_sbp")
    kb.button(text="🪙 Криптовалюта", callback_data="pay_crypto")
    kb.button(text="⬅️ Назад", callback_data="to_main")
    return kb.adjust(1, 1, 1).as_markup()


def get_crypto_method_kb():
    """Выбор монеты"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🟢 USDT", callback_data="crypto_usdt")
    kb.button(text="💎 TON (Toncoin)", callback_data="crypto_direct:TON")
    kb.button(text="🔷 Ethereum (ETH)", callback_data="crypto_direct:ETH")
    kb.button(text="🟠 Bitcoin (BTC)", callback_data="crypto_direct:BTC")
    kb.button(text="⬅️ Назад к выбору", callback_data="renew")
    return kb.adjust(1, 1, 1, 1, 1).as_markup()


def get_usdt_network_kb():
    """Выбор сети для USDT"""
    kb = InlineKeyboardBuilder()
    kb.button(text="TRC-20 (Tron)", callback_data="crypto_direct:USDT_TRC20")
    kb.button(text="TON", callback_data="crypto_direct:USDT_TON")
    kb.button(text="ERC-20 (Ethereum)", callback_data="crypto_direct:USDT_ERC20")
    kb.button(text="SOL (Solana)", callback_data="crypto_direct:USDT_SOL")
    kb.button(text="⬅️ Назад к монетам", callback_data="pay_crypto")
    return kb.adjust(1, 1, 1, 1, 1).as_markup()


def get_payment_done_kb():
    """Кнопка для возврата в меню после отправки чека"""
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Отмена / Назад", callback_data="to_main")
    return kb.as_markup()