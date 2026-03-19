from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PriceAlert

_MAX_ALERTS_PER_USER = 10


async def create_alert(
    session: AsyncSession,
    user_id: int,
    ticker: str,
    direction: str,
    threshold: Decimal,
    exchange: str | None = None,
) -> PriceAlert | None:
    """Create a price alert. Returns None if user already hit the limit."""
    count_result = await session.execute(
        select(PriceAlert.id).where(
            PriceAlert.user_id == user_id, PriceAlert.is_active.is_(True)
        )
    )
    if len(count_result.fetchall()) >= _MAX_ALERTS_PER_USER:
        return None
    alert = PriceAlert(
        user_id=user_id,
        ticker=ticker.upper(),
        exchange=exchange,
        direction=direction,
        threshold=threshold,
        is_active=True,
    )
    session.add(alert)
    await session.flush()
    return alert


async def list_active_alerts(session: AsyncSession, user_id: int) -> list[PriceAlert]:
    result = await session.execute(
        select(PriceAlert)
        .where(PriceAlert.user_id == user_id, PriceAlert.is_active.is_(True))
        .order_by(PriceAlert.created_at.asc())
    )
    return list(result.scalars())


async def deactivate_alert(
    session: AsyncSession, user_id: int, alert_id: int
) -> bool:
    result = await session.execute(
        update(PriceAlert)
        .where(
            PriceAlert.id == alert_id,
            PriceAlert.user_id == user_id,
            PriceAlert.is_active.is_(True),
        )
        .values(is_active=False)
    )
    return (result.rowcount or 0) > 0


async def list_all_active_alerts(session: AsyncSession) -> list[PriceAlert]:
    result = await session.execute(
        select(PriceAlert).where(PriceAlert.is_active.is_(True))
    )
    return list(result.scalars())


async def mark_triggered(session: AsyncSession, alert_id: int) -> None:
    await session.execute(
        update(PriceAlert)
        .where(PriceAlert.id == alert_id)
        .values(is_active=False, triggered_at=datetime.now(timezone.utc))
    )
