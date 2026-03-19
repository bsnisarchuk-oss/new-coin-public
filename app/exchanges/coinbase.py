from __future__ import annotations

import logging

import aiohttp

from app.exchanges.base import ExchangeConnector, Instrument

LOGGER = logging.getLogger(__name__)

# Public REST API — no authentication required.
_PRODUCTS_URL = "https://api.exchange.coinbase.com/products"


class CoinbaseConnector(ExchangeConnector):
    name = "coinbase"
    supported_market_types = ("spot",)

    async def fetch_instruments(self, market_type: str) -> list[Instrument]:
        if market_type != "spot":
            return []

        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                _PRODUCTS_URL,
                headers={"Accept": "application/json"},
            ) as response:
                response.raise_for_status()
                payload: list[dict] = await response.json()

        out: list[Instrument] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            # Skip disabled or non-online pairs
            if item.get("status") != "online":
                continue
            if item.get("trading_disabled"):
                continue
            base = str(item.get("base_currency", "")).upper()
            quote = str(item.get("quote_currency", "")).upper()
            symbol = str(item.get("id", "")).upper()  # e.g. "BTC-USD"
            if not base or not quote or not symbol:
                continue
            out.append(
                Instrument(
                    exchange=self.name,
                    market_type="spot",
                    symbol=symbol,
                    base=base,
                    quote=quote,
                    raw=item,
                )
            )

        LOGGER.info("Coinbase spot instruments fetched: %s", len(out))
        return out
