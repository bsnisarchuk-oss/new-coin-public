from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DigestQueueItem, Event


async def enqueue(session: AsyncSession, user_id: int, event_id: uuid.UUID) -> None:
    """Add an event to a user's digest queue (ignore if already queued)."""
    existing = await session.execute(
        select(DigestQueueItem.id).where(
            DigestQueueItem.user_id == user_id,
            DigestQueueItem.event_id == event_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return
    session.add(DigestQueueItem(user_id=user_id, event_id=event_id))
    await session.flush()


async def list_user_queue_items(
    session: AsyncSession, user_id: int
) -> list[tuple[uuid.UUID, Event]]:
    """Return queued events for a user without deleting them."""
    result = await session.execute(
        select(DigestQueueItem.event_id, Event)
        .join(Event, DigestQueueItem.event_id == Event.id)
        .where(DigestQueueItem.user_id == user_id)
        .order_by(DigestQueueItem.queued_at.asc())
    )
    return [(event_id, event) for event_id, event in result.all()]


async def delete_user_queue_items(
    session: AsyncSession, user_id: int, event_ids: list[uuid.UUID]
) -> None:
    if not event_ids:
        return
    await session.execute(
        delete(DigestQueueItem).where(
            DigestQueueItem.user_id == user_id,
            DigestQueueItem.event_id.in_(event_ids),
        )
    )


async def pop_user_queue(session: AsyncSession, user_id: int) -> list[Event]:
    """Return all queued events for a user and remove them from the queue."""
    items = await list_user_queue_items(session, user_id)
    event_ids = [event_id for event_id, _ in items]
    await delete_user_queue_items(session, user_id, event_ids)
    return [event for _, event in items]


async def list_users_with_queue(session: AsyncSession) -> list[int]:
    """Return distinct user_ids that have pending digest items."""
    result = await session.execute(
        select(DigestQueueItem.user_id).distinct()
    )
    return [row[0] for row in result.fetchall()]
