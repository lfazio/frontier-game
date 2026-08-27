"""the NPC population: aggregate activity and materialised agents

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_activity",
        sa.Column("system_id", UUID(as_uuid=True), sa.ForeignKey("core.locations.id"),
                  primary_key=True),
        sa.Column("trade_flow", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("patrol_strength", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("raider_pressure", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("civilian_traffic", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("patrol_losses", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("raider_losses", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("last_simulated_on", sa.Integer, nullable=False, server_default="-1"),
        schema="core",
    )
    op.create_table(
        "npc_agents",
        sa.Column("ship_id", UUID(as_uuid=True), sa.ForeignKey("core.ships.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("system_id", UUID(as_uuid=True), sa.ForeignKey("core.locations.id"), nullable=False),
        sa.Column("archetype", sa.String(16), nullable=False),
        sa.Column("slot", sa.SmallInteger, nullable=False),
        sa.Column("faction_id", sa.SmallInteger, sa.ForeignKey("core.factions.id")),
        sa.Column("route", JSONB, nullable=False, server_default="{}"),
        sa.Column("materialised_on", sa.Integer, nullable=False),
        sa.Column("last_seen_on", sa.Integer, nullable=False),
        sa.UniqueConstraint("system_id", "archetype", "slot", name="npc_slot"),
        schema="core",
    )
    op.create_index("npc_agents_stale", "npc_agents", ["last_seen_on"], schema="core")


def downgrade() -> None:
    op.drop_table("npc_agents", schema="core")
    op.drop_table("system_activity", schema="core")
