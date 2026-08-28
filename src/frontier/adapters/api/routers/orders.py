"""Standing orders — what a ship does while its player is away. GDD §4.4.

The screen that writes these has to read them first: a form that opens blank would quietly
replace orders the player set weeks ago with whatever its defaults happen to be.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer
from frontier.adapters.db import models
from frontier.domain.fleet.standing_orders import StandingOrders

router = APIRouter(prefix="/v1", tags=["orders"])


@router.get("/orders")
async def orders(player_id: CurrentPlayer, c: ContainerDep) -> dict[str, Any]:
    async with c.sessions() as session:
        row = (
            await session.execute(
                select(models.StandingOrders).where(models.StandingOrders.player_id == player_id)
            )
        ).scalar_one_or_none()

    # Registration seeds a row, so the fallback is a guard against a deleted one, not the
    # ordinary case — which is why nothing here tells the client whether it fired.
    fallback = StandingOrders.default()
    return {
        "posture": row.posture if row else fallback.posture.value,
        "engage_hostile": row.engage_hostile if row else fallback.engage_hostile,
        "engage_above_cargo": row.engage_above_cargo if row else fallback.engage_above_cargo,
        "retreat_at_hull_pct": row.retreat_at_hull_pct if row else fallback.retreat_at_hull_pct,
        "auto_reply": row.auto_reply if row else fallback.auto_reply,
    }
