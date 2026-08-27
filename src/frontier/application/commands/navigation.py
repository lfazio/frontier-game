"""jump and scan — SDD §5.4."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from uuid import UUID

from frontier.application.commands.base import State, StateSpec
from frontier.application.ports import RngPort
from frontier.domain.decisions import Accepted, Decision, Rejected, RejectionCode
from frontier.domain.events.model import EventDraft, Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.domain.hex.coordinates import HexAddr
from frontier.domain.hex.geometry import addr_distance, distance
from frontier.domain.rules.ruleset import ActionKind, RuleSet

LY_PER_CYCLE = 4


@dataclass(slots=True)
class JumpCommand:
    """AP and fuel are spent at departure; the ship lands in tick stage 1 — GDD §5.1."""

    id: UUID
    idempotency_key: UUID
    to_system: HexAddr
    action: str = field(default="jump", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True, known_systems=True)

    def _cost(self, state: State, rules: RuleSet) -> tuple[int, int, int]:
        here = state.ship.position.parent() if state.ship else None
        same_region = here is not None and here.parent() == self.to_system.parent()
        action = ActionKind.JUMP_INTRA_REGION if same_region else ActionKind.JUMP_INTER_REGION
        light_years = (
            addr_distance(here, self.to_system)
            if same_region and here is not None
            else distance(here.parent().tip, self.to_system.parent().tip) * 6  # type: ignore[union-attr]
            if here is not None and here.parent() is not None
            else 10
        )
        return rules.ap_cost(action), rules.world.fuel_per_jump_ly * max(1, light_years), light_years

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.ship is None:
            return Rejected(RejectionCode.TARGET_UNKNOWN)
        if state.ship.in_transit:
            return Rejected(RejectionCode.IN_TRANSIT)
        if state.ship.docked_at is not None:
            return Rejected(RejectionCode.MUST_LAUNCH_FIRST)
        if str(self.to_system) not in state.known_systems:
            return Rejected(RejectionCode.TARGET_UNKNOWN, {"system": str(self.to_system)})
        if self.to_system.contains(state.ship.position):
            return Rejected(RejectionCode.NOT_ADJACENT, {"reason": "already in that system"})

        ap_cost, fuel_cost, light_years = self._cost(state, rules)
        if light_years > state.ship.jump_range_ly:
            return Rejected(
                RejectionCode.BEYOND_JUMP_RANGE,
                {"distance_ly": light_years, "range_ly": state.ship.jump_range_ly},
            )
        if state.player.ap_balance < ap_cost:
            return Rejected(RejectionCode.INSUFFICIENT_AP, {"need": ap_cost})
        if state.ship.fuel < fuel_cost:
            return Rejected(RejectionCode.INSUFFICIENT_FUEL, {"need": fuel_cost, "have": state.ship.fuel})
        return Accepted(ap_cost=ap_cost, fuel_cost=fuel_cost)

    def cycles(self, state: State, rules: RuleSet) -> int:
        _, _, light_years = self._cost(state, rules)
        return max(1, ceil(light_years / LY_PER_CYCLE))

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None
        state.ship.fuel -= accepted.fuel_cost
        state.ship.in_transit = True
        state.departure = (self.to_system, self.cycles(state, rules))
        return []


@dataclass(slots=True)
class ScanCommand:
    id: UUID
    idempotency_key: UUID
    action: str = field(default="scan", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True, contacts=True, nearby=True)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.ship is None:
            return Rejected(RejectionCode.TARGET_UNKNOWN)
        if state.ship.in_transit:
            return Rejected(RejectionCode.IN_TRANSIT)
        cost = rules.ap_cost(ActionKind.SCAN)
        if state.player.ap_balance < cost:
            return Rejected(RejectionCode.INSUFFICIENT_AP, {"need": cost})
        return Accepted(ap_cost=cost)

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None
        reach = state.ship.sensor_range
        contacts = [c for c in state.contacts if _within(state.ship.position, c.position, reach)]
        found = [n for n in state.nearby if _within(state.ship.position, n.path, reach)]
        state.discovered = [n.id for n in found if n.discovered_on is None or n.id not in state.known_ids]

        drafts: list[EventDraft] = [
            EventDraft(
                type=EventType.SCAN_PERFORMED,
                origin=state.ship.position,
                scope=Scope.LOCAL,
                visibility=Visibility.PARTICIPANTS,
                severity=Severity.TRIVIAL,
                participants=frozenset({state.player.id}),
                payload={"range": reach, "contacts_found": len(contacts)},
            )
        ]
        drafts += [
            EventDraft(
                type=EventType.DISCOVERY,
                origin=n.path,
                scope=Scope.SYSTEM,
                visibility=Visibility.PUBLIC,
                severity=Severity.MINOR,
                participants=frozenset({state.player.id}),
                payload={"location_id": str(n.id), "kind": n.kind, "name": n.name},
            )
            for n in found
            if n.discovered_on is None and n.kind != "void"
        ]
        return drafts


def _within(here: HexAddr, there: HexAddr, reach: int) -> bool:
    try:
        return addr_distance(here, there) <= reach
    except Exception:
        return False
