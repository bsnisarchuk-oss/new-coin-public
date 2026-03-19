"""Cross-exchange price comparison for arbitrage detection."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

LOGGER = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=10)
_CACHE_TTL_SEC = 90  # не обращаемся к биржам чаще раза в 90 секунд для одного символа


@dataclass
class ArbitrageResult:
    prices: dict[str, float] = field(default_factory=dict)  # exchange -> mid price
    spread_pct: float | None = None  # (max - min) / min * 100
    cheapest: str | None = None
    most_expensive: str | None = None


def _f(value: object) -> float | None:
    """Convert value to positive float or return None."""
    if value is None:
        return None
    try:
        v = float(value)  # type: ignore[arg-type]
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _mid(bid: float | None, ask: float | None) -> float | None:
    if bid is not None and ask is not None:
        return (bid + ask) / 2
    return None


class ArbitrageService:
    """Fetches mid-prices from all supported exchanges in parallel."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None
        # cache: (base, quote) -> (ArbitrageResult, timestamp)
        self._cache: dict[tuple[str, str], tuple[ArbitrageResult, float]] = {}

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(timeout=_TIMEOUT)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            LOGGER.warning("ArbitrageService used before start(); creating temporary session")
            return aiohttp.ClientSession(timeout=_TIMEOUT)
        return self._session

    async def fetch_all_prices(self, base: str, quote: str) -> ArbitrageResult:
        """Fetch prices from all exchanges in parallel and compute arbitrage spread."""
        cache_key = (base.upper(), quote.upper())
        cached, ts = self._cache.get(cache_key, (None, 0.0))
        if cached is not None and (time.monotonic() - ts) < _CACHE_TTL_SEC:
            return cached

        tasks = [
            self._binance(base, quote),
            self._bybit(base, quote),
            self._okx(base, quote),
            self._mexc(base, quote),
            self._coinbase(base, quote),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        prices: dict[str, float] = {}
        for r in results:
            if isinstance(r, Exception) or r is None:
                continue
            exchange, price = r
            prices[exchange] = price

        if len(prices) >= 2:
            max_price = max(prices.values())
            min_price = min(prices.values())
            spread_pct = (max_price - min_price) / min_price * 100 if min_price > 0 else None
            cheapest = min(prices, key=lambda k: prices[k])
            most_expensive = max(prices, key=lambda k: prices[k])
        else:
            spread_pct = None
            cheapest = next(iter(prices), None)
            most_expensive = next(iter(prices), None)

        result = ArbitrageResult(
            prices=prices,
            spread_pct=spread_pct,
            cheapest=cheapest,
            most_expensive=most_expensive,
        )
        self._cache[cache_key] = (result, time.monotonic())
        return result

    # ──────────────────────────────────────────── exchange fetchers ──────

    async def _binance(self, base: str, quote: str) -> Optional[tuple[str, float]]:
        symbol = f"{base}{quote}".upper()
        try:
            session = self._get_session()
            async with session.get(
                "https://api.binance.com/api/v3/ticker/bookTicker",
                params={"symbol": symbol},
            ) as r:
                if r.status != 200:
                    return None
                data = await r.json()
            price = _mid(_f(data.get("bidPrice")), _f(data.get("askPrice")))
            return ("binance", price) if price else None
        except Exception as e:
            LOGGER.debug("Binance arb error %s%s: %s", base, quote, e)
            return None

    async def _bybit(self, base: str, quote: str) -> Optional[tuple[str, float]]:
        symbol = f"{base}{quote}".upper()
        try:
            session = self._get_session()
            async with session.get(
                "https://api.bybit.com/v5/market/tickers",
                params={"category": "spot", "symbol": symbol},
            ) as r:
                if r.status != 200:
                    return None
                data = await r.json()
            rows = (data.get("result") or {}).get("list") or []
            row = rows[0] if rows else {}
            price = _mid(_f(row.get("bid1Price")), _f(row.get("ask1Price"))) or _f(row.get("lastPrice"))
            return ("bybit", price) if price else None
        except Exception as e:
            LOGGER.debug("Bybit arb error %s%s: %s", base, quote, e)
            return None

    async def _okx(self, base: str, quote: str) -> Optional[tuple[str, float]]:
        inst_id = f"{base}-{quote}".upper()  # e.g. BTC-USDT
        try:
            session = self._get_session()
            async with session.get(
                "https://www.okx.com/api/v5/market/ticker",
                params={"instId": inst_id},
            ) as r:
                if r.status != 200:
                    return None
                data = await r.json()
            items = data.get("data") or []
            item = items[0] if items else {}
            price = _mid(_f(item.get("bidPx")), _f(item.get("askPx"))) or _f(item.get("last"))
            return ("okx", price) if price else None
        except Exception as e:
            LOGGER.debug("OKX arb error %s-%s: %s", base, quote, e)
            return None

    async def _mexc(self, base: str, quote: str) -> Optional[tuple[str, float]]:
        symbol = f"{base}{quote}".upper()
        try:
            session = self._get_session()
            async with session.get(
                "https://api.mexc.com/api/v3/ticker/bookTicker",
                params={"symbol": symbol},
            ) as r:
                if r.status != 200:
                    return None
                data = await r.json()
            price = _mid(_f(data.get("bidPrice")), _f(data.get("askPrice")))
            return ("mexc", price) if price else None
        except Exception as e:
            LOGGER.debug("MEXC arb error %s%s: %s", base, quote, e)
            return None

    async def _coinbase(self, base: str, quote: str) -> Optional[tuple[str, float]]:
        # Coinbase uses USD, not USDT
        cb_quote = "USD" if quote.upper() == "USDT" else quote.upper()
        product_id = f"{base.upper()}-{cb_quote}"
        try:
            session = self._get_session()
            async with session.get(
                f"https://api.exchange.coinbase.com/products/{product_id}/ticker"
            ) as r:
                if r.status != 200:
                    return None
                data = await r.json()
            price = _mid(_f(data.get("bid")), _f(data.get("ask"))) or _f(data.get("price"))
            return ("coinbase", price) if price else None
        except Exception as e:
            LOGGER.debug("Coinbase arb error %s-%s: %s", base, cb_quote, e)
            return None
