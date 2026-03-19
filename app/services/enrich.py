from __future__ import annotations

import logging
from typing import Any

import aiohttp

from app.config import Settings

LOGGER = logging.getLogger(__name__)

_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class EnrichmentService:
    def __init__(self, settings: Settings) -> None:
        self._min_vol_5m = settings.min_vol_5m
        self._max_spread = settings.max_spread
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        """Create the shared HTTP session. Call once before first use."""
        self._session = aiohttp.ClientSession(timeout=_HTTP_TIMEOUT)

    async def close(self) -> None:
        """Close the shared HTTP session on shutdown."""
        if self._session is not None:
            await self._session.close()
            self._session = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # Fallback: create a temporary session if called before start()
            LOGGER.warning("EnrichmentService used before start(); creating a temporary session")
            return aiohttp.ClientSession(timeout=_HTTP_TIMEOUT)
        return self._session

    async def enrich_event(
        self,
        exchange: str,
        market_type: str,
        symbol: str,
        base: str,
        quote: str,
    ) -> tuple[dict[str, Any], list[str]]:
        enriched: dict[str, Any] = {"usdt_pair": quote.upper() == "USDT"}
        flags: list[str] = []

        try:
            exch = exchange.lower()
            if exch == "binance":
                enriched.update(await self._fetch_binance(symbol))
            elif exch == "bybit":
                enriched.update(await self._fetch_bybit(symbol, market_type))
            elif exch == "okx":
                enriched.update(await self._fetch_okx(base, quote, market_type))
            elif exch == "mexc":
                enriched.update(await self._fetch_mexc(symbol))
            elif exch == "coinbase":
                enriched.update(await self._fetch_coinbase(base, quote))
        except Exception:
            LOGGER.exception("Failed to enrich event for %s %s", exchange, symbol)

        if quote.upper() != "USDT":
            flags.append("NO_USDT_PAIR")

        volume_5m = _to_float(enriched.get("volume_5m"))
        spread = _to_float(enriched.get("spread"))
        if volume_5m is not None and volume_5m < self._min_vol_5m:
            flags.append("LOW_LIQUIDITY")
        if spread is not None and spread > self._max_spread:
            flags.append("HIGH_SPREAD")

        return enriched, flags

    async def _fetch_binance(self, symbol: str) -> dict[str, Any]:
        book_url = "https://api.binance.com/api/v3/ticker/bookTicker"
        stats_url = "https://api.binance.com/api/v3/ticker/24hr"
        session = self._get_session()
        async with session.get(book_url, params={"symbol": symbol}) as r:
            r.raise_for_status()
            book = await r.json()
        async with session.get(stats_url, params={"symbol": symbol}) as r:
            r.raise_for_status()
            stats = await r.json()

        bid = _to_float(book.get("bidPrice"))
        ask = _to_float(book.get("askPrice"))
        price = _to_float(stats.get("lastPrice"))
        quote_volume_24h = _to_float(stats.get("quoteVolume"))
        volume_5m = quote_volume_24h / 288 if quote_volume_24h is not None else None
        spread = self._calc_spread(bid, ask)
        return {"price": price, "volume_5m": volume_5m, "spread": spread}

    async def _fetch_bybit(self, symbol: str, market_type: str) -> dict[str, Any]:
        category = "spot" if market_type == "spot" else "linear"
        url = "https://api.bybit.com/v5/market/tickers"
        session = self._get_session()
        async with session.get(url, params={"category": category, "symbol": symbol}) as r:
            r.raise_for_status()
            payload = await r.json()

        result = payload.get("result") or {}
        rows = result.get("list") or []
        row = rows[0] if rows else {}
        bid = _to_float(row.get("bid1Price"))
        ask = _to_float(row.get("ask1Price"))
        price = _to_float(row.get("lastPrice"))
        turnover_24h = _to_float(row.get("turnover24h"))
        volume_5m = turnover_24h / 288 if turnover_24h is not None else None
        spread = self._calc_spread(bid, ask)
        return {"price": price, "volume_5m": volume_5m, "spread": spread}

    async def _fetch_okx(self, base: str, quote: str, market_type: str) -> dict[str, Any]:
        inst_type = "SWAP" if market_type == "futures" else "SPOT"
        inst_id = (
            f"{base.upper()}-{quote.upper()}-SWAP"
            if inst_type == "SWAP"
            else f"{base.upper()}-{quote.upper()}"
        )
        url = "https://www.okx.com/api/v5/market/ticker"
        session = self._get_session()
        async with session.get(url, params={"instId": inst_id}) as r:
            r.raise_for_status()
            payload = await r.json()

        data = (payload.get("data") or [{}])[0]
        bid = _to_float(data.get("bidPx"))
        ask = _to_float(data.get("askPx"))
        price = _to_float(data.get("last"))
        # volCcy24h = 24h quote-currency volume for SPOT (USDT equivalent)
        vol_ccy_24h = _to_float(data.get("volCcy24h"))
        volume_5m = vol_ccy_24h / 288 if vol_ccy_24h is not None else None
        spread = self._calc_spread(bid, ask)
        return {"price": price, "volume_5m": volume_5m, "spread": spread}

    async def _fetch_mexc(self, symbol: str) -> dict[str, Any]:
        book_url = "https://api.mexc.com/api/v3/ticker/bookTicker"
        stats_url = "https://api.mexc.com/api/v3/ticker/24hr"
        session = self._get_session()
        async with session.get(book_url, params={"symbol": symbol}) as r:
            r.raise_for_status()
            book = await r.json()
        async with session.get(stats_url, params={"symbol": symbol}) as r:
            r.raise_for_status()
            stats = await r.json()

        bid = _to_float(book.get("bidPrice"))
        ask = _to_float(book.get("askPrice"))
        price = _to_float(stats.get("lastPrice"))
        quote_volume_24h = _to_float(stats.get("quoteVolume"))
        volume_5m = quote_volume_24h / 288 if quote_volume_24h is not None else None
        spread = self._calc_spread(bid, ask)
        return {"price": price, "volume_5m": volume_5m, "spread": spread}

    async def _fetch_coinbase(self, base: str, quote: str) -> dict[str, Any]:
        # Coinbase uses USD, not USDT
        cb_quote = "USD" if quote.upper() == "USDT" else quote.upper()
        product_id = f"{base.upper()}-{cb_quote}"
        url = f"https://api.exchange.coinbase.com/products/{product_id}/ticker"
        session = self._get_session()
        async with session.get(url) as r:
            r.raise_for_status()
            data = await r.json()
        bid = _to_float(data.get("bid"))
        ask = _to_float(data.get("ask"))
        price = _to_float(data.get("price"))
        # Coinbase volume is 24h base volume; convert to approximate quote volume
        base_volume_24h = _to_float(data.get("volume"))
        volume_5m = (base_volume_24h * price / 288) if (base_volume_24h and price) else None
        spread = self._calc_spread(bid, ask)
        return {"price": price, "volume_5m": volume_5m, "spread": spread}

    async def fetch_klines(
        self,
        exchange: str,
        symbol: str,
        market_type: str,
        base: str,
        quote: str,
        minutes: int,
    ) -> list[float]:
        """Return close prices oldest→newest for a sparkline. Empty list on failure."""
        # Choose candle interval based on report window
        if minutes <= 15:
            interval_binance = "1m"
            interval_bybit = "1"
            interval_okx = "1m"
            interval_coinbase = "ONE_MINUTE"
            limit = max(minutes, 1)
        elif minutes <= 60:
            interval_binance = "5m"
            interval_bybit = "5"
            interval_okx = "5m"
            interval_coinbase = "FIVE_MINUTE"
            limit = minutes // 5
        elif minutes <= 240:
            interval_binance = "5m"
            interval_bybit = "5"
            interval_okx = "5m"
            interval_coinbase = "FIVE_MINUTE"
            limit = minutes // 5
        else:
            # 24h and above: use 30m candles (~48 candles for 24h)
            interval_binance = "30m"
            interval_bybit = "30"
            interval_okx = "30m"
            interval_coinbase = "THIRTY_MINUTE"
            limit = minutes // 30

        exch = exchange.lower()
        session = self._get_session()
        try:
            if exch == "binance":
                return await self._klines_binance(session, symbol, interval_binance, limit)
            if exch == "bybit":
                return await self._klines_bybit(session, symbol, market_type, interval_bybit, limit)
            if exch == "mexc":
                return await self._klines_mexc(session, symbol, interval_binance, limit)
            if exch == "okx":
                return await self._klines_okx(session, base, quote, market_type, interval_okx, limit)
            if exch == "coinbase":
                return await self._klines_coinbase(session, base, quote, interval_coinbase, limit)
        except Exception:
            LOGGER.debug("Failed to fetch klines for %s %s", exchange, symbol)
        return []

    async def _klines_binance(
        self, session: aiohttp.ClientSession, symbol: str, interval: str, limit: int
    ) -> list[float]:
        url = "https://api.binance.com/api/v3/klines"
        async with session.get(url, params={"symbol": symbol, "interval": interval, "limit": limit}) as r:
            r.raise_for_status()
            data = await r.json()
        # Each candle: [open_time, open, high, low, close, ...]
        return [float(c[4]) for c in data if c]

    async def _klines_bybit(
        self, session: aiohttp.ClientSession, symbol: str, market_type: str,
        interval: str, limit: int,
    ) -> list[float]:
        category = "spot" if market_type == "spot" else "linear"
        url = "https://api.bybit.com/v5/market/kline"
        async with session.get(
            url, params={"category": category, "symbol": symbol, "interval": interval, "limit": limit}
        ) as r:
            r.raise_for_status()
            payload = await r.json()
        rows = (payload.get("result") or {}).get("list") or []
        # Bybit returns newest-first: [timestamp, open, high, low, close, volume, turnover]
        return [float(c[4]) for c in reversed(rows) if c]

    async def _klines_mexc(
        self, session: aiohttp.ClientSession, symbol: str, interval: str, limit: int
    ) -> list[float]:
        url = "https://api.mexc.com/api/v3/klines"
        async with session.get(url, params={"symbol": symbol, "interval": interval, "limit": limit}) as r:
            r.raise_for_status()
            data = await r.json()
        return [float(c[4]) for c in data if c]

    async def _klines_okx(
        self, session: aiohttp.ClientSession, base: str, quote: str,
        market_type: str, bar: str, limit: int,
    ) -> list[float]:
        inst_type = "SWAP" if market_type == "futures" else "SPOT"
        inst_id = f"{base.upper()}-{quote.upper()}" if inst_type == "SPOT" else f"{base.upper()}-{quote.upper()}-SWAP"
        url = "https://www.okx.com/api/v5/market/candles"
        async with session.get(url, params={"instId": inst_id, "bar": bar, "limit": limit}) as r:
            r.raise_for_status()
            payload = await r.json()
        rows = payload.get("data") or []
        # OKX returns newest-first: [ts, open, high, low, close, vol, volCcy, ...]
        return [float(c[4]) for c in reversed(rows) if c]

    async def _klines_coinbase(
        self, session: aiohttp.ClientSession, base: str, quote: str,
        granularity: str, limit: int,
    ) -> list[float]:
        cb_quote = "USD" if quote.upper() == "USDT" else quote.upper()
        product_id = f"{base.upper()}-{cb_quote}"
        url = f"https://api.exchange.coinbase.com/products/{product_id}/candles"
        async with session.get(url, params={"granularity": granularity, "limit": limit}) as r:
            r.raise_for_status()
            data = await r.json()
        # Coinbase returns newest-first: [timestamp, low, high, open, close, volume]
        return [float(c[4]) for c in reversed(data) if c]

    @staticmethod
    def _calc_spread(bid: float | None, ask: float | None) -> float | None:
        if bid is None or ask is None:
            return None
        mid = (bid + ask) / 2
        if mid <= 0:
            return None
        return (ask - bid) / mid
