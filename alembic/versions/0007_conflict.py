"""encounters, territory and per-player discovery

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from frontier.adapters.db.types import LTree

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "encounter_queue",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("world_day", sa.Integer, nullable=False),
        sa.Column("attacker_id", UUID(as_uuid=True), sa.ForeignKey("core.ships.id"), nullable=False),
        sa.Column("defender_id", UUID(as_uuid=True), sa.ForeignKey("core.ships.id"), nullable=False),
        sa.Column("at_path", LTree(), nullable=False),
        sa.Column("intent", sa.String(16), nullable=False, server_default="attack"),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("world_day", "attacker_id", "defender_id", name="one_attack_per_pair"),
        schema="core",
    )
    op.create_index("encounters_pending", "encounter_queue", ["world_day"], schema="core",
                    postgresql_where=sa.text("NOT resolved"))

    op.create_table(
        "territory",
        sa.Column("system_id", UUID(as_uuid=True), sa.ForeignKey("core.locations.id"),
                  primary_key=True),
        sa.Column("faction_id", sa.SmallInteger, sa.ForeignKey("core.factions.id"), primary_key=True),
        sa.Column("influence", sa.Numeric(6, 4), nullable=False, server_default="0"),
        schema="core",
    )
    op.create_table(
        "player_discoveries",
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("core.players.id"), primary_key=True),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("core.locations.id"),
                  primary_key=True),
        sa.Column("seen_on", sa.Integer, nullable=False),
        schema="core",
    )


def downgrade() -> None:
    for table in ("player_discoveries", "territory", "encounter_queue"):
        op.drop_table(table, schema="core")
