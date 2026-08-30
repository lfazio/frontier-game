"""accept_mission and complete_mission — SDD §5.4.

A mission states an outcome and leaves the method to the player (GDD §5.5), so completion is
checked against the world, not against a scripted sequence of steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from frontier.application.commands.base import State, StateSpec
from frontier.application.ports import RngPort
from frontier.domain.decisions import Accepted, Decision, Rejected, RejectionCode
from frontier.domain.events.model import EventDraft, Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.domain.rules.ruleset import ActionKind, RuleSet


@dataclass(slots=True)
class AcceptMissionCommand:
    id: UUID
    idempotency_key: UUID
    mission_id: UUID
    action: str = field(default="accept_mission", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True, mission=True, mission_id=self.mission_id)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.mission is None:
            return Rejected(RejectionCode.UNKNOWN_MISSION, {"mission_id": str(self.mission_id)})
        if state.mission.assigned:
            return Rejected(RejectionCode.MISSION_TAKEN)
        if state.player.faction_id not in (None, state.mission.faction_id):
            return Rejected(RejectionCode.WRONG_FACTION, {"mission_faction": state.mission.faction_id})
        return Accepted(ap_cost=rules.ap_cost(ActionKind.MISSION_STAGE))

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None and state.mission is not None
        state.mission_change = ("accept", self.mission_id)
        # Whatever the work turns out to be, taking it is what changes the pilot. Declining
        # writes nothing: there is no decline command, and an ignored offer just expires.
        state.player.clearance = max(state.player.clearance, state.mission.grants_clearance)
        return [
            EventDraft(
                type=EventType.MISSION_ACCEPTED,
                origin=state.ship.position,
                scope=Scope.LOCAL,
                visibility=Visibility.PARTICIPANTS,
                severity=Severity.MINOR,
                participants=frozenset({state.player.id}),
                payload={"mission_id": str(self.mission_id), "kind": state.mission.kind},
            )
        ]


@dataclass(slots=True)
class CompleteMissionCommand:
    id: UUID
    idempotency_key: UUID
    mission_id: UUID
    action: str = field(default="complete_mission", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True, mission=True, mission_id=self.mission_id)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.mission is None or not state.mission.mine:
            return Rejected(RejectionCode.UNKNOWN_MISSION)
        if state.ship is None:
            return Rejected(RejectionCode.TARGET_UNKNOWN)
        system = state.ship.position.parent()
        if system is None or str(system) != state.mission.system_path:
            return Rejected(RejectionCode.NOT_AT_MISSION_SITE, {"required": state.mission.system_path})
        return Accepted(ap_cost=rules.ap_cost(ActionKind.MISSION_STAGE))

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None and state.mission is not None
        state.mission_change = ("complete", self.mission_id)
        state.player.credits += state.mission.reward_credits
        return [
            EventDraft(
                type=EventType.MISSION_COMPLETED,
                origin=state.ship.position,
                scope=Scope.SYSTEM,
                visibility=Visibility.PUBLIC,
                severity=Severity.NOTABLE,
                participants=frozenset({state.player.id}),
                payload={
                    "mission_id": str(self.mission_id),
                    "kind": state.mission.kind,
                    "reward": state.mission.reward_credits,
                    "faction_id": state.mission.faction_id,
                },
            )
        ]
