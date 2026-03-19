from __future__ import annotations

import re

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.repo import users as users_repo
from app.db.repo import watchlist as watchlist_repo

router = Router()

_TICKER_RE = re.compile(r"^[A-Z0-9]{1,16}$")


def _validate_ticker(raw: str) -> str | None:
    ticker = raw.strip().upper()
    if not _TICKER_RE.match(ticker):
        return None
    return ticker


def _text(key: str, lang: str, **kwargs: str | int) -> str:
    ru = {
        "watch.invalid": "Формат: /watch <TICKER> (только буквы и цифры, до 16 символов)",
        "watch.added": "{ticker} добавлен в watchlist",
        "watch.duplicate": (
            "{ticker} уже в watchlist, либо достигнут лимит "
            "({limit} тикеров)"
        ),
        "watchlist": "Watchlist: {items}",
        "watchlist.empty": "Watchlist: -",
        "unwatch.invalid": "Формат: /unwatch <TICKER> (только буквы и цифры, до 16 символов)",
        "unwatch.removed": "{ticker} удален из watchlist",
        "unwatch.missing": "{ticker} не найден в watchlist",
    }
    en = {
        "watch.invalid": "Format: /watch <TICKER> (letters and digits only, up to 16 characters)",
        "watch.added": "{ticker} added to the watchlist",
        "watch.duplicate": (
            "{ticker} is already in the watchlist or the limit was reached "
            "({limit} tickers)"
        ),
        "watchlist": "Watchlist: {items}",
        "watchlist.empty": "Watchlist: -",
        "unwatch.invalid": "Format: /unwatch <TICKER> (letters and digits only, up to 16 characters)",
        "unwatch.removed": "{ticker} removed from the watchlist",
        "unwatch.missing": "{ticker} was not found in the watchlist",
    }
    text = (en if lang == "en" else ru)[key]
    return text.format(**kwargs) if kwargs else text


@router.message(Command("watch"))
async def cmd_watch(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    ticker = _validate_ticker(command.args or "")
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=message.from_user.language_code,
        )
        if not ticker:
            await session.commit()
            await message.answer(_text("watch.invalid", lang))
            return
        added = await watchlist_repo.add_watch(session, user.id, ticker)
        await session.commit()
    if added:
        await message.answer(_text("watch.added", lang, ticker=ticker))
    else:
        await message.answer(
            _text(
                "watch.duplicate",
                lang,
                ticker=ticker,
                limit=watchlist_repo._MAX_WATCHLIST_SIZE,
            )
        )


@router.message(Command("watchlist"))
async def cmd_watchlist(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=message.from_user.language_code,
        )
        items = await watchlist_repo.list_watchlist(session, user.id)
        await session.commit()
    if items:
        await message.answer(_text("watchlist", lang, items=", ".join(items)))
    else:
        await message.answer(_text("watchlist.empty", lang))


@router.message(Command("unwatch"))
async def cmd_unwatch(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    ticker = _validate_ticker(command.args or "")
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=message.from_user.language_code,
        )
        if not ticker:
            await session.commit()
            await message.answer(_text("unwatch.invalid", lang))
            return
        removed = await watchlist_repo.remove_watch(session, user.id, ticker)
        await session.commit()
    if removed:
        await message.answer(_text("unwatch.removed", lang, ticker=ticker))
    else:
        await message.answer(_text("unwatch.missing", lang, ticker=ticker))
