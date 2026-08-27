"""Fixtures for tests that need the database from `make up`."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from frontier.adapters.db import models
from frontier.adapters.db.engine import make_engine, make_sessionmaker
from frontier.adapters.rules_loader import load_ruleset
from frontier.cli.world import build_world
from frontier.config.settings import Settings

RULESET_ROOT = Path(__file__).resolve().parents[1] / "data" / "rulesets"
# Deleted in dependency order rather than truncated: `locations.discovered_by` references
# `players`, so TRUNCATE ... CASCADE would take the generated world with it.
PLAYER_TABLES = (
    "evt.events_outbox",
    "evt.event_deliveries",
    "evt.events",
    "evt.digests",
    "psycho.forecasts",
    "psycho.history_variables",
    "hist.chronicle",
    "core.mission_assignments",
    "core.missions",
    "core.reputation",
    "core.ap_ledger",
    "core.commands",
    "core.cargo",
    "core.encounter_queue",
    "core.npc_agents",
    "core.player_discoveries",
    "core.standing_orders",
    "core.journeys",
    "core.ships",
    "core.players",
    "core.teams",
    "core.accounts",
    "hist.tick_stages",
    "hist.tick_runs",
)


@pytest.fixture(scope="session")
def db_settings() -> Settings:
    settings = Settings(ruleset_root=RULESET_ROOT, jwt_secret="integration-secret-at-least-32-bytes-long")
    env = {**os.environ, "JWT_SECRET": settings.jwt_secret}
    assert (
        subprocess.run(["alembic", "upgrade", "head"], env=env, check=False, capture_output=True).returncode
        == 0
    )
    asyncio.run(build_world(settings, force=True))
    return settings


@pytest.fixture
async def clean(db_settings: Settings) -> Settings:
    """Every test starts from a generated world with no players and world day 0.

    Engines are created and disposed inside the test's own loop: asyncpg binds connections to
    the loop that opened them.
    """
    engine = make_engine(db_settings.database_url)
    async with engine.begin() as conn:
        # The migration tests roll the schema back and forward, which takes the world with it.
        # Regenerating here keeps every other test independent of run order.
        populated = (await conn.execute(select(func.count()).select_from(models.Location))).scalar_one()
        await conn.execute(text("UPDATE core.locations SET discovered_by = NULL"))
        for table in PLAYER_TABLES:
            await conn.execute(text(f"DELETE FROM {table}"))
        await conn.execute(text("UPDATE core.world_state SET world_day = 0, phase = 'open'"))
    await engine.dispose()
    if not populated:
        await build_world(db_settings, force=True)
    return db_settings


@pytest.fixture
async def sessions(clean: Settings):
    engine = make_engine(clean.database_url)
    yield make_sessionmaker(engine)
    await engine.dispose()


@pytest.fixture
def rules():
    return load_ruleset(RULESET_ROOT, "2026.1")
