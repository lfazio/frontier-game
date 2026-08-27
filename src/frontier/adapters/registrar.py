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
from frontier.adapters.memory.store import Account, MemoryPlayer, World
from frontier.domain.fleet.ship import Ship
from frontier.worldgen.fixture import STARTING_SHIP, starting_position


class Taken(Exception):
    def __init__(self, field: str) -> None:
        self.field = field


class Registrar(Protocol):
    async def register(self, email: str, password: str, callsign: str) -> UUID: ...
    async def authenticate(self, email: str, password: str) -> UUID | None: ...


class MemoryRegistrar:
    def __init__(self, world: World, daily_grant: int) -> None:
        self._w = world
        self._grant = daily_grant

    async def register(self, email: str, password: str, callsign: str) -> UUID:
        if any(a.email == email for a in self._w.accounts.values()):
            raise Taken("email")
        if any(p.callsign == callsign for p in self._w.players.values()):
            raise Taken("callsign")
        player = MemoryPlayer(id=uuid4(), callsign=callsign, ap_balance=self._grant)
        self._w.players[player.id] = player
        self._w.accounts[player.id] = Account(
            id=uuid4(), email=email, password_hash=hash_password(password), player_id=player.id
        )
        ship = Ship(id=uuid4(), player_id=player.id, position=starting_position(), **STARTING_SHIP)
        self._w.ships[ship.id] = ship
        return player.id

    async def authenticate(self, email: str, password: str) -> UUID | None:
        account = next((a for a in self._w.accounts.values() if a.email == email), None)
        if account is None or not verify_password(account.password_hash, password):
            return None
        return account.player_id


class SqlRegistrar:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], daily_grant: int) -> None:
        self._sessions = sessions
        self._grant = daily_grant

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
                **STARTING_SHIP,
            )
            session.add_all([account, player, ship])
            return player.id

    async def authenticate(self, email: str, password: str) -> UUID | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(models.Account, models.Player)
                    .join(models.Player, models.Player.account_id == models.Account.id)
                    .where(models.Account.email == email)
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
