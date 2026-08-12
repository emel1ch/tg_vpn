import json
import os

_LOCALES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locales")
_DEFAULT_LANG = "ru"
_cache: dict[str, dict] = {}


def _load(lang: str) -> dict:
    if lang not in _cache:
        path = os.path.join(_LOCALES_DIR, f"{lang}.json")
        if not os.path.exists(path):
            lang = _DEFAULT_LANG
            path = os.path.join(_LOCALES_DIR, f"{lang}.json")
        with open(path, encoding="utf-8") as f:
            _cache[lang] = json.load(f)
    return _cache[lang]


def t(key: str, lang: str = _DEFAULT_LANG, **kwargs) -> str:
    """
    Базовая i18n-инфраструктура (Фаза 3.4). Переведён пока только главное
    меню и онбординг (cmd_start/get_main_menu) — остальные тексты
    мигрируют в locales/*.json постепенно.
    """
    translations = _load(lang)
    text = translations.get(key)
    if text is None:
        text = _load(_DEFAULT_LANG).get(key, key)
    return text.format(**kwargs) if kwargs else text
