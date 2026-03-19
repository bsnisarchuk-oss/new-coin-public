"""Add analytics_events table

Revision ID: 20260301_0003
Revises: 20260220_0002
Create Date: 2026-03-01 13:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260301_0003"
down_revision = "20260220_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "event_time",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("exchange", sa.String(length=32), nullable=True),
        sa.Column("market_type", sa.String(length=16), nullable=True),
        sa.Column("placement", sa.String(length=32), nullable=True),
        sa.Column("button_id", sa.String(length=32), nullable=True),
        sa.Column(
            "properties",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("ix_analytics_events_event_time", "analytics_events", ["event_time"])
    op.create_index(
        "ix_analytics_events_user_id_event_time",
        "analytics_events",
        ["user_id", "event_time"],
    )
    op.create_index(
        "ix_analytics_events_event_name_event_time",
        "analytics_events",
        ["event_name", "event_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_events_event_name_event_time", table_name="analytics_events")
    op.drop_index("ix_analytics_events_user_id_event_time", table_name="analytics_events")
    op.drop_index("ix_analytics_events_event_time", table_name="analytics_events")
    op.drop_table("analytics_events")

