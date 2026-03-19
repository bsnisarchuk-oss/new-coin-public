from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.models import Event
from app.db.repo import users as users_repo

router = Router()

_MARKET_EMOJI = {"spot": "🟢", "futures": "🔵"}


@router.message(Command("top"))
async def cmd_top(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    lang = "ru"

    async with session_factory() as session:
        if message.from_user is not None:
            user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
            lang = preferred_lang(
                user.settings,
                telegram_lang_code=message.from_user.language_code,
            )
        result = await session.execute(
            select(Event)
            .where(Event.first_seen_at >= since)
            .order_by(Event.score.desc(), Event.first_seen_at.desc())
            .limit(10)
        )
        events = list(result.scalars())

    if not events:
        await message.answer(
            "No new listings were detected over the last 24 hours."
            if lang == "en"
            else "За последние 24 часа новых листингов не обнаружено."
        )
        return

    lines = [
        "🏆 <b>Top listings over 24 hours</b>\n"
        if lang == "en"
        else "🏆 <b>Топ листингов за 24 часа</b>\n"
    ]
    for index, event in enumerate(events, 1):
        market_emoji = _MARKET_EMOJI.get(event.market_type.value, "⚪")
        price = (event.enriched or {}).get("price")
        price_str = f" · ${price}" if price else ""
        lines.append(
            f"{index}. {market_emoji} <b>{event.symbol_base}/{event.symbol_quote}</b>"
            f" — {event.exchange.capitalize()}{price_str}\n"
            f"   Score: {event.score}/100 | {event.event_type.value.replace('_', ' ')}"
        )

    await message.answer("\n".join(lines))
