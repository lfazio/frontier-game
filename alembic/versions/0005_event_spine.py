"""the event spine: partitioned log, deliveries and outbox

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from frontier.adapters.db.types import LTree

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

PARTITION_DAYS = 30
PARTITIONS = 12


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS evt")
    op.execute(f"""
        CREATE TABLE evt.events (
            id              uuid        NOT NULL,
            world_day       int         NOT NULL,
            occurred_at     timestamptz NOT NULL,
            type            text        NOT NULL,
            origin_path     ltree       NOT NULL,
            scope           smallint    NOT NULL,
            visibility      text        NOT NULL,
            clearance       smallint    NOT NULL DEFAULT 0,
            severity        smallint    NOT NULL,
            participants    uuid[]      NOT NULL DEFAULT '{{}}',
            payload         jsonb       NOT NULL,
            ruleset_version text        NOT NULL,
            causation_id    uuid,
            PRIMARY KEY (world_day, id)
        ) PARTITION BY RANGE (world_day)
    """)
    for index in range(PARTITIONS):
        low, high = index * PARTITION_DAYS, (index + 1) * PARTITION_DAYS
        op.execute(
            f"CREATE TABLE evt.events_d{low:05d} PARTITION OF evt.events "
            f"FOR VALUES FROM ({low}) TO ({high})"
        )
    op.execute("CREATE INDEX events_path_gist ON evt.events USING gist (origin_path)")
    op.execute("CREATE INDEX events_id ON evt.events (id)")

    op.create_table(
        "event_deliveries",
        sa.Column("recipient_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", UUID(as_uuid=True), nullable=False),
        sa.Column("world_day", sa.Integer, nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("recipient_id", "event_id"),
        schema="evt",
    )
    op.create_index("deliveries_unread", "event_deliveries", ["recipient_id", "event_id"],
                    schema="evt", postgresql_where=sa.text("read_at IS NULL"))

    op.create_table(
        "events_outbox",
        sa.Column("event_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("world_day", sa.Integer, nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="evt",
    )

    op.create_table(
        "digests",
        sa.Column("player_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("world_day", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("summary", JSONB, nullable=False, server_default="{}"),
        schema="evt",
    )
    # Silences an unused-import warning while keeping the type available to later revisions.
    assert LTree is not None


def downgrade() -> None:
    op.drop_table("digests", schema="evt")
    op.drop_table("events_outbox", schema="evt")
    op.drop_table("event_deliveries", schema="evt")
    op.execute("DROP TABLE evt.events CASCADE")
