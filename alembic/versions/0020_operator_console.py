"""the operator console: its own schema, its own role, and a read-mostly boundary

Revision ID: 0020
Revises: 0019

`admin_role` is the fourth role, defined the way the other three are — by what the database will
let it do (ARCH ADR-13). It reads widely, including `cont`, because whoever runs a world already
can and pretending otherwise would be theatre. It writes exactly one thing: the marker that lets
a failed tick be resumed. A console that cannot write cannot be the cause of a dispute about
what happened.

The registry itself — who may operate, and who let them in — lives in `admin`, which `api_role`
holds nothing on. An operator account is not a player account: different tables, different
tokens, and neither surface mentions the other (ADMIN §2).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

ADMIN = "admin_role"
API = "api_role"
READABLE = ("core", "evt", "hist", "psycho", "cont")


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS admin")
    op.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ADMIN}') THEN
                CREATE ROLE {ADMIN} NOLOGIN;
            END IF;
        END $$
    """)

    op.create_table(
        "operators",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_on", sa.Integer, nullable=False, server_default="0"),
        schema="admin",
    )
    op.create_table(
        "grants",
        sa.Column("operator_id", UUID(as_uuid=True), sa.ForeignKey("admin.operators.id"), primary_key=True),
        # A world is named, never joined to: the console reaches several worlds, and each is its
        # own database (ADMIN §2, QA-3).
        sa.Column("world", sa.String(64), primary_key=True),
        sa.Column("permission", sa.String(16), nullable=False),
        # Null only for the origin, who was let in by nobody.
        sa.Column("granted_by", UUID(as_uuid=True), sa.ForeignKey("admin.operators.id"), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="admin",
    )
    op.create_check_constraint(
        "permission_is_known",
        "grants",
        "permission IN ('origin', 'watch', 'operate', 'directorate')",
        schema="admin",
    )
    # The origin is what a world falls back on: exactly one per world, and nothing may remove it.
    op.execute("""
        CREATE UNIQUE INDEX grants_one_origin_per_world
        ON admin.grants (world) WHERE permission = 'origin'
    """)

    op.execute(f"GRANT USAGE ON SCHEMA admin TO {ADMIN}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA admin TO {ADMIN}")
    for schema in READABLE:
        op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {ADMIN}")
        op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {ADMIN}")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO {ADMIN}")
    # The single write into the world: marking a failed tick resumable (ADMIN §6).
    op.execute(f"GRANT UPDATE ON hist.tick_runs TO {ADMIN}")

    # The game's own role has no business in the registry, and never learns it exists.
    op.execute(f"REVOKE ALL ON SCHEMA admin FROM {API}")
    op.execute(f"GRANT {ADMIN} TO CURRENT_USER")


def downgrade() -> None:
    for schema in READABLE:
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} REVOKE SELECT ON TABLES FROM {ADMIN}")
        op.execute(f"REVOKE ALL ON SCHEMA {schema} FROM {ADMIN}")
    op.execute("DROP INDEX IF EXISTS admin.grants_one_origin_per_world")
    op.drop_table("grants", schema="admin")
    op.drop_table("operators", schema="admin")
    op.execute("DROP SCHEMA IF EXISTS admin CASCADE")
