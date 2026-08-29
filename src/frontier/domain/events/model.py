"""One event model for chat, combat, discovery and economy — GDD §7.6, ARCH §7.2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any
from uuid import UUID

from frontier.domain.events.types import EventType
from frontier.domain.hex.coordinates import HexAddr


class Scope(IntEnum):
    """Ordered: an event may be promoted to a wider scope — GDD §7.7."""

    LOCAL = 0
    PLANET = 1
    SYSTEM = 2
    REGION = 3
    UNIVERSE = 4


class Visibility(StrEnum):
    """Who may ever receive the event, before sensors are considered."""

    PUBLIC = "public"
    PARTICIPANTS = "participants"
    TEAM = "team"
    FACTION = "faction"
    CLEARANCE = "clearance"


class Severity(IntEnum):
    TRIVIAL = 0
    MINOR = 1
    NOTABLE = 2
    MAJOR = 3
    HISTORIC = 4


@dataclass(frozen=True, slots=True)
class EventDraft:
    """What a command emits. The application stamps identity, time and ruleset."""

    type: EventType
    origin: HexAddr
    scope: Scope
    visibility: Visibility
    severity: Severity = Severity.MINOR
    participants: frozenset[UUID] = field(default_factory=frozenset)
    payload: dict[str, Any] = field(default_factory=dict)
    clearance: int = 0


@dataclass(frozen=True, slots=True)
class Event:
    id: UUID
    world_day: int
    occurred_at: datetime
    type: EventType
    origin: HexAddr
    scope: Scope
    visibility: Visibility
    severity: Severity
    participants: frozenset[UUID]
    payload: dict[str, Any]
    ruleset_version: str
    clearance: int = 0
    causation_id: UUID | None = None
