from utils.i18n import t


def test_t_returns_russian_by_default():
    assert t("menu.payment") == "💳 Оплата"


def test_t_returns_english_translation():
    assert t("menu.payment", "en") == "💳 Payment"


def test_t_falls_back_to_russian_for_unknown_lang():
    assert t("menu.payment", "fr") == "💳 Оплата"


def test_t_formats_placeholders():
    text = t("welcome_back", "ru", uid=42)
    assert "42" in text
