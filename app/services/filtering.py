from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.db.models import Event, MuteRule, MuteType


@dataclass(slots=True)
class UserFilters:
    enabled_exchanges: set[str]
    enabled_market_types: set[str]
    only_usdt: bool
    min_score: int


def normalize_filters(raw: dict[str, Any], settings: Settings) -> UserFilters:
    enabled_exchanges = {
        str(x).strip().lower()
        for x in raw.get("enabled_exchanges", settings.default_enabled_exchanges)
        if str(x).strip()
    }
    enabled_market_types = {
        str(x).strip().lower()
        for x in raw.get("enabled_market_types", settings.default_enabled_market_types)
        if str(x).strip()
    }
    only_usdt = bool(raw.get("only_usdt", settings.default_only_usdt))
    min_score = int(raw.get("min_score", settings.default_min_score))
    return UserFilters(
        enabled_exchanges=enabled_exchanges,
        enabled_market_types=enabled_market_types,
        only_usdt=only_usdt,
        min_score=min_score,
    )


def event_passes_filters(event: Event, filters: UserFilters, mute_rules: list[MuteRule]) -> bool:
    if event.exchange.lower() not in filters.enabled_exchanges:
        return False
    if event.market_type.value.lower() not in filters.enabled_market_types:
        return False
    if filters.only_usdt and event.symbol_quote.upper() != "USDT":
        return False
    if event.score < filters.min_score:
        return False
    if _is_muted(event, mute_rules):
        return False
    return True


def _is_muted(event: Event, mute_rules: list[MuteRule]) -> bool:
    base = event.symbol_base.lower()
    exchange = event.exchange.lower()
    event_key = event.event_key.lower()
    for mute in mute_rules:
        if mute.type == MuteType.TICKER and mute.value == base:
            return True
        if mute.type == MuteType.EXCHANGE and mute.value == exchange:
            return True
        if mute.type == MuteType.KEYWORD and mute.value and mute.value in event_key:
            return True
    return False

