"""Composition root — the only module that knows both ports and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial

from frontier.adapters.clock import SeededRng, SystemClock, UuidFactory
from frontier.adapters.memory.store import World
from frontier.adapters.memory.uow import MemoryUnitOfWork
from frontier.adapters.rules_loader import load_ruleset
from frontier.application.executor import Executor
from frontier.config.settings import Settings

WORLD_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(slots=True)
class Container:
    settings: Settings
    world: World
    executor: Executor
    clock: SystemClock


def build(settings: Settings | None = None, world: World | None = None) -> Container:
    settings = settings or Settings()
    world = world if world is not None else World()
    clock = SystemClock(WORLD_EPOCH)
    rules = load_ruleset(settings.ruleset_root, settings.ruleset_version)
    executor = Executor(
        uow_factory=partial(MemoryUnitOfWork, world),
        clock=clock,
        rng=SeededRng(settings.world_seed, clock),
        ids=UuidFactory(clock),
        rules=rules,
    )
    return Container(settings=settings, world=world, executor=executor, clock=clock)
