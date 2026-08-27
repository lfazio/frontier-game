"""Stage 4 — the NPC population, at two fidelities. GDD §2.7, SDD §6.5, ADR-15.

4a runs over every system in the galaxy: aggregate flows, evolving whether or not anyone is
looking, and moving real goods where no hauler was materialised. 4b runs only over systems a
player can currently see, and turns those flows into individual ships.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select, update

from frontier.adapters.db import models
from frontier.simulation.stages.base import TickContext

ARCHETYPES = ("hauler", "patrol", "raider")
NPC_SHIP = {
    "hauler": {
        "hull": 80,
        "hull_max": 80,
        "shields": 20,
        "shields_max": 20,
        "fuel": 100,
        "fuel_max": 100,
        "cargo_max": 40,
        "sensor_range": 2,
    },
    "patrol": {
        "hull": 140,
        "hull_max": 140,
        "shields": 60,
        "shields_max": 60,
        "fuel": 100,
        "fuel_max": 100,
        "cargo_max": 5,
        "sensor_range": 4,
    },
    "raider": {
        "hull": 90,
        "hull_max": 90,
        "shields": 30,
        "shields_max": 30,
        "fuel": 100,
        "fuel_max": 100,
        "cargo_max": 20,
        "sensor_range": 3,
    },
}


class NpcPopulation:
    """ARCH stage 4, NPC half. Faction strategic AI is deferred and nothing here assumes it."""

    name = "npc_population"

    async def run(self, ctx: TickContext) -> dict[str, int]:
        flows = await self._aggregate(ctx)
        moved = await self._move_unobserved_goods(ctx, flows)
        observed = await self._observed_systems(ctx)
        created = await self._materialise(ctx, flows, observed)
        acted = await self._act(ctx)
        return {
            "systems": len(flows),
            "goods_moved": moved,
            "observed": len(observed),
            "npcs_created": created,
            "npcs_acted": acted,
        }

    async def _aggregate(self, ctx: TickContext) -> dict[UUID, models.SystemActivity]:
        """Predator and prey: rich trade with thin patrols is what raises raider pressure."""
        npc = ctx.rules.npc
        rows = {
            row.system_id: row
            for row in (
                await ctx.session.execute(
                    select(models.SystemActivity).order_by(models.SystemActivity.system_id)
                )
            ).scalars()
        }
        control = await self._control(ctx)
        gradients = await self._price_gradients(ctx)

        for system_id, row in rows.items():
            trade_target = _clamp(
                npc.k_trade * gradients.get(system_id, 0.0) * (1 - float(row.raider_pressure))
            )
            patrol_target = control.get(system_id, 0.0)
            raider_target = _clamp(npc.k_raider * float(row.trade_flow) * (1 - float(row.patrol_strength)))

            row.trade_flow = _blend(row.trade_flow, trade_target, npc.trade_relax)
            row.patrol_strength = _blend(
                row.patrol_strength, patrol_target, npc.patrol_relax, float(row.patrol_losses)
            )
            row.raider_pressure = _blend(
                row.raider_pressure, raider_target, npc.raider_relax, float(row.raider_losses)
            )
            # Unobserved attrition: patrols and raiders wear each other down.
            attrition = float(row.patrol_strength) * float(row.raider_pressure) * 0.1
            row.patrol_losses = Decimal(f"{attrition:.4f}")
            row.raider_losses = Decimal(f"{attrition:.4f}")
            row.last_simulated_on = ctx.world_day
        return rows

    async def _control(self, ctx: TickContext) -> dict[UUID, float]:
        rows = (await ctx.session.execute(select(models.Territory))).scalars().all()
        best: dict[UUID, float] = defaultdict(float)
        for row in rows:
            best[row.system_id] = max(best[row.system_id], float(row.influence))
        return best

    async def _price_gradients(self, ctx: TickContext) -> dict[UUID, float]:
        """A system's trade pull is how far its stocks sit from their targets."""
        rows = (
            await ctx.session.execute(
                select(models.Location.parent_id, models.Market.stock, models.Market.target_stock).join(
                    models.Market, models.Market.station_id == models.Location.id
                )
            )
        ).all()
        totals: dict[UUID, list[float]] = defaultdict(list)
        for system_id, stock, target in rows:
            totals[system_id].append(abs(stock - target) / max(1, target))
        return {k: min(1.0, sum(v) / len(v)) for k, v in totals.items() if v}

    async def _move_unobserved_goods(self, ctx: TickContext, flows: dict[UUID, models.SystemActivity]) -> int:
        """Trade happens where nobody is watching — GDD §2.7, criterion A13."""
        moved = 0
        for system_id, row in flows.items():
            volume = round(float(row.trade_flow) * ctx.rules.npc.haul_capacity)
            if volume <= 0:
                continue
            lines = (
                (
                    await ctx.session.execute(
                        select(models.Market)
                        .join(models.Location, models.Location.id == models.Market.station_id)
                        .where(models.Location.parent_id == system_id)
                        .order_by(models.Market.station_id, models.Market.commodity)
                    )
                )
                .scalars()
                .all()
            )
            for line in lines:
                if line.stock > line.target_stock:
                    line.stock = max(line.target_stock, line.stock - volume)
                    moved += volume
                elif line.stock < line.target_stock:
                    line.stock = min(line.target_stock, line.stock + volume)
                    moved += volume
        return moved

    async def _observed_systems(self, ctx: TickContext) -> set[UUID]:
        rows = (
            (
                await ctx.session.execute(
                    select(models.Ship.system_id)
                    .where(models.Ship.player_id.is_not(None), models.Ship.destroyed_on.is_(None))
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        return set(rows)

    async def _materialise(
        self, ctx: TickContext, flows: dict[UUID, models.SystemActivity], observed: set[UUID]
    ) -> int:
        """Materialisation is one-way: once a system has been seen, its crews stay and the
        server keeps playing them (design answer S5). `last_seen_on` records the last visit
        but no longer decides anyone's fate.
        """
        npc = ctx.rules.npc
        created = 0
        existing = defaultdict(set)
        for agent in (await ctx.session.execute(select(models.NpcAgent))).scalars():
            existing[agent.system_id].add((agent.archetype, agent.slot))

        for system_id in sorted(observed, key=str):
            row = flows.get(system_id)
            if row is None:
                continue
            wanted = {
                "hauler": round(float(row.trade_flow) * npc.per_flow_unit["hauler"]),
                "patrol": round(float(row.patrol_strength) * npc.per_flow_unit["patrol"]),
                "raider": round(float(row.raider_pressure) * npc.per_flow_unit["raider"]),
            }
            for archetype, count in wanted.items():
                for slot in range(count):
                    if (archetype, slot) in existing[system_id]:
                        continue
                    await self._spawn(ctx, system_id, archetype, slot)
                    created += 1
            await ctx.session.execute(
                update(models.NpcAgent)
                .where(models.NpcAgent.system_id == system_id)
                .values(last_seen_on=ctx.world_day)
            )

        return created

    async def _act(self, ctx: TickContext) -> int:
        """Every materialised NPC acts, watched or not, through the same market players use.

        The server plays them wherever they are (S5), so a system a player visited once keeps
        a working crew rather than reverting to arithmetic the moment they leave.
        """
        agents = (
            await ctx.session.execute(
                select(models.NpcAgent, models.Ship)
                .join(models.Ship, models.Ship.id == models.NpcAgent.ship_id)
                .order_by(models.NpcAgent.ship_id)
            )
        ).all()

        acted = 0
        for agent, ship in agents:
            budget = ctx.rules.npc.actions_per_cycle.get(agent.archetype, 0)
            if not budget:
                continue
            if agent.archetype == "hauler":
                acted += await self._haul(ctx, ship, budget)
            else:
                acted += await self._drift(ctx, agent, ship)
        return acted

    async def _haul(self, ctx: TickContext, ship: models.Ship, budget: int) -> int:
        """Buy where a station is long, sell where it is short: prices visibly move."""
        lines = (
            (
                await ctx.session.execute(
                    select(models.Market)
                    .join(models.Location, models.Location.id == models.Market.station_id)
                    .where(models.Location.parent_id == ship.system_id)
                    .order_by(models.Market.station_id, models.Market.commodity)
                )
            )
            .scalars()
            .all()
        )
        if len(lines) < 2:
            return 0

        surplus = max(lines, key=lambda m: m.stock - m.target_stock)
        if surplus.stock <= surplus.target_stock:
            return 0
        destination = next(
            (
                m
                for m in lines
                if m.commodity == surplus.commodity
                and m.station_id != surplus.station_id
                and m.stock < m.target_stock
            ),
            None,
        )
        if destination is None:
            return 0

        volume = min(ship.cargo_max, surplus.stock - surplus.target_stock, budget * 5)
        if volume <= 0:
            return 0
        surplus.stock -= volume
        destination.stock += volume
        landing = (
            await ctx.session.execute(
                select(models.Location.path).where(models.Location.id == destination.station_id)
            )
        ).scalar_one()
        await ctx.session.execute(
            update(models.Ship).where(models.Ship.id == ship.id).values(position_path=landing)
        )
        return 1

    async def _drift(self, ctx: TickContext, agent: models.NpcAgent, ship: models.Ship) -> int:
        """Legible movement: patrols and raiders work a fixed system, not the whole galaxy."""
        rng = ctx.rng_for("npc-move", str(ship.id), ctx.world_day)
        neighbourhood = (
            (
                await ctx.session.execute(
                    select(models.Location)
                    .where(models.Location.parent_id == agent.system_id)
                    .order_by(models.Location.path)
                )
            )
            .scalars()
            .all()
        )
        if not neighbourhood:
            return 0
        target = neighbourhood[rng.randrange(len(neighbourhood))]
        await ctx.session.execute(
            update(models.Ship).where(models.Ship.id == ship.id).values(position_path=target.path)
        )
        return 1

    async def _spawn(self, ctx: TickContext, system_id: UUID, archetype: str, slot: int) -> None:
        """Identity is seeded from (system, archetype, slot), so the same slot is the same NPC."""
        rng = ctx.rng_for("npc", str(system_id), archetype, slot)
        hexes = (
            (
                await ctx.session.execute(
                    select(models.Location)
                    .where(models.Location.parent_id == system_id)
                    .order_by(models.Location.path)
                )
            )
            .scalars()
            .all()
        )
        if not hexes:
            return
        home = hexes[rng.randrange(len(hexes))]
        ship_id = uuid4()
        ctx.session.add(
            models.Ship(
                id=ship_id,
                player_id=None,
                system_id=system_id,
                position_path=home.path,
                **NPC_SHIP[archetype],
            )
        )
        # The agent row references the ship, and no relationship tells the unit of work that.
        await ctx.session.flush()
        ctx.session.add(
            models.NpcAgent(
                ship_id=ship_id,
                system_id=system_id,
                archetype=archetype,
                slot=slot,
                faction_id=1 if archetype == "patrol" else (3 if archetype == "raider" else None),
                route={"home": str(home.path)},
                materialised_on=ctx.world_day,
                last_seen_on=ctx.world_day,
            )
        )


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _blend(current: Decimal, target: float, rate: float, losses: float = 0.0) -> Decimal:
    value = _clamp(float(current) + (target - float(current)) * rate - losses)
    return Decimal(f"{value:.4f}")
