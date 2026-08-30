"""What the console reads from a world — ADMIN §3.1 and §3.2.

Everything here is a `SELECT`. A stage's duration is not stored anywhere: `tick_stages` records
when each finished, so a stage's time is the gap since the one before it, and the first is
measured from the run's start. That is a read model, not a schema change — the tick has no
business carrying numbers it does not use.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from frontier.adapters.db import models


async def overview(session: AsyncSession) -> dict[str, Any]:
    state = (await session.execute(select(models.WorldState))).scalar_one_or_none()
    last = (
        await session.execute(select(models.TickRun).order_by(models.TickRun.world_day.desc()).limit(1))
    ).scalar_one_or_none()

    counts = (
        await session.execute(
            text(
                "SELECT (SELECT count(*) FROM core.locations WHERE kind = 'system') AS systems, "
                "       (SELECT count(*) FROM core.players) AS pilots, "
                "       (SELECT count(*) FROM core.teams) AS crews, "
                "       (SELECT count(*) FROM core.locations WHERE kind = 'void' AND level = 2) AS empty"
            )
        )
    ).one()

    era = (
        await session.execute(select(models.Era).where(models.Era.ended_on.is_(None)))
    ).scalar_one_or_none()
    open_crises = (
        await session.execute(
            select(func.count())
            .select_from(models.Crisis)
            .where(models.Crisis.resolved_on.is_(None), models.Crisis.answered_on.is_(None))
        )
    ).scalar_one()
    soonest = (
        await session.execute(
            select(func.min(models.Crisis.expires_on)).where(
                models.Crisis.resolved_on.is_(None), models.Crisis.answered_on.is_(None)
            )
        )
    ).scalar_one()
    hulls = (
        await session.execute(
            text(
                "SELECT count(*) FROM core.npc_agents n JOIN core.ships s ON s.id = n.ship_id "
                "WHERE n.archetype = 'incursion' AND s.destroyed_on IS NULL"
            )
        )
    ).scalar_one()

    day = state.world_day if state else None
    return {
        "world_day": day,
        "phase": state.phase if state else None,
        "counts": {
            "systems": counts.systems,
            "pilots": counts.pilots,
            "crews": counts.crews,
            "empty_space": counts.empty,
        },
        "last_tick": _run(last),
        "history": {
            "era": era.name if era else None,
            "era_began_on": era.began_on if era else None,
            "open_crises": int(open_crises),
            # In days, because "expires on day 85" means nothing without today's number.
            "soonest_expiry_in": (soonest - day) if (soonest is not None and day is not None) else None,
            "incursion_hulls": int(hulls),
        },
    }


async def runs(session: AsyncSession, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        (await session.execute(select(models.TickRun).order_by(models.TickRun.world_day.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return [_run(row) for row in rows]


async def stages_of(session: AsyncSession, day: int) -> dict[str, Any] | None:
    run = (
        await session.execute(select(models.TickRun).where(models.TickRun.world_day == day))
    ).scalar_one_or_none()
    if run is None:
        return None

    rows = (
        (
            await session.execute(
                select(models.TickStage)
                .where(models.TickStage.world_day == day)
                .order_by(models.TickStage.completed_at)
            )
        )
        .scalars()
        .all()
    )

    stages: list[dict[str, Any]] = []
    previous = run.started_at
    for row in rows:
        seconds = _seconds(previous, row.completed_at)
        previous = row.completed_at
        stages.append({"stage": row.stage, "seconds": seconds, "metrics": row.metrics})

    elapsed = _seconds(run.started_at, run.finished_at or previous)
    for stage in stages:
        stage["share"] = round(stage["seconds"] / elapsed, 4) if elapsed else 0.0

    detail = _run(run)
    detail["stages"] = stages
    # A run with no finish and no stage since is where it stopped; the stage after the last one
    # recorded is the one that broke.
    detail["stopped_after"] = stages[-1]["stage"] if stages and run.finished_at is None else None
    return detail


def _run(row: models.TickRun | None) -> dict[str, Any]:
    if row is None:
        return {"world_day": None, "finished": False}
    return {
        "world_day": row.world_day,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "finished": row.finished_at is not None,
        "seconds": _seconds(row.started_at, row.finished_at),
        "retry_requested": row.retry_requested_at is not None,
    }


def _seconds(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return round((end - start).total_seconds(), 3)
