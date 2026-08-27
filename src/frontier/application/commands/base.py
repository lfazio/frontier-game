"""The command contract — SDD §5.3."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from uuid import UUID

from frontier.application.ports import Player, RngPort
from frontier.domain.decisions import Accepted, Decision
from frontier.domain.events.model import EventDraft
from frontier.domain.fleet.cargo import Cargo
from frontier.domain.fleet.ship import Ship
from frontier.domain.fleet.standing_orders import StandingOrders
from frontier.domain.hex.coordinates import HexAddr
from frontier.domain.rules.ruleset import RuleSet


@dataclass(frozen=True, slots=True)
class StateSpec:
    """What the executor must fetch. Keeping I/O declarative keeps it in one place."""

    ship: bool = False
    station: bool = False
    market: bool = False
    contacts: bool = False
    nearby: bool = False
    known_systems: bool = False
    orders: bool = False
    team: bool = False
    team_id: UUID | None = None
    resolve: tuple[HexAddr, ...] = ()


@dataclass(slots=True)
class MarketLine:
    commodity: str
    stock: int
    target_stock: int
    base_price: int


@dataclass(slots=True)
class Station:
    id: UUID
    path: HexAddr
    name: str | None = None


@dataclass(slots=True)
class State:
    player: Player
    ship: Ship | None = None
    cargo: Cargo = field(default_factory=Cargo)
    station: Station | None = None
    market: dict[str, MarketLine] | None = None
    team: TeamRef | None = None
    contacts: list[Contact] = field(default_factory=list)
    nearby: list[NearbyLocation] = field(default_factory=list)
    known_addresses: frozenset[str] = field(default_factory=frozenset)
    known_systems: frozenset[str] = field(default_factory=frozenset)
    known_ids: frozenset[UUID] = field(default_factory=frozenset)
    orders: StandingOrders = field(default_factory=StandingOrders.default)
    # Written by commands, read by the state store when it persists the result.
    departure: tuple[HexAddr, int] | None = None
    discovered: list[UUID] = field(default_factory=list)
    engaged: UUID | None = None
    orders_changed: bool = False
    combat_result: tuple[UUID, int, int] | None = None
    team_change: tuple[str, str, int] | None = None


@dataclass(slots=True)
class TeamRef:
    id: UUID
    name: str
    faction_id: int


@dataclass(slots=True)
class NearbyLocation:
    id: UUID
    path: HexAddr
    kind: str
    name: str | None
    discovered_on: int | None


@dataclass(slots=True)
class Contact:
    ship_id: UUID
    player_id: UUID | None
    position: HexAddr
    hull: int
    hull_max: int
    shields: int
    sensor_range: int
    docked: bool


@runtime_checkable
class Command(Protocol):
    id: UUID
    idempotency_key: UUID
    action: str

    def loads(self) -> StateSpec: ...
    def check(self, state: State, rules: RuleSet) -> Decision: ...
    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]: ...
