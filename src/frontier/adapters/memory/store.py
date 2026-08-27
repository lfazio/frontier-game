"""In-memory adapters. P0 proves the ports; SQLAlchemy repositories land in P1 and P3."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from frontier.domain.events.model import Event
from frontier.domain.fleet.ship import Ship
from frontier.domain.hex.coordinates import HexAddr


@dataclass(slots=True)
class MemoryPlayer:
    id: UUID
    callsign: str
    ap_balance: int
    credits: int = 0


@dataclass(slots=True)
class Account:
    id: UUID
    email: str
    password_hash: str
    player_id: UUID


@dataclass(slots=True)
class ApLedgerRow:
    player_id: UUID
    delta: int
    reason: str
    command_id: UUID | None


@dataclass
class World:
    """The whole mutable world, so a test can assert on it directly."""

    accounts: dict[UUID, Account] = field(default_factory=dict)
    players: dict[UUID, MemoryPlayer] = field(default_factory=dict)
    ships: dict[UUID, Ship] = field(default_factory=dict)
    locations: set[str] = field(default_factory=set)
    ledger: list[ApLedgerRow] = field(default_factory=list)
    commands: dict[tuple[UUID, UUID], dict[str, object]] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    phase: str = "open"
    world_day: int = 0

    def ship_of(self, player_id: UUID) -> Ship:
        return next(s for s in self.ships.values() if s.player_id == player_id)

    def add_location(self, addr: HexAddr) -> None:
        self.locations.add(str(addr))
