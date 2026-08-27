"""Rules settled by design answers S1 to S6 — SDD §17."""

from __future__ import annotations

from math import floor

from frontier.domain.decisions import Accepted, Rejected, RejectionCode


def rescue_tax(credits: int, rules) -> int:
    """The formula stage 2 applies, kept here so the intent is testable without a database."""
    return max(0, credits - floor(credits * rules.combat.rescue_tax_fraction))


def test_the_rescue_tax_is_a_share_of_what_you_have(rules):
    """S1: a salvage fee, not a fine — it scales with means."""
    assert rescue_tax(100_000, rules) - 100_000 < rescue_tax(1_000, rules) - 1_000


def test_the_rescue_tax_never_bankrupts_a_pilot(rules):
    """A flat penalty could strand a poor player; a fraction cannot."""
    for credits in (0, 1, 7, 999, 10**9):
        assert 0 <= rescue_tax(credits, rules) <= credits


def test_the_rescue_tax_sits_in_its_agreed_band(rules):
    assert 0.03 <= rules.combat.rescue_tax_fraction <= 0.10


def test_a_hull_has_a_jump_range_of_its_own(rules):
    """S3: range depends on the ship, not only the tank."""
    assert rules.world.jump_range_default_ly > 0


def test_beyond_jump_range_is_its_own_refusal():
    rejected = Rejected(RejectionCode.BEYOND_JUMP_RANGE, {"distance_ly": 40, "range_ly": 8})
    assert rejected.code.value == "BEYOND_JUMP_RANGE"
    assert not isinstance(rejected, Accepted)


def test_npcs_have_no_dissolution_setting_left(rules):
    """S5: crews persist and the server plays them, so the knob would be a lie."""
    assert not hasattr(rules.npc, "dissolve_after_cycles")
