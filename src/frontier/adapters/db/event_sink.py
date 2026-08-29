"""Writes the event log, its narrow-audience deliveries and the outbox — all in the caller's
transaction, so an event a client hears about can never have been rolled back (ARCH ADR-11).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from frontier.adapters.db import models
from frontier.application.visibility import resolve_audience
from frontier.domain.events.model import Event, Visibility


class SqlEventSink:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def append(self, events: list[Event]) -> None:
        if not events:
            return
        team_of = await self._teams({p for e in events for p in e.participants})
        for event in events:
            self._s.add(
                models.Event(
                    id=event.id,
                    world_day=event.world_day,
                    occurred_at=event.occurred_at,
                    type=event.type.value,
                    origin_path=event.origin,
                    scope=int(event.scope),
                    visibility=event.visibility.value,
                    clearance=event.clearance,
                    severity=int(event.severity),
                    participants=sorted(event.participants),
                    payload=event.payload,
                    ruleset_version=event.ruleset_version,
                    causation_id=event.causation_id,
                )
            )
            for recipient in await self._recipients(event, team_of):
                self._s.add(
                    models.EventDelivery(recipient_id=recipient, event_id=event.id, world_day=event.world_day)
                )
            self._s.add(models.EventOutbox(event_id=event.id, world_day=event.world_day))

    async def _recipients(self, event: Event, team_of: dict[UUID, UUID]) -> set[UUID]:
        audience = resolve_audience(event, team_of)
        if not audience.is_narrow:
            return set()
        recipients = set(audience.players)
        if audience.team_id is not None:
            rows = await self._s.execute(
                select(models.Player.id).where(models.Player.team_id == audience.team_id)
            )
            recipients |= set(rows.scalars())
        if audience.clearance is not None:
            rows = await self._s.execute(
                select(models.Player.id).where(models.Player.clearance >= audience.clearance)
            )
            recipients |= set(rows.scalars())
        return recipients

    async def _teams(self, player_ids: set[UUID]) -> dict[UUID, UUID]:
        if not player_ids:
            return {}
        rows = await self._s.execute(
            select(models.Player.id, models.Player.team_id).where(
                models.Player.id.in_(player_ids), models.Player.team_id.is_not(None)
            )
        )
        return {pid: team for pid, team in rows if team is not None}


def is_narrow(visibility: Visibility) -> bool:
    return visibility in (Visibility.PARTICIPANTS, Visibility.TEAM, Visibility.CLEARANCE)
