"""The daily tick: exactly once, resumable, stage by stage. SDD §6.1, ARCH §9.3."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from frontier.adapters.clock import SystemClock, UuidFactory
from frontier.adapters.db import models
from frontier.domain.events.payloads import validate
from frontier.domain.rules.ruleset import RuleSet
from frontier.simulation.stages.base import Features, Stage, TickContext
from frontier.simulation.stages.chronicle import ChronicleAndRetention
from frontier.simulation.stages.digests import BuildDigests
from frontier.simulation.stages.economy import EconomyStep
from frontier.simulation.stages.encounters import ResolveEncounters
from frontier.simulation.stages.grant_ap import GrantActionPoints
from frontier.simulation.stages.missions import MissionLifecycle
from frontier.simulation.stages.population import NpcPopulation
from frontier.simulation.stages.promotion import EventPromotion
from frontier.simulation.stages.psychohistory import PsychohistoryUpdate
from frontier.simulation.stages.settle_travel import SettleTravel
from frontier.simulation.stages.territory import TerritoryRecompute

log = logging.getLogger(__name__)

LOCK_KEY = "frontier:tick"

TICK_STAGES: tuple[Stage, ...] = (
    SettleTravel(),
    ResolveEncounters(),
    EconomyStep(),
    NpcPopulation(),  # the NPC half of stage 4 only
    TerritoryRecompute(),
    MissionLifecycle(),
    PsychohistoryUpdate(),
    EventPromotion(),
    ChronicleAndRetention(),
    GrantActionPoints(),
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
        self,
        sessions: async_sessionmaker[AsyncSession],
        rules: RuleSet,
        clock: SystemClock,
        rng_for: Any,
        features: Features | None = None,
        extra_stages: tuple[Stage, ...] = (),
    ) -> None:
        self._sessions = sessions
        self._rules = rules
        self._clock = clock
        self._rng_for = rng_for
        self._features = features or Features()
        self._extra = extra_stages
        self._ids = UuidFactory(clock)

    async def run(self, stages: tuple[Stage, ...] | None = None) -> TickReport:
        # Sorted by the stage's own declared number, so a stage loaded by name lands in its
        # designed place rather than on the end. Stable, so equal numbers keep tuple order.
        stages = (
            tuple(sorted(TICK_STAGES + self._extra, key=lambda stage: stage.order))
            if stages is None
            else stages
        )
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

    async def _write_events(self, session: AsyncSession, ctx: TickContext) -> None:
        """Stamp and persist whatever the stage raised, in the stage's own transaction."""
        if not ctx.drafts:
            return
        now = self._clock.now()
        for draft in ctx.drafts:
            validate(draft)
            event_id = self._ids.new()
            session.add(
                models.Event(
                    id=event_id,
                    world_day=ctx.world_day,
                    occurred_at=now,
                    type=draft.type.value,
                    origin_path=draft.origin,
                    scope=int(draft.scope),
                    visibility=draft.visibility.value,
                    clearance=0,
                    severity=int(draft.severity),
                    participants=sorted(draft.participants),
                    payload=draft.payload,
                    ruleset_version=self._rules.version,
                )
            )
            session.add(models.EventOutbox(event_id=event_id, world_day=ctx.world_day))
        ctx.drafts.clear()

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
                session=session,
                world_day=day,
                rules=self._rules,
                clock=self._clock,
                rng_for=self._rng_for,
                features=self._features,
            )
            role = getattr(stage, "role", None)
            if role:
                await session.execute(text(f"SET LOCAL ROLE {role}"))
            metrics = await stage.run(ctx)
            if role:
                await session.execute(text("RESET ROLE"))
            await self._write_events(session, ctx)
            session.add(models.TickStage(world_day=day, stage=stage.name, metrics=metrics))
            await session.commit()
            log.info("tick stage complete", extra={"stage": stage.name, "world_day": day})
            return metrics
