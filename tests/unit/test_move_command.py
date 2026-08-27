"""The move rule, as SDD §5.4 orders its preconditions."""

from __future__ import annotations

from uuid import uuid4

import pytest

from frontier.application.commands.base import State
from frontier.application.commands.move import MoveCommand
from frontier.domain.decisions import Accepted, Rejected, RejectionCode
from frontier.domain.hex.coordinates import Axial
from frontier.worldgen.fixture import HEXES, SYSTEM, starting_position


class _Player:
    def __init__(self, ap: int) -> None:
        self.id, self.ap_balance, self.credits = uuid4(), ap, 0


def build_state(world, player_id, ap: int | None = None):
    player = world.players[player_id]
    if ap is not None:
        player.ap_balance = ap
    ship = world.ship_of(player_id)
    return State(player=player, ship=ship, known_addresses=frozenset(world.locations))


def move_to(hex_: Axial) -> MoveCommand:
    return MoveCommand(id=uuid4(), idempotency_key=uuid4(), to=SYSTEM.child(hex_))


def test_an_adjacent_hex_is_accepted(world, player_id, rules):
    decision = move_to(HEXES[1]).check(build_state(world, player_id), rules)
    assert decision == Accepted(ap_cost=1, fuel_cost=1)


def test_a_distant_hex_is_not_adjacent(world, player_id, rules):
    world.add_location(SYSTEM.child(Axial(5, 0)))
    decision = move_to(Axial(5, 0)).check(build_state(world, player_id), rules)
    assert isinstance(decision, Rejected) and decision.code is RejectionCode.NOT_ADJACENT


def test_a_destination_outside_the_world_is_refused(world, player_id, rules):
    decision = move_to(Axial(42, 42)).check(build_state(world, player_id), rules)
    assert isinstance(decision, Rejected) and decision.code is RejectionCode.UNKNOWN_DESTINATION


def test_a_docked_ship_must_launch_first(world, player_id, rules):
    world.ship_of(player_id).docked_at = uuid4()
    decision = move_to(HEXES[1]).check(build_state(world, player_id), rules)
    assert isinstance(decision, Rejected) and decision.code is RejectionCode.MUST_LAUNCH_FIRST


def test_transit_is_checked_before_docking(world, player_id, rules):
    ship = world.ship_of(player_id)
    ship.in_transit, ship.docked_at = True, uuid4()
    decision = move_to(HEXES[1]).check(build_state(world, player_id), rules)
    assert isinstance(decision, Rejected) and decision.code is RejectionCode.IN_TRANSIT


def test_ap_is_checked_before_fuel(world, player_id, rules):
    world.ship_of(player_id).fuel = 0
    decision = move_to(HEXES[1]).check(build_state(world, player_id, ap=0), rules)
    assert isinstance(decision, Rejected) and decision.code is RejectionCode.INSUFFICIENT_AP


def test_an_empty_tank_stops_the_ship(world, player_id, rules):
    world.ship_of(player_id).fuel = 0
    decision = move_to(HEXES[1]).check(build_state(world, player_id), rules)
    assert isinstance(decision, Rejected) and decision.code is RejectionCode.INSUFFICIENT_FUEL


def test_apply_moves_the_ship_and_burns_fuel(world, player_id, rules):
    state = build_state(world, player_id)
    command = move_to(HEXES[1])
    accepted = command.check(state, rules)
    fuel_before = state.ship.fuel
    events = command.apply(state, accepted, rules, rng=None)

    assert state.ship.position == SYSTEM.child(HEXES[1])
    assert state.ship.fuel == fuel_before - 1
    assert [e.type.value for e in events] == ["SHIP_ENTERED"]
    assert events[0].payload["from"] == str(starting_position())
    assert events[0].payload["actor_kind"] == "player"


@pytest.mark.parametrize("hex_", HEXES[1:])
def test_every_neighbour_of_the_start_is_reachable(world, player_id, rules, hex_):
    assert isinstance(move_to(hex_).check(build_state(world, player_id), rules), Accepted)
