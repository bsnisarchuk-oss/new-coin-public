from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app.services.enrich import EnrichmentService


def _settings() -> Settings:
    return Settings(
        bot_token="token",
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        poll_interval_sec=60,
        dedup_ttl_hours=24,
        max_notifications_per_hour=20,
        min_vol_5m=10000.0,
        max_spread=0.02,
        bootstrap_on_empty=True,
        default_only_usdt=False,
        default_min_score=0,
        default_enabled_exchanges=("binance", "bybit"),
        default_enabled_market_types=("spot", "futures"),
        admin_id=None,
    )


def _response(payload: dict) -> AsyncMock:
    response = AsyncMock()
    response.raise_for_status = MagicMock()
    response.json = AsyncMock(return_value=payload)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    return response


@pytest.mark.asyncio
async def test_okx_spot_enrichment_uses_spot_instrument_id() -> None:
    service = EnrichmentService(_settings())
    fake_session = MagicMock()
    fake_session.closed = False
    fake_session.get.return_value = _response(
        {
            "data": [
                {
                    "bidPx": "99",
                    "askPx": "101",
                    "last": "100",
                    "volCcy24h": "288000",
                }
            ]
        }
    )
    service._session = fake_session

    enriched = await service._fetch_okx("BTC", "USDT", "spot")

    _, kwargs = fake_session.get.call_args
    assert kwargs["params"]["instId"] == "BTC-USDT"
    assert enriched["price"] == 100.0
    assert enriched["volume_5m"] == 1000.0
