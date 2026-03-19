from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, EventType, MarketType
from app.db.repo import events as events_repo
from app.exchanges.base import ExchangeConnector, Instrument
from app.services.dedup import build_event_key

LOGGER = logging.getLogger(__name__)


@dataclass
class DelistingAlert:
    exchange: str
    market_type: MarketType
    symbol_base: str
    symbol_quote: str


class MarketDetector:
    def __init__(
        self,
        connectors: Sequence[ExchangeConnector],
        bootstrap_on_empty: bool = True,
    ) -> None:
        self._connectors = list(connectors)
        self._bootstrap_on_empty = bootstrap_on_empty

    async def detect_new_events(
        self, session: AsyncSession
    ) -> tuple[list[Event], list[DelistingAlert]]:
        created_events: list[Event] = []
        delisting_alerts: list[DelistingAlert] = []

        for connector in self._connectors:
            for market_type_name in connector.supported_market_types:
                market_type = _market_type_from_name(market_type_name)
                instruments = await _fetch_with_retry(connector, market_type_name)
                if instruments is None:
                    continue
                if not instruments:
                    continue

                known_snapshots = await events_repo.list_known_snapshots(
                    session=session,
                    exchange=connector.name,
                    market_type=market_type,
                )
                known_symbols = {snap.symbol for snap in known_snapshots}

                if not known_symbols and self._bootstrap_on_empty:
                    await events_repo.upsert_snapshots(
                        session=session,
                        exchange=connector.name,
                        market_type=market_type,
                        instruments=instruments,
                    )
                    LOGGER.info(
                        "Bootstrap snapshots for %s/%s with %s instruments",
                        connector.name,
                        market_type.value,
                        len(instruments),
                    )
                    continue

                current_symbols = {inst.symbol for inst in instruments}

                # New listings
                new_instruments = [x for x in instruments if x.symbol not in known_symbols]

                # Delistings: in snapshot but no longer on exchange
                gone_symbols = known_symbols - current_symbols
                if gone_symbols:
                    # Circuit breaker: if more than 20% of known instruments disappeared
                    # at once, treat it as a mass-delisting category event / API anomaly
                    # and skip user notifications (still update snapshot below).
                    gone_ratio = len(gone_symbols) / len(known_symbols)
                    if gone_ratio > 0.20 or len(gone_symbols) > 50:
                        LOGGER.warning(
                            "Mass delisting ignored (circuit breaker): %d/%d symbols gone "
                            "on %s/%s (%.0f%%) — skipping notifications",
                            len(gone_symbols),
                            len(known_symbols),
                            connector.name,
                            market_type.value,
                            gone_ratio * 100,
                        )
                    else:
                        snap_by_symbol = {snap.symbol: snap for snap in known_snapshots}
                        for sym in gone_symbols:
                            snap = snap_by_symbol.get(sym)
                            if snap:
                                delisting_alerts.append(
                                    DelistingAlert(
                                        exchange=connector.name,
                                        market_type=market_type,
                                        symbol_base=snap.symbol_base,
                                        symbol_quote=snap.symbol_quote,
                                    )
                                )
                        LOGGER.info(
                            "Detected %s delisted symbols on %s/%s",
                            len(gone_symbols),
                            connector.name,
                            market_type.value,
                        )

                await events_repo.upsert_snapshots(
                    session=session,
                    exchange=connector.name,
                    market_type=market_type,
                    instruments=instruments,
                )

                if not new_instruments:
                    continue

                for instrument in new_instruments:
                    event = _make_event(connector.name, market_type, instrument)
                    session.add(event)
                    created_events.append(event)
                LOGGER.info(
                    "Detected %s new instruments for %s/%s",
                    len(new_instruments),
                    connector.name,
                    market_type.value,
                )

        if created_events:
            await session.flush()
        return created_events, delisting_alerts


async def _fetch_with_retry(
    connector: "ExchangeConnector",
    market_type_name: str,
    max_attempts: int = 3,
) -> "list[Instrument] | None":
    """Fetch instruments with exponential backoff (1 → 2 → 4s). Returns None on failure."""
    delay = 1.0
    for attempt in range(1, max_attempts + 1):
        try:
            return await connector.fetch_instruments(market_type_name)
        except Exception as exc:
            if attempt == max_attempts:
                LOGGER.error(
                    "Failed to fetch instruments from %s/%s after %d attempts: %s",
                    connector.name,
                    market_type_name,
                    max_attempts,
                    exc,
                )
                return None
            LOGGER.warning(
                "Attempt %d/%d failed for %s/%s (%s), retrying in %.0fs…",
                attempt,
                max_attempts,
                connector.name,
                market_type_name,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
            delay *= 2
    return None  # unreachable, satisfies type checker


def _market_type_from_name(name: str) -> MarketType:
    return MarketType.SPOT if name == "spot" else MarketType.FUTURES


def _event_type_from_market(market_type: MarketType) -> EventType:
    if market_type == MarketType.SPOT:
        return EventType.SPOT_LISTING
    return EventType.FUTURES_LISTING


def _make_event(exchange: str, market_type: MarketType, instrument: Instrument) -> Event:
    event_type = _event_type_from_market(market_type)
    event_key = build_event_key(
        exchange=exchange,
        event_type=event_type,
        market_type=market_type,
        base=instrument.base,
        quote=instrument.quote,
    )
    return Event(
        exchange=exchange,
        event_type=event_type,
        market_type=market_type,
        symbol_base=instrument.base,
        symbol_quote=instrument.quote,
        first_seen_at=datetime.now(timezone.utc),
        pairs=[instrument.symbol],
        event_key=event_key,
        meta={"symbol": instrument.symbol, "raw": instrument.raw},
        enriched={},
        flags=[],
        score=0,
    )
