from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.lang import preferred_lang
from app.config import Settings
from app.db.models import Event, MarketType
from app.db.repo import users as users_repo

router = Router()

_PERIODS = [
    ("24h", timedelta(hours=24)),
    ("7d", timedelta(days=7)),
    ("30d", timedelta(days=30)),
]
_BAR_WIDTH = 10


def _bar(value: int, max_value: int) -> str:
    if max_value == 0:
        return "░" * _BAR_WIDTH
    filled = round(_BAR_WIDTH * value / max_value)
    return "█" * filled + "░" * (_BAR_WIDTH - filled)


async def _count_for_period(
    session: AsyncSession,
    since: datetime,
) -> dict[str, dict[str, int]]:
    result = await session.execute(
        select(
            Event.exchange,
            Event.market_type,
            func.count(Event.id).label("cnt"),
        )
        .where(Event.first_seen_at >= since)
        .group_by(Event.exchange, Event.market_type)
    )
    data: dict[str, dict[str, int]] = {}
    for exchange, market_type, count in result.fetchall():
        market = market_type.value if isinstance(market_type, MarketType) else str(market_type)
        data.setdefault(exchange, {})[market] = count
    return data


@router.message(Command("analytics"))
async def cmd_analytics(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        lang = "ru"
        if message.from_user is not None:
            user = await users_repo.get_or_create_user(session, message.from_user.id, settings)
            lang = preferred_lang(
                user.settings,
                telegram_lang_code=message.from_user.language_code,
            )
        sections: list[str] = [
            "📊 <b>Listing stats</b>\n"
            if lang == "en"
            else "📊 <b>Статистика листингов</b>\n"
        ]
        for label, delta in _PERIODS:
            since = now - delta
            data = await _count_for_period(session, since)
            if not data:
                sections.append(
                    f"<b>For {label}:</b> no data\n"
                    if lang == "en"
                    else f"<b>За {label}:</b> нет данных\n"
                )
                continue

            rows: list[tuple[str, str, int]] = []
            for exchange, markets in sorted(data.items()):
                for market_type, count in sorted(markets.items()):
                    rows.append((exchange.capitalize(), market_type, count))

            max_count = max(count for _, _, count in rows)
            total = sum(count for _, _, count in rows)
            lines = [
                f"<b>For {label}</b> (total {total}):"
                if lang == "en"
                else f"<b>За {label}</b> (всего {total}):"
            ]
            for exchange, market_type, count in rows:
                lines.append(f"  {exchange} {market_type}: {_bar(count, max_count)} {count}")
            sections.append("\n".join(lines) + "\n")

    await message.answer("\n".join(sections))
