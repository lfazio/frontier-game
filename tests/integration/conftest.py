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
from frontier.cli.world import build_world
from frontier.config.settings import Settings

RULESET_ROOT = Path(__file__).resolve().parents[2] / "data" / "rulesets"
# Deleted in dependency order rather than truncated: `locations.discovered_by` references
# `players`, so TRUNCATE ... CASCADE would take the generated world with it.
PLAYER_TABLES = (
    "core.ap_ledger",
    "core.commands",
    "core.journeys",
    "core.ships",
    "core.players",
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
