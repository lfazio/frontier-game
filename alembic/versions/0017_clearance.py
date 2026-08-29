"""clearance as a property of a pilot, and a generation for a pilot who is replaced

Revision ID: 0017
Revises: 0016

Clearance sits on `core.players` rather than in `cont`, so resolving who may receive a
`CLEARANCE` event is ordinary SQL over ordinary tables: the delivery code never mentions the
hidden faction, and its import graph and stack traces stay clean (GDD §9.4). The column is
never serialised — the anti-leak suite asserts that over every player-facing response.

`generation` is what makes a lost pilot a *new* pilot rather than a mutated one (GDD §9.14).
There is deliberately no column linking the two: re-recruitment evaluates the new pilot's own
record, so the link is not merely forbidden but unnecessary (ARCH §18).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("clearance", sa.SmallInteger, nullable=False, server_default="0"),
        schema="core",
    )
    op.add_column(
        "players",
        sa.Column("generation", sa.SmallInteger, nullable=False, server_default="1"),
        schema="core",
    )
    op.create_check_constraint("clearance_non_negative", "players", "clearance >= 0", schema="core")
    op.create_check_constraint("generation_positive", "players", "generation >= 1", schema="core")
    # Deliveries for a clearance event are resolved by this predicate, so it is worth an index.
    op.create_index(
        "players_cleared",
        "players",
        ["clearance"],
        schema="core",
        postgresql_where=sa.text("clearance > 0"),
    )


def downgrade() -> None:
    op.drop_index("players_cleared", table_name="players", schema="core")
    op.drop_constraint("generation_positive", "players", schema="core")
    op.drop_constraint("clearance_non_negative", "players", schema="core")
    op.drop_column("players", "generation", schema="core")
    op.drop_column("players", "clearance", schema="core")
