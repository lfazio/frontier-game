"""SQLAlchemy repositories. Each implements a port; none is imported by the application."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from frontier.adapters.db import models
from frontier.domain.events.model import Event
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
        )

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


class LoggingEventSink:
    """P1 holds events in memory and logs them; `evt.events` arrives with the spine in P2."""

    def __init__(self) -> None:
        self.collected: list[Event] = []

    async def append(self, events: list[Event]) -> None:
        self.collected.extend(events)
