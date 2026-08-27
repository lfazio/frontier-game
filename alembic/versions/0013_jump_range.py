"""every hull has a jump range of its own

Revision ID: 0013
Revises: 0012

Design answer S3: how far a ship can jump depends on the ship, not only on the tank.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ships", sa.Column("jump_range_ly", sa.Integer, nullable=False,
                                     server_default="8"), schema="core")


def downgrade() -> None:
    op.drop_column("ships", "jump_range_ly", schema="core")
