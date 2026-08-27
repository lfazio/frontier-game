"""Migrations apply, roll back and roll forward — SDD §15 task 0.4.

Marked `integration`: it needs the Postgres from `make up`.
"""

from __future__ import annotations

import os
import subprocess

import pytest

pytestmark = pytest.mark.integration


def alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "JWT_SECRET": "integration-secret-at-least-32-bytes-long"}
    return subprocess.run(["alembic", *args], capture_output=True, text=True, env=env, check=False)


@pytest.fixture(scope="module", autouse=True)
def _at_head():
    assert alembic("upgrade", "head").returncode == 0
    yield


def test_the_schema_rolls_back_and_forward_again():
    assert alembic("downgrade", "base").returncode == 0
    assert alembic("upgrade", "head").returncode == 0


def test_the_three_factions_are_seeded():
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from frontier.config.settings import Settings

    async def read() -> list[str]:
        engine = create_async_engine(Settings().database_url)
        async with engine.connect() as conn:
            rows = await conn.execute(text("SELECT code FROM core.factions ORDER BY id"))
            result = [r[0] for r in rows]
        await engine.dispose()
        return result

    assert asyncio.run(read()) == ["empire", "republic", "pirates"]


def test_a_negative_ap_balance_is_refused_by_the_database():
    """Criterion A3 is enforced by a CHECK, not only by application code."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import create_async_engine

    from frontier.config.settings import Settings

    async def attempt() -> None:
        engine = create_async_engine(Settings().database_url)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO core.accounts (id, email, password_hash)"
                    " VALUES (gen_random_uuid(), 'neg@example.com', 'x')"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO core.players (id, account_id, callsign, ap_balance)"
                    " SELECT gen_random_uuid(), id, 'Negative', -1 FROM core.accounts"
                    " WHERE email = 'neg@example.com'"
                )
            )
        await engine.dispose()

    with pytest.raises(IntegrityError):
        asyncio.run(attempt())
