"""Stage 6 — missions are generated from the state of the world, not from a script. GDD §5.5.

The same situation produces different work for different factions: a Republic relay in a system
is an opportunity for the Republic, a problem for the Empire and a target for the Pirates.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete, func, select

from frontier.adapters.db import models
from frontier.simulation.stages.base import TickContext

LIFETIME = 6
OFFERS_PER_FACTION = 4

TEMPLATES = {
    "patrol": ("Patrol {place} and drive off raiders.", 900, 2),
    "supply": ("Deliver goods to {place}: its stocks are short.", 700, 1),
    "raid": ("Raid the trade running through {place}.", 1100, 2),
    "survey": ("Survey {place} and report what is there.", 500, 1),
}
BY_FACTION = {1: ("patrol", "supply"), 2: ("supply", "survey"), 3: ("raid", "survey")}


class MissionLifecycle:
    name = "missions"
    role: str | None = None
    order = 6

    async def run(self, ctx: TickContext) -> dict[str, int]:
        expired = await self._expire(ctx)
        created = await self._offer(ctx)
        return {"missions_offered": created, "missions_expired": expired}

    async def _expire(self, ctx: TickContext) -> int:
        stale = (
            (
                await ctx.session.execute(
                    select(models.Mission.id).where(models.Mission.expires_on < ctx.world_day)
                )
            )
            .scalars()
            .all()
        )
        if not stale:
            return 0
        await ctx.session.execute(
            delete(models.MissionAssignment).where(
                models.MissionAssignment.mission_id.in_(stale), models.MissionAssignment.status == "active"
            )
        )
        await ctx.session.execute(delete(models.Mission).where(models.Mission.id.in_(stale)))
        return len(stale)

    async def _offer(self, ctx: TickContext) -> int:
        pressure = await self._pressure(ctx)
        created = 0
        for faction_id, kinds in BY_FACTION.items():
            open_offers = (
                await ctx.session.execute(
                    select(func.count())
                    .select_from(models.Mission)
                    .where(models.Mission.faction_id == faction_id)
                )
            ).scalar_one()
            for index in range(max(0, OFFERS_PER_FACTION - open_offers)):
                if not pressure:
                    break
                rng = ctx.rng_for("missions", faction_id, ctx.world_day, index)
                system_id, name, score = pressure[rng.randrange(len(pressure))]
                kind = kinds[rng.randrange(len(kinds))]
                brief, credits, reputation = TEMPLATES[kind]
                ctx.session.add(
                    models.Mission(
                        id=uuid4(),
                        faction_id=faction_id,
                        kind=kind,
                        system_id=system_id,
                        brief=brief.format(place=name),
                        terms={"score": round(score, 3)},
                        reward_credits=round(credits * (1 + score)),
                        reward_reputation=reputation,
                        offered_on=ctx.world_day,
                        expires_on=ctx.world_day + LIFETIME,
                    )
                )
                created += 1
        return created

    async def _pressure(self, ctx: TickContext) -> list[tuple[object, str, float]]:
        """Where the world is under strain is where the factions want something done."""
        rows = (
            await ctx.session.execute(
                select(models.Location.id, models.Location.name, models.SystemActivity)
                .join(models.SystemActivity, models.SystemActivity.system_id == models.Location.id)
                .order_by(models.Location.path)
            )
        ).all()
        scored = [
            (
                system_id,
                name or "an unnamed system",
                float(activity.raider_pressure) + float(activity.trade_flow),
            )
            for system_id, name, activity in rows
        ]
        scored.sort(key=lambda row: (-row[2], str(row[0])))
        return scored[:12]
