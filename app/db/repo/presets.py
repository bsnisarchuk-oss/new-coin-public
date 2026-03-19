from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FilterPreset

_MAX_PRESETS_PER_USER = 5


async def save_preset(
    session: AsyncSession, user_id: int, name: str, settings: dict[str, Any]
) -> FilterPreset | None:
    """Upsert a preset by name. Returns None if limit reached and name is new."""
    existing = await session.execute(
        select(FilterPreset).where(
            FilterPreset.user_id == user_id, FilterPreset.name == name
        )
    )
    preset = existing.scalar_one_or_none()

    if preset is not None:
        # Overwrite existing preset with same name
        preset.settings = settings
        await session.flush()
        return preset

    # Check count limit
    count_result = await session.execute(
        select(FilterPreset.id).where(FilterPreset.user_id == user_id)
    )
    if len(count_result.fetchall()) >= _MAX_PRESETS_PER_USER:
        return None

    preset = FilterPreset(user_id=user_id, name=name, settings=settings)
    session.add(preset)
    await session.flush()
    return preset


async def load_preset(
    session: AsyncSession, user_id: int, name: str
) -> FilterPreset | None:
    result = await session.execute(
        select(FilterPreset).where(
            FilterPreset.user_id == user_id, FilterPreset.name == name
        )
    )
    return result.scalar_one_or_none()


async def list_presets(session: AsyncSession, user_id: int) -> list[FilterPreset]:
    result = await session.execute(
        select(FilterPreset)
        .where(FilterPreset.user_id == user_id)
        .order_by(FilterPreset.created_at.asc())
    )
    return list(result.scalars())


async def delete_preset(session: AsyncSession, user_id: int, name: str) -> bool:
    result = await session.execute(
        delete(FilterPreset).where(
            FilterPreset.user_id == user_id, FilterPreset.name == name
        )
    )
    return (result.rowcount or 0) > 0
