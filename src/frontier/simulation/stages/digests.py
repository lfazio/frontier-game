"""Stage 12/13 — the daily overview each player reads at login. GDD §3.4, SDD §6.8.

Built from the day's events for that player, so the first screen after login answers "what
happened to me" without another query.
"""

from __future__ import annotations

from collections import Counter
from uuid import UUID

from sqlalchemy import delete, select

from frontier.adapters.db import models
from frontier.simulation.stages.base import TickContext


class BuildDigests:
    name = "build_digests"
    role: str | None = None
    order = 12

    async def run(self, ctx: TickContext) -> dict[str, int]:
        day = ctx.world_day
        rows = (
            await ctx.session.execute(
                select(models.EventDelivery.recipient_id, models.Event.type)
                .join(models.Event, models.Event.id == models.EventDelivery.event_id)
                .where(models.EventDelivery.world_day.in_((day - 1, day)))
                .order_by(models.EventDelivery.recipient_id)
            )
        ).all()

        by_player: dict[UUID, Counter[str]] = {}
        for recipient, event_type in rows:
            by_player.setdefault(recipient, Counter())[event_type] += 1

        players = (await ctx.session.execute(select(models.Player.id))).scalars().all()
        await ctx.session.execute(delete(models.Digest).where(models.Digest.world_day == day))
        for player_id in players:
            counts = by_player.get(player_id, Counter())
            ctx.session.add(
                models.Digest(
                    player_id=player_id,
                    world_day=day,
                    summary={"events": dict(counts), "total": sum(counts.values())},
                )
            )
        return {"digests_built": len(players)}
