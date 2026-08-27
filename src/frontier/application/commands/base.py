"""The command contract — SDD §5.3."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from uuid import UUID

from frontier.application.ports import Player, RngPort
from frontier.domain.decisions import Accepted, Decision
from frontier.domain.events.model import EventDraft
from frontier.domain.fleet.ship import Ship
from frontier.domain.hex.coordinates import HexAddr
from frontier.domain.rules.ruleset import RuleSet


@dataclass(frozen=True, slots=True)
class StateSpec:
    """What the executor must fetch. Keeping I/O declarative keeps it in one place."""

    ship: bool = False
    resolve: tuple[HexAddr, ...] = ()


@dataclass(slots=True)
class State:
    player: Player
    ship: Ship | None = None
    known_addresses: frozenset[str] = field(default_factory=frozenset)


@runtime_checkable
class Command(Protocol):
    id: UUID
    idempotency_key: UUID
    action: str

    def loads(self) -> StateSpec: ...
    def check(self, state: State, rules: RuleSet) -> Decision: ...
    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]: ...
