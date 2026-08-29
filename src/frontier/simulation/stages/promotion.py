"""Stage 9 — significance carries an event outward. GDD §7.7, SDD §7.2.

A skirmish becomes a battle becomes a war because severity accumulated in one place, not because
anyone wrote a pipeline for it. Each promoted event keeps a `causation_id` back to its causes, so
a player reading history can trace a war to the fight that started it.
"""

from __future__ import annotations

from collections import defaultdict
from uuid import uuid4

from sqlalchemy import select

from frontier.adapters.db import models
from frontier.domain.events.model import Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.domain.hex.coordinates import HexAddr
from frontier.simulation.stages.base import TickContext

STEPS = (
    (Scope.LOCAL, Scope.SYSTEM, "local_to_system"),
    (Scope.SYSTEM, Scope.REGION, "system_to_region"),
    (Scope.REGION, Scope.UNIVERSE, "region_to_universe"),
)
DEPTH = {Scope.SYSTEM: 3, Scope.REGION: 2, Scope.UNIVERSE: 1}


class EventPromotion:
    name = "event_promotion"
    role: str | None = None
    order = 9

    async def run(self, ctx: TickContext) -> dict[str, int]:
        window = ctx.world_day - ctx.rules.events.promotion_window_cycles
        promoted = 0

        for from_scope, to_scope, key in STEPS:
            threshold = ctx.rules.events.promotion_threshold[key]
            rows = (
                (
                    await ctx.session.execute(
                        select(models.Event)
                        .where(models.Event.world_day > window, models.Event.scope == int(from_scope))
                        .order_by(models.Event.id)
                    )
                )
                .scalars()
                .all()
            )

            weight: dict[str, int] = defaultdict(int)
            cause: dict[str, models.Event] = {}
            for row in rows:
                container = _container(row.origin_path, to_scope)
                weight[container] += row.severity
                cause.setdefault(container, row)

            for container, total in sorted(weight.items()):
                if total < threshold or await self._already(ctx, container, to_scope):
                    continue
                await self._emit(ctx, container, to_scope, total, cause[container])
                promoted += 1
        return {"promoted": promoted}

    async def _already(self, ctx: TickContext, container: str, scope: Scope) -> bool:
        found = await ctx.session.execute(
            select(models.Event.id)
            .where(models.Event.world_day == ctx.world_day, models.Event.scope == int(scope))
            .where(models.Event.type == EventType.HISTORICAL_EVENT.value)
            .where(models.Event.origin_path == HexAddr.parse(container))
            .limit(1)
        )
        return found.scalar_one_or_none() is not None

    async def _emit(
        self, ctx: TickContext, container: str, scope: Scope, total: int, cause: models.Event
    ) -> None:
        severity = Severity.MAJOR if scope < Scope.UNIVERSE else Severity.HISTORIC
        ctx.session.add(
            models.Event(
                id=uuid4(),
                world_day=ctx.world_day,
                occurred_at=ctx.clock.now(),
                type=EventType.HISTORICAL_EVENT.value,
                origin_path=HexAddr.parse(container),
                scope=int(scope),
                visibility=Visibility.PUBLIC.value,
                clearance=0,
                severity=int(severity),
                participants=[],
                ruleset_version=ctx.rules.version,
                causation_id=cause.id,
                payload={
                    "weight": total,
                    "from_scope": int(cause.scope),
                    "caused_by": str(cause.id),
                    "sample_type": cause.type,
                },
            )
        )


def _container(origin: HexAddr, scope: Scope) -> str:
    depth = DEPTH[scope]
    steps = origin.steps[:depth] if depth < len(origin.steps) else origin.steps
    return HexAddr(steps).ltree()
