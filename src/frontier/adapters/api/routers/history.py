"""Eras and crises — what the world has been through, and what it is in — PSDD §2.4.

Both are conditions of a *region*, never of a player: nothing here has an actor.

Neither is redacted, and there is nothing to redact: the star chart is already public (D-67), so
a region's name and its troubles are common knowledge. What is inside a system stays private,
and no crisis says anything about that.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer
from frontier.adapters.db import models

router = APIRouter(prefix="/v1", tags=["history"])


@router.get("/history/eras")
async def eras(player_id: CurrentPlayer, c: ContainerDep) -> dict[str, Any]:
    async with c.sessions() as session:
        rows = (
            (await session.execute(select(models.Era).order_by(models.Era.began_on.desc()))).scalars().all()
        )
    return {
        "eras": [
            {
                "id": str(row.id),
                "name": row.name,
                "began_on": row.began_on,
                "ended_on": row.ended_on,
                "summary": row.summary,
            }
            for row in rows
        ]
    }


@router.get("/history/crises")
async def crises(player_id: CurrentPlayer, c: ContainerDep) -> dict[str, Any]:
    async with c.sessions() as session:
        rows = (
            (
                await session.execute(
                    select(models.Crisis)
                    .where(models.Crisis.resolved_on.is_(None))
                    .order_by(models.Crisis.severity.desc(), models.Crisis.opened_on)
                )
            )
            .scalars()
            .all()
        )
    return {
        "crises": [
            {
                "id": str(row.id),
                "region": str(row.region_id),
                "variable": row.variable,
                "opened_on": row.opened_on,
                "expires_on": row.expires_on,
                "severity": row.severity,
            }
            for row in rows
        ]
    }
