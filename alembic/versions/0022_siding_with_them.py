"""a pilot may side with an incursion, and the record of it does not wash off

Revision ID: 0022
Revises: 0021

Two columns, and the difference between them is the design (GDD §8.12):

  `allegiance`      what a pilot is doing now, and may stop doing.
  `first_sided_on`  that they ever did, which nothing clears.

The penalty attaches to the second. A cost that could be shed by renouncing at the right moment
would make collaboration a tactic rather than a choice about which side of a war you are on.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("allegiance", sa.String(16), nullable=True), schema="core")
    op.add_column("players", sa.Column("first_sided_on", sa.Integer, nullable=True), schema="core")
    op.create_check_constraint(
        "allegiance_is_known", "players", "allegiance IS NULL OR allegiance = 'incursion'", schema="core"
    )
    # Collaboration is public by design, so this index serves the world, not a secret.
    op.create_index(
        "players_sided",
        "players",
        ["allegiance"],
        schema="core",
        postgresql_where=sa.text("allegiance IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("players_sided", table_name="players", schema="core")
    op.drop_constraint("allegiance_is_known", "players", schema="core")
    op.drop_column("players", "first_sided_on", schema="core")
    op.drop_column("players", "allegiance", schema="core")
