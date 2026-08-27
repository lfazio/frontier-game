"""move — SDD §5.4."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from frontier.application.commands.base import State, StateSpec
from frontier.application.ports import RngPort
from frontier.domain.decisions import Accepted, Decision, Rejected, RejectionCode
from frontier.domain.events.model import EventDraft, Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.domain.fleet.ship import apply_move, check_move
from frontier.domain.hex.coordinates import HexAddr
from frontier.domain.rules.ruleset import RuleSet


@dataclass(slots=True)
class MoveCommand:
    id: UUID
    idempotency_key: UUID
    to: HexAddr
    action: str = field(default="move", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True, resolve=(self.to,))

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.ship is None:
            return Rejected(RejectionCode.TARGET_UNKNOWN, {"reason": "player has no ship"})
        if str(self.to) not in state.known_addresses:
            return Rejected(RejectionCode.UNKNOWN_DESTINATION, {"to": str(self.to)})
        return check_move(state.ship, state.player.ap_balance, self.to, rules)

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None
        origin = state.ship.position
        apply_move(state.ship, self.to, accepted)
        return [
            EventDraft(
                type=EventType.SHIP_ENTERED,
                origin=self.to,
                scope=Scope.LOCAL,
                visibility=Visibility.PUBLIC,
                severity=Severity.TRIVIAL,
                participants=frozenset({state.player.id}),
                payload={
                    "ship_id": str(state.ship.id),
                    "actor_kind": "npc" if state.ship.is_npc else "player",
                    "from": str(origin),
                    "to": str(self.to),
                },
            )
        ]
