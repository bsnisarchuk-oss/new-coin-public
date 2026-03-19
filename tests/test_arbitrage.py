"""Tests for ArbitrageService caching behaviour (no real HTTP calls)."""
from __future__ import annotations

import time

import pytest

from app.services.arbitrage import ArbitrageResult, ArbitrageService, _CACHE_TTL_SEC


def _make_result(**prices: float) -> ArbitrageResult:
    return ArbitrageResult(prices=prices)


@pytest.mark.asyncio
async def test_cache_hit_returns_same_object() -> None:
    """Second call within TTL must return the cached result without HTTP calls."""
    service = ArbitrageService()
    fake = _make_result(binance=100.0, bybit=101.0)
    service._cache[("BTC", "USDT")] = (fake, time.monotonic())

    result = await service.fetch_all_prices("BTC", "USDT")
    assert result is fake


@pytest.mark.asyncio
async def test_cache_miss_on_expired_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Expired cache entry should trigger a fresh fetch."""
    service = ArbitrageService()
    fake = _make_result(binance=100.0)
    # Timestamp far in the past — already expired
    service._cache[("ETH", "USDT")] = (fake, time.monotonic() - _CACHE_TTL_SEC - 1)

    gathered: list[str] = []

    async def _mock_binance(base: str, quote: str):  # noqa: ANN001
        gathered.append("binance")
        return ("binance", 99.0)

    async def _noop(base: str, quote: str):  # noqa: ANN001
        return None

    monkeypatch.setattr(service, "_binance", _mock_binance)
    monkeypatch.setattr(service, "_bybit", _noop)
    monkeypatch.setattr(service, "_okx", _noop)
    monkeypatch.setattr(service, "_mexc", _noop)
    monkeypatch.setattr(service, "_coinbase", _noop)

    result = await service.fetch_all_prices("ETH", "USDT")
    assert gathered == ["binance"], "Fresh HTTP call should have been made"
    assert result.prices == {"binance": 99.0}


@pytest.mark.asyncio
async def test_cache_key_is_case_insensitive() -> None:
    """Cache key normalises base/quote to uppercase."""
    service = ArbitrageService()
    fake = _make_result(binance=50.0)
    service._cache[("SOL", "USDT")] = (fake, time.monotonic())

    result = await service.fetch_all_prices("sol", "usdt")
    assert result is fake


def test_arbitrage_result_spread_calculation() -> None:
    """Spread percentage is computed correctly for known prices."""
    prices = {"binance": 100.0, "bybit": 102.0}
    max_p, min_p = max(prices.values()), min(prices.values())
    spread = (max_p - min_p) / min_p * 100
    assert round(spread, 4) == 2.0
