"""The generator is reproducible from a seed — SDD §7, task 1.4."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from frontier.adapters.clock import SeededRng
from frontier.adapters.db import models
from frontier.domain.hex.coordinates import Level
from frontier.worldgen.generator import Shape, generate, levels_used, summarise

pytestmark = pytest.mark.integration


def test_the_same_seed_builds_the_same_world():
    first = generate(SeededRng("a-seed").for_)
    second = generate(SeededRng("a-seed").for_)
    assert [(r.id, r.path.ltree(), r.kind) for r in first] == [(r.id, r.path.ltree(), r.kind) for r in second]


def test_a_different_seed_builds_a_different_world():
    assert [r.id for r in generate(SeededRng("a-seed").for_)] != [
        r.id for r in generate(SeededRng("b-seed").for_)
    ]


def test_the_generated_shape_matches_the_design():
    rows = generate(SeededRng("shape").for_)
    counts = summarise(rows)
    assert counts["galaxy"] == 1
    assert counts["region"] == Shape().regions
    assert 40 <= counts["system"] <= 56
    assert counts["star"] == counts["system"]
    assert levels_used(rows) == {Level.GALAXY, Level.REGION, Level.SYSTEM, Level.PLANET}


def test_every_system_hex_is_addressable():
    """A destination check is a lookup, not a radius calculation — D-17."""
    rows = generate(SeededRng("hexes").for_)
    per_system = 1 + 3 * 8 * 9
    assert sum(1 for r in rows if r.level == Level.PLANET) == per_system * summarise(rows)["system"]


async def test_the_world_is_written_with_one_spawn_per_faction(sessions):
    async with sessions() as session:
        spawns = (
            (
                await session.execute(
                    select(models.Location)
                    .where(models.Location.attrs.has_key("spawn"))
                    .order_by(models.Location.path)
                )
            )
            .scalars()
            .all()
        )
        stored = (await session.execute(select(func.count()).select_from(models.Location))).scalar_one()

    assert len(spawns) == 3
    assert {s.kind for s in spawns} == {"station"}
    assert {s.attrs["spawn"] for s in spawns} == {"empire", "republic", "pirates"}
    assert stored > 10_000


async def test_home_systems_start_discovered(sessions):
    async with sessions() as session:
        discovered = (
            await session.execute(
                select(func.count())
                .select_from(models.Location)
                .where(models.Location.discovered_on.is_not(None))
            )
        ).scalar_one()
    assert discovered > 0


def test_a_region_is_filled_space_not_a_scatter_of_systems():
    """Every region hex is a row, empty ones included — D-17, one level up."""
    shape = Shape(regions=2, region_radius=4, system_radius=2, systems_per_region=(3, 5))
    rows = generate(SeededRng("a-seed").for_, shape)

    hexes_in_a_disc = 1 + 3 * shape.region_radius * (shape.region_radius + 1)
    for region in (r for r in rows if r.kind == "region"):
        children = [r for r in rows if r.parent_id == region.id]
        assert len(children) == hexes_in_a_disc
        assert {r.kind for r in children} == {"system", "void"}


def test_the_galaxy_is_one_connected_shape():
    """Regions pack from the centre, so the galaxy map has no holes in it."""
    rows = generate(SeededRng("a-seed").for_, Shape(regions=4, region_radius=2, system_radius=2))
    regions = [(r.q, r.r) for r in rows if r.kind == "region"]

    for spot in regions[1:]:
        touching = any(
            (abs(spot[0] - o[0]) + abs(spot[1] - o[1]) + abs(spot[0] + spot[1] - o[0] - o[1])) / 2 == 1
            for o in regions
            if o != spot
        )
        assert touching, f"region at {spot} is detached from the rest of the galaxy"


def test_the_shape_is_rule_data_not_a_constant():
    """A bigger region is more empty space around the same systems."""
    small = generate(SeededRng("a-seed").for_, Shape(regions=1, region_radius=3, system_radius=2))
    large = generate(SeededRng("a-seed").for_, Shape(regions=1, region_radius=9, system_radius=2))

    voids = lambda rows: len([r for r in rows if r.kind == "void" and r.level == 1 + 1])  # noqa: E731
    assert voids(large) > voids(small)
