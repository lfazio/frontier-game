"""SQLAlchemy repositories. Each implements a port; none is imported by the application."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from frontier.adapters.db import models
from frontier.adapters.db.state_store import to_domain
from frontier.domain.fleet.ship import Ship
from frontier.domain.hex.coordinates import HexAddr


class PlayerRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_for_update(self, player_id: UUID) -> models.Player:
        """`FOR UPDATE` is what linearises one player's commands — SDD §5.2."""
        result = await self._s.execute(
            select(models.Player).where(models.Player.id == player_id).with_for_update()
        )
        return result.scalar_one()

    async def debit_ap(
        self, player_id: UUID, amount: int, command_id: UUID, reason: str, world_day: int
    ) -> None:
        if amount:
            self._s.add(
                models.ApLedger(
                    player_id=player_id,
                    world_day=world_day,
                    delta=-amount,
                    reason=reason,
                    command_id=command_id,
                )
            )
        await self._s.execute(
            update(models.Player)
            .where(models.Player.id == player_id)
            .values(ap_balance=models.Player.ap_balance - amount)
        )


class ShipRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self._systems: dict[UUID, UUID] = {}

    async def of_player(self, player_id: UUID) -> Ship:
        row = (
            await self._s.execute(
                select(models.Ship).where(
                    models.Ship.player_id == player_id, models.Ship.destroyed_on.is_(None)
                )
            )
        ).scalar_one()
        self._systems[row.id] = row.system_id
        # One mapper for one table. Listing the columns again here is how this repository came
        # to silently drop shields and jump range, leaving `/v1/me` reporting the defaults.
        ship = to_domain(row)
        ship.in_transit = await self._in_transit(row.id)
        return ship

    async def _in_transit(self, ship_id: UUID) -> bool:
        """A jump in flight is an unsettled journey; nothing on the ship row records it."""
        return (
            await self._s.execute(
                select(models.Journey.id)
                .where(models.Journey.ship_id == ship_id, models.Journey.settled.is_(False))
                .limit(1)
            )
        ).scalar_one_or_none() is not None

    async def save(self, ship: Ship) -> None:
        await self._s.execute(
            update(models.Ship)
            .where(models.Ship.id == ship.id)
            .values(
                position_path=ship.position,
                fuel=ship.fuel,
                hull=ship.hull,
                docked_at=ship.docked_at,
                destroyed_on=ship.destroyed_on,
            )
        )


class LocationRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def exists(self, addr: HexAddr) -> bool:
        found = await self._s.execute(select(models.Location.id).where(models.Location.path == addr).limit(1))
        return found.scalar_one_or_none() is not None

    async def within(self, prefix: HexAddr) -> list[models.Location]:
        """Containment is a prefix test, and `<@` is its index — SDD §4.2."""
        rows = await self._s.execute(
            select(models.Location)
            .where(text("path <@ CAST(:prefix AS ltree)").bindparams(prefix=prefix.ltree()))
            .order_by(models.Location.path)
        )
        return list(rows.scalars())


class CommandLog:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def find(self, player_id: UUID, idempotency_key: UUID) -> dict[str, object] | None:
        row = (
            await self._s.execute(
                select(models.Command).where(
                    models.Command.player_id == player_id,
                    models.Command.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        return None if row is None else {"status": row.status, "outcome": row.outcome}

    async def record(
        self,
        player_id: UUID,
        key: UUID,
        action: str,
        status: str,
        outcome: dict[str, object],
        world_day: int,
        ruleset_version: str,
    ) -> None:
        from uuid import uuid4

        self._s.add(
            models.Command(
                id=uuid4(),
                player_id=player_id,
                idempotency_key=key,
                action=action,
                request={},
                outcome=outcome,
                status=status,
                ruleset_version=ruleset_version,
                world_day=world_day,
            )
        )


class WorldStateRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _row(self) -> models.WorldState:
        return (await self._s.execute(select(models.WorldState))).scalar_one()

    async def phase(self) -> str:
        return (await self._row()).phase

    async def world_day(self) -> int:
        return (await self._row()).world_day

    async def set_phase(self, phase: str) -> None:
        await self._s.execute(update(models.WorldState).values(phase=phase))

    async def advance(self) -> int:
        row = await self._row()
        await self._s.execute(update(models.WorldState).values(world_day=row.world_day + 1))
        return row.world_day + 1
