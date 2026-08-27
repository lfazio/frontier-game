"""knowledge as a strategic resource

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("knowledge", sa.Integer, nullable=False,
                                       server_default="0"), schema="core")
    op.create_check_constraint("knowledge_non_negative", "players", "knowledge >= 0", schema="core")


def downgrade() -> None:
    op.drop_constraint("knowledge_non_negative", "players", schema="core")
    op.drop_column("players", "knowledge", schema="core")
