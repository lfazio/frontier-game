"""missions, reputation and faction defection

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "missions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("faction_id", sa.SmallInteger, sa.ForeignKey("core.factions.id"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("system_id", UUID(as_uuid=True), sa.ForeignKey("core.locations.id"),
                  nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), sa.ForeignKey("core.locations.id")),
        sa.Column("brief", sa.String(300), nullable=False),
        sa.Column("terms", JSONB, nullable=False, server_default="{}"),
        sa.Column("reward_credits", sa.Integer, nullable=False),
        sa.Column("reward_reputation", sa.Integer, nullable=False, server_default="1"),
        sa.Column("offered_on", sa.Integer, nullable=False),
        sa.Column("expires_on", sa.Integer, nullable=False),
        schema="core",
    )
    op.create_index("missions_open", "missions", ["faction_id", "expires_on"], schema="core")

    op.create_table(
        "mission_assignments",
        sa.Column("mission_id", UUID(as_uuid=True), sa.ForeignKey("core.missions.id"),
                  primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("core.players.id"),
                  primary_key=True),
        sa.Column("stage", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("accepted_on", sa.Integer, nullable=False),
        sa.Column("closed_on", sa.Integer),
        schema="core",
    )
    op.create_index("assignments_active", "mission_assignments", ["player_id"], schema="core",
                    postgresql_where=sa.text("status = 'active'"))

    op.create_table(
        "reputation",
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("core.players.id"),
                  primary_key=True),
        sa.Column("faction_id", sa.SmallInteger, sa.ForeignKey("core.factions.id"),
                  primary_key=True),
        sa.Column("score", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("score BETWEEN -100 AND 100", name="reputation_range"),
        schema="core",
    )

    op.add_column("teams", sa.Column("defected_on", sa.Integer), schema="core")


def downgrade() -> None:
    op.drop_column("teams", "defected_on", schema="core")
    op.drop_table("reputation", schema="core")
    op.drop_table("mission_assignments", schema="core")
    op.drop_table("missions", schema="core")
