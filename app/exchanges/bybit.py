from __future__ import annotations

import logging
from typing import Any

import aiohttp

from app.exchanges.base import ExchangeConnector, Instrument

LOGGER = logging.getLogger(__name__)


class BybitConnector(ExchangeConnector):
    name = "bybit"
    supported_market_types = ("spot", "futures")
    _url = "https://api.bybit.com/v5/market/instruments-info"

    async def fetch_instruments(self, market_type: str) -> list[Instrument]:
        category = "spot" if market_type == "spot" else "linear"
        timeout = aiohttp.ClientTimeout(total=20)
        items: list[dict[str, Any]] = []
        cursor = ""

        async with aiohttp.ClientSession(timeout=timeout) as session:
            while True:
                params = {"category": category, "limit": 1000}
                if cursor:
                    params["cursor"] = cursor
                async with session.get(self._url, params=params) as response:
                    response.raise_for_status()
                    payload = await response.json()
                result = payload.get("result") or {}
                page = result.get("list") or []
                if isinstance(page, list):
                    items.extend(x for x in page if isinstance(x, dict))
                cursor = str(result.get("nextPageCursor") or "")
                if not cursor:
                    break

        out: list[Instrument] = []
        normalized_market_type = "spot" if market_type == "spot" else "futures"
        for item in items:
            status = str(item.get("status", "")).lower()
            if status and status not in {"trading", "settling"}:
                continue
            symbol = str(item.get("symbol", "")).upper()
            base = str(item.get("baseCoin", "")).upper()
            quote = str(item.get("quoteCoin", "")).upper()
            if not symbol or not base or not quote:
                continue
            out.append(
                Instrument(
                    exchange=self.name,
                    market_type=normalized_market_type,
                    symbol=symbol,
                    base=base,
                    quote=quote,
                    raw=item,
                )
            )

        LOGGER.info("Bybit %s instruments fetched: %s", category, len(out))
        return out

