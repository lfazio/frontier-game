"""the location tree, addressed by ltree

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from frontier.adapters.db.types import LTree

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")
    op.create_table(
        "locations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("core.locations.id")),
        sa.Column("level", sa.SmallInteger, nullable=False),
        sa.Column("q", sa.Integer, nullable=False),
        sa.Column("r", sa.Integer, nullable=False),
        sa.Column("path", LTree(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("name", sa.String(64)),
        sa.Column("discovered_on", sa.Integer),
        sa.Column("discovered_by", UUID(as_uuid=True), sa.ForeignKey("core.players.id")),
        sa.Column("attrs", JSONB, nullable=False, server_default="{}"),
        sa.UniqueConstraint("parent_id", "q", "r", name="locations_parent_hex"),
        schema="core",
    )
    op.create_index("locations_path_gist", "locations", ["path"], schema="core", postgresql_using="gist")
    op.create_index("locations_kind_station", "locations", ["kind"], schema="core",
                    postgresql_where=sa.text("kind = 'station'"))


def downgrade() -> None:
    op.drop_table("locations", schema="core")
