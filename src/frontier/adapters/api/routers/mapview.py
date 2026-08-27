"""Map streaming — one tile per request, cached by ETag. SDD §9.1."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Response

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer
from frontier.adapters.api.errors import problem
from frontier.adapters.db.feed import viewer_for
from frontier.adapters.db.map_tiles import MapTiles
from frontier.domain.hex.coordinates import HexAddr

router = APIRouter(prefix="/v1", tags=["map"])


@router.get("/map/tiles")
async def tile(
    path: str,
    player_id: CurrentPlayer,
    c: ContainerDep,
    response: Response,
    if_none_match: str | None = Header(default=None),
) -> Any:
    try:
        prefix = HexAddr.parse(path)
    except ValueError:
        return problem(400, "MALFORMED", "not an address", path=path)

    rules = c.executor.rules
    async with c.sessions() as session:
        viewer = await viewer_for(
            session, player_id, rules.world.sensor_range_base, rules.world.radio_range_base
        )
        day = await _world_day(session)
        built = await MapTiles(session).tile(prefix, player_id, day, viewer.sensor_range, viewer.position)

    etag = built.etag()
    if if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=30"
    return built.as_dict()


async def _world_day(session: Any) -> int:
    from sqlalchemy import select

    from frontier.adapters.db import models

    return int((await session.execute(select(models.WorldState.world_day))).scalar_one())
