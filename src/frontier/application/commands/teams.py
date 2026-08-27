"""Teams — the primary multiplayer unit, and where a player's faction comes from. GDD §6.5."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from frontier.application.commands.base import State, StateSpec
from frontier.application.ports import RngPort
from frontier.domain.decisions import Accepted, Decision, Rejected, RejectionCode
from frontier.domain.events.model import EventDraft, Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.domain.rules.ruleset import RuleSet


@dataclass(slots=True)
class CreateTeamCommand:
    id: UUID
    idempotency_key: UUID
    name: str
    faction_id: int
    action: str = field(default="create_team", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.player.team_id is not None:
            return Rejected(RejectionCode.ALREADY_IN_TEAM)
        if self.faction_id not in (1, 2, 3):
            return Rejected(RejectionCode.UNKNOWN_FACTION, {"faction_id": self.faction_id})
        return Accepted(ap_cost=0)

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        state.team_change = ("create", self.name, self.faction_id)
        return [_membership(state, EventType.TEAM_JOINED, self.name)]


@dataclass(slots=True)
class JoinTeamCommand:
    id: UUID
    idempotency_key: UUID
    team_id: UUID
    action: str = field(default="join_team", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True, team=True, team_id=self.team_id)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.player.team_id is not None:
            return Rejected(RejectionCode.ALREADY_IN_TEAM)
        if state.team is None:
            return Rejected(RejectionCode.UNKNOWN_TEAM, {"team_id": str(self.team_id)})
        return Accepted(ap_cost=0)

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.team is not None
        state.team_change = ("join", state.team.name, state.team.faction_id)
        return [_membership(state, EventType.TEAM_JOINED, state.team.name)]


@dataclass(slots=True)
class LeaveTeamCommand:
    id: UUID
    idempotency_key: UUID
    action: str = field(default="leave_team", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.player.team_id is None:
            return Rejected(RejectionCode.NOT_IN_TEAM)
        return Accepted(ap_cost=0)

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        state.team_change = ("leave", "", 0)
        return [_membership(state, EventType.TEAM_LEFT, "")]


@dataclass(slots=True)
class DefectCommand:
    """Changing allegiance is a political event, not a menu operation — GDD §6.7."""

    id: UUID
    idempotency_key: UUID
    to_faction_id: int
    action: str = field(default="defect", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.player.team_id is None:
            return Rejected(RejectionCode.NOT_IN_TEAM)
        if self.to_faction_id not in (1, 2, 3):
            return Rejected(RejectionCode.UNKNOWN_FACTION, {"faction_id": self.to_faction_id})
        if self.to_faction_id == state.player.faction_id:
            return Rejected(RejectionCode.WRONG_FACTION, {"reason": "already that faction"})
        return Accepted(ap_cost=0)

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None
        previous = state.player.faction_id or 0
        state.defection = self.to_faction_id
        state.reputation_change = (previous, -25)
        return [
            EventDraft(
                type=EventType.TEAM_DEFECTED,
                origin=state.ship.position,
                scope=Scope.UNIVERSE,
                visibility=Visibility.PUBLIC,
                severity=Severity.HISTORIC,
                participants=frozenset({state.player.id}),
                payload={
                    "team_id": str(state.player.team_id),
                    "from_faction": previous,
                    "to_faction": self.to_faction_id,
                },
            )
        ]


def _membership(state: State, type_: EventType, team_name: str) -> EventDraft:
    assert state.ship is not None
    return EventDraft(
        type=type_,
        origin=state.ship.position,
        scope=Scope.LOCAL,
        visibility=Visibility.TEAM,
        severity=Severity.MINOR,
        participants=frozenset({state.player.id}),
        payload={
            "player_id": str(state.player.id),
            "team_id": str(state.player.team_id) if state.player.team_id else "",
            "team_name": team_name,
        },
    )
