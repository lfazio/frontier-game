"""Stage 1 — arrivals land before anything else happens today. SDD §6.2.

Idempotent through the `settled` flag, which is what makes a crashed tick safe to resume.
"""

from __future__ import annotations

from sqlalchemy import select, update

from frontier.adapters.db import models
from frontier.domain.events.model import EventDraft, Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.simulation.stages.base import TickContext


class SettleTravel:
    name = "settle_travel"
    role: str | None = None

    async def run(self, ctx: TickContext) -> dict[str, int]:
        pending = (
            (
                await ctx.session.execute(
                    select(models.Journey)
                    .where(models.Journey.arrives_on <= ctx.world_day, models.Journey.settled.is_(False))
                    .order_by(models.Journey.id)
                )
            )
            .scalars()
            .all()
        )

        for journey in pending:
            await ctx.session.execute(
                update(models.Ship)
                .where(models.Ship.id == journey.ship_id)
                .values(position_path=journey.to_path, system_id=journey.to_system_id)
            )
            await ctx.session.execute(
                update(models.Journey).where(models.Journey.id == journey.id).values(settled=True)
            )
            ctx.emit(
                EventDraft(
                    type=EventType.SHIP_ENTERED,
                    origin=journey.to_path,
                    scope=Scope.LOCAL,
                    visibility=Visibility.PUBLIC,
                    severity=Severity.TRIVIAL,
                    payload={
                        "ship_id": str(journey.ship_id),
                        "actor_kind": "player",
                        "from": str(journey.from_path),
                        "to": str(journey.to_path),
                    },
                )
            )
        return {"journeys_settled": len(pending)}
