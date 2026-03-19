from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import User


def build_default_settings(settings: Settings) -> dict[str, Any]:
    return {
        "enabled_exchanges": list(settings.default_enabled_exchanges),
        "enabled_market_types": list(settings.default_enabled_market_types),
        "only_usdt": settings.default_only_usdt,
        "min_score": settings.default_min_score,
        "digest_only_until": None,
    }


async def get_or_create_user(
    session: AsyncSession, user_id: int, app_settings: Settings
) -> User:
    user = await session.get(User, user_id)
    if user is not None:
        if not user.settings:
            user.settings = build_default_settings(app_settings)
        return user

    user = User(id=user_id, settings=build_default_settings(app_settings))
    session.add(user)
    await session.flush()
    return user


async def list_all_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User))
    return list(result.scalars())


def merge_user_settings(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    merged.update(patch)
    return merged


def is_user_in_digest_mode(user: User) -> bool:
    digest_until = (user.settings or {}).get("digest_only_until")
    if not digest_until:
        return False
    try:
        dt = datetime.fromisoformat(digest_until)
    except ValueError:
        return False
    return dt > datetime.now(timezone.utc)


def is_user_paused(user: User) -> bool:
    paused_until = (user.settings or {}).get("paused_until")
    if not paused_until:
        return False
    try:
        dt = datetime.fromisoformat(paused_until)
    except ValueError:
        return False
    return dt > datetime.now(timezone.utc)

