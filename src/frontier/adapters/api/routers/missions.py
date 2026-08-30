"""Mission offers and the player's own board — GDD §5.5."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer
from frontier.adapters.db import models

router = APIRouter(prefix="/v1", tags=["missions"])


@router.get("/missions")
async def offers(player_id: CurrentPlayer, c: ContainerDep) -> dict[str, Any]:
    """Offers a player may take, plus the ones they already hold."""
    async with c.sessions() as session:
        player = (
            await session.execute(select(models.Player).where(models.Player.id == player_id))
        ).scalar_one()

        taken = {
            row.mission_id
            for row in (
                await session.execute(
                    select(models.MissionAssignment).where(models.MissionAssignment.status == "active")
                )
            ).scalars()
        }
        mine = {
            row.mission_id
            for row in (
                await session.execute(
                    select(models.MissionAssignment).where(
                        models.MissionAssignment.player_id == player_id,
                        models.MissionAssignment.status == "active",
                    )
                )
            ).scalars()
        }
        rows = (
            await session.execute(
                select(models.Mission, models.Location.path, models.Location.name)
                .join(models.Location, models.Location.id == models.Mission.system_id)
                .order_by(models.Mission.offered_on.desc(), models.Mission.id)
            )
        ).all()
        reputation = {
            row.faction_id: row.score
            for row in (
                await session.execute(
                    select(models.Reputation).where(models.Reputation.player_id == player_id)
                )
            ).scalars()
        }

    def render(mission: models.Mission, path: object, name: str | None) -> dict[str, Any]:
        return {
            "id": str(mission.id),
            "kind": mission.kind,
            "faction_id": mission.faction_id,
            "brief": mission.brief,
            "system": str(path),
            "system_name": name,
            "reward_credits": mission.reward_credits,
            "reward_reputation": mission.reward_reputation,
            "expires_on": mission.expires_on,
        }

    return {
        "faction_id": player.faction_id,
        "reputation": reputation,
        "mine": [render(m, p, n) for m, p, n in rows if m.id in mine],
        "offers": [
            render(m, p, n)
            for m, p, n in rows
            if m.id not in taken
            and player.faction_id in (None, m.faction_id)
            # An addressed offer is on one board and no other. Everyone else's board is the
            # board it always was, which is what makes an approach unobservable.
            and m.offered_to in (None, player_id)
        ],
    }
