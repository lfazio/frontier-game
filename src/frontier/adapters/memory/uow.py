"""A unit of work over the in-memory world, with rollback so failures behave like a database."""

from __future__ import annotations

import copy
from types import TracebackType
from uuid import UUID

from frontier.adapters.memory.store import ApLedgerRow, World
from frontier.domain.events.model import Event
from frontier.domain.fleet.ship import Ship
from frontier.domain.hex.coordinates import HexAddr


class _Players:
    def __init__(self, world: World) -> None:
        self._w = world

    async def get_for_update(self, player_id: UUID) -> object:
        return self._w.players[player_id]

    async def debit_ap(
        self, player_id: UUID, amount: int, command_id: UUID, reason: str, world_day: int
    ) -> None:
        player = self._w.players[player_id]
        if player.ap_balance < amount:
            raise ValueError("ap_balance would go negative")
        player.ap_balance -= amount
        self._w.ledger.append(ApLedgerRow(player_id, -amount, reason, command_id))


class _Ships:
    def __init__(self, world: World) -> None:
        self._w = world

    async def of_player(self, player_id: UUID) -> Ship:
        return self._w.ship_of(player_id)

    async def save(self, ship: Ship) -> None:
        self._w.ships[ship.id] = ship


class _Locations:
    def __init__(self, world: World) -> None:
        self._w = world

    async def exists(self, addr: HexAddr) -> bool:
        return str(addr) in self._w.locations


class _Commands:
    def __init__(self, world: World) -> None:
        self._w = world

    async def find(self, player_id: UUID, idempotency_key: UUID) -> dict[str, object] | None:
        return self._w.commands.get((player_id, idempotency_key))

    async def record(
        self,
        player_id: UUID,
        key: UUID,
        action: str,
        status: str,
        outcome: dict[str, object],
        world_day: int,
        ruleset_version: str,
    ) -> None:
        self._w.commands[(player_id, key)] = {
            "action": action,
            "status": status,
            "outcome": outcome,
            "world_day": world_day,
            "ruleset_version": ruleset_version,
        }


class _Events:
    def __init__(self, world: World) -> None:
        self._w = world

    async def append(self, events: list[Event]) -> None:
        self._w.events.extend(events)


class _WorldState:
    def __init__(self, world: World) -> None:
        self._w = world

    async def phase(self) -> str:
        return self._w.phase

    async def world_day(self) -> int:
        return self._w.world_day


class MemoryUnitOfWork:
    def __init__(self, world: World) -> None:
        self._committed = world
        self._snapshot: World | None = None
        self.world = _WorldState(world)

    async def __aenter__(self) -> MemoryUnitOfWork:
        self._snapshot = copy.deepcopy(self._committed)
        self.players = _Players(self._committed)
        self.ships = _Ships(self._committed)
        self.locations = _Locations(self._committed)
        self.commands = _Commands(self._committed)
        self.events = _Events(self._committed)
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        if exc_type is not None and self._snapshot is not None:
            self._restore(self._snapshot)
        self._snapshot = None

    async def commit(self) -> None:
        self._snapshot = copy.deepcopy(self._committed)

    def _restore(self, snapshot: World) -> None:
        w = self._committed
        w.players, w.ships, w.locations = snapshot.players, snapshot.ships, snapshot.locations
        w.ledger, w.commands, w.events = snapshot.ledger, snapshot.commands, snapshot.events
        w.phase = snapshot.phase
