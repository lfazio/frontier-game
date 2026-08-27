"""Who may see an event, and in what detail — GDD §7.2, ARCH §7.4, SDD §5.5.

There is one implementation of this and there must remain one: sensors, chat range and, later,
Continuity secrecy all read from here. A second copy is how a leak happens.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any
from uuid import UUID

from frontier.domain.events.model import Event, Scope, Visibility
from frontier.domain.events.types import EventType
from frontier.domain.hex.coordinates import HexAddr, ScaleMismatch
from frontier.domain.hex.geometry import addr_distance


class Quality(IntEnum):
    NONE = 0
    PARTIAL = 1
    FULL = 2


@dataclass(frozen=True, slots=True)
class ViewerContext:
    player_id: UUID
    position: HexAddr | None
    sensor_range: int
    radio_range: int
    team_id: UUID | None = None
    faction_id: int | None = None


@dataclass(frozen=True, slots=True)
class AudienceSpec:
    """Who *may* receive an event, before sensors narrow it further."""

    players: frozenset[UUID] = frozenset()
    team_id: UUID | None = None
    faction_id: int | None = None
    spatial: tuple[HexAddr, Scope] | None = None

    @property
    def is_narrow(self) -> bool:
        """Narrow audiences fan out on write; broad ones are queried on read — ARCH §7.4."""
        return bool(self.players) or self.team_id is not None


@dataclass(frozen=True, slots=True)
class EventView:
    id: UUID
    world_day: int
    occurred_at: str
    type: str
    origin: str
    scope: int
    quality: Quality
    payload: dict[str, Any]


def resolve_audience(event: Event, team_of: dict[UUID, UUID] | None = None) -> AudienceSpec:
    team_of = team_of or {}
    match event.visibility:
        case Visibility.PARTICIPANTS:
            return AudienceSpec(players=event.participants)
        case Visibility.TEAM:
            teams = {team_of[p] for p in event.participants if p in team_of}
            return AudienceSpec(team_id=next(iter(teams), None), players=event.participants)
        case Visibility.FACTION | Visibility.PUBLIC:
            return AudienceSpec(spatial=(event.origin, event.scope))
        case _:
            return AudienceSpec()


SCOPE_DEPTH: dict[Scope, int] = {
    Scope.UNIVERSE: 1,
    Scope.REGION: 2,
    Scope.SYSTEM: 3,
}


def scope_container(origin: HexAddr, scope: Scope) -> HexAddr:
    """How far an event carries, as an address prefix — GDD §7.7."""
    depth = SCOPE_DEPTH.get(scope)
    if depth is None or depth >= len(origin.steps):
        return origin
    return HexAddr(origin.steps[:depth])


def observation_quality(viewer: ViewerContext, event: Event) -> Quality:
    """The MVP sensor model. Every row of this table is covered by a test."""
    if viewer.player_id in event.participants:
        return Quality.FULL
    if viewer.position is None:
        return Quality.NONE

    # Scope first: a system-wide announcement is heard by the system, not by whoever is close.
    if event.scope >= Scope.SYSTEM:
        return (
            Quality.FULL
            if scope_container(event.origin, event.scope).contains(viewer.position)
            else Quality.NONE
        )

    try:
        steps = addr_distance(viewer.position, event.origin)
    except ScaleMismatch:
        return Quality.NONE

    if event.type is EventType.MESSAGE and steps <= viewer.radio_range:
        return Quality.FULL
    if steps * 2 <= viewer.sensor_range:
        return Quality.FULL
    if steps <= viewer.sensor_range:
        return Quality.PARTIAL
    return Quality.NONE


def render_public(event: Event) -> EventView | None:
    """What a viewer with no ship and no account may see — UX §9.

    Deliberately the weakest entitlement in the game: public events that already carry to a whole
    system or wider, and nothing else. A spectator has no sensors, so it can never learn anything
    a player standing there would not already know.
    """
    if event.visibility is not Visibility.PUBLIC or event.scope < Scope.SYSTEM:
        return None
    return EventView(
        id=event.id,
        world_day=event.world_day,
        occurred_at=event.occurred_at.isoformat(),
        type=event.type.value,
        origin=str(event.origin),
        scope=int(event.scope),
        quality=Quality.PARTIAL,
        payload=_redact(event),
    )


def render_for(viewer: ViewerContext, event: Event) -> EventView | None:
    """Redaction happens here, before serialisation. A client is never sent what it must not show."""
    quality = observation_quality(viewer, event)
    if quality is Quality.NONE:
        return None
    payload = dict(event.payload) if quality is Quality.FULL else _redact(event)
    return EventView(
        id=event.id,
        world_day=event.world_day,
        occurred_at=event.occurred_at.isoformat(),
        type=event.type.value,
        origin=str(event.origin if quality is Quality.FULL else _fuzz(event.origin)),
        scope=int(event.scope),
        quality=quality,
        payload=payload,
    )


def _redact(event: Event) -> dict[str, Any]:
    """Partial contact: something is out there, but not who."""
    keep = {"actor_kind"}
    kept = {k: v for k, v in event.payload.items() if k in keep}
    return {"contact": "unidentified", **kept}


def _fuzz(origin: HexAddr) -> HexAddr:
    """Round the reported position to the parent, so a weak contact is a direction, not a fix."""
    return origin.parent() or origin


def stamp_view(view: EventView) -> dict[str, Any]:
    return {
        "id": str(view.id),
        "world_day": view.world_day,
        "occurred_at": view.occurred_at,
        "type": view.type,
        "origin": view.origin,
        "scope": view.scope,
        "quality": view.quality.name.lower(),
        "payload": view.payload,
    }
