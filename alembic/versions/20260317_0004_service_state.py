"""Add service_state table

Revision ID: 20260317_0004
Revises: 20260301_0003
Create Date: 2026-03-17 21:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260317_0004"
down_revision = "20260301_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("service", sa.String(length=64), nullable=False),
        sa.Column("state_key", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("service", "state_key", name="uq_service_state_service_key"),
    )
    op.create_index("ix_service_state_service", "service_state", ["service"])


def downgrade() -> None:
    op.drop_index("ix_service_state_service", table_name="service_state")
    op.drop_table("service_state")
