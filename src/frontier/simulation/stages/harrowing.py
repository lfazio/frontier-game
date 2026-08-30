"""Stage 85 — a crisis left alone long enough brings something with it. GDD §8.12, PSDD §5.

The Harrowing needs no new mechanism. An incursion ship is a ship: it has hulls, it holds a
position, it spends Action Points, and it is resolved by the encounter code every other fight
uses. What is new is this stage, which watches crises expire, and a fourth archetype.

They arrive in the empty space between systems — an address that exists only because a region is
filled space (D-68). From there they close on the nearest system, which is what gives a region
warning that something is coming.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select

from frontier.adapters.db import models
from frontier.domain.events.model import EventDraft, Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.simulation.stages.base import TickContext

ARCHETYPE = "incursion"


class Harrowing:
    name = "harrowing"
    role: str | None = None
    order = 85

    async def run(self, ctx: TickContext) -> dict[str, int]:
        if not ctx.features.psychohistory:
            # No model, no crises, so nothing can expire unanswered.
            return {"disabled": 1}

        expired = (
            (
                await ctx.session.execute(
                    select(models.Crisis).where(
                        models.Crisis.resolved_on.is_(None),
                        models.Crisis.answered_on.is_(None),
                        models.Crisis.expires_on <= ctx.world_day,
                    )
                )
            )
            .scalars()
            .all()
        )

        # The slot is unique per berth, and a berth may already hold hulls from an earlier
        # crisis. Counting up from the highest in use cannot collide with anything, here or in
        # any wave before it.
        next_slot = 1 + int(
            (
                await ctx.session.execute(
                    select(func.coalesce(func.max(models.NpcAgent.slot), -1)).where(
                        models.NpcAgent.archetype == ARCHETYPE
                    )
                )
            ).scalar_one()
        )

        raised = hulls = 0
        for crisis in sorted(expired, key=lambda row: (row.region_id.hex, row.variable)):
            arrived = await self._incursion(ctx, crisis, next_slot)
            next_slot += arrived
            crisis.answered_on = ctx.world_day
            if arrived:
                raised += 1
                hulls += arrived
        return {"incursions": raised, "hulls": hulls}

    async def _incursion(self, ctx: TickContext, crisis: models.Crisis, first_slot: int) -> int:
        """Every expired crisis brings one; severity decides how many hulls (Q-B)."""
        empty = (
            (
                await ctx.session.execute(
                    select(models.Location)
                    .where(
                        models.Location.parent_id == crisis.region_id,
                        models.Location.kind == "void",
                    )
                    .order_by(models.Location.path)
                )
            )
            .scalars()
            .all()
        )
        if not empty:
            return 0

        rules = ctx.rules.npc
        rng = ctx.rng_for("harrowing", crisis.region_id.hex, ctx.world_day)
        wanted = rules.hulls_for(crisis.severity)
        for offset in range(wanted):
            berth = empty[rng.randrange(len(empty))]
            index = first_slot + offset
            ship_id = uuid4()
            ctx.session.add(
                models.Ship(
                    id=ship_id,
                    player_id=None,
                    hull=rules.incursion_hull,
                    hull_max=rules.incursion_hull,
                    shields=rules.incursion_shields,
                    shields_max=rules.incursion_shields,
                    fuel=999,
                    fuel_max=999,
                    cargo_max=0,
                    sensor_range=rules.incursion_sensor_range,
                    jump_range_ly=ctx.rules.world.jump_range_default_ly,
                    # Deep space is its own place: the ship's "system" is the empty hex itself.
                    system_id=berth.id,
                    position_path=berth.path,
                )
            )
            await ctx.session.flush()
            ctx.session.add(
                models.NpcAgent(
                    ship_id=ship_id,
                    system_id=berth.id,
                    archetype=ARCHETYPE,
                    slot=index,
                    faction_id=None,
                    route={"region": str(crisis.region_id), "crisis": str(crisis.id)},
                    materialised_on=ctx.world_day,
                    last_seen_on=ctx.world_day,
                    ap_balance=rules.incursion_ap,
                    last_grant_day=ctx.world_day,
                )
            )

        # The region hears it. Nobody has to be watching for the world to change.
        ctx.emit(
            EventDraft(
                type=EventType.HISTORICAL_EVENT,
                origin=empty[0].path,
                scope=Scope.REGION,
                visibility=Visibility.PUBLIC,
                severity=Severity.HISTORIC,
                payload={"weight": int(crisis.severity), "caused_by": str(crisis.id)},
            )
        )
        return wanted


def stage() -> Harrowing:
    return Harrowing()
