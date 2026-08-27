"""A walking skeleton of the daily loop: register, move, run out of AP.

`make demo`. It exists so the command path can be watched without a client.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from frontier.adapters.memory.fixture import seed_fixture_world
from frontier.adapters.memory.store import MemoryPlayer, World
from frontier.application.commands.move import MoveCommand
from frontier.config.container import build
from frontier.config.settings import Settings
from frontier.domain.fleet.ship import Ship
from frontier.worldgen.fixture import HEXES, STARTING_SHIP, SYSTEM, starting_position


async def main() -> None:
    world = World()
    seed_fixture_world(world)
    container = build(settings=Settings(), world=world)
    rules = container.executor.rules

    player = MemoryPlayer(id=uuid4(), callsign="Cmdr Demo", ap_balance=rules.ap.daily_grant)
    world.players[player.id] = player
    ship = Ship(id=uuid4(), player_id=player.id, position=starting_position(), **STARTING_SHIP)
    world.ships[ship.id] = ship

    print(f"ruleset {rules.version}   world day {world.world_day}")
    print(f"start    {ship.position}  ap={player.ap_balance} fuel={ship.fuel}\n")

    for step in range(12):
        target = SYSTEM.child(HEXES[1 if step % 2 == 0 else 0])
        command = MoveCommand(id=uuid4(), idempotency_key=uuid4(), to=target)
        result = await container.executor.execute(command, player.id)
        outcome = result.rejection.code.value if result.rejection else "moved"
        print(f"  {step + 1:>2}. {outcome:<16} {ship.position}  ap={player.ap_balance} fuel={ship.fuel}")

    print(
        f"\nevents {len(world.events)}   ledger {sum(r.delta for r in world.ledger)} AP"
        f"   balance {player.ap_balance}"
    )


if __name__ == "__main__":
    asyncio.run(main())
