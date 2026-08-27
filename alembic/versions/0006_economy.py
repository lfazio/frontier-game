"""cargo, standing orders and station markets

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cargo",
        sa.Column("ship_id", UUID(as_uuid=True), sa.ForeignKey("core.ships.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("commodity", sa.String(24), primary_key=True),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("avg_unit_cost", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("qty > 0", name="cargo_positive"),
        schema="core",
    )
    op.create_table(
        "standing_orders",
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("core.players.id"), primary_key=True),
        sa.Column("posture", sa.String(20), nullable=False, server_default="evade"),
        sa.Column("engage_hostile", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("engage_above_cargo", sa.Integer),
        sa.Column("retreat_at_hull_pct", sa.Integer, nullable=False, server_default="50"),
        sa.Column("auto_reply", sa.String(200)),
        sa.CheckConstraint("retreat_at_hull_pct BETWEEN 0 AND 100", name="retreat_pct_range"),
        schema="core",
    )
    op.create_table(
        "markets",
        sa.Column("station_id", UUID(as_uuid=True), sa.ForeignKey("core.locations.id"),
                  primary_key=True),
        sa.Column("commodity", sa.String(24), primary_key=True),
        sa.Column("stock", sa.Integer, nullable=False),
        sa.Column("target_stock", sa.Integer, nullable=False),
        sa.Column("base_price", sa.Integer, nullable=False),
        sa.CheckConstraint("stock >= 0", name="stock_non_negative"),
        schema="core",
    )


def downgrade() -> None:
    for table in ("markets", "standing_orders", "cargo"):
        op.drop_table(table, schema="core")
