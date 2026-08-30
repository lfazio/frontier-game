"""Combat resolution — SDD §6.3.

One resolver serves live NPC fights and the tick's queued player encounters, so an offline
defender can never be subject to different physics (GDD §3.5). Every roll is drawn from a seeded
generator and the seed travels in the event, so a disputed outcome is answered by replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from random import Random
from uuid import UUID

from frontier.domain.fleet.standing_orders import Posture, StandingOrders
from frontier.domain.rules.ruleset import CombatRules


class Outcome(StrEnum):
    ATTACKER_WON = "attacker_won"
    DEFENDER_WON = "defender_won"
    ESCAPED = "escaped"
    SURRENDERED = "surrendered"
    STALEMATE = "stalemate"


@dataclass(slots=True)
class Combatant:
    ship_id: UUID
    hull: int
    hull_max: int
    shields: int
    sensor_range: int
    orders: StandingOrders = field(default_factory=StandingOrders.default)
    cargo_value: int = 0
    # Of the incursion, rather than merely fighting for it.
    is_harrower: bool = False
    # Siding now, and having ever sided. The second is what the penalty attaches to (GDD §8.12).
    sided_now: bool = False
    sided_ever: bool = False

    @property
    def destroyed(self) -> bool:
        return self.hull <= 0

    @property
    def hull_pct(self) -> int:
        return round(100 * self.hull / max(1, self.hull_max))


@dataclass(slots=True)
class EncounterResult:
    outcome: Outcome
    rounds: int
    log: list[dict[str, object]]
    damage: dict[str, int]
    seed: str


def resolve(
    attacker: Combatant, defender: Combatant, rules: CombatRules, rng: Random, seed: str
) -> EncounterResult:
    log: list[dict[str, object]] = []
    damage = {str(attacker.ship_id): 0, str(defender.ship_id): 0}

    if defender.orders.posture is Posture.SURRENDER_CARGO:
        return EncounterResult(Outcome.SURRENDERED, 0, log, damage, seed)

    for round_no in range(1, rules.max_rounds_per_encounter + 1):
        escaper = _who_flees(attacker, defender)
        if escaper is not None and rng.random() < rules.escape_base_chance:
            log.append({"round": round_no, "escaped": str(escaper.ship_id)})
            return EncounterResult(Outcome.ESCAPED, round_no, log, damage, seed)

        for shooter, target in ((attacker, defender), (defender, attacker)):
            if shooter.destroyed or target.destroyed:
                continue
            hit = rng.random() < _hit_chance(shooter, target, rules)
            dealt = (
                _apply(target, rng.randint(rules.weapon_damage_min, rules.weapon_damage_max), rules)
                if hit
                else 0
            )
            damage[str(shooter.ship_id)] += dealt
            log.append({"round": round_no, "shooter": str(shooter.ship_id), "hit": hit, "damage": dealt})

        if defender.destroyed:
            return EncounterResult(Outcome.ATTACKER_WON, round_no, log, damage, seed)
        if attacker.destroyed:
            return EncounterResult(Outcome.DEFENDER_WON, round_no, log, damage, seed)

    return EncounterResult(Outcome.STALEMATE, rules.max_rounds_per_encounter, log, damage, seed)


def _hit_chance(shooter: Combatant, target: Combatant, rules: CombatRules) -> float:
    edge = (shooter.sensor_range - target.sensor_range) * rules.sensor_hit_bonus_per_point
    return min(0.95, max(0.05, rules.base_hit_chance + edge + _allegiance_edge(shooter, target, rules)))


def _allegiance_edge(shooter: Combatant, target: Combatant, rules: CombatRules) -> float:
    """What siding with an incursion is worth, and what it costs — GDD §8.12.

    The bonus is held only while sided and only against humankind: it is help, and help stops.
    The penalty is held by anyone who ever sided, against Harrowers, for ever — renouncing at
    the right moment must not be a way to shed it.
    """
    if shooter.is_harrower or (shooter.sided_now and target.sided_now):
        return 0.0
    if target.is_harrower:
        return -rules.collaborator_hit_malus if shooter.sided_ever else 0.0
    if shooter.sided_now:
        return rules.collaborator_hit_bonus
    return 0.0


def _apply(target: Combatant, damage: int, rules: CombatRules) -> int:
    absorbed = min(target.shields, int(damage * rules.shield_absorb_ratio))
    target.shields -= absorbed
    target.hull = max(0, target.hull - (damage - absorbed))
    return damage


def _who_flees(attacker: Combatant, defender: Combatant) -> Combatant | None:
    for side in (defender, attacker):
        if side.orders.posture is Posture.EVADE:
            return side
        if side.hull_pct < side.orders.retreat_at_hull_pct:
            return side
    return None
