"""Reads ruleset TOML from disk and hands the domain a validated value — SDD §3.4."""

from __future__ import annotations

import tomllib
from pathlib import Path

from frontier.domain.rules.ruleset import RuleSet, RuleSetError


def load_ruleset(root: Path, version: str) -> RuleSet:
    directory = root / version
    if not directory.is_dir():
        raise RuleSetError(f"no ruleset at {directory}")
    files = {p.stem: tomllib.loads(p.read_text()) for p in sorted(directory.glob("*.toml"))}
    return RuleSet.from_mapping(version, files)
