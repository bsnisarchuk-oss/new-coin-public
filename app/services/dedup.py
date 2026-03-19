from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import EventType, MarketType, User
from app.db.repo import deliveries as deliveries_repo
from app.db.repo import users as users_repo


def build_event_key(
    exchange: str,
    event_type: EventType,
    market_type: MarketType,
    base: str,
    quote: str | None,
) -> str:
    normalized_quote = (quote or "NA").upper()
    return (
        f"{exchange.lower()}:{event_type.value}:{market_type.value}:{base.upper()}:{normalized_quote}"
    )


class DedupDecision(str, Enum):
    ALLOW = "allow"
    SKIP_ALREADY_SENT = "skip_already_sent"
    SKIP_PAUSED = "skip_paused"
    QUEUE_DIGEST_ACTIVE = "queue_digest_active"
    QUEUE_RATE_LIMITED = "queue_rate_limited"


class DedupService:
    def __init__(self, settings: Settings) -> None:
        self._dedup_ttl_hours = settings.dedup_ttl_hours
        self._max_notifications_per_hour = settings.max_notifications_per_hour

    async def check_delivery(
        self, session: AsyncSession, user: User, event_key: str
    ) -> DedupDecision:
        now = datetime.now(timezone.utc)
        dedup_since = now - timedelta(hours=self._dedup_ttl_hours)
        already_sent = await deliveries_repo.was_sent_since(
            session=session,
            user_id=user.id,
            event_key=event_key,
            since=dedup_since,
        )
        if already_sent:
            return DedupDecision.SKIP_ALREADY_SENT

        if users_repo.is_user_paused(user):
            return DedupDecision.SKIP_PAUSED

        if users_repo.is_user_in_digest_mode(user):
            return DedupDecision.QUEUE_DIGEST_ACTIVE

        sent_last_hour = await deliveries_repo.count_sent_last_hour(session, user.id)
        if sent_last_hour >= self._max_notifications_per_hour:
            new_settings = users_repo.merge_user_settings(
                user.settings or {},
                {"digest_only_until": (now + timedelta(hours=1)).isoformat()},
            )
            user.settings = new_settings
            await session.flush()
            return DedupDecision.QUEUE_RATE_LIMITED
        return DedupDecision.ALLOW

    async def can_deliver(
        self, session: AsyncSession, user: User, event_key: str
    ) -> bool:
        return (
            await self.check_delivery(session=session, user=user, event_key=event_key)
            == DedupDecision.ALLOW
        )
