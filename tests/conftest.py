from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from frontier.adapters.memory.fixture import seed_fixture_world
from frontier.adapters.memory.store import MemoryPlayer, World
from frontier.adapters.rules_loader import load_ruleset
from frontier.config.container import build
from frontier.config.settings import Settings
from frontier.domain.fleet.ship import Ship
from frontier.worldgen.fixture import STARTING_SHIP, starting_position

RULESET_ROOT = Path(__file__).resolve().parents[1] / "data" / "rulesets"


@pytest.fixture
def rules():
    return load_ruleset(RULESET_ROOT, "2026.1")


@pytest.fixture
def settings():
    return Settings(ruleset_root=RULESET_ROOT, jwt_secret="test-secret-" + "x" * 32)


@pytest.fixture
def world(rules):
    w = World()
    seed_fixture_world(w)
    player = MemoryPlayer(id=uuid4(), callsign="Test", ap_balance=rules.ap.daily_grant)
    w.players[player.id] = player
    ship = Ship(id=uuid4(), player_id=player.id, position=starting_position(), **STARTING_SHIP)
    w.ships[ship.id] = ship
    return w


@pytest.fixture
def player_id(world):
    return next(iter(world.players))


@pytest.fixture
def container(settings, world):
    return build(settings=settings, world=world)
