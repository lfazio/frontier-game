"""a crisis left alone long enough brings something with it

Revision ID: 0019
Revises: 0018

`answered_on` records the day an expired crisis raised its incursion, so the stage can tell an
unanswered crisis from one it has already dealt with. Without it the same expiry would raise a
fresh wave every cycle, for ever.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crises", sa.Column("answered_on", sa.Integer, nullable=True), schema="psycho")
    op.create_index(
        "crises_unanswered",
        "crises",
        ["expires_on"],
        schema="psycho",
        postgresql_where=sa.text("resolved_on IS NULL AND answered_on IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("crises_unanswered", table_name="crises", schema="psycho")
    op.drop_column("crises", "answered_on", schema="psycho")
