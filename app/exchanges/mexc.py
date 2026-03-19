from __future__ import annotations

import logging

import aiohttp

from app.exchanges.base import ExchangeConnector, Instrument

LOGGER = logging.getLogger(__name__)

_SPOT_URL = "https://api.mexc.com/api/v3/exchangeInfo"
_FUTURES_URL = "https://contract.mexc.com/api/v1/contract/detail"


class MEXCConnector(ExchangeConnector):
    name = "mexc"
    supported_market_types = ("spot", "futures")

    async def fetch_instruments(self, market_type: str) -> list[Instrument]:
        timeout = aiohttp.ClientTimeout(total=20)
        out: list[Instrument] = []

        async with aiohttp.ClientSession(timeout=timeout) as session:
            if market_type == "spot":
                async with session.get(_SPOT_URL) as response:
                    response.raise_for_status()
                    payload = await response.json()

                for item in payload.get("symbols", []):
                    if not isinstance(item, dict):
                        continue
                    if str(item.get("status", "")) != "1":
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

            else:
                async with session.get(_FUTURES_URL) as response:
                    response.raise_for_status()
                    payload = await response.json()

                for item in (payload.get("data") or []):
                    if not isinstance(item, dict):
                        continue
                    # state 0 = enabled
                    if item.get("state") != 0:
                        continue
                    base = str(item.get("baseCoin", "")).upper()
                    quote = str(item.get("quoteCoin", "")).upper()
                    symbol = str(item.get("symbol", "")).upper()
                    if not base or not quote or not symbol:
                        continue
                    out.append(
                        Instrument(
                            exchange=self.name,
                            market_type="futures",
                            symbol=symbol,
                            base=base,
                            quote=quote,
                            raw=item,
                        )
                    )

        LOGGER.info("MEXC %s instruments fetched: %s", market_type, len(out))
        return out
