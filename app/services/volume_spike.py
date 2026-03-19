"""Volume spike detector.

Every 15 minutes, checks 24h Binance volume for all watchlist symbols.
If the current 5m-equivalent volume is >3x the exponential moving average,
sends a one-time alert (with 1h cooldown) to users watching that ticker.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repo import state as state_repo
from app.db.repo import watchlist as watchlist_repo
from app.db.repo.users import list_all_users
from app.i18n import get_user_lang, t

LOGGER = logging.getLogger(__name__)

_SPIKE_THRESHOLD = 3.0      # current vol > 3× baseline → spike
_COOLDOWN = timedelta(hours=1)
_EMA_ALPHA = 0.3            # weight of the new sample in the moving average
_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)
_BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"
_STATE_SERVICE = "volume_spike"
_STATE_KEY = "watchlist_state"


class VolumeSpikeService:
    def __init__(
        self,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._bot = bot
        self._session_factory = session_factory

    async def check_all(self) -> None:
        async with self._session_factory() as session:
            watching = await watchlist_repo.find_all_watched(session)
            users = await list_all_users(session)

        if not watching:
            return

        user_settings: dict[int, dict | None] = {u.id: u.settings for u in users}
        baselines, last_alerts = await self._load_state()
        volumes = await self._fetch_volumes(list(watching.keys()))
        if not volumes:
            return

        now = datetime.now(timezone.utc)
        for base, vol_5m in volumes.items():
            baseline = baselines.get(base)
            if baseline is None or baseline <= 0:
                baselines[base] = vol_5m
                continue

            if vol_5m > _SPIKE_THRESHOLD * baseline:
                last = last_alerts.get(base)
                if last is None or (now - last) >= _COOLDOWN:
                    last_alerts[base] = now
                    await self._notify(
                        base, vol_5m, baseline,
                        watching.get(base, []),
                        user_settings,
                    )

            # Update EMA regardless of spike
            baselines[base] = (1 - _EMA_ALPHA) * baseline + _EMA_ALPHA * vol_5m

        await self._save_state(baselines, last_alerts)

    async def _fetch_volumes(self, symbol_bases: list[str]) -> dict[str, float]:
        """Return {symbol_base: vol_5m_usdt} using Binance batch ticker API."""
        symbols_json = json.dumps([f"{b}USDT" for b in symbol_bases])
        try:
            async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as http:
                async with http.get(
                    _BINANCE_TICKER_URL,
                    params={"symbols": symbols_json},
                ) as resp:
                    if resp.status != 200:
                        return {}
                    data = await resp.json()
        except Exception:
            LOGGER.debug("Volume spike: failed to fetch Binance tickers")
            return {}

        result: dict[str, float] = {}
        for item in data:
            symbol: str = item.get("symbol", "")
            if not symbol.endswith("USDT"):
                continue
            base = symbol[:-4]
            try:
                vol_5m = float(item.get("quoteVolume", 0)) / 288
                if vol_5m > 0:
                    result[base] = vol_5m
            except (TypeError, ValueError):
                continue
        return result

    async def _notify(
        self,
        base: str,
        current_vol: float,
        baseline: float,
        user_ids: list[int],
        user_settings: dict[int, dict | None],
    ) -> None:
        multiplier = f"{current_vol / baseline:.1f}x" if baseline > 0 else "?"
        vol_str = f"{current_vol:,.0f}"
        for uid in user_ids:
            lang = get_user_lang(user_settings.get(uid))
            text = t("volume_spike.alert", lang, base=base, multiplier=multiplier, vol=vol_str)
            try:
                await self._bot.send_message(uid, text)
            except TelegramForbiddenError:
                pass
            except Exception:
                LOGGER.debug("Volume spike: failed to notify user %s", uid)

    async def _load_state(self) -> tuple[dict[str, float], dict[str, datetime]]:
        async with self._session_factory() as session:
            payload = await state_repo.get_payload(session, _STATE_SERVICE, _STATE_KEY)

        baselines = {
            str(base): float(value)
            for base, value in (payload or {}).get("baselines", {}).items()
            if value is not None
        }
        last_alerts: dict[str, datetime] = {}
        for base, iso_value in (payload or {}).get("last_alerts", {}).items():
            try:
                last_alerts[str(base)] = datetime.fromisoformat(str(iso_value))
            except ValueError:
                continue
        return baselines, last_alerts

    async def _save_state(
        self,
        baselines: dict[str, float],
        last_alerts: dict[str, datetime],
    ) -> None:
        async with self._session_factory() as session:
            await state_repo.set_payload(
                session,
                _STATE_SERVICE,
                _STATE_KEY,
                {
                    "baselines": {
                        base: round(value, 8)
                        for base, value in baselines.items()
                    },
                    "last_alerts": {
                        base: dt.isoformat()
                        for base, dt in last_alerts.items()
                    },
                },
            )
            await session.commit()
