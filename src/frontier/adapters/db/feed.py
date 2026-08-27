"""Reading the merged feed — SDD §9.3.

Narrow-audience events come from deliveries, spatial events from the log by path prefix. Both
are ordered by UUIDv7, which is monotonic, so the merge is an ordered zip with no timestamp
comparison. Every row still passes through `render_for` before it reaches a client.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from frontier.adapters.db import models
from frontier.application.visibility import EventView, ViewerContext, render_for
from frontier.domain.events.model import Event, Scope, Severity, Visibility
from frontier.domain.events.types import EventType

MAX_LIMIT = 200


def _to_domain(row: models.Event) -> Event:
    return Event(
        id=row.id,
        world_day=row.world_day,
        occurred_at=row.occurred_at,
        type=EventType(row.type),
        origin=row.origin_path,
        scope=Scope(row.scope),
        visibility=Visibility(row.visibility),
        severity=Severity(row.severity),
        participants=frozenset(row.participants),
        payload=row.payload,
        ruleset_version=row.ruleset_version,
        clearance=row.clearance,
        causation_id=row.causation_id,
    )


class FeedRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def page(
        self, viewer: ViewerContext, *, after: UUID | None = None, limit: int = 50
    ) -> list[EventView]:
        limit = min(limit, MAX_LIMIT)
        candidates = await self._candidates(viewer, after, limit)
        views = [v for v in (render_for(viewer, e) for e in candidates) if v is not None]
        return views[:limit]

    async def _candidates(self, viewer: ViewerContext, after: UUID | None, limit: int) -> list[Event]:
        """Over-fetch: redaction can drop rows, so the page is trimmed after rendering."""
        delivered = (
            select(models.Event)
            .join(models.EventDelivery, models.EventDelivery.event_id == models.Event.id)
            .where(models.EventDelivery.recipient_id == viewer.player_id)
        )

        spatial = select(models.Event).where(models.Event.visibility == Visibility.PUBLIC.value)
        if viewer.position is not None:
            system = viewer.position.parent() or viewer.position
            spatial = spatial.where(
                text("origin_path <@ CAST(:prefix AS ltree)").bindparams(prefix=system.ltree())
            )

        rows: dict[UUID, models.Event] = {}
        for query in (delivered, spatial):
            if after is not None:
                query = query.where(models.Event.id > after)
            result = await self._s.execute(query.order_by(models.Event.id.desc()).limit(limit * 3))
            for row in result.scalars():
                rows[row.id] = row
        return [_to_domain(r) for r in sorted(rows.values(), key=lambda r: r.id, reverse=True)]

    async def unread(self, player_id: UUID) -> int:
        found = await self._s.execute(
            select(models.EventDelivery).where(
                models.EventDelivery.recipient_id == player_id, models.EventDelivery.read_at.is_(None)
            )
        )
        return len(list(found.scalars()))


async def viewer_for(
    session: AsyncSession, player_id: UUID, sensor_default: int, radio_default: int
) -> ViewerContext:
    row = (
        await session.execute(
            select(models.Player, models.Ship)
            .outerjoin(models.Ship, models.Ship.player_id == models.Player.id)
            .where(models.Player.id == player_id)
        )
    ).first()
    if row is None:
        raise LookupError(player_id)
    player, ship = row
    return ViewerContext(
        player_id=player_id,
        position=ship.position_path if ship else None,
        sensor_range=ship.sensor_range if ship else sensor_default,
        radio_range=radio_default,
        team_id=player.team_id,
        faction_id=player.faction_id,
    )


def as_dict(view: EventView) -> dict[str, Any]:
    from frontier.application.visibility import stamp_view

    return stamp_view(view)
