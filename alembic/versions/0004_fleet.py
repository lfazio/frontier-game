"""ships and journeys

Revision ID: 0004
Revises: 0003

Brought forward from the P3 slot: a unit of work spanning Postgres for locations and memory for
ships would be worse than reordering two migrations, and tick stage 1 needs journeys to settle.
See detailed design D-16.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from frontier.adapters.db.types import LTree

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("core.players.id")),
        sa.Column("hull", sa.Integer, nullable=False),
        sa.Column("hull_max", sa.Integer, nullable=False),
        sa.Column("shields", sa.Integer, nullable=False, server_default="0"),
        sa.Column("shields_max", sa.Integer, nullable=False, server_default="0"),
        sa.Column("fuel", sa.Integer, nullable=False),
        sa.Column("fuel_max", sa.Integer, nullable=False),
        sa.Column("cargo_max", sa.Integer, nullable=False),
        sa.Column("sensor_range", sa.Integer, nullable=False),
        sa.Column("system_id", UUID(as_uuid=True), sa.ForeignKey("core.locations.id"), nullable=False),
        sa.Column("position_path", LTree(), nullable=False),
        sa.Column("docked_at", UUID(as_uuid=True), sa.ForeignKey("core.locations.id")),
        sa.Column("destroyed_on", sa.Integer),
        sa.CheckConstraint("hull >= 0", name="hull_non_negative"),
        sa.CheckConstraint("fuel >= 0", name="fuel_non_negative"),
        schema="core",
    )
    op.create_index("ships_one_per_player", "ships", ["player_id"], unique=True, schema="core",
                    postgresql_where=sa.text("player_id IS NOT NULL AND destroyed_on IS NULL"))
    op.create_index("ships_position_gist", "ships", ["position_path"], schema="core",
                    postgresql_using="gist")
    op.create_index("ships_system", "ships", ["system_id"], schema="core",
                    postgresql_where=sa.text("destroyed_on IS NULL"))

    op.create_table(
        "journeys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ship_id", UUID(as_uuid=True), sa.ForeignKey("core.ships.id"), nullable=False),
        sa.Column("from_path", LTree(), nullable=False),
        sa.Column("to_path", LTree(), nullable=False),
        sa.Column("to_system_id", UUID(as_uuid=True), sa.ForeignKey("core.locations.id"), nullable=False),
        sa.Column("departed_on", sa.Integer, nullable=False),
        sa.Column("arrives_on", sa.Integer, nullable=False),
        sa.Column("settled", sa.Boolean, nullable=False, server_default=sa.false()),
        schema="core",
    )
    op.create_index("journeys_pending", "journeys", ["arrives_on"], schema="core",
                    postgresql_where=sa.text("NOT settled"))


def downgrade() -> None:
    op.drop_table("journeys", schema="core")
    op.drop_table("ships", schema="core")
