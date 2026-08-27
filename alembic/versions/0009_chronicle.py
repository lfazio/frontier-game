"""the permanent historical record

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from frontier.adapters.db.types import LTree

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chronicle",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("world_day", sa.Integer, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.SmallInteger, nullable=False),
        sa.Column("origin_path", LTree(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", JSONB, nullable=False, server_default="{}"),
        sa.Column("causation_id", UUID(as_uuid=True)),
        schema="hist",
    )
    op.create_index("chronicle_day", "chronicle", ["world_day"], schema="hist")
    op.create_index("chronicle_path_gist", "chronicle", ["origin_path"], schema="hist",
                    postgresql_using="gist")


def downgrade() -> None:
    op.drop_table("chronicle", schema="hist")
