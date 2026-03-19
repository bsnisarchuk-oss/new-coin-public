from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WatchlistItem

_MAX_WATCHLIST_SIZE = 50


async def add_watch(session: AsyncSession, user_id: int, symbol_base: str) -> bool:
    """Add ticker to watchlist. Returns False if already exists or limit reached."""
    symbol = symbol_base.upper()
    existing = await session.execute(
        select(WatchlistItem.id).where(
            WatchlistItem.user_id == user_id,
            WatchlistItem.symbol_base == symbol,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return False
    count_result = await session.execute(
        select(func.count()).where(WatchlistItem.user_id == user_id)
    )
    if (count_result.scalar_one() or 0) >= _MAX_WATCHLIST_SIZE:
        return False
    session.add(WatchlistItem(user_id=user_id, symbol_base=symbol))
    await session.flush()
    return True


async def remove_watch(session: AsyncSession, user_id: int, symbol_base: str) -> bool:
    result = await session.execute(
        delete(WatchlistItem).where(
            WatchlistItem.user_id == user_id,
            WatchlistItem.symbol_base == symbol_base.upper(),
        )
    )
    return (result.rowcount or 0) > 0


async def list_watchlist(session: AsyncSession, user_id: int) -> list[str]:
    result = await session.execute(
        select(WatchlistItem.symbol_base)
        .where(WatchlistItem.user_id == user_id)
        .order_by(WatchlistItem.symbol_base.asc())
    )
    return [row[0] for row in result.fetchall()]


async def find_all_watched(session: AsyncSession) -> dict[str, list[int]]:
    """Return {symbol_base: [user_id, ...]} for every entry in the watchlist."""
    result = await session.execute(
        select(WatchlistItem.symbol_base, WatchlistItem.user_id)
    )
    grouped: dict[str, list[int]] = {}
    for base, uid in result.fetchall():
        grouped.setdefault(base, []).append(uid)
    return grouped


async def find_users_watching(session: AsyncSession, symbol_bases: list[str]) -> dict[str, list[int]]:
    """Return {symbol_base: [user_id, ...]} for all watched symbols in the given list."""
    if not symbol_bases:
        return {}
    uppers = [s.upper() for s in symbol_bases]
    result = await session.execute(
        select(WatchlistItem.symbol_base, WatchlistItem.user_id).where(
            WatchlistItem.symbol_base.in_(uppers)
        )
    )
    grouped: dict[str, list[int]] = {}
    for base, uid in result.fetchall():
        grouped.setdefault(base, []).append(uid)
    return grouped

