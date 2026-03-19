from __future__ import annotations

from app.i18n import get_user_lang


def guess_lang(language_code: str | None) -> str:
    return "en" if (language_code or "").lower().startswith("en") else "ru"


def preferred_lang(
    user_settings: dict | None,
    *,
    telegram_lang_code: str | None = None,
) -> str:
    if user_settings and user_settings.get("lang") in {"ru", "en"}:
        return get_user_lang(user_settings)
    return guess_lang(telegram_lang_code)
