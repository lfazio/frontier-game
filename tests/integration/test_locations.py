"""Containment is a prefix test, and `<@` is its index — SDD §4.2, task 1.3."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text

from frontier.adapters.db import models
from frontier.adapters.db.repositories import LocationRepo
from frontier.domain.hex.coordinates import HexAddr

pytestmark = pytest.mark.integration


async def test_a_system_query_returns_exactly_its_subtree(sessions):
    async with sessions() as session:
        system = (
            await session.execute(
                select(models.Location)
                .where(models.Location.kind == "system")
                .order_by(models.Location.path)
                .limit(1)
            )
        ).scalar_one()

        subtree = await LocationRepo(session).within(system.path)
        direct = (
            await session.execute(
                select(func.count())
                .select_from(models.Location)
                .where(models.Location.parent_id == system.id)
            )
        ).scalar_one()

    assert all(system.path.contains(row.path) for row in subtree)
    assert len(subtree) == direct + 1  # the children, plus the system itself


async def test_the_galaxy_contains_everything(sessions):
    async with sessions() as session:
        total = (await session.execute(select(func.count()).select_from(models.Location))).scalar_one()
        galaxy = (
            await session.execute(select(models.Location).where(models.Location.kind == "galaxy"))
        ).scalar_one()
        assert len(await LocationRepo(session).within(galaxy.path)) == total


async def test_a_path_outside_the_world_matches_nothing(sessions):
    async with sessions() as session:
        assert await LocationRepo(session).within(HexAddr.parse("ga9_9")) == []


async def test_the_gist_index_is_used_for_containment(sessions):
    """A sequential scan here would be a silent performance regression."""
    async with sessions() as session:
        system = (
            await session.execute(
                select(models.Location)
                .where(models.Location.kind == "system")
                .order_by(models.Location.path)
                .limit(1)
            )
        ).scalar_one()
        plan = (
            (
                await session.execute(
                    text("EXPLAIN SELECT id FROM core.locations WHERE path <@ CAST(:p AS ltree)").bindparams(
                        p=system.path.ltree()
                    )
                )
            )
            .scalars()
            .all()
        )

    assert any("locations_path_gist" in line for line in plan), plan


async def test_addresses_round_trip_through_the_database(sessions):
    async with sessions() as session:
        row = (
            await session.execute(
                select(models.Location)
                .where(models.Location.kind == "station")
                .order_by(models.Location.path)
                .limit(1)
            )
        ).scalar_one()

    assert isinstance(row.path, HexAddr)
    assert HexAddr.parse(str(row.path)) == row.path
    assert row.path.tip.q == row.q and row.path.tip.r == row.r
