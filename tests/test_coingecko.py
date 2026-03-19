"""Tests for CoinInfoService (CoinGecko integration)."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.coingecko import CoinInfoService, _MISS_TTL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service() -> CoinInfoService:
    svc = CoinInfoService()
    svc._session = MagicMock()  # Prevent "no session" early-return
    return svc


def _mock_response(status: int, json_data: dict):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


SEARCH_HIT = {
    "coins": [{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"}]
}

COIN_DATA = {
    "description": {"en": "Bitcoin is the first decentralized cryptocurrency."},
    "links": {"homepage": ["https://bitcoin.org", ""]},
    "genesis_date": "2009-01-03",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_coin_info_success():
    """Happy path: search + fetch return data."""
    svc = _make_service()
    svc._session.get.side_effect = [
        _mock_response(200, SEARCH_HIT),   # search call
        _mock_response(200, COIN_DATA),    # info call
    ]

    info = await svc.get_coin_info("BTC")

    assert info is not None
    assert "Bitcoin is the first" in info["description"]
    assert info["homepage"] == "https://bitcoin.org"
    assert info["genesis_year"] == "2009"


@pytest.mark.asyncio
async def test_cache_hit_avoids_second_request():
    """Second call for same symbol should use cache (no extra HTTP calls)."""
    svc = _make_service()
    svc._session.get.side_effect = [
        _mock_response(200, SEARCH_HIT),
        _mock_response(200, COIN_DATA),
    ]

    await svc.get_coin_info("BTC")
    call_count_after_first = svc._session.get.call_count

    # Second call — should be fully cached
    await svc.get_coin_info("BTC")
    assert svc._session.get.call_count == call_count_after_first


@pytest.mark.asyncio
async def test_miss_cache_prevents_retry():
    """Coin not found on CoinGecko → miss cache → no second request within TTL."""
    svc = _make_service()
    svc._session.get.return_value = _mock_response(200, {"coins": []})

    result1 = await svc.get_coin_info("NEWMEME")
    assert result1 is None

    call_count = svc._session.get.call_count

    # Second call within TTL should use miss cache, not hit API
    result2 = await svc.get_coin_info("NEWMEME")
    assert result2 is None
    assert svc._session.get.call_count == call_count


@pytest.mark.asyncio
async def test_miss_cache_retries_after_ttl():
    """After miss TTL expires the service tries CoinGecko again."""
    svc = _make_service()
    svc._session.get.return_value = _mock_response(200, {"coins": []})

    await svc.get_coin_info("MEME")
    # Expire the miss cache entry
    svc._miss_cache["MEME"] = time.monotonic() - _MISS_TTL - 1

    await svc.get_coin_info("MEME")
    # Should have made 2 search requests total
    assert svc._session.get.call_count == 2


@pytest.mark.asyncio
async def test_api_error_returns_none():
    """If CoinGecko returns non-200, get_coin_info returns None gracefully."""
    svc = _make_service()
    svc._session.get.return_value = _mock_response(429, {})

    result = await svc.get_coin_info("ETH")
    assert result is None


@pytest.mark.asyncio
async def test_html_stripped_from_description():
    """HTML tags in description should be stripped."""
    svc = _make_service()
    coin_data_with_html = {
        "description": {"en": "<p>Bitcoin is <b>great</b>.</p>"},
        "links": {"homepage": ["https://bitcoin.org"]},
        "genesis_date": None,
    }
    svc._session.get.side_effect = [
        _mock_response(200, SEARCH_HIT),
        _mock_response(200, coin_data_with_html),
    ]

    info = await svc.get_coin_info("BTC")
    assert info is not None
    assert "<" not in info["description"]
    assert "Bitcoin is great." in info["description"]


@pytest.mark.asyncio
async def test_description_truncated():
    """Descriptions longer than 200 chars should be truncated with ellipsis."""
    svc = _make_service()
    long_desc = "X" * 300
    coin_data_long = {
        "description": {"en": long_desc},
        "links": {"homepage": ["https://example.com"]},
        "genesis_date": None,
    }
    svc._session.get.side_effect = [
        _mock_response(200, SEARCH_HIT),
        _mock_response(200, coin_data_long),
    ]

    info = await svc.get_coin_info("BTC")
    assert info is not None
    assert len(info["description"]) <= 200
    assert info["description"].endswith("…")
