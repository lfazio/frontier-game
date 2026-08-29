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


def test_a_restricted_commodity_is_stocked_only_by_its_issuer(rules):
    """PSDD §2.3: the non-transferable default is data, not a rule buried in code."""
    assert rules.economy.tradable_at("knowledge", "institute")
    assert not rules.economy.tradable_at("knowledge", "mining")
    assert not rules.economy.tradable_at("knowledge", None)
    # Everything unrestricted trades anywhere, including at an Institute.
    assert rules.economy.tradable_at("grain", "institute")
    assert rules.economy.tradable_at("grain", None)


def test_restricting_something_that_does_not_exist_fails_the_load(rules, tmp_path):
    """A typo in `restricted` is caught at load time, never at play time."""
    from pathlib import Path

    from frontier.adapters.rules_loader import load_ruleset

    shipped = Path(__file__).resolve().parents[2] / "data" / "rulesets" / "2026.1"
    root = tmp_path / "rulesets" / "2026.1"
    root.mkdir(parents=True)
    for source in shipped.glob("*.toml"):
        (root / source.name).write_bytes(source.read_bytes())

    economy = (root / "economy.toml").read_text()
    (root / "economy.toml").write_text(economy.replace("[restricted]\nknowledge =", "[restricted]\nrumour ="))
    with pytest.raises(RuleSetError, match="no such commodity"):
        load_ruleset(tmp_path / "rulesets", "2026.1")

    (root / "economy.toml").write_text(economy.replace('knowledge = "institute"', 'knowledge = "museum"'))
    with pytest.raises(RuleSetError, match="no such station type"):
        load_ruleset(tmp_path / "rulesets", "2026.1")
