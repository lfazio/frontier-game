"""attack and set_standing_orders — SDD §5.4, D-4.

Player-versus-player always resolves at tick stage 2, even when both players are online, so an
offline defender can never be treated differently from a present one (GDD §3.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from frontier.application.commands.base import Contact, State, StateSpec
from frontier.application.ports import RngPort
from frontier.domain.decisions import Accepted, Decision, Rejected, RejectionCode
from frontier.domain.encounter.resolution import Combatant, Outcome, resolve
from frontier.domain.events.model import EventDraft, Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.domain.fleet.standing_orders import Posture, StandingOrders
from frontier.domain.hex.geometry import addr_distance
from frontier.domain.rules.ruleset import ActionKind, RuleSet

WEAPON_REACH = 1


@dataclass(slots=True)
class AttackCommand:
    id: UUID
    idempotency_key: UUID
    target_ship_id: UUID
    action: str = field(default="attack", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True, contacts=True)

    def _target(self, state: State) -> Contact | None:
        return next((c for c in state.contacts if c.ship_id == self.target_ship_id), None)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.ship is None:
            return Rejected(RejectionCode.TARGET_UNKNOWN)
        if self.target_ship_id == state.ship.id:
            return Rejected(RejectionCode.SELF_TARGET)
        target = self._target(state)
        if target is None:
            return Rejected(RejectionCode.TARGET_NOT_VISIBLE)
        if addr_distance(state.ship.position, target.position) > WEAPON_REACH:
            return Rejected(RejectionCode.OUT_OF_RANGE)
        if target.docked or state.ship.docked_at is not None:
            return Rejected(RejectionCode.TARGET_DOCKED)
        cost = rules.ap_cost(ActionKind.COMBAT_ROUND)
        if state.player.ap_balance < cost:
            return Rejected(RejectionCode.INSUFFICIENT_AP, {"need": cost})
        return Accepted(ap_cost=cost)

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None
        target = self._target(state)
        assert target is not None

        started = EventDraft(
            type=EventType.COMBAT_STARTED,
            origin=state.ship.position,
            scope=Scope.LOCAL,
            visibility=Visibility.PUBLIC,
            severity=Severity.NOTABLE,
            participants=frozenset({state.player.id}),
            payload={"attacker": str(state.ship.id), "defender": str(self.target_ship_id)},
        )
        if target.player_id is not None:
            # Queued for the tick: one code path resolves every player-versus-player encounter.
            state.engaged = self.target_ship_id
            return [started]

        return [started, *_resolve_now(state, target, rules, rng)]


def _resolve_now(state: State, target: Contact, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
    assert state.ship is not None
    attacker = Combatant(
        ship_id=state.ship.id,
        hull=state.ship.hull,
        hull_max=state.ship.hull_max,
        shields=state.ship.shields,
        sensor_range=state.ship.sensor_range,
        orders=StandingOrders(posture=Posture.AGGRESSIVE, retreat_at_hull_pct=0),
    )
    defender = Combatant(
        ship_id=target.ship_id,
        hull=target.hull,
        hull_max=target.hull_max,
        shields=target.shields,
        sensor_range=target.sensor_range,
        orders=StandingOrders(posture=Posture.DEFEND, retreat_at_hull_pct=30),
    )
    seed = f"{state.ship.id}:{target.ship_id}"
    result = resolve(attacker, defender, rules.combat, rng.for_("encounter", seed), seed)

    state.ship.hull, state.ship.shields = attacker.hull, attacker.shields
    state.combat_result = (defender.ship_id, defender.hull, defender.shields)

    drafts = [
        EventDraft(
            type=EventType.COMBAT_RESOLVED,
            origin=state.ship.position,
            scope=Scope.LOCAL,
            visibility=Visibility.PUBLIC,
            severity=Severity.NOTABLE,
            participants=frozenset({state.player.id}),
            payload={
                "outcome": result.outcome.value,
                "rounds": result.rounds,
                "seed": result.seed,
                "damage": result.damage,
            },
        )
    ]
    if result.outcome is Outcome.ATTACKER_WON:
        drafts.append(
            EventDraft(
                type=EventType.SHIP_DESTROYED,
                origin=state.ship.position,
                scope=Scope.SYSTEM,
                visibility=Visibility.PUBLIC,
                severity=Severity.MAJOR,
                participants=frozenset({state.player.id}),
                payload={"ship_id": str(defender.ship_id), "by": str(state.ship.id)},
            )
        )
    return drafts


@dataclass(slots=True)
class SetStandingOrdersCommand:
    id: UUID
    idempotency_key: UUID
    orders: StandingOrders
    action: str = field(default="set_standing_orders", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(orders=True)

    def check(self, state: State, rules: RuleSet) -> Decision:
        return Accepted(ap_cost=rules.ap_cost(ActionKind.STANDING_ORDERS))

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        state.orders = self.orders
        state.orders_changed = True
        return []
