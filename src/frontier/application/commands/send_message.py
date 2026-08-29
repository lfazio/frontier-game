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
    # A fourth channel, carried by entitlement rather than by position: no relay, no range, no
    # delay, anywhere in the world. Speaking on it needs an entitlement nobody else holds, and
    # asking for it without one is refused exactly as an unknown channel would be.
    DIRECTORATE = "directorate"


CHANNEL_SCOPE: dict[Channel, tuple[Scope, Visibility]] = {
    Channel.LOCAL: (Scope.LOCAL, Visibility.PUBLIC),
    Channel.SYSTEM: (Scope.SYSTEM, Visibility.PUBLIC),
    Channel.TEAM: (Scope.LOCAL, Visibility.TEAM),
    Channel.DIRECTORATE: (Scope.UNIVERSE, Visibility.CLEARANCE),
}


def channel_or_none(name: str) -> Channel | None:
    """An unknown name is not an error here; the command refuses it like any other it cannot use."""
    try:
        return Channel(name)
    except ValueError:
        return None


@dataclass(slots=True)
class SendMessageCommand:
    id: UUID
    idempotency_key: UUID
    channel: Channel | None
    text: str
    action: str = field(default="send_message", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.ship is None:
            return Rejected(RejectionCode.TARGET_UNKNOWN, {"reason": "player has no ship"})
        if not self.text.strip():
            return Rejected(RejectionCode.MALFORMED_MESSAGE)
        # An unknown channel and one the sender is not entitled to use are refused identically,
        # so the set of channels that exist cannot be probed for (GDD §10.4 C9).
        if self.channel is None or not self._may_speak(state):
            return Rejected(RejectionCode.MALFORMED_MESSAGE)
        return Accepted(ap_cost=rules.ap_cost(ActionKind.MESSAGE))

    def _may_speak(self, state: State) -> bool:
        if self.channel is Channel.DIRECTORATE:
            return state.player.clearance >= 1
        return True

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None and self.channel is not None
        scope, visibility = CHANNEL_SCOPE[self.channel]
        return [
            EventDraft(
                clearance=1 if visibility is Visibility.CLEARANCE else 0,
                type=EventType.MESSAGE,
                origin=state.ship.position,
                scope=scope,
                visibility=visibility,
                severity=Severity.TRIVIAL,
                participants=frozenset({state.player.id}),
                # The speaker is named in the payload, so a partial sighting drops it with the
                # rest of the text rather than leaking who spoke from behind a redaction.
                payload={
                    "text": self.text[:MAX_LENGTH],
                    "channel": self.channel.value,
                    "from": state.player.callsign,
                },
            )
        ]
