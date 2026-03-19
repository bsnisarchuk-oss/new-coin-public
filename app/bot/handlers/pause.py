from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.repo import users as users_repo

router = Router()

_DURATION_RE = re.compile(r"^(\d+)(m|h|d)$", re.IGNORECASE)
_MAX_PAUSE_HOURS = 72


def _parse_duration(raw: str) -> timedelta | None:
    match = _DURATION_RE.match(raw.strip())
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    return timedelta(days=value)


def _text(key: str, lang: str, **kwargs: str) -> str:
    ru = {
        "none": "Уведомления активны, паузы нет.",
        "removed": "Пауза снята. Уведомления возобновлены.",
        "invalid": (
            "Неверный формат. Примеры: /pause 30m  /pause 2h  /pause 1d\n"
            "Максимальная пауза — 72h."
        ),
        "paused": (
            "Уведомления приостановлены до {until}.\n"
            "Чтобы снять паузу досрочно — /pause"
        ),
    }
    en = {
        "none": "Notifications are active, there is no pause.",
        "removed": "Pause removed. Notifications resumed.",
        "invalid": (
            "Invalid format. Examples: /pause 30m  /pause 2h  /pause 1d\n"
            "Maximum pause length is 72h."
        ),
        "paused": (
            "Notifications paused until {until}.\n"
            "To remove the pause early, use /pause"
        ),
    }
    text = (en if lang == "en" else ru)[key]
    return text.format(**kwargs) if kwargs else text


@router.message(Command("pause"))
async def cmd_pause(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    args = (command.args or "").strip()

    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=message.from_user.language_code,
        )

        if not args:
            current = user.settings or {}
            if not current.get("paused_until"):
                await session.commit()
                await message.answer(_text("none", lang))
                return
            user.settings = users_repo.merge_user_settings(current, {"paused_until": None})
            await session.commit()
            await message.answer(_text("removed", lang))
            return

        delta = _parse_duration(args)
        if delta is None:
            await session.commit()
            await message.answer(_text("invalid", lang))
            return

        max_delta = timedelta(hours=_MAX_PAUSE_HOURS)
        if delta > max_delta:
            delta = max_delta

        paused_until = datetime.now(timezone.utc) + delta
        user.settings = users_repo.merge_user_settings(
            user.settings or {},
            {"paused_until": paused_until.isoformat()},
        )
        await session.commit()

    until_str = paused_until.strftime("%H:%M UTC %d %b")
    await message.answer(_text("paused", lang, until=until_str))
