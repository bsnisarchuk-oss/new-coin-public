from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ServiceState


async def get_payload(
    session: AsyncSession,
    service: str,
    state_key: str,
) -> dict | None:
    result = await session.execute(
        select(ServiceState.payload).where(
            ServiceState.service == service,
            ServiceState.state_key == state_key,
        )
    )
    payload = result.scalar_one_or_none()
    return dict(payload) if payload is not None else None


async def set_payload(
    session: AsyncSession,
    service: str,
    state_key: str,
    payload: dict,
) -> None:
    stmt = insert(ServiceState).values(
        service=service,
        state_key=state_key,
        payload=payload,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_service_state_service_key",
        set_={
            "payload": stmt.excluded.payload,
            "updated_at": text("now()"),
        },
    )
    await session.execute(stmt)
