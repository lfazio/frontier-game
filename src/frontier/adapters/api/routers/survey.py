"""A rationed look at the whole world — GDD §9.6, PSDD §4.4.

The projection is the one watch mode already serves: strictly weaker than a player's own view,
and read-only, so this route emits no event and touches no write path. What is different is the
entitlement and the ration.

The ration is claimed for the *faction*, not the caller. One member spending it spends it for
everyone, which is what makes it a shared instrument rather than a personal advantage.

Anyone without the entitlement gets the same `404` as a route that does not exist, so its
absence and its refusal are the same answer.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer
from frontier.adapters.db import models
from frontier.adapters.db.map_tiles import MapTiles
from frontier.domain.hex.coordinates import HexAddr

router = APIRouter(prefix="/v1", tags=["map"])

RATION_KEY = "survey:ration"


@router.get("/survey")
async def survey(player_id: CurrentPlayer, c: ContainerDep) -> dict[str, Any]:
    async with c.sessions() as session:
        cleared = (
            await session.execute(select(models.Player.clearance).where(models.Player.id == player_id))
        ).scalar_one_or_none()
        if not cleared:
            # Word for word what a route that does not exist answers. `NOT_FOUND`, which the
            # resource endpoints use, would mark this one as a real route being withheld.
            raise HTTPException(status_code=404, detail="Not Found")

        interval = c.settings.watch_interval_seconds or c.executor.rules.continuity.watch_interval_seconds
        if c.bus is None or not await c.bus.claim(RATION_KEY, interval):
            # Spent. Saying so is safe: only a holder ever reaches this line.
            raise HTTPException(status_code=429, detail="RATION_SPENT")

        day = (await session.execute(select(models.WorldState.world_day))).scalar_one()
        tiles = MapTiles(session)
        galaxy = await tiles.public_tile(HexAddr.parse("ga0_0"), day)
        regions = [
            (await tiles.public_tile(HexAddr.parse(entry["path"]), day)).as_dict() for entry in galaxy.entries
        ]

    return {"world_day": day, "galaxy": galaxy.as_dict(), "regions": regions}
