from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from frontier.adapters.clock import SystemClock
from frontier.domain.rules.ruleset import RuleSet


@dataclass(frozen=True, slots=True)
class Features:
    """Systems that ship dark until the world is old enough to tune them — GDD §10.3."""

    psychohistory: bool = False


@dataclass(slots=True)
class TickContext:
    session: AsyncSession
    world_day: int
    rules: RuleSet
    clock: SystemClock
    rng_for: Any
    features: Features = field(default_factory=Features)
    metrics: dict[str, int] = field(default_factory=dict)


class Stage(Protocol):
    name: str

    async def run(self, ctx: TickContext) -> dict[str, int]: ...
