from __future__ import annotations

import pytest

from frontier.domain.rules.ruleset import ActionKind, RuleSet, RuleSetError


def test_costs_come_from_data(rules):
    assert rules.ap_cost(ActionKind.MOVE_HEX) == 1
    assert rules.version == "2026.1"


def test_unspent_ap_half_carries_to_the_ceiling(rules):
    assert rules.ap.carry(7) == 3
    assert rules.ap.carry(100) == rules.ap.carry_ceiling


def test_an_unknown_key_fails_the_load(rules):
    files = {
        "ap_costs": {
            "daily_grant": 10,
            "carry_over_fraction": 0.5,
            "carry_ceiling": 5,
            "surprise": 1,
            "cost": {a.value: 1 for a in ActionKind},
        },
        "world": {f: 1 for f in _world_fields()},
    }
    with pytest.raises(RuleSetError, match="surprise"):
        RuleSet.from_mapping("test", files)


def test_a_missing_cost_fails_the_load():
    costs = {a.value: 1 for a in ActionKind}
    costs.pop(ActionKind.SCAN.value)
    files = {
        "ap_costs": {"daily_grant": 10, "carry_over_fraction": 0.5, "carry_ceiling": 5, "cost": costs},
        "world": {f: 1 for f in _world_fields()},
    }
    with pytest.raises(RuleSetError, match="scan"):
        RuleSet.from_mapping("test", files)


def _world_fields():
    from frontier.domain.rules.ruleset import WorldRules

    return WorldRules.__dataclass_fields__
