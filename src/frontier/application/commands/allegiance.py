"""Siding with an incursion, and renouncing it — GDD §8.12.

Two commands and one asymmetry. Siding is a decision about *this* emergency and can be taken
back; having sided cannot. The bonus is held while sided, the penalty by anyone who ever was, so
renouncing at the right moment is not a way to shed the cost.

Both are announced at Universe scope. There is nothing secret here: the design requires that
everyone knows, which is what separates this from the hidden faction entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from frontier.application.commands.base import State, StateSpec
from frontier.application.ports import RngPort
from frontier.domain.decisions import Accepted, Decision, Rejected, RejectionCode
from frontier.domain.events.model import EventDraft, Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.domain.rules.ruleset import RuleSet

INCURSION = "incursion"


@dataclass(slots=True)
class SideWithIncursionCommand:
    id: UUID
    idempotency_key: UUID
    action: str = field(default="side_with_incursion", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True, incursion=True)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.ship is None:
            return Rejected(RejectionCode.TARGET_UNKNOWN)
        if state.player.allegiance == INCURSION:
            return Rejected(RejectionCode.ALREADY_SIDED)
        if not state.incursion_nearby:
            # There is nobody here to side with. It is a decision about this emergency, in this
            # region, and not a standing political position.
            return Rejected(RejectionCode.NO_INCURSION_HERE)
        return Accepted(ap_cost=0)

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None
        # `first_sided_on` is stamped where the world day is known, and only if it is still
        # unset — the day someone first sided is not a thing that happens twice.
        state.player.allegiance = INCURSION
        state.standing_collapse = rules.combat.collaboration_standing_penalty
        return [
            EventDraft(
                type=EventType.SIDED_WITH_INCURSION,
                origin=state.ship.position,
                scope=Scope.UNIVERSE,
                visibility=Visibility.PUBLIC,
                severity=Severity.HISTORIC,
                participants=frozenset({state.player.id}),
                payload={"callsign": state.player.callsign, "sided": True},
            )
        ]


@dataclass(slots=True)
class RenounceIncursionCommand:
    id: UUID
    idempotency_key: UUID
    action: str = field(default="renounce_incursion", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.ship is None:
            return Rejected(RejectionCode.TARGET_UNKNOWN)
        if state.player.allegiance != INCURSION:
            return Rejected(RejectionCode.NOT_SIDED)
        return Accepted(ap_cost=0)

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None
        # `first_sided_on` is deliberately untouched. Standing does not come back either.
        state.player.allegiance = None
        return [
            EventDraft(
                type=EventType.SIDED_WITH_INCURSION,
                origin=state.ship.position,
                scope=Scope.UNIVERSE,
                visibility=Visibility.PUBLIC,
                severity=Severity.MAJOR,
                participants=frozenset({state.player.id}),
                payload={"callsign": state.player.callsign, "sided": False},
            )
        ]
