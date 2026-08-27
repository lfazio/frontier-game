"""send_message — chat is an event like any other. GDD §7.6, SDD §5.4."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from frontier.application.commands.base import State, StateSpec
from frontier.application.ports import RngPort
from frontier.domain.decisions import Accepted, Decision, Rejected, RejectionCode
from frontier.domain.events.model import EventDraft, Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.domain.rules.ruleset import ActionKind, RuleSet

MAX_LENGTH = 500


class Channel(StrEnum):
    LOCAL = "local"
    SYSTEM = "system"
    TEAM = "team"


CHANNEL_SCOPE: dict[Channel, tuple[Scope, Visibility]] = {
    Channel.LOCAL: (Scope.LOCAL, Visibility.PUBLIC),
    Channel.SYSTEM: (Scope.SYSTEM, Visibility.PUBLIC),
    Channel.TEAM: (Scope.LOCAL, Visibility.TEAM),
}


@dataclass(slots=True)
class SendMessageCommand:
    id: UUID
    idempotency_key: UUID
    channel: Channel
    text: str
    action: str = field(default="send_message", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.ship is None:
            return Rejected(RejectionCode.TARGET_UNKNOWN, {"reason": "player has no ship"})
        if not self.text.strip():
            return Rejected(RejectionCode.MALFORMED_MESSAGE)
        return Accepted(ap_cost=rules.ap_cost(ActionKind.MESSAGE))

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None
        scope, visibility = CHANNEL_SCOPE[self.channel]
        return [
            EventDraft(
                type=EventType.MESSAGE,
                origin=state.ship.position,
                scope=scope,
                visibility=visibility,
                severity=Severity.TRIVIAL,
                participants=frozenset({state.player.id}),
                payload={"text": self.text[:MAX_LENGTH], "channel": self.channel.value},
            )
        ]
