"""Loads exactly what a command declared it needs, and saves what it changed — SDD §5.3.

Keeping the fetch set declarative means the I/O for every command lives in one reviewable place
rather than spreading through handlers.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from frontier.adapters.db import models
from frontier.application.commands.base import (
    Contact,
    MarketLine,
    MissionRef,
    NearbyLocation,
    State,
    StateSpec,
    Station,
    TeamRef,
)
from frontier.domain.fleet.cargo import Cargo
from frontier.domain.fleet.ship import Ship
from frontier.domain.fleet.standing_orders import Posture, StandingOrders
from frontier.domain.hex.coordinates import HexAddr


class SqlStateStore:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._ship_row: models.Ship | None = None

    async def load(self, spec: StateSpec, player_id: UUID) -> State:
        player = (
            await self._s.execute(
                select(models.Player).where(models.Player.id == player_id).with_for_update()
            )
        ).scalar_one()

        state = State(player=player)
        if spec.ship:
            state.ship, state.cargo = await self._ship(player_id)
        if spec.station and state.ship is not None:
            state.station = await self._station(state.ship)
        if spec.market and state.ship is not None and state.ship.docked_at is not None:
            state.market = await self._market(state.ship.docked_at)
        if spec.contacts and state.ship is not None:
            state.contacts = await self._contacts(state.ship)
        if spec.nearby and state.ship is not None:
            state.nearby, state.known_ids = await self._nearby(player_id, state.ship)
        if spec.known_systems:
            state.known_systems = await self._known_systems(player_id)
        if spec.incursion and state.ship is not None:
            state.incursion_nearby = await self._incursion_near(state.ship.position)
        if spec.orders:
            state.orders = await self._orders(player_id)
        if spec.mission and spec.mission_id is not None:
            state.mission = await self._mission_ref(spec.mission_id, player_id)
        if spec.team and spec.team_id is not None:
            state.team = await self._team_ref(spec.team_id)
        if spec.resolve:
            known = {
                str(addr)
                for addr in spec.resolve
                if (
                    await self._s.execute(
                        select(models.Location.id).where(models.Location.path == addr).limit(1)
                    )
                ).scalar_one_or_none()
                is not None
            }
            state.known_addresses = frozenset(known)
        return state

    async def save(self, state: State) -> None:
        if self._ship_row is not None and state.ship is not None:
            row, ship = self._ship_row, state.ship
            row.position_path, row.fuel, row.hull = ship.position, ship.fuel, ship.hull
            row.shields, row.docked_at = ship.shields, ship.docked_at
            row.destroyed_on = ship.destroyed_on
            await self._save_cargo(ship.id, state.cargo)
        if state.departure is not None and state.ship is not None:
            await self._depart(state)
        if state.discovered:
            await self._discover(state)
        if state.engaged is not None and state.ship is not None:
            await self._engage(state)
        if state.orders_changed:
            await self._save_orders(state)
        if state.combat_result is not None:
            ship_id, hull, shields = state.combat_result
            await self._s.execute(
                update(models.Ship)
                .where(models.Ship.id == ship_id)
                .values(hull=hull, shields=shields, destroyed_on=await self._day() if hull <= 0 else None)
            )
        if state.mission_change is not None:
            await self._apply_mission_change(state)
        if state.defection is not None:
            await self._defect(state)
        if state.player.allegiance == "incursion" and state.player.first_sided_on is None:
            state.player.first_sided_on = await self._day()
        if state.standing_collapse is not None:
            for faction_id in (1, 2, 3):
                await self._adjust_reputation(state.player.id, faction_id, -state.standing_collapse)
        if state.reputation_change is not None:
            faction_id, delta = state.reputation_change
            if faction_id:
                await self._adjust_reputation(state.player.id, faction_id, delta)
        if state.team_change is not None:
            await self._apply_team_change(state)
        if state.market is not None:
            for line in state.market.values():
                await self._s.execute(
                    text(
                        "UPDATE core.markets SET stock = :stock "
                        "WHERE station_id = :station AND commodity = :commodity"
                    ).bindparams(
                        stock=line.stock,
                        station=state.ship.docked_at,  # type: ignore[union-attr]
                        commodity=line.commodity,
                    )
                )

    async def _nearby(self, player_id: UUID, ship: Ship) -> tuple[list[NearbyLocation], frozenset[UUID]]:
        system = ship.position.parent() or ship.position
        rows = (
            (
                await self._s.execute(
                    select(models.Location)
                    .where(text("path <@ CAST(:prefix AS ltree)").bindparams(prefix=system.ltree()))
                    .where(models.Location.level == int(ship.position.level))
                )
            )
            .scalars()
            .all()
        )
        known = (
            (
                await self._s.execute(
                    select(models.PlayerDiscovery.location_id).where(
                        models.PlayerDiscovery.player_id == player_id
                    )
                )
            )
            .scalars()
            .all()
        )
        return (
            [NearbyLocation(r.id, r.path, r.kind, r.name, r.discovered_on) for r in rows],
            frozenset(known),
        )

    async def _known_systems(self, player_id: UUID) -> frozenset[str]:
        rows = (
            (
                await self._s.execute(
                    select(models.Location.path)
                    .join(models.PlayerDiscovery, models.PlayerDiscovery.location_id == models.Location.id)
                    .where(models.PlayerDiscovery.player_id == player_id, models.Location.kind == "system")
                )
            )
            .scalars()
            .all()
        )
        return frozenset(str(p) for p in rows)

    async def _incursion_near(self, position: HexAddr) -> bool:
        """Is the Harrowing in this pilot's region? Siding is a decision about *this* emergency."""
        region = position.parent()
        region = region.parent() if region is not None else None
        if region is None:
            return False
        found = (
            await self._s.execute(
                text(
                    "SELECT 1 FROM core.npc_agents n "
                    "JOIN core.ships s ON s.id = n.ship_id "
                    "JOIN core.locations berth ON berth.id = s.system_id "
                    "WHERE n.archetype = 'incursion' AND s.destroyed_on IS NULL "
                    "  AND berth.path <@ CAST(:region AS ltree) LIMIT 1"
                ).bindparams(region=region.ltree())
            )
        ).scalar_one_or_none()
        return found is not None

    async def _orders(self, player_id: UUID) -> StandingOrders:
        row = (
            await self._s.execute(
                select(models.StandingOrders).where(models.StandingOrders.player_id == player_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return StandingOrders.default()
        return StandingOrders(
            posture=Posture(row.posture),
            engage_hostile=row.engage_hostile,
            engage_above_cargo=row.engage_above_cargo,
            retreat_at_hull_pct=row.retreat_at_hull_pct,
            auto_reply=row.auto_reply,
        )

    async def _ship(self, player_id: UUID) -> tuple[Ship, Cargo]:
        row = (
            await self._s.execute(
                select(models.Ship).where(
                    models.Ship.player_id == player_id, models.Ship.destroyed_on.is_(None)
                )
            )
        ).scalar_one()
        self._ship_row = row
        lines = (
            (await self._s.execute(select(models.Cargo).where(models.Cargo.ship_id == row.id)))
            .scalars()
            .all()
        )
        cargo = Cargo(
            lines={line.commodity: line.qty for line in lines},
            cost_basis={line.commodity: line.avg_unit_cost for line in lines},
        )
        return to_domain(row), cargo

    async def _station(self, ship: Ship) -> Station | None:
        row = (
            await self._s.execute(
                select(models.Location).where(
                    models.Location.path == ship.position, models.Location.kind == "station"
                )
            )
        ).scalar_one_or_none()
        return None if row is None else Station(id=row.id, path=row.path, name=row.name)

    async def _market(self, station_id: UUID) -> dict[str, MarketLine]:
        rows = (
            (await self._s.execute(select(models.Market).where(models.Market.station_id == station_id)))
            .scalars()
            .all()
        )
        return {r.commodity: MarketLine(r.commodity, r.stock, r.target_stock, r.base_price) for r in rows}

    async def _contacts(self, ship: Ship) -> list[Contact]:
        """Narrow by system in SQL, filter by hex distance in Python — D-3."""
        system = ship.position.parent() or ship.position
        rows = (
            (
                await self._s.execute(
                    select(models.Ship)
                    .where(text("position_path <@ CAST(:prefix AS ltree)").bindparams(prefix=system.ltree()))
                    .where(models.Ship.destroyed_on.is_(None), models.Ship.id != ship.id)
                )
            )
            .scalars()
            .all()
        )
        return [
            Contact(
                ship_id=r.id,
                player_id=r.player_id,
                position=r.position_path,
                hull=r.hull,
                hull_max=r.hull_max,
                shields=r.shields,
                sensor_range=r.sensor_range,
                docked=r.docked_at is not None,
            )
            for r in rows
        ]

    async def _save_cargo(self, ship_id: UUID, cargo: Cargo) -> None:
        await self._s.execute(text("DELETE FROM core.cargo WHERE ship_id = :ship").bindparams(ship=ship_id))
        for commodity, qty in cargo.lines.items():
            self._s.add(
                models.Cargo(
                    ship_id=ship_id,
                    commodity=commodity,
                    qty=qty,
                    avg_unit_cost=cargo.cost_basis.get(commodity, 0),
                )
            )

    async def _day(self) -> int:
        return int((await self._s.execute(select(models.WorldState.world_day))).scalar_one())

    async def _depart(self, state: State) -> None:
        assert state.ship is not None and state.departure is not None
        target, cycles = state.departure
        day = await self._day()
        landing = (
            await self._s.execute(
                select(models.Location)
                .where(text("path <@ CAST(:prefix AS ltree)").bindparams(prefix=target.ltree()))
                .where(models.Location.kind == "station")
                .order_by(models.Location.path)
                .limit(1)
            )
        ).scalar_one_or_none()
        if landing is None:
            landing = (
                await self._s.execute(select(models.Location).where(models.Location.path == target))
            ).scalar_one()
        self._s.add(
            models.Journey(
                id=uuid4(),
                ship_id=state.ship.id,
                from_path=state.ship.position,
                to_path=landing.path,
                to_system_id=landing.parent_id or landing.id,
                departed_on=day,
                arrives_on=day + cycles,
            )
        )

    async def _discover(self, state: State) -> None:
        day = await self._day()
        # Exploration is one of the ways Knowledge is earned — GDD §8.9.
        await self._s.execute(
            update(models.Player)
            .where(models.Player.id == state.player.id)
            .values(knowledge=models.Player.knowledge + len(state.discovered))
        )
        for location_id in state.discovered:
            await self._s.execute(
                text(
                    "INSERT INTO core.player_discoveries (player_id, location_id, seen_on) "
                    "VALUES (:player, :location, :day) ON CONFLICT DO NOTHING"
                ).bindparams(player=state.player.id, location=location_id, day=day)
            )
            await self._s.execute(
                update(models.Location)
                .where(models.Location.id == location_id, models.Location.discovered_on.is_(None))
                .values(discovered_on=day, discovered_by=state.player.id)
            )

    async def _engage(self, state: State) -> None:
        assert state.ship is not None and state.engaged is not None
        await self._s.execute(
            text(
                "INSERT INTO core.encounter_queue "
                "(id, world_day, attacker_id, defender_id, at_path, intent) "
                "VALUES (:id, :day, :attacker, :defender, CAST(:path AS ltree), 'attack') "
                "ON CONFLICT DO NOTHING"
            ).bindparams(
                id=uuid4(),
                day=await self._day(),
                attacker=state.ship.id,
                defender=state.engaged,
                path=state.ship.position.ltree(),
            )
        )

    async def _save_orders(self, state: State) -> None:
        orders = state.orders
        await self._s.execute(
            text(
                "INSERT INTO core.standing_orders "
                "(player_id, posture, engage_hostile, engage_above_cargo, retreat_at_hull_pct, auto_reply) "
                "VALUES (:player, :posture, :hostile, :above, :retreat, :reply) "
                "ON CONFLICT (player_id) DO UPDATE SET posture = :posture, engage_hostile = :hostile, "
                "engage_above_cargo = :above, retreat_at_hull_pct = :retreat, auto_reply = :reply"
            ).bindparams(
                player=state.player.id,
                posture=orders.posture.value,
                hostile=orders.engage_hostile,
                above=orders.engage_above_cargo,
                retreat=orders.retreat_at_hull_pct,
                reply=orders.auto_reply,
            )
        )

    async def _team_ref(self, team_id: UUID) -> TeamRef | None:
        row = (
            await self._s.execute(select(models.Team).where(models.Team.id == team_id))
        ).scalar_one_or_none()
        return None if row is None else TeamRef(row.id, row.name, row.faction_id)

    async def _apply_team_change(self, state: State) -> None:
        assert state.team_change is not None
        kind, name, faction_id = state.team_change
        if kind == "create":
            team = models.Team(id=uuid4(), name=name, faction_id=faction_id, founded_on=await self._day())
            self._s.add(team)
            await self._s.flush()
            target: UUID | None = team.id
        elif kind == "join":
            target = state.team.id if state.team else None
        else:
            target = None

        previous = state.player.team_id
        await self._s.execute(
            update(models.Player)
            .where(models.Player.id == state.player.id)
            .values(team_id=target, faction_id=faction_id if target else None)
        )
        if previous is not None and target is None:
            await self._delete_if_empty(previous)

    async def _delete_if_empty(self, team_id: UUID) -> None:
        remaining = (
            await self._s.execute(select(models.Player.id).where(models.Player.team_id == team_id).limit(1))
        ).scalar_one_or_none()
        if remaining is None:
            await self._s.execute(text("DELETE FROM core.teams WHERE id = :id").bindparams(id=team_id))

    async def _mission_ref(self, mission_id: UUID, player_id: UUID) -> MissionRef | None:
        row = (
            await self._s.execute(select(models.Mission).where(models.Mission.id == mission_id))
        ).scalar_one_or_none()
        if row is None:
            return None
        assignments = (
            (
                await self._s.execute(
                    select(models.MissionAssignment).where(
                        models.MissionAssignment.mission_id == mission_id,
                        models.MissionAssignment.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        system_path = (
            await self._s.execute(select(models.Location.path).where(models.Location.id == row.system_id))
        ).scalar_one()
        return MissionRef(
            id=row.id,
            kind=row.kind,
            faction_id=row.faction_id,
            system_path=str(system_path),
            reward_credits=row.reward_credits,
            reward_reputation=row.reward_reputation,
            assigned=bool(assignments),
            mine=any(a.player_id == player_id for a in assignments),
            grants_clearance=int(row.terms.get("clearance", 0)),
        )

    async def _apply_mission_change(self, state: State) -> None:
        assert state.mission_change is not None and state.mission is not None
        kind, mission_id = state.mission_change
        day = await self._day()
        if kind == "accept":
            self._s.add(
                models.MissionAssignment(mission_id=mission_id, player_id=state.player.id, accepted_on=day)
            )
            return

        await self._s.execute(
            update(models.MissionAssignment)
            .where(
                models.MissionAssignment.mission_id == mission_id,
                models.MissionAssignment.player_id == state.player.id,
            )
            .values(status="complete", closed_on=day)
        )
        await self._s.execute(
            update(models.Player)
            .where(models.Player.id == state.player.id)
            .values(credits=state.player.credits)
        )
        await self._adjust_reputation(
            state.player.id, state.mission.faction_id, state.mission.reward_reputation
        )

    async def _defect(self, state: State) -> None:
        assert state.defection is not None and state.player.team_id is not None
        day = await self._day()
        await self._s.execute(
            update(models.Team)
            .where(models.Team.id == state.player.team_id)
            .values(faction_id=state.defection, defected_on=day)
        )
        await self._s.execute(
            update(models.Player)
            .where(models.Player.team_id == state.player.team_id)
            .values(faction_id=state.defection)
        )

    async def _adjust_reputation(self, player_id: UUID, faction_id: int, delta: int) -> None:
        """Reputation is earned by action and clamped, so it can never run away — GDD §6.7."""
        await self._s.execute(
            text(
                "INSERT INTO core.reputation (player_id, faction_id, score) "
                "VALUES (:player, :faction, GREATEST(-100, LEAST(100, :delta))) "
                "ON CONFLICT (player_id, faction_id) DO UPDATE "
                "SET score = GREATEST(-100, LEAST(100, core.reputation.score + :delta))"
            ).bindparams(player=player_id, faction=faction_id, delta=delta)
        )


def to_domain(row: models.Ship) -> Ship:
    return Ship(
        id=row.id,
        player_id=row.player_id,
        position=row.position_path,
        hull=row.hull,
        hull_max=row.hull_max,
        fuel=row.fuel,
        fuel_max=row.fuel_max,
        cargo_max=row.cargo_max,
        sensor_range=row.sensor_range,
        docked_at=row.docked_at,
        destroyed_on=row.destroyed_on,
        shields=row.shields,
        shields_max=row.shields_max,
        jump_range_ly=row.jump_range_ly,
    )
