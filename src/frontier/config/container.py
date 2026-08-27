"""Composition root — the only module that knows both ports and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from frontier.adapters.clock import SeededRng, SystemClock, UuidFactory
from frontier.adapters.db.engine import make_engine, make_sessionmaker
from frontier.adapters.db.uow import SqlUnitOfWork
from frontier.adapters.memory.fixture import seed_fixture_world
from frontier.adapters.memory.store import World
from frontier.adapters.memory.uow import MemoryUnitOfWork
from frontier.adapters.registrar import MemoryRegistrar, Registrar, SqlRegistrar
from frontier.adapters.rules_loader import load_ruleset
from frontier.application.executor import Executor
from frontier.config.settings import Settings


@dataclass(slots=True)
class Container:
    settings: Settings
    executor: Executor
    clock: SystemClock
    registrar: Registrar
    world: World | None = None
    engine: AnyEngine = None
    sessions: Any = None


AnyEngine = AsyncEngine | None


def build(settings: Settings | None = None, world: World | None = None) -> Container:
    """In-memory wiring: the fixture world of P0, used by fast tests and the demo."""
    settings = settings or Settings()
    world = world if world is not None else World()
    seed_fixture_world(world)
    clock = SystemClock()
    rules = load_ruleset(settings.ruleset_root, settings.ruleset_version)
    executor = Executor(
        uow_factory=partial(MemoryUnitOfWork, world),
        clock=clock,
        rng=SeededRng(settings.world_seed),
        ids=UuidFactory(clock),
        rules=rules,
    )
    return Container(
        settings=settings,
        executor=executor,
        clock=clock,
        world=world,
        registrar=MemoryRegistrar(world, rules.ap.daily_grant),
    )


def build_sql(settings: Settings | None = None) -> Container:
    """PostgreSQL wiring: the real world."""
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    sessions = make_sessionmaker(engine)
    clock = SystemClock()
    rules = load_ruleset(settings.ruleset_root, settings.ruleset_version)
    executor = Executor(
        uow_factory=partial(SqlUnitOfWork, sessions),
        clock=clock,
        rng=SeededRng(settings.world_seed),
        ids=UuidFactory(clock),
        rules=rules,
    )
    return Container(
        settings=settings,
        executor=executor,
        clock=clock,
        registrar=SqlRegistrar(sessions, rules.ap.daily_grant),
        engine=engine,
        sessions=sessions,
    )
