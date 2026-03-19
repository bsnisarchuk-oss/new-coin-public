from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, MarketSnapshot, MarketType
from app.exchanges.base import Instrument


async def list_known_symbols(
    session: AsyncSession, exchange: str, market_type: MarketType
) -> set[str]:
    result = await session.execute(
        select(MarketSnapshot.symbol).where(
            MarketSnapshot.exchange == exchange,
            MarketSnapshot.market_type == market_type,
        )
    )
    return {row[0] for row in result.fetchall()}


async def list_known_snapshots(
    session: AsyncSession, exchange: str, market_type: MarketType
) -> list[MarketSnapshot]:
    result = await session.execute(
        select(MarketSnapshot).where(
            MarketSnapshot.exchange == exchange,
            MarketSnapshot.market_type == market_type,
        )
    )
    return list(result.scalars())


async def upsert_snapshots(
    session: AsyncSession, exchange: str, market_type: MarketType, instruments: list[Instrument]
) -> None:
    if not instruments:
        return

    now = datetime.now(timezone.utc)
    current_symbols = [item.symbol for item in instruments]
    await session.execute(
        delete(MarketSnapshot).where(
            MarketSnapshot.exchange == exchange,
            MarketSnapshot.market_type == market_type,
            MarketSnapshot.symbol.not_in(current_symbols),
        )
    )
    values = [
        {
            "exchange": exchange,
            "market_type": market_type,
            "symbol": item.symbol,
            "symbol_base": item.base,
            "symbol_quote": item.quote,
            "last_seen_at": now,
        }
        for item in instruments
    ]
    stmt = insert(MarketSnapshot).values(values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_market_snapshots_exchange_market_symbol",
        set_={
            "symbol_base": stmt.excluded.symbol_base,
            "symbol_quote": stmt.excluded.symbol_quote,
            "last_seen_at": now,
        },
    )
    await session.execute(stmt)


async def get_event(session: AsyncSession, event_id: uuid.UUID) -> Event | None:
    return await session.get(Event, event_id)


_HISTORY_PAGE_SIZE = 10


async def list_events_page(
    session: AsyncSession,
    page: int,
    exchange: str | None = None,
) -> tuple[list[Event], int]:
    """Return (events, total_count) for the requested page, newest first."""
    base_q = select(Event)
    count_q = select(func.count(Event.id))
    if exchange:
        base_q = base_q.where(Event.exchange == exchange.lower())
        count_q = count_q.where(Event.exchange == exchange.lower())

    total = int((await session.execute(count_q)).scalar_one() or 0)
    events = list(
        (
            await session.execute(
                base_q.order_by(Event.first_seen_at.desc())
                .offset(page * _HISTORY_PAGE_SIZE)
                .limit(_HISTORY_PAGE_SIZE)
            )
        ).scalars()
    )
    return events, total


async def count_events_last_hours(session: AsyncSession, hours: int) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await session.execute(
        select(func.count(Event.id)).where(Event.first_seen_at >= since)
    )
    return int(result.scalar_one() or 0)
