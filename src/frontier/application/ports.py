"""Ports the application depends on. Adapters implement them — ARCH §3.1, SDD §5.1."""

from __future__ import annotations

from datetime import datetime
from random import Random
from typing import Protocol
from uuid import UUID

from frontier.domain.events.model import Event
from frontier.domain.fleet.ship import Ship
from frontier.domain.hex.coordinates import HexAddr


class ClockPort(Protocol):
    def now(self) -> datetime: ...


class RngPort(Protocol):
    def for_(self, *parts: str | int) -> Random: ...


class IdPort(Protocol):
    def new(self) -> UUID: ...


class Player(Protocol):
    id: UUID
    callsign: str
    ap_balance: int
    credits: int
    team_id: UUID | None
    faction_id: int | None
    clearance: int
    knowledge: int


class PlayerRepo(Protocol):
    async def get_for_update(self, player_id: UUID) -> Player: ...
    async def debit_ap(
        self, player_id: UUID, amount: int, command_id: UUID, reason: str, world_day: int
    ) -> None: ...


class ShipRepo(Protocol):
    async def of_player(self, player_id: UUID) -> Ship: ...
    async def save(self, ship: Ship) -> None: ...


class LocationRepo(Protocol):
    async def exists(self, addr: HexAddr) -> bool: ...


class CommandLog(Protocol):
    async def find(self, player_id: UUID, idempotency_key: UUID) -> dict[str, object] | None: ...
    async def record(
        self,
        player_id: UUID,
        key: UUID,
        action: str,
        status: str,
        outcome: dict[str, object],
        world_day: int,
        ruleset_version: str,
    ) -> None: ...


class EventSink(Protocol):
    async def append(self, events: list[Event]) -> None: ...


class WorldState(Protocol):
    async def phase(self) -> str: ...
    async def world_day(self) -> int: ...


class StateStore(Protocol):
    async def load(self, spec: object, player_id: UUID) -> object: ...
    async def save(self, state: object) -> None: ...


class UnitOfWork(Protocol):
    players: PlayerRepo
    ships: ShipRepo
    locations: LocationRepo
    commands: CommandLog
    events: EventSink
    world: WorldState
    state: StateStore

    async def __aenter__(self) -> UnitOfWork: ...
    async def __aexit__(self, *exc: object) -> None: ...
    async def commit(self) -> None: ...
