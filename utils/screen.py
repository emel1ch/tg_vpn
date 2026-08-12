from aiogram import types


async def render_screen(message: types.Message, text: str, reply_markup=None, parse_mode="HTML",
                        disable_web_page_preview=False):
    """
    Единый паттерн отрисовки экрана: сначала пробуем отредактировать текущее
    сообщение (быстро, без мигания чата), а если не вышло (например, текущее
    сообщение — фото, или его вообще нельзя редактировать) — удаляем и шлём
    новое.
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode,
                                disable_web_page_preview=disable_web_page_preview)
    except Exception:
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode,
                             disable_web_page_preview=disable_web_page_preview)
