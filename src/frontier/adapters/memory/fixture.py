"""Loads the fixture world into the in-memory store."""

from __future__ import annotations

from frontier.adapters.memory.store import World
from frontier.worldgen.fixture import addresses


def seed_fixture_world(world: World) -> None:
    for addr in addresses():
        world.add_location(addr)
