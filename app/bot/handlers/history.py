from __future__ import annotations

import math

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.callback_data import HistoryPageCB
from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.repo import events as events_repo
from app.db.repo import users as users_repo

router = Router()

_PAGE_SIZE = 10
_ALLOWED_HISTORY_EXCHANGES = ("binance", "bybit", "coinbase", "okx", "mexc")
_ALLOWED_HISTORY_EXCHANGES_SET = set(_ALLOWED_HISTORY_EXCHANGES)


def _text(key: str, lang: str, **kwargs: str | int) -> str:
    ru = {
        "header": "📋 История листингов{exchange} — стр. {page}/{total_pages} (всего {total})\n",
        "exchange_suffix": " [{exchange}]",
        "empty": "Пока нет листингов.",
        "invalid_exchange": (
            "Неверная биржа.\n"
            "Используй: /history <exchange>\n"
            "Доступно: {available}"
        ),
        "prev": "◀ Prev",
        "next": "Next ▶",
    }
    en = {
        "header": "📋 Listing history{exchange} — page {page}/{total_pages} (total {total})\n",
        "exchange_suffix": " [{exchange}]",
        "empty": "No listings yet.",
        "invalid_exchange": (
            "Invalid exchange.\n"
            "Use: /history <exchange>\n"
            "Available: {available}"
        ),
        "prev": "◀ Prev",
        "next": "Next ▶",
    }
    text = (en if lang == "en" else ru)[key]
    return text.format(**kwargs) if kwargs else text


def _format_history_page(
    events: list,
    *,
    page: int,
    total: int,
    exchange_filter: str,
    lang: str,
) -> str:
    total_pages = max(1, math.ceil(total / _PAGE_SIZE))
    exchange_suffix = (
        _text("exchange_suffix", lang, exchange=exchange_filter.capitalize())
        if exchange_filter
        else ""
    )
    header = _text(
        "header",
        lang,
        exchange=exchange_suffix,
        page=page + 1,
        total_pages=total_pages,
        total=total,
    )
    if not events:
        return f"{header}\n{_text('empty', lang)}"
    lines = [header]
    for event in events:
        timestamp = event.first_seen_at.strftime("%d.%m %H:%M")
        market = "Spot" if event.market_type.value == "spot" else "Futures"
        score = event.score or 0
        lines.append(
            f"• <b>{event.symbol_base}/{event.symbol_quote}</b> "
            f"{event.exchange.capitalize()} {market} | Score {score} | {timestamp} UTC"
        )
    return "\n".join(lines)


def _build_nav_keyboard(
    *,
    page: int,
    total: int,
    exchange_filter: str,
    lang: str,
) -> InlineKeyboardMarkup:
    total_pages = max(1, math.ceil(total / _PAGE_SIZE))
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(
            InlineKeyboardButton(
                text=_text("prev", lang),
                callback_data=HistoryPageCB(
                    page=page - 1,
                    exchange=exchange_filter,
                ).pack(),
            )
        )
    if page < total_pages - 1:
        buttons.append(
            InlineKeyboardButton(
                text=_text("next", lang),
                callback_data=HistoryPageCB(
                    page=page + 1,
                    exchange=exchange_filter,
                ).pack(),
            )
        )
    return InlineKeyboardMarkup(inline_keyboard=[buttons] if buttons else [])


@router.message(Command("history"))
async def cmd_history(
    message: Message,
    command: CommandObject,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    exchange_filter = (command.args or "").strip().lower()
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=message.from_user.language_code,
        )
        if exchange_filter and exchange_filter not in _ALLOWED_HISTORY_EXCHANGES_SET:
            available = ", ".join(_ALLOWED_HISTORY_EXCHANGES)
            await session.commit()
            await message.answer(
                _text("invalid_exchange", lang, available=available)
            )
            return
        events, total = await events_repo.list_events_page(
            session,
            page=0,
            exchange=exchange_filter or None,
        )
        await session.commit()
    text = _format_history_page(
        events,
        page=0,
        total=total,
        exchange_filter=exchange_filter,
        lang=lang,
    )
    keyboard = _build_nav_keyboard(
        page=0,
        total=total,
        exchange_filter=exchange_filter,
        lang=lang,
    )
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(HistoryPageCB.filter())
async def cb_history_page(
    callback: CallbackQuery,
    callback_data: HistoryPageCB,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    page = max(0, callback_data.page)
    exchange_filter = callback_data.exchange
    async with session_factory() as session:
        user = await users_repo.get_or_create_user(session, callback.from_user.id, settings)
        lang = preferred_lang(
            user.settings,
            telegram_lang_code=callback.from_user.language_code,
        )
        events, total = await events_repo.list_events_page(
            session,
            page=page,
            exchange=exchange_filter or None,
        )
        await session.commit()
    text = _format_history_page(
        events,
        page=page,
        total=total,
        exchange_filter=exchange_filter,
        lang=lang,
    )
    keyboard = _build_nav_keyboard(
        page=page,
        total=total,
        exchange_filter=exchange_filter,
        lang=lang,
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
