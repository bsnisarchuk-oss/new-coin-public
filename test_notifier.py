"""Tests for app.services.formatter — message formatting (pure functions, no I/O)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import Event, EventType, MarketType
from app.services.formatter import fmt_price as _fmt_price, format_event_message


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _event(**kwargs) -> Event:
    defaults = dict(
        exchange="binance",
        event_type=EventType.SPOT_LISTING,
        market_type=MarketType.SPOT,
        symbol_base="BTC",
        symbol_quote="USDT",
        first_seen_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        event_key="binance:SPOT_LISTING:spot:BTC:USDT",
        pairs=["BTCUSDT"],
        meta={},
        enriched={},
        score=45,
        flags=[],
    )
    defaults.update(kwargs)
    return Event(**defaults)


# ---------------------------------------------------------------------------
# _fmt_price
# ---------------------------------------------------------------------------

def test_fmt_price_large_value() -> None:
    assert _fmt_price(65000.5) == "65,000.50"


def test_fmt_price_medium_value() -> None:
    assert _fmt_price(1.5) == "1.5"


def test_fmt_price_medium_no_trailing_zeros() -> None:
    result = _fmt_price(1.23456)
    assert result == "1.2346"


def test_fmt_price_small_value_no_trailing_zeros() -> None:
    result = _fmt_price(0.00001234)
    assert result.startswith("0.")
    assert not result.endswith("0")
    assert "1234" in result


def test_fmt_price_exactly_one_thousand() -> None:
    assert _fmt_price(1000.0) == "1,000.00"


# ---------------------------------------------------------------------------
# format_event_message — basic structure
# ---------------------------------------------------------------------------

def test_format_basic_event_header() -> None:
    msg = format_event_message(_event())
    assert "BTC/USDT" in msg
    assert "Binance" in msg
    assert "Score: 45/100" in msg
    assert "2026-03-01 12:00" in msg


def test_format_no_enrichment_shows_na() -> None:
    msg = format_event_message(_event())
    assert "Metrics: n/a" in msg


def test_format_no_flags_shows_dash() -> None:
    msg = format_event_message(_event(flags=[]))
    assert "Flags: -" in msg


def test_format_flags_shown() -> None:
    msg = format_event_message(_event(flags=["LOW_LIQUIDITY", "HIGH_SPREAD"]))
    assert "LOW_LIQUIDITY, HIGH_SPREAD" in msg


def test_format_futures_event_type_label() -> None:
    msg = format_event_message(
        _event(event_type=EventType.FUTURES_LISTING, market_type=MarketType.FUTURES)
    )
    assert "FUTURES LISTING" in msg


def test_format_spot_event_type_label() -> None:
    msg = format_event_message(_event(event_type=EventType.SPOT_LISTING))
    assert "SPOT LISTING" in msg


# ---------------------------------------------------------------------------
# format_event_message — enrichment metrics
# ---------------------------------------------------------------------------

def test_format_with_price_shows_metric() -> None:
    msg = format_event_message(_event(enriched={"price": 65000.0}))
    assert "Price:" in msg
    assert "Metrics: n/a" not in msg


def test_format_with_all_metrics() -> None:
    msg = format_event_message(
        _event(enriched={"price": 65000.0, "volume_5m": 120000.0, "spread": 0.0008})
    )
    assert "Price:" in msg
    assert "Vol(5m):" in msg
    assert "Spread:" in msg


# ---------------------------------------------------------------------------
# format_event_message — arbitrage block
# ---------------------------------------------------------------------------

def test_format_arbitrage_block_shown_with_two_exchanges() -> None:
    msg = format_event_message(
        _event(
            enriched={
                "arb_prices": {"binance": 65000.0, "bybit": 65010.0},
                "arb_spread_pct": 0.015,
                "arb_cheapest": "binance",
                "arb_most_expensive": "bybit",
            }
        )
    )
    assert "💱 Цены на биржах:" in msg
    assert "Binance" in msg
    assert "Bybit" in msg
    assert "Арб. спред:" in msg


def test_format_arbitrage_cheapest_marked_down() -> None:
    msg = format_event_message(
        _event(
            enriched={
                "arb_prices": {"binance": 65000.0, "bybit": 65010.0},
                "arb_cheapest": "binance",
                "arb_most_expensive": "bybit",
            }
        )
    )
    # Cheapest marked with ↓, most expensive with ↑
    assert "↓" in msg
    assert "↑" in msg


def test_format_arbitrage_block_hidden_with_one_exchange() -> None:
    """Only 1 exchange price → arbitrage block must not appear."""
    msg = format_event_message(
        _event(enriched={"arb_prices": {"binance": 65000.0}})
    )
    assert "💱 Цены на биржах:" not in msg


def test_format_arbitrage_block_hidden_when_empty() -> None:
    msg = format_event_message(_event(enriched={"arb_prices": {}}))
    assert "💱 Цены на биржах:" not in msg


# ---------------------------------------------------------------------------
# format_event_message — CoinGecko coin_info block
# ---------------------------------------------------------------------------

def test_format_coin_info_full_block() -> None:
    msg = format_event_message(
        _event(
            enriched={
                "coin_info": {
                    "genesis_year": 2020,
                    "description": "A DeFi token for swaps",
                    "homepage": "https://example.com",
                }
            }
        )
    )
    assert "🪙 О монете:" in msg
    assert "Запущен: 2020" in msg
    assert "A DeFi token for swaps" in msg
    assert "https://example.com" in msg


def test_format_coin_info_partial_only_homepage() -> None:
    msg = format_event_message(
        _event(enriched={"coin_info": {"homepage": "https://example.com"}})
    )
    assert "🪙 О монете:" in msg
    assert "Запущен" not in msg
    assert "https://example.com" in msg


def test_format_coin_info_absent_no_block() -> None:
    msg = format_event_message(_event(enriched={}))
    assert "🪙 О монете:" not in msg


# ---------------------------------------------------------------------------
# format_event_message — exchange name capitalisation
# ---------------------------------------------------------------------------

def test_format_exchange_name_capitalised() -> None:
    msg = format_event_message(_event(exchange="mexc"))
    assert "Mexc" in msg


def test_format_non_usdt_pair() -> None:
    """Non-USDT quote currency appears correctly in the pair label."""
    msg = format_event_message(_event(symbol_base="ETH", symbol_quote="BTC"))
    assert "ETH/BTC" in msg
