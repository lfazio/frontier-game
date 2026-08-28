"""Crews a player can find and join — GDD §6.

A team is a public organisation: its name, banner and size are how it recruits, so the roster of
teams is not redacted. Who is in one is another matter and is not answered here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer
from frontier.adapters.db import models

router = APIRouter(prefix="/v1", tags=["teams"])


@router.get("/teams")
async def teams(player_id: CurrentPlayer, c: ContainerDep) -> dict[str, Any]:
    async with c.sessions() as session:
        sizes = dict(
            (
                await session.execute(
                    select(models.Player.team_id, func.count())
                    .where(models.Player.team_id.is_not(None))
                    .group_by(models.Player.team_id)
                )
            ).all()
        )
        rows = (await session.execute(select(models.Team).order_by(models.Team.name))).scalars().all()
        player = (
            await session.execute(select(models.Player).where(models.Player.id == player_id))
        ).scalar_one()

    return {
        "yours": str(player.team_id) if player.team_id else None,
        "teams": [
            {
                "id": str(row.id),
                "name": row.name,
                "faction_id": row.faction_id,
                "founded_on": row.founded_on,
                "members": sizes.get(row.id, 0),
                "defected_on": row.defected_on,
            }
            for row in rows
        ],
    }
