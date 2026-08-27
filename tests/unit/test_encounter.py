"""Combat resolves the same way twice — SDD §6.3, GDD C6."""

from __future__ import annotations

from random import Random
from uuid import UUID

from frontier.domain.encounter.resolution import Combatant, Outcome, resolve
from frontier.domain.fleet.standing_orders import Posture, StandingOrders

ATTACKER = UUID("11111111-1111-1111-1111-111111111111")
DEFENDER = UUID("22222222-2222-2222-2222-222222222222")


def fighter(ship_id=ATTACKER, hull=100, posture=Posture.DEFEND, retreat=0, sensors=3) -> Combatant:
    return Combatant(
        ship_id=ship_id,
        hull=hull,
        hull_max=100,
        shields=0,
        sensor_range=sensors,
        orders=StandingOrders(posture=posture, retreat_at_hull_pct=retreat),
    )


def pair(**kwargs) -> tuple[Combatant, Combatant]:
    return fighter(ATTACKER, **kwargs), fighter(DEFENDER, **kwargs)


def test_the_same_seed_resolves_identically(rules):
    a, b = pair()
    first = resolve(a, b, rules.combat, Random("seed-1"), "seed-1")
    c, d = pair()
    second = resolve(c, d, rules.combat, Random("seed-1"), "seed-1")
    assert (first.outcome, first.rounds, first.log) == (second.outcome, second.rounds, second.log)


def test_a_different_seed_can_differ(rules):
    outcomes = {
        resolve(*pair(), rules.combat, Random(f"seed-{i}"), str(i)).log[0]["damage"] for i in range(20)
    }
    assert len(outcomes) > 1


def test_a_surrendering_defender_ends_it_immediately(rules):
    result = resolve(
        fighter(), fighter(DEFENDER, posture=Posture.SURRENDER_CARGO), rules.combat, Random("x"), "x"
    )
    assert result.outcome is Outcome.SURRENDERED
    assert result.rounds == 0


def test_shields_absorb_before_the_hull_takes_damage(rules):
    attacker = fighter(ATTACKER, posture=Posture.AGGRESSIVE)
    defender = fighter(DEFENDER, posture=Posture.AGGRESSIVE)
    defender.shields = 200
    resolve(attacker, defender, rules.combat, Random("shielded"), "s")
    assert defender.shields < 200


def test_an_evading_defender_tries_to_run(rules):
    result = resolve(
        fighter(posture=Posture.AGGRESSIVE),
        fighter(DEFENDER, posture=Posture.EVADE),
        rules.combat,
        Random("runner"),
        "r",
    )
    assert result.outcome in (Outcome.ESCAPED, Outcome.ATTACKER_WON, Outcome.STALEMATE)


def test_a_fight_always_terminates(rules):
    result = resolve(
        fighter(posture=Posture.AGGRESSIVE),
        fighter(posture=Posture.AGGRESSIVE),
        rules.combat,
        Random("long"),
        "l",
    )
    assert result.rounds <= rules.combat.max_rounds_per_encounter
