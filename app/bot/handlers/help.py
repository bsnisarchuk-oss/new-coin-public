from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.repo import users as users_repo
from app.i18n import get_user_lang, t

router = Router()


@router.message(Command("help"))
async def cmd_help(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    lang = "ru"
    if message.from_user is not None:
        async with session_factory() as session:
            user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
            lang = get_user_lang(user.settings)
    await message.answer(t("help.text", lang))
