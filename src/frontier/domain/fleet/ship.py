"""Ships and the movement rule — GDD §4.2, SDD §3.3, §5.4."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from frontier.domain.decisions import Accepted, Decision, Rejected, RejectionCode
from frontier.domain.hex.coordinates import HexAddr, ScaleMismatch
from frontier.domain.hex.geometry import addr_distance
from frontier.domain.rules.ruleset import ActionKind, RuleSet


@dataclass(slots=True)
class Ship:
    id: UUID
    player_id: UUID | None
    position: HexAddr
    hull: int
    hull_max: int
    fuel: int
    fuel_max: int
    cargo_max: int
    sensor_range: int
    shields: int = 0
    shields_max: int = 0
    docked_at: UUID | None = None
    in_transit: bool = False
    destroyed_on: int | None = None

    @property
    def is_npc(self) -> bool:
        return self.player_id is None


def check_move(ship: Ship, ap_balance: int, to: HexAddr, rules: RuleSet) -> Decision:
    """Preconditions in the order of SDD §5.4, so rejections are predictable."""
    if ship.in_transit:
        return Rejected(RejectionCode.IN_TRANSIT)
    if ship.docked_at is not None:
        return Rejected(RejectionCode.MUST_LAUNCH_FIRST)
    try:
        steps = addr_distance(ship.position, to)
    except ScaleMismatch:
        return Rejected(RejectionCode.SCALE_MISMATCH, {"from": str(ship.position), "to": str(to)})
    if steps != 1:
        return Rejected(RejectionCode.NOT_ADJACENT, {"distance": steps})

    ap_cost = rules.ap_cost(ActionKind.MOVE_HEX)
    if ap_balance < ap_cost:
        return Rejected(RejectionCode.INSUFFICIENT_AP, {"need": ap_cost, "have": ap_balance})
    fuel_cost = rules.world.fuel_per_hex
    if ship.fuel < fuel_cost:
        return Rejected(RejectionCode.INSUFFICIENT_FUEL, {"need": fuel_cost, "have": ship.fuel})
    return Accepted(ap_cost=ap_cost, fuel_cost=fuel_cost)


def apply_move(ship: Ship, to: HexAddr, accepted: Accepted) -> None:
    ship.position = to
    ship.fuel -= accepted.fuel_cost
