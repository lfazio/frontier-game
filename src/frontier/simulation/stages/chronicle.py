"""Stage 10 — what history keeps, and what it lets go. GDD §7.8, §8.10, SDD §6.8.

Promoted events become permanent Chronicle entries before anything expires, so the record can
never lose something the retention job was about to drop.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete, func, select

from frontier.adapters.db import models
from frontier.domain.events.model import Scope
from frontier.simulation.stages.base import TickContext

TITLES = {
    Scope.SYSTEM: "Unrest in {place}",
    Scope.REGION: "Conflict across {place}",
    Scope.UNIVERSE: "A turning point at {place}",
}


class ChronicleAndRetention:
    name = "chronicle"

    async def run(self, ctx: TickContext) -> dict[str, int]:
        kept = await self._promote_to_history(ctx)
        expired = await self._expire(ctx)
        return {"chronicled": kept, "events_expired": expired}

    async def _promote_to_history(self, ctx: TickContext) -> int:
        rows = (
            (
                await ctx.session.execute(
                    select(models.Event)
                    .where(models.Event.world_day == ctx.world_day)
                    .where(models.Event.severity >= ctx.rules.events.chronicle_min_severity)
                    .order_by(models.Event.id)
                )
            )
            .scalars()
            .all()
        )

        existing = set(
            (
                await ctx.session.execute(
                    select(models.Chronicle.causation_id).where(models.Chronicle.world_day == ctx.world_day)
                )
            ).scalars()
        )

        kept = 0
        for row in rows:
            if row.id in existing:
                continue
            place = await self._name_of(ctx, row.origin_path)
            template = TITLES.get(Scope(row.scope), "{place}")
            ctx.session.add(
                models.Chronicle(
                    id=uuid4(),
                    world_day=row.world_day,
                    occurred_at=row.occurred_at,
                    scope=row.scope,
                    origin_path=row.origin_path,
                    type=row.type,
                    title=template.format(place=place),
                    body=dict(row.payload),
                    causation_id=row.id,
                )
            )
            kept += 1
        return kept

    async def _name_of(self, ctx: TickContext, path: object) -> str:
        row = (
            await ctx.session.execute(select(models.Location.name).where(models.Location.path == path))
        ).scalar_one_or_none()
        return row or str(path)

    async def _expire(self, ctx: TickContext) -> int:
        """Local noise has a short life; anything worth keeping is already in the Chronicle."""
        total = 0
        for scope in (Scope.LOCAL, Scope.PLANET, Scope.SYSTEM):
            days = ctx.rules.events.retention_days(int(scope))
            if days is None:
                continue
            cutoff = ctx.world_day - days
            if cutoff <= 0:
                continue
            removed = (
                await ctx.session.execute(
                    select(func.count())
                    .select_from(models.Event)
                    .where(models.Event.scope == int(scope), models.Event.world_day < cutoff)
                )
            ).scalar_one()
            await ctx.session.execute(
                delete(models.Event).where(models.Event.scope == int(scope), models.Event.world_day < cutoff)
            )
            await ctx.session.execute(
                delete(models.EventDelivery).where(models.EventDelivery.world_day < cutoff)
            )
            total += removed
        return total
