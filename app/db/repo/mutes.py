from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MuteRule, MuteType


async def add_mute(
    session: AsyncSession, user_id: int, mute_type: MuteType, value: str
) -> None:
    normalized = value.lower().strip()
    existing = await session.execute(
        select(MuteRule.id).where(
            MuteRule.user_id == user_id,
            MuteRule.type == mute_type,
            MuteRule.value == normalized,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return
    session.add(MuteRule(user_id=user_id, type=mute_type, value=normalized))
    await session.flush()


async def list_mutes_for_users(
    session: AsyncSession, user_ids: list[int]
) -> dict[int, list[MuteRule]]:
    """Load mute rules for multiple users in a single query, grouped by user_id."""
    if not user_ids:
        return {}
    result = await session.execute(
        select(MuteRule).where(MuteRule.user_id.in_(user_ids)).order_by(MuteRule.id.asc())
    )
    grouped: dict[int, list[MuteRule]] = {uid: [] for uid in user_ids}
    for rule in result.scalars():
        grouped[rule.user_id].append(rule)
    return grouped


async def list_mutes(session: AsyncSession, user_id: int) -> list[MuteRule]:
    result = await session.execute(
        select(MuteRule).where(MuteRule.user_id == user_id).order_by(MuteRule.id.asc())
    )
    return list(result.scalars())


async def remove_mute(
    session: AsyncSession, user_id: int, mute_type: MuteType, value: str
) -> bool:
    result = await session.execute(
        delete(MuteRule).where(
            MuteRule.user_id == user_id,
            MuteRule.type == mute_type,
            MuteRule.value == value.lower().strip(),
        )
    )
    return (result.rowcount or 0) > 0

