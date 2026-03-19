from __future__ import annotations

import logging
import re
import time
from typing import Any

import aiohttp

LOGGER = logging.getLogger(__name__)

_BASE_URL = "https://api.coingecko.com/api/v3"
_TIMEOUT = aiohttp.ClientTimeout(total=10)

# Cache TTLs in seconds
_ID_TTL = 86_400       # 24h — stable mapping symbol→id
_INFO_TTL = 86_400     # 24h — coin metadata rarely changes
_MISS_TTL = 3_600      # 1h  — avoid re-querying unknown coins


def _strip_html(text: str) -> str:
    """Remove HTML tags from CoinGecko description."""
    return re.sub(r"<[^>]+>", "", text).strip()


class CoinInfoService:
    """Fetch brief coin metadata from CoinGecko (no API key required)."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None
        # {base_upper: (coin_id, timestamp)}
        self._id_cache: dict[str, tuple[str, float]] = {}
        # {coin_id: (info_dict, timestamp)}
        self._info_cache: dict[str, tuple[dict, float]] = {}
        # {base_upper: timestamp}  — coins not found on CoinGecko
        self._miss_cache: dict[str, float] = {}

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(timeout=_TIMEOUT)

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def get_coin_info(self, base: str) -> dict[str, Any] | None:
        """Return coin info dict or None if not found / API unavailable.

        Dict keys: description (str), homepage (str|None), genesis_year (str|None).
        """
        key = base.upper()
        now = time.monotonic()

        # Miss cache — known unknown coin, skip for a while
        miss_ts = self._miss_cache.get(key)
        if miss_ts is not None and now - miss_ts < _MISS_TTL:
            return None

        # Resolve CoinGecko coin ID
        coin_id = await self._resolve_id(key, now)
        if coin_id is None:
            self._miss_cache[key] = now
            return None

        # Fetch / return cached info
        cached = self._info_cache.get(coin_id)
        if cached and now - cached[1] < _INFO_TTL:
            return cached[0]

        info = await self._fetch_info(coin_id)
        if info is None:
            return None

        self._info_cache[coin_id] = (info, now)
        return info

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _resolve_id(self, key: str, now: float) -> str | None:
        """Return CoinGecko coin ID for a ticker symbol, using cache."""
        cached = self._id_cache.get(key)
        if cached and now - cached[1] < _ID_TTL:
            return cached[0]

        coin_id = await self._search_id(key)
        if coin_id:
            self._id_cache[key] = (coin_id, now)
        return coin_id

    async def _search_id(self, symbol: str) -> str | None:
        """Search CoinGecko for the best match by ticker symbol."""
        if self._session is None:
            return None
        try:
            url = f"{_BASE_URL}/search"
            async with self._session.get(url, params={"query": symbol}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        except Exception:
            LOGGER.debug("CoinGecko search failed for %s", symbol, exc_info=True)
            return None

        coins = data.get("coins") or []
        sym_lower = symbol.lower()
        # Prefer exact symbol match; fall back to first result
        for coin in coins:
            if (coin.get("symbol") or "").lower() == sym_lower:
                return coin.get("id")
        return coins[0].get("id") if coins else None

    async def _fetch_info(self, coin_id: str) -> dict[str, Any] | None:
        """Fetch coin details from CoinGecko and extract relevant fields."""
        if self._session is None:
            return None
        try:
            url = f"{_BASE_URL}/coins/{coin_id}"
            params = {
                "localization": "false",
                "tickers": "false",
                "market_data": "false",
                "community_data": "false",
                "developer_data": "false",
            }
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        except Exception:
            LOGGER.debug("CoinGecko fetch failed for %s", coin_id, exc_info=True)
            return None

        # Description — strip HTML, truncate
        raw_desc = (data.get("description") or {}).get("en") or ""
        desc = _strip_html(raw_desc)
        if len(desc) > 200:
            desc = desc[:197].rstrip() + "…"

        # Homepage
        links = data.get("links") or {}
        homepages: list = links.get("homepage") or []
        homepage = next((h for h in homepages if h), None)

        # Launch year from genesis_date (format: "YYYY-MM-DD" or None)
        genesis_date: str | None = data.get("genesis_date")
        genesis_year: str | None = None
        if genesis_date:
            genesis_year = genesis_date[:4]

        # Only return if at least description or homepage is available
        if not desc and not homepage:
            return None

        return {
            "description": desc or None,
            "homepage": homepage,
            "genesis_year": genesis_year,
        }
