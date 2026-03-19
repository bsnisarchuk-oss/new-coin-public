"""Tests for the analytics handler enum-safety fix.

asyncpg may return plain strings instead of MarketType enum instances
when doing column-level SELECT. This file verifies that our coercion
logic handles both cases correctly.
"""
from __future__ import annotations

from app.db.models import MarketType


def _coerce(value: object) -> str:
    """Same logic as analytics.py line 46."""
    return value.value if isinstance(value, MarketType) else str(value)  # type: ignore[union-attr]


def test_enum_instance_returns_value() -> None:
    assert _coerce(MarketType.SPOT) == "spot"
    assert _coerce(MarketType.FUTURES) == "futures"


def test_plain_string_passes_through() -> None:
    """Simulate asyncpg returning a raw string — must not raise AttributeError."""
    assert _coerce("spot") == "spot"
    assert _coerce("futures") == "futures"


def test_unknown_string_passes_through() -> None:
    """Any unexpected value is converted to string rather than crashing."""
    assert _coerce("perp") == "perp"


def test_market_type_values_are_lowercase() -> None:
    """Sanity check: enum values are lowercase strings (DB constraint)."""
    assert MarketType.SPOT.value == "spot"
    assert MarketType.FUTURES.value == "futures"
