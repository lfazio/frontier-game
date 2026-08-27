"""npc crews spend the same daily budget as pilots

Revision ID: 0014
Revises: 0013

GDD §2.7: an NPC is a ship with a pilot who happens to be a program, so nothing it does may be
cheaper for it than for a human.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("npc_agents", sa.Column("ap_balance", sa.Integer, nullable=False,
                                          server_default="0"), schema="core")
    op.add_column("npc_agents", sa.Column("last_grant_day", sa.Integer, nullable=False,
                                          server_default="-1"), schema="core")
    op.create_check_constraint("npc_ap_non_negative", "npc_agents", "ap_balance >= 0",
                               schema="core")


def downgrade() -> None:
    op.drop_constraint("npc_ap_non_negative", "npc_agents", schema="core")
    op.drop_column("npc_agents", "last_grant_day", schema="core")
    op.drop_column("npc_agents", "ap_balance", schema="core")
