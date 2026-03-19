"""Handler for /lang command — switch interface language."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.repo import users as users_repo
from app.i18n import get_user_lang, t

router = Router()

_VALID_LANGS = {"ru", "en"}


@router.message(Command("lang"))
async def cmd_lang(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    parts = (message.text or "").strip().split()
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
        current_lang = get_user_lang(user.settings)

        if len(parts) < 2:
            # Show current language
            await message.answer(t("lang.current", current_lang, code=current_lang))
            return

        new_lang = parts[1].lower()
        if new_lang not in _VALID_LANGS:
            await message.answer(t("lang.unknown", current_lang))
            return

        user.settings = users_repo.merge_user_settings(
            dict(user.settings or {}), {"lang": new_lang}
        )
        await session.commit()

    if new_lang == "ru":
        await message.answer(t("lang.changed_ru", new_lang))
    else:
        await message.answer(t("lang.changed_en", new_lang))
