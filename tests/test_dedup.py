from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app.db.models import EventType, MarketType
from app.services.dedup import DedupDecision, DedupService, build_event_key


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


def test_event_key_format() -> None:
    key = build_event_key(
        exchange="binance",
        event_type=EventType.SPOT_LISTING,
        market_type=MarketType.SPOT,
        base="abc",
        quote="usdt",
    )
    assert key == "binance:SPOT_LISTING:spot:ABC:USDT"


@pytest.mark.asyncio
async def test_check_delivery_skips_already_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = DedupService(_settings())
    session = MagicMock()
    user = SimpleNamespace(id=1, settings={})

    monkeypatch.setattr("app.services.dedup.deliveries_repo.was_sent_since", AsyncMock(return_value=True))
    monkeypatch.setattr("app.services.dedup.users_repo.is_user_paused", lambda _user: False)
    monkeypatch.setattr("app.services.dedup.users_repo.is_user_in_digest_mode", lambda _user: False)
    monkeypatch.setattr("app.services.dedup.deliveries_repo.count_sent_last_hour", AsyncMock(return_value=0))

    decision = await svc.check_delivery(session, user, "k")
    assert decision == DedupDecision.SKIP_ALREADY_SENT


@pytest.mark.asyncio
async def test_check_delivery_queues_when_digest_window_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = DedupService(_settings())
    session = MagicMock()
    user = SimpleNamespace(id=1, settings={"digest_only_until": "2099-01-01T00:00:00+00:00"})

    monkeypatch.setattr("app.services.dedup.deliveries_repo.was_sent_since", AsyncMock(return_value=False))
    monkeypatch.setattr("app.services.dedup.users_repo.is_user_paused", lambda _user: False)
    monkeypatch.setattr("app.services.dedup.users_repo.is_user_in_digest_mode", lambda _user: True)
    monkeypatch.setattr("app.services.dedup.deliveries_repo.count_sent_last_hour", AsyncMock(return_value=0))

    decision = await svc.check_delivery(session, user, "k")
    assert decision == DedupDecision.QUEUE_DIGEST_ACTIVE


@pytest.mark.asyncio
async def test_check_delivery_sets_auto_digest_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = DedupService(_settings())
    session = MagicMock()
    session.flush = AsyncMock()
    user = SimpleNamespace(id=1, settings={})

    monkeypatch.setattr("app.services.dedup.deliveries_repo.was_sent_since", AsyncMock(return_value=False))
    monkeypatch.setattr("app.services.dedup.users_repo.is_user_paused", lambda _user: False)
    monkeypatch.setattr("app.services.dedup.users_repo.is_user_in_digest_mode", lambda _user: False)
    monkeypatch.setattr("app.services.dedup.deliveries_repo.count_sent_last_hour", AsyncMock(return_value=20))

    decision = await svc.check_delivery(session, user, "k")
    assert decision == DedupDecision.QUEUE_RATE_LIMITED
    assert isinstance(user.settings.get("digest_only_until"), str)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_delivery_allows_normal_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = DedupService(_settings())
    session = MagicMock()
    user = SimpleNamespace(id=1, settings={})

    monkeypatch.setattr("app.services.dedup.deliveries_repo.was_sent_since", AsyncMock(return_value=False))
    monkeypatch.setattr("app.services.dedup.users_repo.is_user_paused", lambda _user: False)
    monkeypatch.setattr("app.services.dedup.users_repo.is_user_in_digest_mode", lambda _user: False)
    monkeypatch.setattr("app.services.dedup.deliveries_repo.count_sent_last_hour", AsyncMock(return_value=3))

    decision = await svc.check_delivery(session, user, "k")
    assert decision == DedupDecision.ALLOW
