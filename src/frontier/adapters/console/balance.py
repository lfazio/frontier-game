"""The dials, and the branch a change to them arrives on — ADMIN §3.4, QA-2.

The live ruleset is never edited. Two worlds claiming `2026.1` must behave the same, or a
replayed tick would not reproduce, so what the console offers instead is a **draft**: the same
files with the operator's edits, written as a new version on a branch, to be reviewed and merged
like any other change. A draft that is never merged changes nothing, which is the property that
makes the button safe to press.
"""

from __future__ import annotations

import subprocess
import tomllib
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from frontier.domain.rules.ruleset import RuleSet

# Which file each section of the ruleset lives in.
SECTIONS = {
    "ap": "ap_costs",
    "world": "world",
    "combat": "combat",
    "economy": "economy",
    "npc": "npc",
    "events": "events",
    "continuity": "continuity",
}


def next_version(version: str) -> str:
    """`2026.1` becomes `2026.2`. A draft is the next version, not a variant of this one."""
    head, _, tail = version.rpartition(".")
    return f"{head}.{int(tail) + 1}" if head and tail.isdigit() else f"{version}-draft"


def notes_for(root: Path, version: str) -> dict[str, str]:
    found = root / version / "notes.toml"
    if not found.is_file():
        return {}
    return {str(k): str(v) for k, v in tomllib.loads(found.read_text()).items()}


def dials(rules: RuleSet, notes: dict[str, str]) -> list[dict[str, Any]]:
    """Every tunable number in the ruleset, found by walking it rather than by listing them.

    A dial added to the rules appears here without the console being told, which is the only way
    the screen can be trusted to be complete.
    """
    out: list[dict[str, Any]] = []
    for section in SECTIONS:
        block = getattr(rules, section)
        if not is_dataclass(block):
            continue
        for field in fields(block):
            value = getattr(block, field.name)
            if not isinstance(value, int | float) or isinstance(value, bool):
                continue
            key = f"{section}.{field.name}"
            out.append(
                {
                    "key": key,
                    "section": section,
                    "name": field.name,
                    "value": value,
                    "note": notes.get(key, ""),
                    "integral": isinstance(value, int),
                }
            )
    return out


def _rewrite(source: str, key: str, value: Any) -> str:
    """Replace one top-level assignment, leaving every comment and blank line where it was.

    Rewriting the file line by line rather than re-serialising the parsed document is what keeps
    the notes and section comments the ruleset is full of — a regenerated TOML would lose them.
    """
    lines = source.split("\n")
    depth_ok = True
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            # Past the first table header, an assignment belongs to that table, not the top.
            depth_ok = False
            continue
        if not depth_ok or not stripped or stripped.startswith("#"):
            continue
        name, _, _ = stripped.partition("=")
        if name.strip() == key:
            rendered = value if isinstance(value, int) else f"{value:g}"
            lines[index] = f"{key} = {rendered}"
            return "\n".join(lines)
    raise KeyError(key)


def draft(root: Path, version: str, new_version: str, edits: dict[str, Any], author: str) -> dict[str, Any]:
    """Write the edited ruleset as a new version, on a branch if this is a work tree."""
    source = root / version
    target = root / new_version
    if target.exists():
        raise FileExistsError(new_version)

    changed: dict[str, dict[str, Any]] = {}
    contents = {p.name: p.read_text() for p in sorted(source.glob("*.toml"))}
    for key, value in edits.items():
        section, _, name = key.partition(".")
        filename = f"{SECTIONS[section]}.toml"
        contents[filename] = _rewrite(contents[filename], name, value)
        changed[key] = {"to": value}

    target.mkdir(parents=True)
    for name, text in contents.items():
        (target / name).write_text(text)

    branch = f"ruleset/{new_version}"
    committed = _commit(root, target, branch, new_version, author)
    return {
        "version": new_version,
        "path": str(target),
        "branch": branch if committed else None,
        "committed": committed,
        "changed": changed,
    }


def _commit(root: Path, target: Path, branch: str, version: str, author: str) -> bool:
    """Best effort. A draft on disk is still a draft; the branch is a convenience, not the point."""

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False, timeout=30
        )

    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        return False
    if git("switch", "-c", branch).returncode != 0:
        return False
    git("add", str(target))
    done = git("commit", "-m", f"Draft ruleset {version}, from the console by {author}")
    return done.returncode == 0
