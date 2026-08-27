"""the hidden faction: its own schema, and roles that bound what it can do

Revision ID: 0015
Revises: 0014

Two boundaries, both enforced by grants rather than by discipline (ARCH ADR-13):

  `api_role`  — everything the public surface needs, and no privilege on `cont` at all. A
                serialisation mistake cannot leak what the connection cannot read.
  `cont_role` — the Continuity's own capability list. It may read the world, write its own
                records, and nudge population flows. It holds no write privilege on players,
                ships, credits or cargo, so GDD §9.13 — push, never force — is something the
                database refuses rather than something the code remembers.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

API = "api_role"
CONT = "cont_role"
PUBLIC_SCHEMAS = ("core", "evt", "hist")


def _ensure(role: str) -> None:
    op.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN;
            END IF;
        END $$
    """)
    op.execute(f"GRANT {role} TO CURRENT_USER")


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS cont")

    op.create_table(
        "cells",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("designation", sa.String(32), nullable=False, unique=True),
        sa.Column("region_id", UUID(as_uuid=True), nullable=False),
        sa.Column("clearance", sa.SmallInteger, nullable=False, server_default="1"),
        sa.Column("founded_on", sa.Integer, nullable=False),
        sa.CheckConstraint("clearance BETWEEN 1 AND 5", name="clearance_tiers"),
        schema="cont",
    )
    op.create_table(
        "agents",
        sa.Column("ship_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cell_id", UUID(as_uuid=True), sa.ForeignKey("cont.cells.id"), nullable=False),
        sa.Column("node", sa.String(16), nullable=False),
        sa.Column("clearance", sa.SmallInteger, nullable=False, server_default="1"),
        sa.Column("cover_faction_id", sa.SmallInteger),
        sa.Column("recruited_on", sa.Integer, nullable=False),
        sa.CheckConstraint("clearance BETWEEN 1 AND 5", name="agent_clearance_tiers"),
        schema="cont",
    )
    op.create_table(
        "interventions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("world_day", sa.Integer, nullable=False),
        sa.Column("cell_id", UUID(as_uuid=True), sa.ForeignKey("cont.cells.id")),
        sa.Column("region_id", UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("magnitude", sa.Numeric(5, 4), nullable=False),
        sa.Column("rationale", JSONB, nullable=False, server_default="{}"),
        schema="cont",
    )
    op.create_index("interventions_day", "interventions", ["world_day"], schema="cont")
    op.create_table(
        "budget",
        sa.Column("world_day", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("allowed", sa.Integer, nullable=False),
        sa.Column("used", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("used <= allowed", name="budget_not_exceeded"),
        schema="cont",
    )

    _ensure(API)
    for schema in PUBLIC_SCHEMAS:
        op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {API}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO {API}")
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {API}")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
                   f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {API}")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
                   f"GRANT USAGE, SELECT ON SEQUENCES TO {API}")
    op.execute(f"GRANT USAGE ON SCHEMA psycho TO {API}")
    op.execute(f"GRANT SELECT ON psycho.forecasts, psycho.history_variables TO {API}")
    # Deliberately absent: any grant on cont.

    _ensure(CONT)
    op.execute(f"GRANT USAGE ON SCHEMA cont TO {CONT}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA cont TO {CONT}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA cont "
               f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {CONT}")
    op.execute(f"GRANT USAGE ON SCHEMA core TO {CONT}")
    op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA core TO {CONT}")
    op.execute(f"GRANT USAGE ON SCHEMA psycho TO {CONT}")
    op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA psycho TO {CONT}")
    # The whole of its reach into the world: it may lean on populations, nothing else.
    op.execute(f"GRANT UPDATE ON core.system_activity TO {CONT}")


def downgrade() -> None:
    for table in ("budget", "interventions", "agents", "cells"):
        op.drop_table(table, schema="cont")
    op.execute("DROP SCHEMA IF EXISTS cont CASCADE")
