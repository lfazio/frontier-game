"""Drafting a ruleset — ADMIN §3.4, QA-2.

The property that matters is at the top of the file it tests: the live ruleset is never edited.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from frontier.adapters.console.balance import dials, draft, next_version, notes_for
from frontier.domain.rules.ruleset import RuleSetError

SHIPPED = Path(__file__).resolve().parents[2] / "data" / "rulesets"


@pytest.fixture
def rulesets(tmp_path: Path) -> Path:
    root = tmp_path / "rulesets"
    root.mkdir()
    shutil.copytree(SHIPPED / "2026.1", root / "2026.1")
    return root


def test_every_dial_in_the_ruleset_is_listed(rules):
    """Found by walking the rules, so a dial added tomorrow appears without being registered."""
    found = dials(rules, {})

    keys = {d["key"] for d in found}
    assert "world.region_radius" in keys
    assert "combat.collaborator_hit_malus" in keys
    assert "npc.incursion_hull" in keys
    # Mappings are not dials: a commodity price table is not one number to turn.
    assert not any(k.endswith(".commodities") or k.endswith(".cost") for k in keys)
    assert all(isinstance(d["value"], int | float) for d in found)


def test_every_shipped_dial_carries_a_note(rules):
    """The note is part of adding a dial, not documentation written afterwards."""
    notes = notes_for(SHIPPED, "2026.1")

    without = [d["key"] for d in dials(rules, notes) if not d["note"]]

    assert without == [], f"dials with no note: {without}"


def test_a_draft_is_a_new_version_and_the_live_one_is_untouched(rulesets):
    from frontier.adapters.rules_loader import load_ruleset

    before = load_ruleset(rulesets, "2026.1")

    made = draft(rulesets, "2026.1", "2026.2", {"world.region_radius": 20}, author="an operator")

    after = load_ruleset(rulesets, "2026.1")
    drafted = load_ruleset(rulesets, "2026.2")
    assert made["version"] == "2026.2"
    assert drafted.world.region_radius == 20
    assert after.world.region_radius == before.world.region_radius, "the live ruleset was edited"


def test_a_draft_keeps_the_comments_that_explain_it(rulesets):
    draft(rulesets, "2026.1", "2026.2", {"world.region_radius": 20}, author="an operator")

    source = (rulesets / "2026.1" / "world.toml").read_text()
    copy = (rulesets / "2026.2" / "world.toml").read_text()

    assert copy.count("#") == source.count("#"), "a comment was lost in the rewrite"
    assert "region_radius = 20" in copy
    assert (rulesets / "2026.2" / "notes.toml").is_file()


def test_a_draft_will_not_overwrite_a_version(rulesets):
    draft(rulesets, "2026.1", "2026.2", {"world.region_radius": 20}, author="an operator")

    with pytest.raises(FileExistsError):
        draft(rulesets, "2026.1", "2026.2", {"world.region_radius": 21}, author="an operator")


def test_an_unknown_dial_is_refused_rather_than_invented(rulesets):
    with pytest.raises(KeyError):
        draft(rulesets, "2026.1", "world.no_such_dial", {"world.no_such_dial": 1}, author="x")


def test_a_draft_in_a_work_tree_lands_on_a_branch(rulesets):
    subprocess.run(["git", "init", "-q", "."], cwd=rulesets, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.io"], cwd=rulesets, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=rulesets, check=True)
    subprocess.run(["git", "add", "-A"], cwd=rulesets, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=rulesets, check=True)

    made = draft(rulesets, "2026.1", "2026.2", {"ap.daily_grant": 12}, author="lfazio")

    assert made["committed"] is True
    assert made["branch"] == "ruleset/2026.2"
    head = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=rulesets, capture_output=True, text=True
    )
    assert head.stdout.strip() == "ruleset/2026.2"


def test_a_draft_outside_a_work_tree_is_still_a_draft(rulesets):
    """The branch is a convenience; a draft on disk is the deliverable."""
    made = draft(rulesets, "2026.1", "2026.2", {"ap.daily_grant": 12}, author="lfazio")

    assert made["committed"] is False and made["branch"] is None
    assert Path(made["path"]).is_dir()


def test_the_next_version_is_the_next_one():
    assert next_version("2026.1") == "2026.2"
    assert next_version("2026.19") == "2026.20"
    assert next_version("weird") == "weird-draft"


def test_a_drafted_ruleset_still_loads(rulesets):
    from frontier.adapters.rules_loader import load_ruleset

    draft(
        rulesets,
        "2026.1",
        "2026.2",
        {"world.jump_range_default_ly": 16, "events.crisis_threshold": 0.22, "ap.daily_grant": 12},
        author="an operator",
    )

    fresh = load_ruleset(rulesets, "2026.2")
    assert fresh.world.jump_range_default_ly == 16
    assert fresh.events.crisis_threshold == pytest.approx(0.22)
    assert fresh.ap.daily_grant == 12


def test_a_ruleset_with_an_unknown_file_is_still_refused(rulesets):
    """`notes` is allowed because nothing reads it. Anything else is still a mistake."""
    from frontier.adapters.rules_loader import load_ruleset

    (rulesets / "2026.1" / "wishes.toml").write_text("hope = 1\n")

    with pytest.raises(RuleSetError, match="unknown ruleset file"):
        load_ruleset(rulesets, "2026.1")
