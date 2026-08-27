"""Composition root — the only module that knows both ports and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from frontier.adapters.bus.redis_bus import RedisBus
from frontier.adapters.clock import SeededRng, SystemClock, UuidFactory
from frontier.adapters.db.engine import make_engine, make_sessionmaker
from frontier.adapters.db.uow import SqlUnitOfWork
from frontier.adapters.registrar import Registrar, SqlRegistrar
from frontier.adapters.rules_loader import load_ruleset
from frontier.application.executor import Executor
from frontier.config.settings import Settings


@dataclass(slots=True)
class Container:
    settings: Settings
    executor: Executor
    clock: SystemClock
    registrar: Registrar
    engine: AnyEngine = None
    sessions: Any = None
    bus: RedisBus | None = None


AnyEngine = AsyncEngine | None


def build_sql(settings: Settings | None = None) -> Container:
    """PostgreSQL wiring: the real world."""
    settings = settings or Settings()
    engine = make_engine(settings.database_url, role=settings.api_role)
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
        bus=RedisBus(settings.redis_url),
    )
