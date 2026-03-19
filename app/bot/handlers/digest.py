from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.repo import users as users_repo

router = Router()


def _text(key: str, lang: str, **kwargs: str) -> str:
    ru = {
        "usage": "Использование: /digest on  или  /digest off",
        "status": (
            "Дайджест-режим сейчас <b>{status}</b>.\n"
            "Включить: /digest on  |  Выключить: /digest off\n\n"
            "В дайджест-режиме события не приходят мгновенно — раз в час бот отправляет сводку за период."
        ),
        "status.on": "включён",
        "status.off": "выключен",
        "already.on": "уже включён",
        "already.off": "уже выключен",
        "already": "Дайджест-режим {status}.",
        "enabled": (
            "✅ Дайджест-режим <b>включён</b>.\n"
            "Новые листинги будут накапливаться и отправляться раз в час."
        ),
        "disabled": (
            "✅ Дайджест-режим <b>выключен</b>.\n"
            "Уведомления снова приходят мгновенно."
        ),
    }
    en = {
        "usage": "Usage: /digest on  or  /digest off",
        "status": (
            "Digest mode is currently <b>{status}</b>.\n"
            "Enable: /digest on  |  Disable: /digest off\n\n"
            "In digest mode events do not arrive instantly — the bot sends one summary every hour."
        ),
        "status.on": "enabled",
        "status.off": "disabled",
        "already.on": "already enabled",
        "already.off": "already disabled",
        "already": "Digest mode is {status}.",
        "enabled": (
            "✅ <b>Digest mode enabled</b>.\n"
            "New listings will be accumulated and sent once per hour."
        ),
        "disabled": (
            "✅ <b>Digest mode disabled</b>.\n"
            "Notifications will arrive instantly again."
        ),
    }
    text = (en if lang == "en" else ru)[key]
    return text.format(**kwargs) if kwargs else text


@router.message(Command("digest"))
async def cmd_digest(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    arg = (command.args or "").strip().lower()
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=message.from_user.language_code,
        )
        if arg not in {"on", "off", ""}:
            await session.commit()
            await message.answer(_text("usage", lang))
            return

        current = bool((user.settings or {}).get("digest_mode", False))
        if not arg:
            status = _text("status.on", lang) if current else _text("status.off", lang)
            await session.commit()
            await message.answer(_text("status", lang, status=status))
            return

        enable = arg == "on"
        if enable == current:
            status = _text("already.on", lang) if enable else _text("already.off", lang)
            await session.commit()
            await message.answer(_text("already", lang, status=status))
            return

        user.settings = users_repo.merge_user_settings(
            user.settings or {},
            {"digest_mode": enable},
        )
        await session.commit()

    await message.answer(_text("enabled" if enable else "disabled", lang))
