"""crises and eras: what a sustained strain becomes, and what history calls it

Revision ID: 0016
Revises: 0015

Both tables live in `psycho` and carry no foreign key to `core`, exactly as the variables and
forecasts beside them do: the reader role has no privilege on `core`, so a reference it could
not follow would be a lie in the schema (ARCH ADR-12).

Neither table has a player column, and PSDD B4 asserts that over the whole schema rather than
by sampling. The Model measures regions; naming a player is the one thing it may never do.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

API = "api_role"
READER = "psycho_reader"
CONT = "cont_role"


def upgrade() -> None:
    op.create_table(
        "crises",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("region_id", UUID(as_uuid=True), nullable=False),
        sa.Column("variable", sa.String(32), nullable=False),
        sa.Column("opened_on", sa.Integer, nullable=False),
        sa.Column("expires_on", sa.Integer, nullable=False),
        sa.Column("resolved_on", sa.Integer, nullable=True),
        sa.Column("severity", sa.SmallInteger, nullable=False),
        sa.Column("magnitude", sa.Numeric(6, 4), nullable=False),
        schema="psycho",
    )
    # One open crisis per region and variable: a strain that is already named does not get
    # named again every cycle it persists.
    op.execute("""
        CREATE UNIQUE INDEX crises_one_open_per_variable
        ON psycho.crises (region_id, variable)
        WHERE resolved_on IS NULL
    """)
    op.create_index(
        "crises_open",
        "crises",
        ["expires_on"],
        schema="psycho",
        postgresql_where=sa.text("resolved_on IS NULL"),
    )

    op.create_table(
        "eras",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("began_on", sa.Integer, nullable=False),
        sa.Column("ended_on", sa.Integer, nullable=True),
        sa.Column("summary", sa.String(280), nullable=True),
        schema="psycho",
    )
    op.execute("CREATE UNIQUE INDEX eras_one_open ON psycho.eras ((ended_on IS NULL)) WHERE ended_on IS NULL")

    for role in (READER, CONT):
        op.execute(f"GRANT SELECT ON psycho.crises, psycho.eras TO {role}")
    # The API reads them for the two history endpoints; the stages write them.
    op.execute(f"GRANT SELECT ON psycho.crises, psycho.eras TO {API}")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS psycho.eras_one_open")
    op.drop_table("eras", schema="psycho")
    op.execute("DROP INDEX IF EXISTS psycho.crises_open")
    op.execute("DROP INDEX IF EXISTS psycho.crises_one_open_per_variable")
    op.drop_table("crises", schema="psycho")
