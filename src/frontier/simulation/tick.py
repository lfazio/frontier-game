"""The daily tick: exactly once, resumable, stage by stage. SDD §6.1, ARCH §9.3."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from frontier.adapters.clock import SystemClock
from frontier.adapters.db import models
from frontier.domain.rules.ruleset import RuleSet
from frontier.simulation.stages.base import Stage, TickContext
from frontier.simulation.stages.digests import BuildDigests
from frontier.simulation.stages.economy import EconomyStep
from frontier.simulation.stages.encounters import ResolveEncounters
from frontier.simulation.stages.grant_ap import GrantActionPoints
from frontier.simulation.stages.population import NpcPopulation
from frontier.simulation.stages.settle_travel import SettleTravel
from frontier.simulation.stages.territory import TerritoryRecompute

log = logging.getLogger(__name__)

LOCK_KEY = "frontier:tick"

MVP_STAGES: tuple[Stage, ...] = (
    SettleTravel(),  # ARCH stage 1
    ResolveEncounters(),  # ARCH stage 2
    EconomyStep(),  # ARCH stage 3
    NpcPopulation(),  # ARCH stage 4, NPC half only
    TerritoryRecompute(),  # ARCH stage 5
    GrantActionPoints(),  # ARCH stage 11
    BuildDigests(),  # ARCH stages 12-13
)


class TickBusy(Exception):
    """Another runner holds the advisory lock."""


@dataclass(slots=True)
class TickReport:
    world_day: int
    stages: dict[str, dict[str, int]]
    resumed: bool


class TickRunner:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], rules: RuleSet, clock: SystemClock, rng_for: Any
    ) -> None:
        self._sessions = sessions
        self._rules = rules
        self._clock = clock
        self._rng_for = rng_for

    async def run(self, stages: tuple[Stage, ...] = MVP_STAGES) -> TickReport:
        async with self._sessions() as session:
            await session.begin()
            if not await self._acquire(session):
                raise TickBusy
            day, resumed = await self._open_day(session)
            await session.execute(update(models.WorldState).values(phase="ticking"))
            await session.commit()

        report: dict[str, dict[str, int]] = {}
        for stage in stages:
            report[stage.name] = await self._run_stage(stage, day)

        async with self._sessions() as session:
            await session.begin()
            await session.execute(
                update(models.TickRun).where(models.TickRun.world_day == day).values(finished_at=func.now())
            )
            await session.execute(update(models.WorldState).values(phase="open"))
            await session.commit()
        return TickReport(world_day=day, stages=report, resumed=resumed)

    async def _acquire(self, session: AsyncSession) -> bool:
        held = await session.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:key))").bindparams(key=LOCK_KEY)
        )
        return bool(held.scalar_one())

    async def _open_day(self, session: AsyncSession) -> tuple[int, bool]:
        """Advance the world day once. A resumed run finds its tick_run already open."""
        current = (await session.execute(select(models.WorldState))).scalar_one()
        target = current.world_day + 1

        unfinished = (
            await session.execute(
                select(models.TickRun)
                .where(models.TickRun.finished_at.is_(None))
                .order_by(models.TickRun.world_day.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if unfinished is not None:
            return unfinished.world_day, True

        session.add(models.TickRun(world_day=target))
        await session.execute(update(models.WorldState).values(world_day=target))
        return target, False

    async def _run_stage(self, stage: Stage, day: int) -> dict[str, int]:
        async with self._sessions() as session:
            await session.begin()
            done = (
                await session.execute(
                    select(models.TickStage).where(
                        models.TickStage.world_day == day, models.TickStage.stage == stage.name
                    )
                )
            ).scalar_one_or_none()
            if done is not None:
                # Read before rollback: rolling back expires the row and a refresh would
                # need IO the caller's greenlet no longer has.
                already = dict(done.metrics) | {"skipped": 1}
                await session.rollback()
                return already

            ctx = TickContext(
                session=session, world_day=day, rules=self._rules, clock=self._clock, rng_for=self._rng_for
            )
            metrics = await stage.run(ctx)
            session.add(models.TickStage(world_day=day, stage=stage.name, metrics=metrics))
            await session.commit()
            log.info("tick stage complete", extra={"stage": stage.name, "world_day": day})
            return metrics
