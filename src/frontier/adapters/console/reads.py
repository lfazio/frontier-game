"""What the console reads from a world — ADMIN §3.1 and §3.2.

Everything here is a `SELECT`. A stage's duration is not stored anywhere: `tick_stages` records
when each finished, so a stage's time is the gap since the one before it, and the first is
measured from the run's start. That is a read model, not a schema change — the tick has no
business carrying numbers it does not use.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

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


async def history(session: AsyncSession, day: int | None) -> dict[str, Any]:
    """Eras, crises and incursions — ADMIN §3.3.

    The countdown is the point. An operator should be able to see that a region is about to be
    invaded *before* it is, which is when a world is most worth watching.
    """
    regions = {
        row.id: row.name
        for row in (
            await session.execute(select(models.Location).where(models.Location.kind == "region"))
        ).scalars()
    }

    eras = [
        {
            "name": row.name,
            "began_on": row.began_on,
            "ended_on": row.ended_on,
            "summary": row.summary,
            "current": row.ended_on is None,
        }
        for row in (
            (await session.execute(select(models.Era).order_by(models.Era.began_on.desc()))).scalars().all()
        )
    ]

    crises = (
        (await session.execute(select(models.Crisis).order_by(models.Crisis.opened_on.desc())))
        .scalars()
        .all()
    )

    # Which crisis raised which hulls, and how many are still flying.
    incursions: dict[str, dict[str, Any]] = {}
    for row in (
        await session.execute(
            text(
                "SELECT n.route ->> 'crisis' AS crisis, n.materialised_on AS raised_on, "
                "       count(*) AS hulls, "
                "       count(*) FILTER (WHERE s.destroyed_on IS NULL) AS flying, "
                "       max(region.name) AS region "
                "FROM core.npc_agents n "
                "JOIN core.ships s ON s.id = n.ship_id "
                "JOIN core.locations berth ON berth.id = s.system_id "
                "LEFT JOIN core.locations region ON region.id = "
                "     coalesce(berth.parent_id, berth.id) "
                "WHERE n.archetype = 'incursion' "
                "GROUP BY 1, 2"
            )
        )
    ).all():
        incursions[str(row.crisis)] = {
            "region": row.region,
            "raised_on": row.raised_on,
            "hulls": int(row.hulls),
            "still_flying": int(row.flying),
        }

    def shape(row: models.Crisis) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "region": regions.get(row.region_id, "unknown"),
            "variable": row.variable,
            "severity": row.severity,
            "opened_on": row.opened_on,
            "expires_on": row.expires_on,
            "days_left": (row.expires_on - day) if day is not None else None,
            "resolved_on": row.resolved_on,
            "answered_on": row.answered_on,
            "incursion": incursions.get(str(row.id)),
        }

    return {
        "era": next((e for e in eras if e["current"]), None),
        "eras": eras,
        "era_threshold": None,
        "open": [shape(c) for c in crises if c.resolved_on is None and c.answered_on is None],
        "answered": [shape(c) for c in crises if c.answered_on is not None],
        "resolved": [shape(c) for c in crises if c.resolved_on is not None][:10],
    }


async def pilots(session: AsyncSession, query: str = "") -> list[dict[str, Any]]:
    """Find a pilot by callsign. Clearance is not a column this may select — ADMIN §3.5."""
    rows = (
        (
            await session.execute(
                select(models.Player)
                .where(models.Player.callsign.ilike(f"%{query}%"))
                .order_by(models.Player.callsign)
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(row.id),
            "callsign": row.callsign,
            "generation": row.generation,
            "allegiance": row.allegiance,
        }
        for row in rows
    ]


async def pilot(session: AsyncSession, player_id: UUID) -> dict[str, Any] | None:
    """One pilot's record: what the server did, and nothing it is meant not to show.

    **Clearance is never read here.** An operator who also plays would otherwise learn who to
    follow, so the console redacts that one field from itself (ADMIN §3.5).
    """
    row = (
        await session.execute(select(models.Player).where(models.Player.id == player_id))
    ).scalar_one_or_none()
    if row is None:
        return None

    ship = (
        await session.execute(
            select(models.Ship).where(models.Ship.player_id == player_id, models.Ship.destroyed_on.is_(None))
        )
    ).scalar_one_or_none()
    team = (
        await session.execute(select(models.Team.name).where(models.Team.id == row.team_id))
    ).scalar_one_or_none()
    standing = (
        await session.execute(
            select(models.Reputation.faction_id, models.Reputation.score).where(
                models.Reputation.player_id == player_id
            )
        )
    ).all()

    events = (
        await session.execute(
            text(
                "SELECT e.type, e.occurred_at, e.world_day, e.payload "
                "FROM evt.events e JOIN evt.event_deliveries d ON d.event_id = e.id "
                "WHERE d.recipient_id = :player "
                "ORDER BY e.occurred_at DESC LIMIT 40"
            ).bindparams(player=player_id)
        )
    ).all()

    return {
        "id": str(row.id),
        "callsign": row.callsign,
        "generation": row.generation,
        "credits": row.credits,
        "action_points": row.ap_balance,
        "knowledge": row.knowledge,
        "crew": team,
        "faction_id": row.faction_id,
        # Public by design: siding with an incursion is announced to the whole world (GDD §8.12).
        "allegiance": row.allegiance,
        "first_sided_on": row.first_sided_on,
        "ship": None
        if ship is None
        else {
            "hull": ship.hull,
            "hull_max": ship.hull_max,
            "shields": ship.shields,
            "fuel": ship.fuel,
            "position": str(ship.position_path),
            "docked": ship.docked_at is not None,
        },
        "standing": [{"faction_id": f, "score": s} for f, s in sorted(standing)],
        "events": [
            {
                "type": e.type,
                "at": e.occurred_at.isoformat(),
                "world_day": e.world_day,
                "payload": e.payload,
            }
            for e in events
        ],
    }


async def directorate(session: AsyncSession, day: int | None) -> dict[str, Any]:
    """What the hidden faction has been doing — ADMIN §3.6.

    An operator tuning it cannot tune what they cannot see, and whoever runs a world can read
    `cont` anyway. What this must not do is change the shape of any *other* screen, which is why
    it is a screen of its own behind its own permission.
    """
    counts = (
        await session.execute(
            text(
                "SELECT (SELECT count(*) FROM cont.cells) AS cells, "
                "       (SELECT count(*) FROM cont.agents) AS agents, "
                "       (SELECT count(*) FROM cont.interventions) AS interventions, "
                "       (SELECT count(*) FROM core.missions WHERE offered_to IS NOT NULL "
                "         AND expires_on >= coalesce(:day, 0)) AS offers"
            ).bindparams(day=day)
        )
    ).one()

    budget = (
        await session.execute(
            text("SELECT world_day, allowed, used FROM cont.budget ORDER BY world_day DESC LIMIT 1")
        )
    ).first()

    leans = (
        await session.execute(
            text(
                "SELECT i.world_day, i.kind, i.magnitude, i.rationale ->> 'lever' AS lever, "
                "       region.name AS region "
                "FROM cont.interventions i "
                "LEFT JOIN core.locations region ON region.id = i.region_id "
                "ORDER BY i.world_day DESC, i.id LIMIT 12"
            )
        )
    ).all()

    return {
        "cells": int(counts.cells),
        "agents": int(counts.agents),
        "interventions": int(counts.interventions),
        "offers_out": int(counts.offers),
        "budget": None
        if budget is None
        else {"world_day": budget.world_day, "allowed": budget.allowed, "used": budget.used},
        "recent": [
            {
                "world_day": row.world_day,
                "kind": row.kind,
                "lever": row.lever,
                "magnitude": float(row.magnitude),
                "region": row.region,
            }
            for row in leans
        ],
    }


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
