from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.models import Event
from app.db.repo import users as users_repo

router = Router()


@router.message(Command("export"))
async def cmd_export(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    since = datetime.now(timezone.utc) - timedelta(days=7)
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
            .order_by(Event.first_seen_at.desc())
            .limit(500)
        )
        events = list(result.scalars())

    if not events:
        await message.answer(
            "No listings found over the last 7 days."
            if lang == "en"
            else "За последние 7 дней листингов не найдено."
        )
        return

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "date_utc",
            "exchange",
            "market_type",
            "event_type",
            "base",
            "quote",
            "score",
            "flags",
            "price",
            "volume_5m",
        ]
    )
    for event in events:
        enriched = event.enriched or {}
        writer.writerow(
            [
                event.first_seen_at.strftime("%Y-%m-%d %H:%M"),
                event.exchange,
                event.market_type.value,
                event.event_type.value,
                event.symbol_base,
                event.symbol_quote,
                event.score,
                "|".join(event.flags or []),
                enriched.get("price", ""),
                enriched.get("volume_5m", ""),
            ]
        )

    filename = f"listings_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    file_bytes = buffer.getvalue().encode("utf-8-sig")
    await message.answer_document(
        BufferedInputFile(file_bytes, filename=filename),
        caption=(
            f"📥 Listings from the last 7 days — {len(events)} rows"
            if lang == "en"
            else f"📥 Листинги за последние 7 дней — {len(events)} записей"
        ),
    )
