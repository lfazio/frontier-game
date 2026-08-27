"""core identity, command audit and the AP ledger

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

FACTIONS = [(1, "empire"), (2, "republic"), (3, "pirates")]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS core")

    op.create_table(
        "accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="core",
    )
    factions = op.create_table(
        "factions",
        sa.Column("id", sa.SmallInteger, primary_key=True, autoincrement=False),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        schema="core",
    )
    op.bulk_insert(factions, [{"id": i, "code": c} for i, c in FACTIONS])

    op.create_table(
        "teams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("faction_id", sa.SmallInteger, sa.ForeignKey("core.factions.id"), nullable=False),
        sa.Column("founded_on", sa.Integer, nullable=False),
        schema="core",
    )
    op.create_table(
        "players",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("core.accounts.id"), nullable=False),
        sa.Column("callsign", sa.String(32), nullable=False, unique=True),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("core.teams.id")),
        sa.Column("faction_id", sa.SmallInteger, sa.ForeignKey("core.factions.id")),
        sa.Column("credits", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("ap_balance", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_grant_day", sa.Integer, nullable=False, server_default="-1"),
        sa.CheckConstraint("credits >= 0", name="credits_non_negative"),
        sa.CheckConstraint("ap_balance >= 0", name="ap_non_negative"),
        sa.CheckConstraint(
            "(team_id IS NULL AND faction_id IS NULL) OR (team_id IS NOT NULL AND faction_id IS NOT NULL)",
            name="faction_matches_team",
        ),
        schema="core",
    )
    op.create_table(
        "commands",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("core.players.id"), nullable=False),
        sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("request", JSONB, nullable=False, server_default="{}"),
        sa.Column("outcome", JSONB),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("ruleset_version", sa.String(16), nullable=False),
        sa.Column("world_day", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("player_id", "idempotency_key", name="commands_idempotency"),
        schema="core",
    )
    op.create_table(
        "ap_ledger",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("core.players.id"), nullable=False),
        sa.Column("world_day", sa.Integer, nullable=False),
        sa.Column("delta", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("command_id", UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="core",
    )
    op.create_index("ap_ledger_command_uniq", "ap_ledger", ["command_id"], unique=True,
                    schema="core", postgresql_where=sa.text("command_id IS NOT NULL"))
    op.create_index("ap_ledger_player_day", "ap_ledger", ["player_id", "world_day"], schema="core")

    op.create_table(
        "world_state",
        sa.Column("id", sa.Boolean, primary_key=True, server_default=sa.true()),
        sa.Column("world_day", sa.Integer, nullable=False, server_default="0"),
        sa.Column("world_seed", sa.String(64), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False, server_default="open"),
        sa.CheckConstraint("id", name="world_state_singleton"),
        schema="core",
    )


def downgrade() -> None:
    for table in ("world_state", "ap_ledger", "commands", "players", "teams", "factions", "accounts"):
        op.drop_table(table, schema="core")
    # The schema itself stays: alembic_version lives in it.
