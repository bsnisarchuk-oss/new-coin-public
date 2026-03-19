from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import health, metrics
from app.db.models import MarketType
from app.db.repo import analytics as analytics_repo
from app.db.repo import state as state_repo
from app.db.repo import watchlist as watchlist_repo
from app.db.repo import events as events_repo
from app.exchanges.base import Instrument


def _scalar_result(*, one: object | None = None, optional: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        scalar_one=lambda: one,
        scalar_one_or_none=lambda: optional,
    )


@pytest.mark.asyncio
async def test_health_handle_reflects_readiness_state() -> None:
    health.set_readiness(False, phase="startup")
    response = await health._handle(MagicMock())
    payload = json.loads(response.text)
    assert payload["status"] == "starting"
    assert payload["phase"] == "startup"

    health.set_readiness(True, phase="ready")
    response = await health._handle(MagicMock())
    payload = json.loads(response.text)
    assert payload["status"] == "ok"
    assert payload["ready"] is True
    assert payload["phase"] == "ready"
    assert payload["uptime_sec"] >= 0


@pytest.mark.asyncio
async def test_start_health_server_registers_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = AsyncMock()
    start = AsyncMock()
    runner = SimpleNamespace(setup=setup)
    app = SimpleNamespace(router=SimpleNamespace(add_get=MagicMock()))
    runner_factory = MagicMock(return_value=runner)
    site_factory = MagicMock(return_value=SimpleNamespace(start=start))
    monkeypatch.setattr("app.health.web.Application", MagicMock(return_value=app))
    monkeypatch.setattr("app.health.web.AppRunner", runner_factory)
    monkeypatch.setattr("app.health.web.TCPSite", site_factory)

    result = await health.start_health_server(port=18080)

    assert result is runner
    assert app.router.add_get.call_count == 2
    setup.assert_awaited_once()
    site_factory.assert_called_once_with(runner, "0.0.0.0", 18080)
    start.assert_awaited_once()


def test_start_metrics_server_covers_disabled_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    assert metrics.start_metrics_server(0) is False

    starter = MagicMock()
    monkeypatch.setattr("app.metrics.start_http_server", starter)
    assert metrics.start_metrics_server(9100) is True
    starter.assert_called_once_with(9100)

    monkeypatch.setattr("app.metrics.start_http_server", MagicMock(side_effect=OSError("busy")))
    assert metrics.start_metrics_server(9101) is False


@pytest.mark.asyncio
async def test_watchlist_repo_add_watch_handles_duplicate_limit_and_success() -> None:
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            _scalar_result(optional=1),
            _scalar_result(optional=None),
            _scalar_result(one=watchlist_repo._MAX_WATCHLIST_SIZE),
            _scalar_result(optional=None),
            _scalar_result(one=1),
        ]
    )
    session.flush = AsyncMock()
    session.add = MagicMock()

    assert await watchlist_repo.add_watch(session, 1, "btc") is False
    assert await watchlist_repo.add_watch(session, 1, "eth") is False
    assert await watchlist_repo.add_watch(session, 1, "sol") is True
    session.flush.assert_awaited_once()
    added = session.add.call_args.args[0]
    assert added.symbol_base == "SOL"


@pytest.mark.asyncio
async def test_watchlist_repo_query_helpers() -> None:
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(rowcount=1),
            SimpleNamespace(fetchall=lambda: [("BTC",), ("ETH",)]),
            SimpleNamespace(fetchall=lambda: [("BTC", 1), ("BTC", 2), ("ETH", 3)]),
            SimpleNamespace(fetchall=lambda: [("BTC", 1), ("BTC", 4)]),
        ]
    )

    assert await watchlist_repo.remove_watch(session, 7, "btc") is True
    assert await watchlist_repo.list_watchlist(session, 7) == ["BTC", "ETH"]
    assert await watchlist_repo.find_all_watched(session) == {"BTC": [1, 2], "ETH": [3]}
    assert await watchlist_repo.find_users_watching(session, []) == {}
    assert await watchlist_repo.find_users_watching(session, ["btc"]) == {"BTC": [1, 4]}


@pytest.mark.asyncio
async def test_analytics_repo_log_event_normalizes_fields() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    session.add = MagicMock()

    event = await analytics_repo.log_event(
        session,
        event_name="button_click",
        source="callback",
        user_id=5,
        exchange="OKX",
        market_type="FUTURES",
        placement="menu",
        button_id="open",
        properties={"a": 1},
    )

    session.add.assert_called_once_with(event)
    session.flush.assert_awaited_once()
    assert event.exchange == "okx"
    assert event.market_type == "futures"
    assert event.properties == {"a": 1}


@pytest.mark.asyncio
async def test_state_repo_get_and_set_payload() -> None:
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalar_one_or_none=lambda: {"seen": [1]}),
            SimpleNamespace(scalar_one_or_none=lambda: None),
            None,
        ]
    )

    assert await state_repo.get_payload(session, "ann", "seen") == {"seen": [1]}
    assert await state_repo.get_payload(session, "ann", "missing") is None
    await state_repo.set_payload(session, "ann", "seen", {"seen": [2]})
    assert session.execute.await_count == 3


@pytest.mark.asyncio
async def test_upsert_snapshots_prunes_missing_symbols_before_upsert() -> None:
    session = MagicMock()
    session.execute = AsyncMock()
    instruments = [
        Instrument(
            exchange="binance",
            market_type="spot",
            symbol="BTCUSDT",
            base="BTC",
            quote="USDT",
            raw={},
        )
    ]

    await events_repo.upsert_snapshots(
        session,
        exchange="binance",
        market_type=MarketType.SPOT,
        instruments=instruments,
    )

    assert session.execute.await_count == 2
    delete_stmt = session.execute.await_args_list[0].args[0]
    upsert_stmt = session.execute.await_args_list[1].args[0]
    delete_sql = str(delete_stmt)
    upsert_sql = str(upsert_stmt)
    assert "DELETE FROM market_snapshots" in delete_sql
    assert "NOT IN" in delete_sql
    assert "INSERT INTO market_snapshots" in upsert_sql
