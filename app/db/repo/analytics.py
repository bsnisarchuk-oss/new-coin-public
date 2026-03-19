from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalyticsEvent


async def log_event(
    session: AsyncSession,
    *,
    event_name: str,
    source: str,
    user_id: int | None = None,
    event_id: uuid.UUID | None = None,
    exchange: str | None = None,
    market_type: str | None = None,
    placement: str | None = None,
    button_id: str | None = None,
    properties: dict[str, Any] | None = None,
) -> AnalyticsEvent:
    event = AnalyticsEvent(
        user_id=user_id,
        event_name=event_name,
        source=source,
        event_id=event_id,
        exchange=(exchange.lower() if exchange else None),
        market_type=(market_type.lower() if market_type else None),
        placement=placement,
        button_id=button_id,
        properties=properties or {},
    )
    session.add(event)
    await session.flush()
    return event

