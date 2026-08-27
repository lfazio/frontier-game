"""The command template's guarantees — SDD §5.2."""

from __future__ import annotations

from uuid import uuid4

import pytest

from frontier.application.commands.move import MoveCommand
from frontier.application.executor import WorldTicking
from frontier.domain.hex.coordinates import Axial
from frontier.worldgen.fixture import HEXES, SYSTEM


def command(to=HEXES[1], key=None):
    return MoveCommand(id=uuid4(), idempotency_key=key or uuid4(), to=SYSTEM.child(to))


async def test_an_accepted_command_debits_ap_and_appends_an_event(container, world, player_id):
    before = world.players[player_id].ap_balance
    result = await container.executor.execute(command(), player_id)

    assert result.status == "accepted"
    assert world.players[player_id].ap_balance == before - 1
    assert len(world.events) == 1
    assert [r.delta for r in world.ledger] == [-1]


async def test_a_replayed_key_does_not_debit_twice(container, world, player_id):
    key = uuid4()
    await container.executor.execute(command(key=key), player_id)
    after_first = world.players[player_id].ap_balance

    replay = await container.executor.execute(command(key=key), player_id)

    assert replay.replayed is True
    assert world.players[player_id].ap_balance == after_first
    assert len(world.ledger) == 1


async def test_a_rejected_command_changes_nothing_but_is_recorded(container, world, player_id):
    world.add_location(SYSTEM.child(Axial(5, 0)))
    before = world.players[player_id].ap_balance

    result = await container.executor.execute(command(to=Axial(5, 0)), player_id)

    assert result.status == "rejected"
    assert world.players[player_id].ap_balance == before
    assert world.events == [] and world.ledger == []
    assert len(world.commands) == 1


async def test_ap_runs_out_after_ten_moves(container, world, player_id):
    """Criterion A2: the eleventh move is refused and nothing changes."""
    hexes = [HEXES[1], HEXES[0]] * 5
    for hex_ in hexes:
        assert (await container.executor.execute(command(to=hex_), player_id)).status == "accepted"

    assert world.players[player_id].ap_balance == 0
    eleventh = await container.executor.execute(command(to=HEXES[1]), player_id)

    assert eleventh.rejection.code.value == "INSUFFICIENT_AP"
    assert len(world.events) == 10
    assert sum(r.delta for r in world.ledger) == -10


async def test_commands_are_refused_while_the_world_turns(container, world, player_id):
    world.phase = "ticking"
    with pytest.raises(WorldTicking):
        await container.executor.execute(command(), player_id)


async def test_the_ledger_reconciles_with_the_balance(container, world, player_id):
    """Criterion A3."""
    granted = world.players[player_id].ap_balance
    for hex_ in (HEXES[1], HEXES[0], HEXES[2]):
        await container.executor.execute(command(to=hex_), player_id)

    assert granted + sum(r.delta for r in world.ledger) == world.players[player_id].ap_balance
