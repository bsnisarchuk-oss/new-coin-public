from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Delivery, Event


async def was_sent_since(
    session: AsyncSession, user_id: int, event_key: str, since: datetime
) -> bool:
    result = await session.execute(
        select(Delivery.id).where(
            Delivery.user_id == user_id,
            Delivery.event_key == event_key,
            Delivery.sent_at >= since,
        )
    )
    return result.scalar_one_or_none() is not None


async def count_sent_last_hour(session: AsyncSession, user_id: int) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    result = await session.execute(
        select(func.count(Delivery.id)).where(
            Delivery.user_id == user_id,
            Delivery.sent_at >= since,
        )
    )
    return int(result.scalar_one() or 0)


async def create_delivery(
    session: AsyncSession, user_id: int, event_id: uuid.UUID, event_key: str
) -> Delivery:
    delivery = Delivery(user_id=user_id, event_id=event_id, event_key=event_key)
    session.add(delivery)
    await session.flush()
    return delivery


async def find_users_notified_for_bases(
    session: AsyncSession, bases: list[str]
) -> dict[str, list[int]]:
    """Return {symbol_base: [user_id, ...]} for users who received delivery for given bases."""
    if not bases:
        return {}
    upper_bases = [b.upper() for b in bases]
    result = await session.execute(
        select(Event.symbol_base, Delivery.user_id)
        .join(Event, Delivery.event_id == Event.id)
        .where(Event.symbol_base.in_(upper_bases))
        .distinct()
    )
    mapping: dict[str, list[int]] = {}
    for symbol_base, user_id in result.all():
        mapping.setdefault(symbol_base.upper(), []).append(user_id)
    return mapping
