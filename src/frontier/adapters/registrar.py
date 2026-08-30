"""Account provisioning: create an account, a player and their one ship.

An adapter concern until it has rules worth testing — it is hashing, identity and a starting
position, none of which the domain decides.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from frontier.adapters.api.security import hash_password, verify_password
from frontier.adapters.db import models

STARTING_SHIP = {
    "hull": 100,
    "hull_max": 100,
    "shields": 40,
    "shields_max": 40,
    "fuel": 60,
    "fuel_max": 60,
    "cargo_max": 20,
    "sensor_range": 3,
}


class Taken(Exception):
    def __init__(self, field: str) -> None:
        self.field = field


class Registrar(Protocol):
    async def register(self, email: str, password: str, callsign: str) -> UUID: ...
    async def authenticate(self, email: str, password: str) -> UUID | None: ...


class SqlRegistrar:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], daily_grant: int, jump_range_ly: int
    ) -> None:
        self._sessions = sessions
        self._grant = daily_grant
        self._jump_range_ly = jump_range_ly

    async def register(self, email: str, password: str, callsign: str) -> UUID:
        async with self._sessions() as session, session.begin():
            if await self._exists(session, models.Account.email, email):
                raise Taken("email")
            if await self._exists(session, models.Player.callsign, callsign):
                raise Taken("callsign")

            spawn = await self._spawn(session)
            account = models.Account(id=uuid4(), email=email, password_hash=hash_password(password))
            player = models.Player(
                id=uuid4(),
                account_id=account.id,
                callsign=callsign,
                credits=5000,
                ap_balance=self._grant,
                last_grant_day=-1,
            )
            ship = models.Ship(
                id=uuid4(),
                player_id=player.id,
                system_id=spawn.parent_id,
                position_path=spawn.path,
                jump_range_ly=self._jump_range_ly,
                **STARTING_SHIP,
            )
            session.add_all(
                [
                    account,
                    player,
                    ship,
                    models.StandingOrders(player_id=player.id),
                ]
            )
            await session.flush()
            await self._reveal_home(session, player.id, spawn)
            return player.id

    async def authenticate(self, email: str, password: str) -> UUID | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(models.Account, models.Player)
                    .join(models.Player, models.Player.account_id == models.Account.id)
                    .where(models.Account.email == email)
                    # An account may have flown more than one pilot. The living one is the
                    # latest generation; the others are history and cannot be signed in as.
                    .order_by(models.Player.generation.desc())
                )
            ).first()
        if row is None or not verify_password(row[0].password_hash, password):
            return None
        player_id: UUID = row[1].id
        return player_id

    async def _exists(self, session: AsyncSession, column: object, value: str) -> bool:
        found = await session.execute(select(func.count()).where(column == value))  # type: ignore[arg-type]
        return bool(found.scalar_one())

    async def _spawn(self, session: AsyncSession) -> models.Location:
        """Players start at a faction home station, chosen deterministically by address."""
        row = (
            await session.execute(
                select(models.Location).where(text("attrs ? 'spawn'")).order_by(models.Location.path).limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise RuntimeError("no spawn point: run `make world` first")
        return row

    async def _reveal_home(self, session: AsyncSession, player_id: UUID, spawn: models.Location) -> None:
        """The star chart is public; what is inside a system is not.

        A new player knows every galaxy, region and system — that is the map anyone can buy —
        plus everything inside their own home system. Planets, stations and wrecks elsewhere are
        found by scanning (GDD §5.2).
        """
        home_system = spawn.path.parent()
        assert home_system is not None
        await session.execute(
            text(
                "INSERT INTO core.player_discoveries (player_id, location_id, seen_on) "
                "SELECT :player, id, 0 FROM core.locations "
                "WHERE kind IN ('galaxy', 'region', 'system') "
                "   OR (path <@ CAST(:system AS ltree) AND kind <> 'void') "
                "ON CONFLICT DO NOTHING"
            ).bindparams(player=player_id, system=home_system.ltree())
        )
