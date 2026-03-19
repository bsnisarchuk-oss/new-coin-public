"""Initial schema

Revision ID: 20260219_0001
Revises: None
Create Date: 2026-02-19 11:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260219_0001"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables"
            "  WHERE table_schema = 'public' AND table_name = :name"
            ")"
        ),
        {"name": name},
    )
    return bool(result.scalar())


def upgrade() -> None:
    # Create enum types idempotently (PostgreSQL DO block)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE event_type AS ENUM ('SPOT_LISTING', 'FUTURES_LISTING');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE market_type AS ENUM ('spot', 'futures');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE mute_type AS ENUM ('exchange', 'ticker', 'keyword');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    event_type = postgresql.ENUM("SPOT_LISTING", "FUTURES_LISTING", name="event_type", create_type=False)
    market_type = postgresql.ENUM("spot", "futures", name="market_type", create_type=False)
    mute_type = postgresql.ENUM("exchange", "ticker", "keyword", name="mute_type", create_type=False)

    if _table_exists("users"):
        return  # Schema already exists, skip all table creation

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("event_type", event_type, nullable=False),
        sa.Column("market_type", market_type, nullable=False),
        sa.Column("symbol_base", sa.String(length=32), nullable=False),
        sa.Column("symbol_quote", sa.String(length=32), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pairs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("announcement_url", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "enriched",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("score", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("event_key", sa.String(length=255), nullable=False),
    )
    op.create_index("ix_events_exchange", "events", ["exchange"])
    op.create_index("ix_events_symbol_base", "events", ["symbol_base"])
    op.create_index("ix_events_event_key", "events", ["event_key"])

    op.create_table(
        "deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_key", sa.String(length=255), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "event_key", name="uq_deliveries_user_event_key"),
    )
    op.create_index("ix_deliveries_user_id", "deliveries", ["user_id"])
    op.create_index("ix_deliveries_event_key", "deliveries", ["event_key"])
    op.create_index(
        "ix_deliveries_user_event_key",
        "deliveries",
        ["user_id", "event_key"],
    )

    op.create_table(
        "watchlist",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol_base", sa.String(length=32), nullable=False),
        sa.UniqueConstraint("user_id", "symbol_base", name="uq_watchlist_user_symbol"),
    )
    op.create_index("ix_watchlist_user_id", "watchlist", ["user_id"])

    op.create_table(
        "mutes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", mute_type, nullable=False),
        sa.Column("value", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("user_id", "type", "value", name="uq_mutes_user_type_value"),
    )
    op.create_index("ix_mutes_user_id", "mutes", ["user_id"])

    op.create_table(
        "market_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("market_type", market_type, nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("symbol_base", sa.String(length=32), nullable=False),
        sa.Column("symbol_quote", sa.String(length=32), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "exchange",
            "market_type",
            "symbol",
            name="uq_market_snapshots_exchange_market_symbol",
        ),
    )
    op.create_index("ix_market_snapshots_exchange", "market_snapshots", ["exchange"])
    op.create_index(
        "ix_market_snapshots_market_type",
        "market_snapshots",
        ["market_type"],
    )

    op.create_table(
        "tracking_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("market_type", market_type, nullable=False),
        sa.Column("symbol_base", sa.String(length=32), nullable=False),
        sa.Column("symbol_quote", sa.String(length=32), nullable=False),
        sa.Column("report_after_minutes", sa.Integer(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_tracking_subscriptions_user_id",
        "tracking_subscriptions",
        ["user_id"],
    )

    op.create_table(
        "callback_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token", sa.String(length=32), nullable=False),
        sa.Column(
            "payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_callback_tokens_token", "callback_tokens", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_callback_tokens_token", table_name="callback_tokens")
    op.drop_table("callback_tokens")

    op.drop_index("ix_tracking_subscriptions_user_id", table_name="tracking_subscriptions")
    op.drop_table("tracking_subscriptions")

    op.drop_index("ix_market_snapshots_market_type", table_name="market_snapshots")
    op.drop_index("ix_market_snapshots_exchange", table_name="market_snapshots")
    op.drop_table("market_snapshots")

    op.drop_index("ix_mutes_user_id", table_name="mutes")
    op.drop_table("mutes")

    op.drop_index("ix_watchlist_user_id", table_name="watchlist")
    op.drop_table("watchlist")

    op.drop_index("ix_deliveries_user_event_key", table_name="deliveries")
    op.drop_index("ix_deliveries_event_key", table_name="deliveries")
    op.drop_index("ix_deliveries_user_id", table_name="deliveries")
    op.drop_table("deliveries")

    op.drop_index("ix_events_event_key", table_name="events")
    op.drop_index("ix_events_symbol_base", table_name="events")
    op.drop_index("ix_events_exchange", table_name="events")
    op.drop_table("events")

    op.drop_table("users")

    mute_type = sa.Enum("exchange", "ticker", "keyword", name="mute_type")
    market_type = sa.Enum("spot", "futures", name="market_type")
    event_type = sa.Enum("SPOT_LISTING", "FUTURES_LISTING", name="event_type")
    bind = op.get_bind()
    mute_type.drop(bind, checkfirst=True)
    market_type.drop(bind, checkfirst=True)
    event_type.drop(bind, checkfirst=True)

