from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.config import Settings
from app.db.models import Event, EventType, MarketType
from app.services.dedup import DedupDecision
from app.services.notifier import EventNotifier


def _settings() -> Settings:
    return Settings(
        bot_token="x",
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        poll_interval_sec=60,
        dedup_ttl_hours=24,
        max_notifications_per_hour=20,
        min_vol_5m=10000.0,
        max_spread=0.02,
        bootstrap_on_empty=True,
        default_only_usdt=False,
        default_min_score=0,
        default_enabled_exchanges=("binance", "bybit", "coinbase", "okx", "mexc"),
        default_enabled_market_types=("spot", "futures"),
        admin_id=None,
    )


def _event(base: str) -> Event:
    return Event(
        id=uuid4(),
        exchange="binance",
        event_type=EventType.SPOT_LISTING,
        market_type=MarketType.SPOT,
        symbol_base=base,
        symbol_quote="USDT",
        first_seen_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        event_key=f"binance:SPOT_LISTING:spot:{base}:USDT",
        pairs=[f"{base}USDT"],
        meta={},
        enriched={},
        score=42,
        flags=[],
    )


@pytest.mark.asyncio
async def test_rate_limited_events_are_queued_and_not_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=1001, settings={})
    events = [_event("AAA"), _event("BBB")]
    session = MagicMock()
    session.flush = AsyncMock()

    bot = SimpleNamespace(send_message=AsyncMock())
    dedup = SimpleNamespace(
        check_delivery=AsyncMock(return_value=DedupDecision.QUEUE_RATE_LIMITED)
    )
    notifier = EventNotifier(
        bot=bot,
        settings=_settings(),
        enrichment_service=SimpleNamespace(),
        dedup_service=dedup,
    )
    notifier._enrich_one = AsyncMock()  # type: ignore[method-assign]

    monkeypatch.setattr(
        "app.services.notifier.users_repo.list_all_users",
        AsyncMock(return_value=[user]),
    )
    monkeypatch.setattr(
        "app.services.notifier.mutes_repo.list_mutes_for_users",
        AsyncMock(return_value={user.id: []}),
    )
    monkeypatch.setattr("app.services.notifier.event_passes_filters", lambda *_args, **_kwargs: True)

    enqueue = AsyncMock()
    create_delivery = AsyncMock()
    log_delivery = AsyncMock()
    monkeypatch.setattr("app.services.notifier.digest_repo.enqueue", enqueue)
    monkeypatch.setattr("app.services.notifier.deliveries_repo.create_delivery", create_delivery)
    monkeypatch.setattr("app.services.notifier._log_delivery", log_delivery)

    await notifier.process_events(session, events)

    assert enqueue.await_count == 2
    assert create_delivery.await_count == 2
    assert log_delivery.await_count == 2
    # Auto-digest notification should be sent once per user, not per event.
    bot.send_message.assert_awaited_once()
