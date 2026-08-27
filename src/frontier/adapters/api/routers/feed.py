"""The merged feed: chat and world events, one ordered stream — GDD §7.9."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer
from frontier.adapters.db.feed import MAX_LIMIT, FeedRepo, as_dict, viewer_for

router = APIRouter(prefix="/v1", tags=["feed"])


@router.get("/feed")
async def feed(
    player_id: CurrentPlayer,
    c: ContainerDep,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
) -> dict[str, Any]:
    rules = c.executor.rules
    async with c.sessions() as session:
        viewer = await viewer_for(
            session, player_id, rules.world.sensor_range_base, rules.world.radio_range_base
        )
        views = await FeedRepo(session).page(viewer, after=after, limit=limit)
    return {
        "events": [as_dict(v) for v in views],
        "cursor": str(views[0].id) if views else None,
    }
