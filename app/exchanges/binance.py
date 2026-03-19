from __future__ import annotations

import logging

import aiohttp

from app.exchanges.base import ExchangeConnector, Instrument

LOGGER = logging.getLogger(__name__)


class BinanceConnector(ExchangeConnector):
    name = "binance"
    supported_market_types = ("spot",)
    _exchange_info_url = "https://api.binance.com/api/v3/exchangeInfo"

    async def fetch_instruments(self, market_type: str) -> list[Instrument]:
        if market_type != "spot":
            return []

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(self._exchange_info_url) as response:
                response.raise_for_status()
                payload = await response.json()

        out: list[Instrument] = []
        for item in payload.get("symbols", []):
            if not isinstance(item, dict):
                continue
            if item.get("status") != "TRADING":
                continue
            base = str(item.get("baseAsset", "")).upper()
            quote = str(item.get("quoteAsset", "")).upper()
            symbol = str(item.get("symbol", "")).upper()
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
        LOGGER.info("Binance spot instruments fetched: %s", len(out))
        return out

