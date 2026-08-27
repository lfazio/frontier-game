from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from frontier.adapters.db.event_sink import SqlEventSink
from frontier.adapters.db.repositories import (
    CommandLog,
    LocationRepo,
    PlayerRepo,
    ShipRepo,
    WorldStateRepo,
)
from frontier.adapters.db.state_store import SqlStateStore


class SqlUnitOfWork:
    """One transaction per command. Everything inside it commits together — SDD §5.2."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> SqlUnitOfWork:
        self.session = self._sessions()
        await self.session.begin()
        self.players = PlayerRepo(self.session)
        self.ships = ShipRepo(self.session)
        self.locations = LocationRepo(self.session)
        self.commands = CommandLog(self.session)
        self.events = SqlEventSink(self.session)
        self.world = WorldStateRepo(self.session)
        self.state = SqlStateStore(self.session)
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        assert self.session is not None
        if exc_type is not None:
            await self.session.rollback()
        await self.session.close()
        self.session = None

    async def commit(self) -> None:
        assert self.session is not None
        await self.session.commit()
