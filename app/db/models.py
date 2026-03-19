from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _enum_values(enum_class: type) -> list[str]:
    """Return enum .value list for SQLAlchemy values_callable.

    SQLAlchemy 2 defaults to using enum .name for DB binding, but our
    PostgreSQL enums were created with lowercase .values ('spot', 'futures').
    Passing values_callable forces SQLAlchemy to use .value instead of .name.
    """
    return [e.value for e in enum_class]


class EventType(str, enum.Enum):
    SPOT_LISTING = "SPOT_LISTING"
    FUTURES_LISTING = "FUTURES_LISTING"


class MarketType(str, enum.Enum):
    SPOT = "spot"
    FUTURES = "futures"


class MuteType(str, enum.Enum):
    EXCHANGE = "exchange"
    TICKER = "ticker"
    KEYWORD = "keyword"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, name="event_type"), nullable=False
    )
    market_type: Mapped[MarketType] = mapped_column(
        Enum(MarketType, name="market_type", values_callable=_enum_values), nullable=False
    )
    symbol_base: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    symbol_quote: Mapped[str] = mapped_column(String(32), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pairs: Mapped[list[str] | None] = mapped_column(JSONB)
    announcement_url: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    enriched: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    flags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    event_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("user_id", "event_key", name="uq_deliveries_user_event_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    event_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    __table_args__ = (
        UniqueConstraint("user_id", "symbol_base", name="uq_watchlist_user_symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol_base: Mapped[str] = mapped_column(String(32), nullable=False)


class MuteRule(Base):
    __tablename__ = "mutes"
    __table_args__ = (
        UniqueConstraint("user_id", "type", "value", name="uq_mutes_user_type_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[MuteType] = mapped_column(
        Enum(MuteType, name="mute_type", values_callable=_enum_values), nullable=False
    )
    value: Mapped[str] = mapped_column(String(64), nullable=False)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "exchange",
            "market_type",
            "symbol",
            name="uq_market_snapshots_exchange_market_symbol",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    market_type: Mapped[MarketType] = mapped_column(
        Enum(MarketType, name="market_type", values_callable=_enum_values), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol_base: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol_quote: Mapped[str] = mapped_column(String(32), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TrackingSubscription(Base):
    __tablename__ = "tracking_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    market_type: Mapped[MarketType] = mapped_column(
        Enum(MarketType, name="market_type", values_callable=_enum_values), nullable=False
    )
    symbol_base: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol_quote: Mapped[str] = mapped_column(String(32), nullable=False)
    report_after_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CallbackToken(Base):
    __tablename__ = "callback_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    payload: Mapped[dict] = mapped_column(
        JSON, nullable=False, server_default=text("'{}'::json")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_events_event_time", "event_time"),
        Index("ix_analytics_events_user_id_event_time", "user_id", "event_time"),
        Index("ix_analytics_events_event_name_event_time", "event_name", "event_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )
    exchange: Mapped[str | None] = mapped_column(String(32), nullable=True)
    market_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    placement: Mapped[str | None] = mapped_column(String(32), nullable=True)
    button_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    properties: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class DigestQueueItem(Base):
    __tablename__ = "digest_queue"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_digest_queue_user_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # base ticker symbol, e.g. "BTC"
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    # optional exchange filter; None = any exchange
    exchange: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 'gt' (price >) or 'lt' (price <)
    direction: Mapped[str] = mapped_column(String(2), nullable=False)
    threshold: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), index=True
    )


class FilterPreset(Base):
    __tablename__ = "filter_presets"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_filter_presets_user_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ServiceState(Base):
    __tablename__ = "service_state"
    __table_args__ = (
        UniqueConstraint("service", "state_key", name="uq_service_state_service_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    state_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
