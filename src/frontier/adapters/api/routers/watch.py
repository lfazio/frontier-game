"""Watch mode — a read-only view of a live world, no account required. UX §9.

Everything here is strictly weaker than what any signed-in player can see: the star chart, who
holds it, and public events that already carry to a whole system or wider. A spectator has no
ship and therefore no sensors, so it can learn nothing about anyone's position or cargo.

On a live world this same projection is the Continuity's rationed watch (*GDD §9.6*); here it is
the demonstration surface, and it is enabled by configuration.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from frontier.adapters.api.deps import ContainerDep
from frontier.adapters.api.errors import problem
from frontier.adapters.db import models
from frontier.adapters.db.feed import _to_domain
from frontier.adapters.db.map_tiles import MapTiles
from frontier.application.visibility import render_public, stamp_view
from frontier.domain.hex.coordinates import HexAddr

router = APIRouter(prefix="/v1/watch", tags=["watch"])

FEED_LIMIT = 60


def _enabled(c: ContainerDep) -> None:
    if not c.settings.features_watch:
        raise HTTPException(status_code=404, detail="NOT_FOUND")


@router.get("/overview")
async def overview(request: Request, c: ContainerDep) -> dict[str, Any]:
    _enabled(c)
    async with c.sessions() as session:
        state = (await session.execute(select(models.WorldState))).scalar_one()
        systems = (
            await session.execute(
                select(func.count()).select_from(models.Location).where(models.Location.kind == "system")
            )
        ).scalar_one()
        pilots = (await session.execute(select(func.count()).select_from(models.Player))).scalar_one()
        crews = (await session.execute(select(func.count()).select_from(models.NpcAgent))).scalar_one()
        galaxy = (
            await session.execute(select(models.Location).where(models.Location.kind == "galaxy"))
        ).scalar_one()
    return {
        "world_day": state.world_day,
        "phase": state.phase,
        "galaxy": str(galaxy.path),
        "systems": systems,
        "pilots": pilots,
        "crews": crews,
    }


@router.get("/map")
async def watch_map(path: str, c: ContainerDep) -> Any:
    _enabled(c)
    try:
        prefix = HexAddr.parse(path)
    except ValueError:
        return problem(400, "MALFORMED", "not an address", path=path)

    async with c.sessions() as session:
        state = (await session.execute(select(models.WorldState))).scalar_one()
        tile = await MapTiles(session).public_tile(prefix, state.world_day)
    return tile.as_dict()


@router.get("/feed")
async def watch_feed(c: ContainerDep) -> dict[str, Any]:
    _enabled(c)
    async with c.sessions() as session:
        rows = (
            (
                await session.execute(
                    select(models.Event)
                    .where(models.Event.visibility == "public", models.Event.scope >= 2)
                    .order_by(models.Event.id.desc())
                    .limit(FEED_LIMIT)
                )
            )
            .scalars()
            .all()
        )
    views = [render_public(_to_domain(row)) for row in rows]
    return {"events": [stamp_view(v) for v in views if v is not None]}
