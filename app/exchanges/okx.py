from __future__ import annotations

import logging

import aiohttp

from app.exchanges.base import ExchangeConnector, Instrument

LOGGER = logging.getLogger(__name__)

_INSTRUMENTS_URL = "https://www.okx.com/api/v5/public/instruments"


class OKXConnector(ExchangeConnector):
    name = "okx"
    supported_market_types = ("spot", "futures")

    async def fetch_instruments(self, market_type: str) -> list[Instrument]:
        inst_type = "SPOT" if market_type == "spot" else "SWAP"
        normalized = "spot" if market_type == "spot" else "futures"

        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                _INSTRUMENTS_URL, params={"instType": inst_type}
            ) as response:
                response.raise_for_status()
                payload = await response.json()

        out: list[Instrument] = []
        for item in payload.get("data", []):
            if not isinstance(item, dict):
                continue
            if item.get("state") != "live":
                continue

            if market_type == "spot":
                base = str(item.get("baseCcy", "")).upper()
                quote = str(item.get("quoteCcy", "")).upper()
            else:
                # SWAP: e.g. BTC-USDT-SWAP; ctValCcy = base coin, settleCcy = quote
                base = str(item.get("ctValCcy", "")).upper()
                quote = str(item.get("settleCcy", "")).upper()

            symbol = str(item.get("instId", "")).upper()
            if not base or not quote or not symbol:
                continue

            out.append(
                Instrument(
                    exchange=self.name,
                    market_type=normalized,
                    symbol=symbol,
                    base=base,
                    quote=quote,
                    raw=item,
                )
            )

        LOGGER.info("OKX %s instruments fetched: %s", market_type, len(out))
        return out
