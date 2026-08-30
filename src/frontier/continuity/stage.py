"""Tick stage 8 — the Continuity leans on the world. GDD §9, ARCH ADR-13.

Nothing imports this module. It is loaded by dotted path from configuration (see
`frontier.simulation.extensions`), so no other file, stack trace or import graph mentions the
Continuity at all — which is most of what keeps §9.4 true.

It runs as `cont_role`, whose grants are its capability list: read the world, write its own
records, adjust population flows. It holds no write privilege on players, ships, credits or
cargo, so §9.13 — push, nudge, delay, accelerate, hide, reveal, but never force — is a thing the
database refuses rather than a thing this code remembers.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text

from frontier.simulation.stages.base import TickContext

LEVERS = ("trade_flow", "patrol_strength", "raider_pressure")
KINDS = ("nudge", "delay", "accelerate", "hide", "reveal")
# What a pilot must have learned before they are worth speaking to. Eligibility is read from
# their own record and nothing else (GDD Q10).
RECRUITMENT_KNOWLEDGE = 3


class ContinuityInterventions:
    name = "continuity"
    role = "cont_role"
    order = 8

    async def run(self, ctx: TickContext) -> dict[str, int]:
        if not ctx.features.continuity:
            return {"disabled": 1}

        systems = int(
            (
                await ctx.session.execute(text("SELECT count(*) FROM core.locations WHERE kind = 'system'"))
            ).scalar_one()
        )
        rules = ctx.rules.continuity
        allowed = rules.interventions_for(systems)

        await self._open_budget(ctx, allowed)
        recruited = await self._recruit(ctx, rules.agents_for(systems))
        drifting = await self._where_it_hurts(ctx)

        used = 0
        for region_id, deviation in drifting[:allowed]:
            if deviation < rules.deviation_floor:
                break
            await self._lean(ctx, region_id, deviation)
            used += 1

        await ctx.session.execute(
            text("UPDATE cont.budget SET used = :used WHERE world_day = :day").bindparams(
                used=used, day=ctx.world_day
            )
        )
        approached = await self._approach(ctx)
        return {
            "allowed": allowed,
            "used": used,
            "agents_recruited": recruited,
            "approached": approached,
        }

    async def _approach(self, ctx: TickContext) -> int:
        """Put an offer on one pilot's board, and on nobody else's — PSDD Q-F.

        The capability is `INSERT` on missions and nothing more: the faction may put work in
        front of someone, and may not edit it, withdraw it, or touch the pilot. A pilot who
        never looks, or who looks and passes, leaves no trace behind — the offer simply expires
        with every other unclaimed one.
        """
        candidate = (
            await ctx.session.execute(
                text(
                    "SELECT p.id FROM core.players p "
                    "WHERE p.clearance = 0 AND p.knowledge >= :threshold "
                    "  AND NOT EXISTS (SELECT 1 FROM core.missions m WHERE m.offered_to = p.id) "
                    "ORDER BY p.id LIMIT 1"
                ).bindparams(threshold=RECRUITMENT_KNOWLEDGE)
            )
        ).scalar_one_or_none()
        if candidate is None:
            return 0

        # An ordinary-looking courier run, offered by an ordinary-looking faction. What makes it
        # a recruitment is a term the board never serialises.
        system_id = (
            await ctx.session.execute(
                text("SELECT id FROM core.locations WHERE kind = 'system' ORDER BY path LIMIT 1")
            )
        ).scalar_one()
        rng = ctx.rng_for("continuity-approach", str(candidate), ctx.world_day)
        await ctx.session.execute(
            text(
                "INSERT INTO core.missions "
                "(id, faction_id, kind, system_id, brief, terms, reward_credits, "
                " reward_reputation, offered_to, offered_on, expires_on) "
                "VALUES (:id, :faction, 'courier', :system, :brief, CAST(:terms AS jsonb), "
                "        :reward, 1, :player, :day, :expires)"
            ).bindparams(
                id=uuid4(),
                faction=ctx.rules.continuity.agent_cover_factions[
                    rng.randrange(len(ctx.rules.continuity.agent_cover_factions))
                ],
                system=system_id,
                brief="Carry a sealed package. Discretion is the fee.",
                terms='{"clearance": 1}',
                reward=1200 + rng.randrange(600),
                player=candidate,
                day=ctx.world_day,
                expires=ctx.world_day + 6,
            )
        )
        return 1

    async def _open_budget(self, ctx: TickContext, allowed: int) -> None:
        await ctx.session.execute(
            text(
                "INSERT INTO cont.budget (world_day, allowed, used) VALUES (:day, :allowed, 0) "
                "ON CONFLICT (world_day) DO UPDATE SET allowed = :allowed, used = 0"
            ).bindparams(day=ctx.world_day, allowed=allowed)
        )

    async def _where_it_hurts(self, ctx: TickContext) -> list[tuple[UUID, float]]:
        """The Model's own deviation, read as an aggregate like anyone else reads it."""
        rows = (
            await ctx.session.execute(
                text(
                    "SELECT region_id, max(deviation) AS drift FROM psycho.forecasts "
                    "WHERE world_day = (SELECT max(world_day) FROM psycho.forecasts) "
                    "GROUP BY region_id ORDER BY drift DESC, region_id"
                )
            )
        ).all()
        return [(row.region_id, float(row.drift)) for row in rows]

    async def _recruit(self, ctx: TickContext, ceiling: int) -> int:
        """Agents are NPC crews given a second identity — the organisation runs itself (Q5)."""
        held = int((await ctx.session.execute(text("SELECT count(*) FROM cont.agents"))).scalar_one())
        if held >= ceiling:
            return 0

        candidates = (
            await ctx.session.execute(
                text(
                    "SELECT n.ship_id, l.parent_id AS region_id FROM core.npc_agents n "
                    "JOIN core.locations l ON l.id = n.system_id "
                    "WHERE n.ship_id NOT IN (SELECT ship_id FROM cont.agents) "
                    "ORDER BY n.ship_id LIMIT :want"
                ).bindparams(want=ceiling - held)
            )
        ).all()

        recruited = 0
        for row in candidates:
            cell_id = await self._cell_for(ctx, row.region_id)
            rng = ctx.rng_for("continuity-agent", str(row.ship_id))
            covers = ctx.rules.continuity.agent_cover_factions
            await ctx.session.execute(
                text(
                    "INSERT INTO cont.agents "
                    "(ship_id, cell_id, node, clearance, cover_faction_id, recruited_on) "
                    "VALUES (:ship, :cell, :node, 1, :cover, :day) ON CONFLICT DO NOTHING"
                ).bindparams(
                    ship=row.ship_id,
                    cell=cell_id,
                    node=f"NODE-{rng.randrange(10, 99)}",
                    cover=covers[rng.randrange(len(covers))],
                    day=ctx.world_day,
                )
            )
            recruited += 1
        return recruited

    async def _cell_for(self, ctx: TickContext, region_id: UUID) -> UUID:
        """One cell per region, and an agent knows only its own — GDD §9.6."""
        found = (
            await ctx.session.execute(
                text("SELECT id FROM cont.cells WHERE region_id = :region").bindparams(region=region_id)
            )
        ).scalar_one_or_none()
        if found is not None:
            return UUID(str(found))

        cell_id = uuid4()
        rng = ctx.rng_for("continuity-cell", str(region_id))
        await ctx.session.execute(
            text(
                "INSERT INTO cont.cells (id, designation, region_id, clearance, founded_on) "
                "VALUES (:id, :designation, :region, :clearance, :day)"
            ).bindparams(
                id=cell_id,
                designation=f"CELL-{rng.randrange(100, 999)}",
                region=region_id,
                clearance=1 + rng.randrange(3),
                day=ctx.world_day,
            )
        )
        return cell_id

    async def _lean(self, ctx: TickContext, region_id: UUID, deviation: float) -> None:
        """A hand on the scales, never on the outcome.

        The magnitude is capped and the lever is a population flow, so the most this can do is
        make something more or less likely for a lot of people at once.
        """
        rng = ctx.rng_for("continuity-lean", str(region_id), ctx.world_day)
        lever = LEVERS[rng.randrange(len(LEVERS))]
        kind = KINDS[rng.randrange(len(KINDS))]
        cap = ctx.rules.continuity.max_magnitude
        magnitude = min(cap, deviation) * (1 if rng.random() < 0.5 else -1)

        await ctx.session.execute(
            text(
                f"UPDATE core.system_activity SET {lever} = "
                f"GREATEST(0, LEAST(1, {lever} + :delta)) "
                "WHERE system_id IN (SELECT id FROM core.locations WHERE parent_id = :region)"
            ).bindparams(delta=Decimal(f"{magnitude:.4f}"), region=region_id)
        )

        cell_id = await self._cell_for(ctx, region_id)
        await ctx.session.execute(
            text(
                "INSERT INTO cont.interventions "
                "(id, world_day, cell_id, region_id, kind, magnitude, rationale) "
                "VALUES (:id, :day, :cell, :region, :kind, :magnitude, CAST(:rationale AS jsonb))"
            ).bindparams(
                id=uuid4(),
                day=ctx.world_day,
                cell=cell_id,
                region=region_id,
                kind=kind,
                magnitude=Decimal(f"{abs(magnitude):.4f}"),
                rationale=f'{{"lever": "{lever}", "deviation": {deviation:.4f}}}',
            )
        )


def stage() -> ContinuityInterventions:
    """Entry point the loader calls by name; keeps the class out of every import graph."""
    return ContinuityInterventions()
