from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _as_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    return float(value)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    poll_interval_sec: int
    dedup_ttl_hours: int
    max_notifications_per_hour: int
    min_vol_5m: float
    max_spread: float
    bootstrap_on_empty: bool
    default_only_usdt: bool
    default_min_score: int
    default_enabled_exchanges: tuple[str, ...]
    default_enabled_market_types: tuple[str, ...]
    admin_id: int | None  # Telegram user ID for error alerts; optional


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ValueError("BOT_TOKEN is required")

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@postgres:5432/new_coin_bot",
    )

    default_exchanges = tuple(
        x.strip().lower()
        for x in os.getenv("DEFAULT_ENABLED_EXCHANGES", "binance,bybit,coinbase,okx,mexc").split(",")
        if x.strip()
    )
    default_market_types = tuple(
        x.strip().lower()
        for x in os.getenv("DEFAULT_ENABLED_MARKET_TYPES", "spot,futures").split(",")
        if x.strip()
    )

    raw_admin = os.getenv("ADMIN_ID", "").strip()
    admin_id = int(raw_admin) if raw_admin.isdigit() else None

    return Settings(
        bot_token=bot_token,
        database_url=database_url,
        poll_interval_sec=_as_int(os.getenv("POLL_INTERVAL_SEC"), 60),
        dedup_ttl_hours=_as_int(os.getenv("DEDUP_TTL_HOURS"), 24),
        max_notifications_per_hour=_as_int(
            os.getenv("MAX_NOTIFICATIONS_PER_HOUR"), 20
        ),
        min_vol_5m=_as_float(os.getenv("MIN_VOL_5M"), 10000.0),
        max_spread=_as_float(os.getenv("MAX_SPREAD"), 0.02),
        bootstrap_on_empty=_as_bool(os.getenv("BOOTSTRAP_ON_EMPTY"), True),
        default_only_usdt=_as_bool(os.getenv("DEFAULT_ONLY_USDT"), False),
        default_min_score=_as_int(os.getenv("DEFAULT_MIN_SCORE"), 0),
        default_enabled_exchanges=default_exchanges or ("binance", "bybit", "coinbase", "okx", "mexc"),
        default_enabled_market_types=default_market_types or ("spot", "futures"),
        admin_id=admin_id,
    )
