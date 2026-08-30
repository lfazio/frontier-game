"""Stage 2 — queued player encounters, resolved from both sides' standing orders. SDD §6.3.

This is the same resolver the live NPC path uses. An offline defender is never subject to
different physics than a present one (GDD §3.5, criterion A6).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import func, select, update

from frontier.adapters.db import models
from frontier.domain.encounter.resolution import Combatant, Outcome, resolve
from frontier.domain.events.model import EventDraft, Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.domain.fleet.standing_orders import Posture, StandingOrders
from frontier.simulation.stages.base import TickContext


class ResolveEncounters:
    name = "resolve_encounters"
    role: str | None = None
    order = 20

    async def run(self, ctx: TickContext) -> dict[str, int]:
        queued = (
            (
                await ctx.session.execute(
                    select(models.EncounterQueue)
                    .where(models.EncounterQueue.resolved.is_(False))
                    .order_by(models.EncounterQueue.id)
                )
            )
            .scalars()
            .all()
        )

        destroyed = 0
        for row in queued:
            attacker = await self._combatant(ctx, row.attacker_id, aggressive=True)
            defender = await self._combatant(ctx, row.defender_id, aggressive=False)
            if attacker is None or defender is None:
                await self._close(ctx, row.id)
                continue

            seed = f"{row.id}"
            result = resolve(attacker, defender, ctx.rules.combat, ctx.rng_for("encounter", seed), seed)
            for side in (attacker, defender):
                await ctx.session.execute(
                    update(models.Ship)
                    .where(models.Ship.id == side.ship_id)
                    .values(
                        hull=side.hull,
                        shields=side.shields,
                        destroyed_on=ctx.world_day if side.destroyed else None,
                    )
                )
            destroyed += sum(1 for side in (attacker, defender) if side.destroyed)
            ctx.emit(
                EventDraft(
                    type=EventType.COMBAT_RESOLVED,
                    origin=row.at_path,
                    scope=Scope.LOCAL,
                    visibility=Visibility.PUBLIC,
                    severity=Severity.NOTABLE,
                    payload={"outcome": result.outcome.value, "rounds": result.rounds, "seed": result.seed},
                )
            )
            for side in (attacker, defender):
                if side.destroyed:
                    ctx.emit(
                        EventDraft(
                            type=EventType.SHIP_DESTROYED,
                            origin=row.at_path,
                            scope=Scope.SYSTEM,
                            visibility=Visibility.PUBLIC,
                            severity=Severity.MAJOR,
                            payload={"ship_id": str(side.ship_id)},
                        )
                    )
            if result.outcome in (Outcome.ATTACKER_WON, Outcome.DEFENDER_WON):
                await self._respawn(ctx, attacker if attacker.destroyed else defender)
            await self._close(ctx, row.id)

        return {"encounters": len(queued), "ships_destroyed": destroyed}

    async def _combatant(self, ctx: TickContext, ship_id: UUID, aggressive: bool) -> Combatant | None:
        ship = (
            await ctx.session.execute(
                select(models.Ship).where(models.Ship.id == ship_id, models.Ship.destroyed_on.is_(None))
            )
        ).scalar_one_or_none()
        if ship is None:
            return None
        orders = StandingOrders(posture=Posture.AGGRESSIVE, retreat_at_hull_pct=0)
        if not aggressive and ship.player_id is not None:
            row = (
                await ctx.session.execute(
                    select(models.StandingOrders).where(models.StandingOrders.player_id == ship.player_id)
                )
            ).scalar_one_or_none()
            if row is not None:
                orders = StandingOrders(
                    posture=Posture(row.posture),
                    engage_hostile=row.engage_hostile,
                    engage_above_cargo=row.engage_above_cargo,
                    retreat_at_hull_pct=row.retreat_at_hull_pct,
                    auto_reply=row.auto_reply,
                )
        return Combatant(
            ship_id=ship.id,
            hull=ship.hull,
            hull_max=ship.hull_max,
            shields=ship.shields,
            sensor_range=ship.sensor_range,
            orders=orders,
        )

    async def _respawn(self, ctx: TickContext, loser: Combatant) -> None:
        """The pilot survives: their capsule is recovered, and they are taxed for the salvage.

        A fraction rather than a flat fee, so the loss scales with what a player has and can
        never leave a poor pilot unable to fly again (design answer S1).
        """
        ship = (
            await ctx.session.execute(select(models.Ship).where(models.Ship.id == loser.ship_id))
        ).scalar_one()
        if ship.player_id is None:
            return
        if await self._lost_for_good(ctx, ship):
            return await self._new_pilot(ctx, ship)
        home = (
            await ctx.session.execute(
                select(models.Location)
                .where(models.Location.attrs.has_key("spawn"))
                .order_by(models.Location.path)
                .limit(1)
            )
        ).scalar_one()
        await ctx.session.execute(
            update(models.Ship)
            .where(models.Ship.id == ship.id)
            .values(
                hull=ship.hull_max,
                shields=ship.shields_max,
                destroyed_on=None,
                position_path=home.path,
                system_id=home.parent_id,
                docked_at=None,
            )
        )
        # One statement, clamped: subtracting first would trip the credits_non_negative CHECK
        # for a player poorer than the penalty.
        await ctx.session.execute(
            update(models.Player)
            .where(models.Player.id == ship.player_id)
            .values(
                credits=func.greatest(
                    0,
                    models.Player.credits
                    - func.floor(models.Player.credits * ctx.rules.combat.rescue_tax_fraction),
                )
            )
        )

    async def _lost_for_good(self, ctx: TickContext, ship: models.Ship) -> bool:
        """Recovery is unreliable during an incursion, and an agent is not recovered — GDD §9.14.

        Read as two ordinary facts: the pilot held a clearance, and something of the Harrowing
        was in the same place. Nothing here consults the hidden faction's own records.
        """
        cleared = (
            await ctx.session.execute(
                select(models.Player.clearance).where(models.Player.id == ship.player_id)
            )
        ).scalar_one_or_none()
        if not cleared:
            return False
        present = (
            await ctx.session.execute(
                select(func.count())
                .select_from(models.NpcAgent)
                .join(models.Ship, models.Ship.id == models.NpcAgent.ship_id)
                .where(
                    models.NpcAgent.archetype == "incursion",
                    models.Ship.system_id == ship.system_id,
                    models.Ship.destroyed_on.is_(None),
                )
            )
        ).scalar_one()
        return bool(present)

    async def _new_pilot(self, ctx: TickContext, ship: models.Ship) -> None:
        """A new pilot, not a mended one.

        The old row stays exactly as it was — dead, with whatever it held — and a fresh pilot
        takes the account on. **No column links the two** (ARCH §18): re-recruitment reads the
        new pilot's own record, so the link is not merely forbidden but unnecessary.
        """
        old = (
            await ctx.session.execute(select(models.Player).where(models.Player.id == ship.player_id))
        ).scalar_one()
        home = (
            await ctx.session.execute(
                select(models.Location)
                .where(models.Location.attrs.has_key("spawn"))
                .order_by(models.Location.path)
                .limit(1)
            )
        ).scalar_one()

        new_id = uuid4()
        ctx.session.add(
            models.Player(
                id=new_id,
                account_id=old.account_id,
                callsign=f"{old.callsign}-{old.generation + 1}",
                credits=old.credits,
                ap_balance=0,
                last_grant_day=-1,
                generation=old.generation + 1,
                clearance=0,
            )
        )
        await ctx.session.flush()
        # The hull goes with the account, not with the pilot who died in it.
        await ctx.session.execute(
            update(models.Ship)
            .where(models.Ship.id == ship.id)
            .values(
                player_id=new_id,
                hull=ship.hull_max,
                shields=ship.shields_max,
                destroyed_on=None,
                position_path=home.path,
                system_id=home.parent_id,
                docked_at=None,
            )
        )
        ctx.session.add(models.StandingOrders(player_id=new_id))

    async def _close(self, ctx: TickContext, encounter_id: UUID) -> None:
        await ctx.session.execute(
            update(models.EncounterQueue)
            .where(models.EncounterQueue.id == encounter_id)
            .values(resolved=True)
        )
