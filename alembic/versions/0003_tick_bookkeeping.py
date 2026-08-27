"""tick runs and per-stage checkpoints

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS hist")
    op.create_table(
        "tick_runs",
        sa.Column("world_day", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        schema="hist",
    )
    op.create_table(
        "tick_stages",
        sa.Column("world_day", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("stage", sa.String(48), primary_key=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("metrics", JSONB, nullable=False, server_default="{}"),
        schema="hist",
    )


def downgrade() -> None:
    op.drop_table("tick_stages", schema="hist")
    op.drop_table("tick_runs", schema="hist")
