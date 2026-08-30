"""an operator may ask for a retry; the worker is what runs it

Revision ID: 0021
Revises: 0020

The console cannot run a tick — that is the worker's job, and a console that could would be able
to change the world (ADMIN §4). What it can do is leave a request on the run, which is the one
table it is allowed to write (ADMIN §6).

A failed tick already resumes by itself on the next run: `_open_day` finds the open row and
carries on from the stage that broke. The request is therefore a signal to run *sooner*, not a
new resume path, and a worker that never reads it changes nothing.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tick_runs",
        sa.Column("retry_requested_at", sa.DateTime(timezone=True), nullable=True),
        schema="hist",
    )
    # Who asked. Not a foreign key: `admin.operators` is the console's register, and the world's
    # own schema does not depend on the console existing at all.
    op.add_column(
        "tick_runs",
        sa.Column("retry_requested_by", UUID(as_uuid=True), nullable=True),
        schema="hist",
    )


def downgrade() -> None:
    op.drop_column("tick_runs", "retry_requested_by", schema="hist")
    op.drop_column("tick_runs", "retry_requested_at", schema="hist")
