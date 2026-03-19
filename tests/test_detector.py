"""Tests for app.services.detector — core listing/delisting detection logic."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models import EventType, MarketType
from app.exchanges.base import Instrument
from app.services.detector import (
    MarketDetector,
    _event_type_from_market,
    _fetch_with_retry,
    _make_event,
    _market_type_from_name,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _instrument(base: str = "BTC", quote: str = "USDT", exchange: str = "binance") -> Instrument:
    return Instrument(
        exchange=exchange,
        market_type="spot",
        symbol=f"{base}{quote}",
        base=base,
        quote=quote,
        raw={},
    )


def _snapshot(symbol: str, base: str, quote: str) -> MagicMock:
    snap = MagicMock()
    snap.symbol = symbol
    snap.symbol_base = base
    snap.symbol_quote = quote
    return snap


def _connector(
    name: str = "binance",
    market_types: tuple[str, ...] = ("spot",),
    instruments: list[Instrument] | None = None,
) -> MagicMock:
    c = MagicMock()
    c.name = name
    c.supported_market_types = market_types
    c.fetch_instruments = AsyncMock(return_value=instruments or [])
    return c


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def test_market_type_from_name_spot() -> None:
    assert _market_type_from_name("spot") == MarketType.SPOT


def test_market_type_from_name_futures() -> None:
    assert _market_type_from_name("futures") == MarketType.FUTURES


def test_event_type_spot() -> None:
    assert _event_type_from_market(MarketType.SPOT) == EventType.SPOT_LISTING


def test_event_type_futures() -> None:
    assert _event_type_from_market(MarketType.FUTURES) == EventType.FUTURES_LISTING


def test_make_event_fields() -> None:
    inst = _instrument("ETH", "USDT")
    event = _make_event("binance", MarketType.SPOT, inst)

    assert event.exchange == "binance"
    assert event.symbol_base == "ETH"
    assert event.symbol_quote == "USDT"
    assert event.event_type == EventType.SPOT_LISTING
    assert event.market_type == MarketType.SPOT
    assert event.event_key == "binance:SPOT_LISTING:spot:ETH:USDT"
    assert event.score == 0
    assert event.enriched == {}
    assert event.flags == []


# ---------------------------------------------------------------------------
# _fetch_with_retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_retry_success_on_first_try() -> None:
    instruments = [_instrument()]
    connector = _connector(instruments=instruments)

    result = await _fetch_with_retry(connector, "spot", max_attempts=3)

    assert result == instruments
    connector.fetch_instruments.assert_called_once_with("spot")


@pytest.mark.asyncio
async def test_fetch_retry_success_on_second_attempt() -> None:
    instruments = [_instrument()]
    connector = _connector()
    connector.fetch_instruments = AsyncMock(
        side_effect=[Exception("timeout"), instruments]
    )

    with patch("app.services.detector.asyncio.sleep", new_callable=AsyncMock):
        result = await _fetch_with_retry(connector, "spot", max_attempts=3)

    assert result == instruments
    assert connector.fetch_instruments.call_count == 2


@pytest.mark.asyncio
async def test_fetch_retry_returns_none_after_all_failures() -> None:
    connector = _connector()
    connector.fetch_instruments = AsyncMock(side_effect=Exception("API down"))

    with patch("app.services.detector.asyncio.sleep", new_callable=AsyncMock):
        result = await _fetch_with_retry(connector, "spot", max_attempts=3)

    assert result is None
    assert connector.fetch_instruments.call_count == 3


# ---------------------------------------------------------------------------
# MarketDetector.detect_new_events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bootstrap_on_empty_returns_no_events() -> None:
    """First run with empty snapshots → bootstrap, no events emitted."""
    connector = _connector(instruments=[_instrument("BTC", "USDT")])
    detector = MarketDetector([connector], bootstrap_on_empty=True)
    session = MagicMock()

    with (
        patch(
            "app.services.detector.events_repo.list_known_snapshots",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.detector.events_repo.upsert_snapshots",
            new_callable=AsyncMock,
        ) as mock_upsert,
    ):
        events, delistings = await detector.detect_new_events(session)

    assert events == []
    assert delistings == []
    mock_upsert.assert_called_once()  # snapshots were saved


@pytest.mark.asyncio
async def test_new_instrument_creates_event() -> None:
    """Instrument absent from known snapshots → Event created."""
    # Both BTC (known) and NEW (new) are returned by the exchange
    connector = _connector(instruments=[_instrument("BTC", "USDT"), _instrument("NEW", "USDT")])
    detector = MarketDetector([connector], bootstrap_on_empty=True)

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    existing = _snapshot("BTCUSDT", "BTC", "USDT")  # BTC was already known

    with (
        patch(
            "app.services.detector.events_repo.list_known_snapshots",
            new_callable=AsyncMock,
            return_value=[existing],
        ),
        patch(
            "app.services.detector.events_repo.upsert_snapshots",
            new_callable=AsyncMock,
        ),
    ):
        events, delistings = await detector.detect_new_events(session)

    assert len(events) == 1
    assert events[0].symbol_base == "NEW"
    assert events[0].exchange == "binance"
    assert delistings == []
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_gone_instrument_creates_delisting_alert() -> None:
    """Symbol in snapshot but missing from exchange → DelistingAlert."""
    # Keep >5 instruments present so 1 gone stays below the 20% circuit-breaker threshold
    present = [_instrument(b, "USDT") for b in ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA"]]
    connector = _connector(instruments=present)
    detector = MarketDetector([connector])

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    known_snaps = [_snapshot(f"{b}USDT", b, "USDT") for b in ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA"]]
    # DOGE is in snapshot but not in current exchange response → delisted
    eth_snap = _snapshot("DOGEUSDT", "DOGE", "USDT")
    known_snaps.append(eth_snap)

    with (
        patch(
            "app.services.detector.events_repo.list_known_snapshots",
            new_callable=AsyncMock,
            return_value=known_snaps,
        ),
        patch(
            "app.services.detector.events_repo.upsert_snapshots",
            new_callable=AsyncMock,
        ),
    ):
        events, delistings = await detector.detect_new_events(session)

    assert events == []
    assert len(delistings) == 1
    assert delistings[0].symbol_base == "DOGE"
    assert delistings[0].exchange == "binance"
    assert delistings[0].market_type == MarketType.SPOT


@pytest.mark.asyncio
async def test_connector_failure_skipped_gracefully() -> None:
    """Connector fails all retries → no crash, no events, no delistings."""
    connector = _connector()
    connector.fetch_instruments = AsyncMock(side_effect=Exception("exchange down"))
    detector = MarketDetector([connector])

    session = MagicMock()

    with patch("app.services.detector.asyncio.sleep", new_callable=AsyncMock):
        events, delistings = await detector.detect_new_events(session)

    assert events == []
    assert delistings == []


@pytest.mark.asyncio
async def test_multiple_connectors_independent() -> None:
    """Two connectors: one has new listing, other fails → only 1 event."""
    good_connector = _connector("binance", instruments=[_instrument("NEW", "USDT")])
    bad_connector = _connector("okx")
    bad_connector.fetch_instruments = AsyncMock(side_effect=Exception("down"))
    bad_connector.supported_market_types = ("spot",)

    detector = MarketDetector([good_connector, bad_connector])
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    existing = _snapshot("BTCUSDT", "BTC", "USDT")

    with (
        patch(
            "app.services.detector.events_repo.list_known_snapshots",
            new_callable=AsyncMock,
            return_value=[existing],
        ),
        patch(
            "app.services.detector.events_repo.upsert_snapshots",
            new_callable=AsyncMock,
        ),
        patch("app.services.detector.asyncio.sleep", new_callable=AsyncMock),
    ):
        events, delistings = await detector.detect_new_events(session)

    assert len(events) == 1
    assert events[0].exchange == "binance"
