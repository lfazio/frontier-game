"""the historical model: aggregate views, variables and forecasts

Revision ID: 0011
Revises: 0010

The `psycho` schema is the Model's whole window onto the world. Its views expose regional
aggregates and no player column at all, and the reader role holds no privilege on `core`, so
GDD §8.4 — the Model predicts populations, never individuals — is enforced by grants rather
than by developer discipline (ARCH ADR-12).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

READER = "psycho_reader"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS psycho")

    op.execute("""
        CREATE VIEW psycho.v_region_economy AS
        SELECT region.id AS region_id,
               count(*)::int                                   AS markets,
               avg(m.stock::numeric / GREATEST(m.target_stock, 1)) AS stock_ratio,
               avg(m.base_price)::numeric                      AS mean_base_price
        FROM core.markets m
        JOIN core.locations station ON station.id = m.station_id
        JOIN core.locations system  ON system.id  = station.parent_id
        JOIN core.locations region  ON region.id  = system.parent_id
        GROUP BY region.id
    """)
    op.execute("""
        CREATE VIEW psycho.v_region_control AS
        SELECT region.id AS region_id, t.faction_id, avg(t.influence) AS influence
        FROM core.territory t
        JOIN core.locations system ON system.id = t.system_id
        JOIN core.locations region ON region.id = system.parent_id
        GROUP BY region.id, t.faction_id
    """)
    op.execute("""
        CREATE VIEW psycho.v_region_population AS
        SELECT region.id AS region_id,
               avg(a.trade_flow)      AS trade_flow,
               avg(a.patrol_strength) AS patrol_strength,
               avg(a.raider_pressure) AS raider_pressure
        FROM core.system_activity a
        JOIN core.locations system ON system.id = a.system_id
        JOIN core.locations region ON region.id = system.parent_id
        GROUP BY region.id
    """)
    # Counts only. No participants, no actor: an event's cast is not the Model's business.
    op.execute("""
        CREATE VIEW psycho.v_region_conflict AS
        SELECT region.id AS region_id, e.world_day,
               count(*) FILTER (WHERE e.type = 'COMBAT_RESOLVED')::int AS combats,
               count(*) FILTER (WHERE e.type = 'SHIP_DESTROYED')::int  AS losses,
               COALESCE(sum(e.severity), 0)::int                       AS severity
        FROM evt.events e
        JOIN core.locations origin ON origin.path = e.origin_path
        JOIN core.locations system ON system.id = origin.parent_id
        JOIN core.locations region ON region.id = system.parent_id
        GROUP BY region.id, e.world_day
    """)

    op.create_table(
        "history_variables",
        sa.Column("region_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("world_day", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("variable", sa.String(32), primary_key=True),
        sa.Column("observed", sa.Numeric(8, 4), nullable=False),
        sa.Column("expected", sa.Numeric(8, 4), nullable=False),
        schema="psycho",
    )
    op.create_table(
        "forecasts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("region_id", UUID(as_uuid=True), nullable=False),
        sa.Column("world_day", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("probability", sa.Numeric(5, 4), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("deviation", sa.Numeric(6, 4), nullable=False),
        sa.UniqueConstraint("region_id", "world_day", "kind", name="one_forecast_per_kind"),
        schema="psycho",
    )
    op.create_index("forecasts_day", "forecasts", ["world_day"], schema="psycho")

    op.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{READER}') THEN
                CREATE ROLE {READER} NOLOGIN;
            END IF;
        END $$
    """)
    op.execute(f"GRANT USAGE ON SCHEMA psycho TO {READER}")
    op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA psycho TO {READER}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA psycho GRANT SELECT ON TABLES TO {READER}")
    # Deliberately absent: any grant on core or evt. The views are the only window.
    op.execute(f"GRANT {READER} TO CURRENT_USER")


def downgrade() -> None:
    op.drop_table("forecasts", schema="psycho")
    op.drop_table("history_variables", schema="psycho")
    for view in ("v_region_conflict", "v_region_population", "v_region_control", "v_region_economy"):
        op.execute(f"DROP VIEW IF EXISTS psycho.{view}")
    op.execute("DROP SCHEMA IF EXISTS psycho CASCADE")
