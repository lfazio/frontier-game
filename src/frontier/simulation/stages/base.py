from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from frontier.adapters.clock import SystemClock
from frontier.domain.events.model import EventDraft
from frontier.domain.rules.ruleset import RuleSet


@dataclass(frozen=True, slots=True)
class Features:
    """Systems that ship dark until the world is old enough to tune them — GDD §10.3."""

    psychohistory: bool = False
    continuity: bool = False


@dataclass(slots=True)
class TickContext:
    session: AsyncSession
    world_day: int
    rules: RuleSet
    clock: SystemClock
    rng_for: Any
    features: Features = field(default_factory=Features)
    # Drafts raised by a stage; the runner stamps and writes them once the stage commits,
    # so "no state change without an event" (ARCH §3.2) holds for the tick as well as for
    # commands.
    drafts: list[EventDraft] = field(default_factory=list)
    metrics: dict[str, int] = field(default_factory=dict)

    def emit(self, draft: EventDraft) -> None:
        self.drafts.append(draft)


class Stage(Protocol):
    name: str
    # A stage may name the database role whose grants bound what it can do.
    role: str | None
    # Its place in the cycle: the ARCH §9.2 stage number times ten. The runner sorts by this, so
    # a stage loaded by name (ARCH ADR-13) takes its proper position without the runner naming
    # it. The spacing is what lets a later stage slot between two without renumbering the
    # architecture — the Harrowing sits at 85, between the Continuity and promotion.
    order: int

    async def run(self, ctx: TickContext) -> dict[str, int]: ...
