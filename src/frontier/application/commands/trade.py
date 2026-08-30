"""dock, launch, buy, sell, repair — SDD §5.4.

Prices are computed here from current stock. A price the client sent is ignored, not validated:
validating one would imply the client is allowed to have one (D-9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from frontier.application.commands.base import State, StateSpec
from frontier.application.ports import RngPort
from frontier.domain.decisions import Accepted, Decision, Rejected, RejectionCode
from frontier.domain.economy.pricing import quote
from frontier.domain.events.model import EventDraft, Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.domain.rules.ruleset import ActionKind, RuleSet


@dataclass(slots=True)
class DockCommand:
    id: UUID
    idempotency_key: UUID
    station_id: UUID
    action: str = field(default="dock", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True, station=True)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.ship is None:
            return Rejected(RejectionCode.TARGET_UNKNOWN)
        if state.ship.in_transit:
            return Rejected(RejectionCode.IN_TRANSIT)
        if state.ship.docked_at is not None:
            return Rejected(RejectionCode.ALREADY_DOCKED)
        if state.station is None or state.station.path != state.ship.position:
            return Rejected(RejectionCode.NOT_ADJACENT, {"station": str(self.station_id)})
        return Accepted(ap_cost=rules.ap_cost(ActionKind.DOCK))

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None
        state.ship.docked_at = self.station_id
        return []


@dataclass(slots=True)
class LaunchCommand:
    id: UUID
    idempotency_key: UUID
    action: str = field(default="launch", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.ship is None:
            return Rejected(RejectionCode.TARGET_UNKNOWN)
        if state.ship.docked_at is None:
            return Rejected(RejectionCode.NOT_DOCKED)
        return Accepted(ap_cost=rules.ap_cost(ActionKind.LAUNCH))

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None
        state.ship.docked_at = None
        return []


@dataclass(slots=True)
class TradeCommand:
    """`buy` and `sell` differ only in direction, so they share their preconditions."""

    id: UUID
    idempotency_key: UUID
    commodity: str
    qty: int
    selling: bool
    action: str = field(default="trade", init=False)

    def __post_init__(self) -> None:
        self.action = "sell" if self.selling else "buy"

    def loads(self) -> StateSpec:
        return StateSpec(ship=True, market=True)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.ship is None:
            return Rejected(RejectionCode.TARGET_UNKNOWN)
        if state.ship.docked_at is None:
            return Rejected(RejectionCode.NOT_DOCKED)
        line = state.market.get(self.commodity) if state.market else None
        if line is None:
            return Rejected(RejectionCode.COMMODITY_UNAVAILABLE, {"commodity": self.commodity})
        if self.selling and rules.economy.is_consumed_on_read(self.commodity):
            # Reading spends it; there is no resale market for something you have learned.
            return Rejected(RejectionCode.NOT_SELLABLE, {"commodity": self.commodity})

        prices = quote(line.stock, line.target_stock, line.base_price, rules.economy)
        if self.selling:
            if state.cargo.qty(self.commodity) < self.qty:
                return Rejected(
                    RejectionCode.INSUFFICIENT_CARGO,
                    {"have": state.cargo.qty(self.commodity), "need": self.qty},
                )
        else:
            if line.stock < self.qty:
                return Rejected(RejectionCode.INSUFFICIENT_STOCK, {"have": line.stock, "need": self.qty})
            if state.player.credits < prices.buy * self.qty:
                return Rejected(
                    RejectionCode.INSUFFICIENT_CREDITS,
                    {"need": prices.buy * self.qty, "have": state.player.credits},
                )
            if state.cargo.used + self.qty > state.ship.cargo_max:
                return Rejected(RejectionCode.CARGO_FULL, {"free": state.ship.cargo_max - state.cargo.used})
        return Accepted(ap_cost=rules.ap_cost(ActionKind.TRADE))

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None and state.market is not None
        line = state.market[self.commodity]
        prices = quote(line.stock, line.target_stock, line.base_price, rules.economy)

        if self.selling:
            unit = prices.sell
            state.cargo.remove(self.commodity, self.qty)
            state.player.credits += unit * self.qty
            line.stock += self.qty
        else:
            unit = prices.buy
            state.cargo.add(self.commodity, self.qty, unit)
            state.player.credits -= unit * self.qty
            line.stock -= self.qty

        return [
            EventDraft(
                type=EventType.TRADE_EXECUTED,
                origin=state.ship.position,
                scope=Scope.LOCAL,
                visibility=Visibility.PARTICIPANTS,
                severity=Severity.TRIVIAL,
                participants=frozenset({state.player.id}),
                payload={
                    "station_id": str(state.ship.docked_at),
                    "commodity": self.commodity,
                    "qty": self.qty if not self.selling else -self.qty,
                    "unit_price": unit,
                },
            )
        ]


@dataclass(slots=True)
class ReadCommand:
    """Spend a unit of something to know it — PSDD Q-D.

    Free, and it needs no station: reading what you already carry is not an act in the world.
    What it costs is the unit, which is gone afterwards.
    """

    id: UUID
    idempotency_key: UUID
    commodity: str
    action: str = field(default="read", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.ship is None:
            return Rejected(RejectionCode.TARGET_UNKNOWN)
        if not rules.economy.is_consumed_on_read(self.commodity):
            return Rejected(RejectionCode.COMMODITY_UNAVAILABLE, {"commodity": self.commodity})
        if state.cargo.qty(self.commodity) < 1:
            return Rejected(
                RejectionCode.INSUFFICIENT_CARGO, {"have": state.cargo.qty(self.commodity), "need": 1}
            )
        return Accepted(ap_cost=0)

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None
        state.cargo.remove(self.commodity, 1)
        state.player.knowledge += 1
        return [
            EventDraft(
                type=EventType.KNOWLEDGE_LEARNED,
                origin=state.ship.position,
                scope=Scope.LOCAL,
                visibility=Visibility.PARTICIPANTS,
                severity=Severity.TRIVIAL,
                participants=frozenset({state.player.id}),
                payload={"commodity": self.commodity, "knowledge": state.player.knowledge},
            )
        ]


@dataclass(slots=True)
class RepairCommand:
    id: UUID
    idempotency_key: UUID
    action: str = field(default="repair", init=False)

    def loads(self) -> StateSpec:
        return StateSpec(ship=True)

    def check(self, state: State, rules: RuleSet) -> Decision:
        if state.ship is None:
            return Rejected(RejectionCode.TARGET_UNKNOWN)
        if state.ship.docked_at is None:
            return Rejected(RejectionCode.NOT_DOCKED)
        missing = state.ship.hull_max - state.ship.hull
        if missing == 0:
            return Accepted(ap_cost=0)
        cost = missing * rules.world.hull_repair_cost_per_point
        if state.player.credits < cost:
            return Rejected(RejectionCode.INSUFFICIENT_CREDITS, {"need": cost})
        return Accepted(ap_cost=rules.ap_cost(ActionKind.REPAIR))

    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[EventDraft]:
        assert state.ship is not None
        missing = state.ship.hull_max - state.ship.hull
        state.player.credits -= missing * rules.world.hull_repair_cost_per_point
        state.ship.hull = state.ship.hull_max
        return []
