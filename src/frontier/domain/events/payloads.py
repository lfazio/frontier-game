"""Typed payloads, one per event type — SDD §3.5.

Adding an event type means adding its payload here and a row in the catalogue table.
Validation is schema-on-write in the domain and schema-on-read in SQL.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from frontier.domain.events.model import EventDraft, Scope, Visibility
from frontier.domain.events.types import EventType


class ShipEnteredPayload(TypedDict):
    ship_id: str
    actor_kind: Literal["player", "npc"]
    from_: str
    to: str


class JourneyCompletedPayload(TypedDict):
    journey_id: str
    arrived_at: str


class MessagePayload(TypedDict):
    text: str
    channel: str


class ApGrantedPayload(TypedDict):
    amount: int
    balance: int


REQUIRED_KEYS: dict[EventType, frozenset[str]] = {
    EventType.SHIP_ENTERED: frozenset({"ship_id", "actor_kind", "from", "to"}),
    EventType.JOURNEY_COMPLETED: frozenset({"journey_id", "arrived_at"}),
    EventType.SCAN_PERFORMED: frozenset({"range", "contacts_found"}),
    EventType.DISCOVERY: frozenset({"location_id", "kind"}),
    EventType.TRADE_EXECUTED: frozenset({"station_id", "commodity", "qty", "unit_price"}),
    EventType.MARKET_SHIFT: frozenset({"station_id", "commodity", "old", "new"}),
    EventType.COMBAT_STARTED: frozenset({"attacker", "defender"}),
    EventType.COMBAT_ROUND: frozenset({"round", "damage"}),
    EventType.COMBAT_RESOLVED: frozenset({"outcome", "rounds", "seed"}),
    EventType.SHIP_DESTROYED: frozenset({"ship_id"}),
    EventType.MESSAGE: frozenset({"text", "channel"}),
    EventType.TERRITORY_CHANGE: frozenset({"system_id", "to_faction"}),
    EventType.AP_GRANTED: frozenset({"amount", "balance"}),
    EventType.TEAM_JOINED: frozenset({"player_id", "team_id"}),
    EventType.TEAM_LEFT: frozenset({"player_id", "team_id"}),
    EventType.HISTORICAL_EVENT: frozenset({"weight", "caused_by"}),
    EventType.MISSION_ACCEPTED: frozenset({"mission_id", "kind"}),
    EventType.MISSION_COMPLETED: frozenset({"mission_id", "kind", "reward"}),
    EventType.REPUTATION_CHANGED: frozenset({"faction_id", "delta", "score"}),
    EventType.TEAM_DEFECTED: frozenset({"team_id", "from_faction", "to_faction"}),
}

DEFAULT_SCOPE: dict[EventType, tuple[Scope, Visibility]] = {
    EventType.SHIP_ENTERED: (Scope.LOCAL, Visibility.PUBLIC),
    EventType.JOURNEY_COMPLETED: (Scope.LOCAL, Visibility.PARTICIPANTS),
    EventType.SCAN_PERFORMED: (Scope.LOCAL, Visibility.PARTICIPANTS),
    EventType.DISCOVERY: (Scope.SYSTEM, Visibility.PUBLIC),
    EventType.TRADE_EXECUTED: (Scope.LOCAL, Visibility.PARTICIPANTS),
    EventType.MARKET_SHIFT: (Scope.PLANET, Visibility.PUBLIC),
    EventType.COMBAT_STARTED: (Scope.LOCAL, Visibility.PUBLIC),
    EventType.COMBAT_ROUND: (Scope.LOCAL, Visibility.PARTICIPANTS),
    EventType.COMBAT_RESOLVED: (Scope.LOCAL, Visibility.PUBLIC),
    EventType.SHIP_DESTROYED: (Scope.SYSTEM, Visibility.PUBLIC),
    EventType.MESSAGE: (Scope.LOCAL, Visibility.PUBLIC),
    EventType.TERRITORY_CHANGE: (Scope.SYSTEM, Visibility.PUBLIC),
    EventType.AP_GRANTED: (Scope.LOCAL, Visibility.PARTICIPANTS),
    EventType.TEAM_JOINED: (Scope.LOCAL, Visibility.TEAM),
    EventType.TEAM_LEFT: (Scope.LOCAL, Visibility.TEAM),
    EventType.HISTORICAL_EVENT: (Scope.SYSTEM, Visibility.PUBLIC),
    EventType.MISSION_ACCEPTED: (Scope.LOCAL, Visibility.PARTICIPANTS),
    EventType.MISSION_COMPLETED: (Scope.SYSTEM, Visibility.PUBLIC),
    EventType.REPUTATION_CHANGED: (Scope.LOCAL, Visibility.PARTICIPANTS),
    EventType.TEAM_DEFECTED: (Scope.UNIVERSE, Visibility.PUBLIC),
}


class UnknownEventType(ValueError):
    """An event type with no payload contract. Adding one is a deliberate act."""


class InvalidPayload(ValueError):
    pass


def validate(draft: EventDraft) -> None:
    required = REQUIRED_KEYS.get(draft.type)
    if required is None:
        raise UnknownEventType(str(draft.type))
    missing = required - set(draft.payload)
    if missing:
        raise InvalidPayload(f"{draft.type}: missing {', '.join(sorted(missing))}")
    _reject_non_json(draft.payload)


def _reject_non_json(payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        if not isinstance(value, str | int | float | bool | list | dict | type(None)):
            raise InvalidPayload(f"{key} is {type(value).__name__}, which jsonb cannot hold")
