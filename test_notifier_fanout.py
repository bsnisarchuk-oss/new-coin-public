from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.config import Settings
from app.db.models import Event, EventType, MarketType
from app.services.dedup import DedupDecision
from app.services.filtering import UserFilters
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
async def test_notifier_reuses_formatted_message_per_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users = [
        SimpleNamespace(id=1001, settings={}),
        SimpleNamespace(id=1002, settings={}),
    ]
    session = MagicMock()
    session.flush = AsyncMock()

    bot = SimpleNamespace(send_message=AsyncMock())
    dedup = SimpleNamespace(check_delivery=AsyncMock(return_value=DedupDecision.ALLOW))
    notifier = EventNotifier(
        bot=bot,
        settings=_settings(),
        enrichment_service=SimpleNamespace(),
        dedup_service=dedup,
    )
    notifier._enrich_events = AsyncMock()  # type: ignore[method-assign]

    monkeypatch.setattr(
        "app.services.notifier.users_repo.list_all_users",
        AsyncMock(return_value=users),
    )
    monkeypatch.setattr(
        "app.services.notifier.mutes_repo.list_mutes_for_users",
        AsyncMock(return_value={1001: [], 1002: []}),
    )
    monkeypatch.setattr("app.services.notifier.event_passes_filters", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("app.services.notifier.deliveries_repo.create_delivery", AsyncMock())
    monkeypatch.setattr("app.services.notifier._log_delivery", AsyncMock())
    monkeypatch.setattr(
        "app.services.notifier.build_event_actions",
        lambda _event, _lang="ru": object(),
    )

    format_calls = 0

    def _format_message(event: Event, *, lang: str) -> str:
        nonlocal format_calls
        format_calls += 1
        return f"{event.event_key}:{lang}"

    monkeypatch.setattr("app.services.notifier.format_event_message", _format_message)

    await notifier.process_events(session, [_event("AAA")])

    assert format_calls == 1
    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_notifier_normalizes_filters_once_per_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users = [SimpleNamespace(id=1001, settings={})]
    session = MagicMock()
    session.flush = AsyncMock()

    bot = SimpleNamespace(send_message=AsyncMock())
    dedup = SimpleNamespace(check_delivery=AsyncMock(return_value=DedupDecision.ALLOW))
    notifier = EventNotifier(
        bot=bot,
        settings=_settings(),
        enrichment_service=SimpleNamespace(),
        dedup_service=dedup,
    )
    notifier._enrich_events = AsyncMock()  # type: ignore[method-assign]

    monkeypatch.setattr(
        "app.services.notifier.users_repo.list_all_users",
        AsyncMock(return_value=users),
    )
    monkeypatch.setattr(
        "app.services.notifier.mutes_repo.list_mutes_for_users",
        AsyncMock(return_value={1001: []}),
    )
    monkeypatch.setattr("app.services.notifier.event_passes_filters", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("app.services.notifier.deliveries_repo.create_delivery", AsyncMock())
    monkeypatch.setattr("app.services.notifier._log_delivery", AsyncMock())
    monkeypatch.setattr(
        "app.services.notifier.build_event_actions",
        lambda _event, _lang="ru": object(),
    )
    monkeypatch.setattr("app.services.notifier.format_event_message", lambda _event, *, lang: f"msg:{lang}")

    normalize_calls = 0

    def _normalize(settings: dict, app_settings: Settings) -> UserFilters:
        nonlocal normalize_calls
        normalize_calls += 1
        return UserFilters(
            enabled_exchanges={"binance"},
            enabled_market_types={"spot"},
            only_usdt=False,
            min_score=0,
        )

    monkeypatch.setattr("app.services.notifier.normalize_filters", _normalize)

    await notifier.process_events(session, [_event("AAA"), _event("BBB")])

    assert normalize_calls == 1
    assert bot.send_message.await_count == 2
