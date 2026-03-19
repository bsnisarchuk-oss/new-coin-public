from datetime import datetime, timezone

from app.config import Settings
from app.db.models import Event, EventType, MarketType, MuteRule, MuteType
from app.services.filtering import event_passes_filters, normalize_filters


def _settings() -> Settings:
    return Settings(
        bot_token="x",
        database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        poll_interval_sec=60,
        dedup_ttl_hours=24,
        max_notifications_per_hour=20,
        min_vol_5m=10000,
        max_spread=0.02,
        bootstrap_on_empty=True,
        default_only_usdt=False,
        default_min_score=0,
        default_enabled_exchanges=("binance", "bybit"),
        default_enabled_market_types=("spot", "futures"),
        admin_id=None,
    )


def _event(exchange: str = "binance", score: int = 45, quote: str = "USDT") -> Event:
    return Event(
        exchange=exchange,
        event_type=EventType.SPOT_LISTING,
        market_type=MarketType.SPOT,
        symbol_base="ABC",
        symbol_quote=quote,
        first_seen_at=datetime.now(timezone.utc),
        event_key=f"{exchange}:SPOT_LISTING:spot:ABC:{quote}",
        pairs=[f"ABC{quote}"],
        meta={},
        enriched={},
        score=score,
        flags=[],
    )


def test_filters_respect_min_score() -> None:
    filters = normalize_filters({"min_score": 50}, _settings())
    assert not event_passes_filters(_event(score=45), filters, [])


def test_event_passes_when_score_meets_threshold() -> None:
    filters = normalize_filters({"min_score": 45}, _settings())
    assert event_passes_filters(_event(score=45), filters, [])


def test_filters_respect_mute_ticker() -> None:
    filters = normalize_filters({}, _settings())
    mute = MuteRule(user_id=1, type=MuteType.TICKER, value="abc")
    assert not event_passes_filters(_event(), filters, [mute])


def test_filters_respect_only_usdt_true() -> None:
    filters = normalize_filters({"only_usdt": True}, _settings())
    assert not event_passes_filters(_event(quote="BTC"), filters, [])
    assert event_passes_filters(_event(quote="USDT"), filters, [])


def test_filters_exchange_not_in_enabled() -> None:
    filters = normalize_filters({"enabled_exchanges": ["binance"]}, _settings())
    assert not event_passes_filters(_event(exchange="okx"), filters, [])


def test_mute_exchange_blocks_event() -> None:
    filters = normalize_filters({}, _settings())
    mute = MuteRule(user_id=1, type=MuteType.EXCHANGE, value="binance")
    assert not event_passes_filters(_event(exchange="binance"), filters, [mute])
