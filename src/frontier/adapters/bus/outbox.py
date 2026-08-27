"""The transactional outbox relay — ARCH ADR-11.

Events are published only after their transaction commits, so a client can never be told about
something that was rolled back. Delivery is at-least-once; clients de-duplicate on event id.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from frontier.adapters.bus.redis_bus import RedisBus
from frontier.adapters.db import models

log = logging.getLogger(__name__)

BATCH = 200
POLL_SECONDS = 0.2


class OutboxRelay:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], bus: RedisBus) -> None:
        self._sessions = sessions
        self._bus = bus

    async def drain_once(self) -> int:
        """`FOR UPDATE SKIP LOCKED` is what makes more than one relay safe."""
        async with self._sessions() as session, session.begin():
            queued = (
                (
                    await session.execute(
                        select(models.EventOutbox)
                        .order_by(models.EventOutbox.queued_at)
                        .limit(BATCH)
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            if not queued:
                return 0

            ids = [row.event_id for row in queued]
            events = (
                (await session.execute(select(models.Event).where(models.Event.id.in_(ids)))).scalars().all()
            )
            await self._bus.publish([_wire(e) for e in events])
            await session.execute(delete(models.EventOutbox).where(models.EventOutbox.event_id.in_(ids)))
        return len(queued)

    async def run_forever(self) -> None:
        while True:
            if not await self.drain_once():
                await asyncio.sleep(POLL_SECONDS)

    async def depth(self) -> int:
        async with self._sessions() as session:
            found = await session.execute(select(func.count()).select_from(models.EventOutbox))
            return int(found.scalar_one())


def _wire(event: models.Event) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "world_day": event.world_day,
        "occurred_at": event.occurred_at.isoformat(),
        "type": event.type,
        "origin": str(event.origin_path),
        "scope": event.scope,
        "visibility": event.visibility,
        "severity": event.severity,
        "participants": [str(p) for p in event.participants],
        "payload": event.payload,
        "ruleset_version": event.ruleset_version,
    }
