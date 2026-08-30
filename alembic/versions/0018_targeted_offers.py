"""an offer addressed to one pilot, and the narrow grant that lets it be posted

Revision ID: 0018
Revises: 0017

Q-F asked which boundary should give: `cont_role` writing `core.missions`, or stage 6 reading
`cont`. Neither. A mission may be *addressed* to a pilot, and the Continuity's capability is to
post an addressed offer — not to write missions in general, and not to touch the pilot.

`offered_to` is null for every ordinary mission, which is every mission the game has today, so
the board is unchanged for everyone who is not being spoken to.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

CONT = "cont_role"


def upgrade() -> None:
    op.add_column(
        "missions",
        sa.Column("offered_to", UUID(as_uuid=True), sa.ForeignKey("core.players.id"), nullable=True),
        schema="core",
    )
    # The board query filters on it every time it is read.
    op.create_index(
        "missions_addressed",
        "missions",
        ["offered_to"],
        schema="core",
        postgresql_where=sa.text("offered_to IS NOT NULL"),
    )
    # Narrow by construction: INSERT only. The faction may put an offer in front of someone; it
    # may not edit or withdraw one, and it still holds nothing on `core.players`.
    op.execute(f"GRANT INSERT ON core.missions TO {CONT}")
    op.execute(f"GRANT SELECT ON core.players TO {CONT}")


def downgrade() -> None:
    op.execute(f"REVOKE INSERT ON core.missions FROM {CONT}")
    op.drop_index("missions_addressed", table_name="missions", schema="core")
    op.drop_column("missions", "offered_to", schema="core")
