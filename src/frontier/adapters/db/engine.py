from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def make_engine(url: str, role: str | None = None) -> AsyncEngine:
    """An engine may pin every connection to a database role.

    The public surface runs as `api_role`, which holds no privilege on the Continuity's schema.
    A serialisation mistake therefore cannot leak what the connection is unable to read at all
    (ARCH ADR-13).
    """
    engine = create_async_engine(url, pool_pre_ping=True)
    if role:
        _pin_role(engine, role)
    return engine


def _pin_role(engine: AsyncEngine, role: str) -> None:
    """Re-assume the role at the start of every transaction.

    Setting it once per connection is not enough: `SET ROLE` issued inside a transaction is
    undone when that transaction rolls back, so a pooled connection quietly reverts to the
    owning user after the first failure. `SET LOCAL ROLE` on each `begin` is re-applied every
    time and cannot outlive its transaction. The anti-leak suite asserts the effective role on
    every probe, because this is precisely the guarantee that can fail silently.
    """

    @event.listens_for(engine.sync_engine, "begin")
    def _assume_role(connection: Any) -> None:
        connection.exec_driver_sql(f"SET LOCAL ROLE {role}")


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
