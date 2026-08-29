"""The log, its deliveries and the outbox — SDD §4.2, tasks 2.1, 2.2, 2.4."""

from __future__ import annotations

import asyncio
from functools import partial
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from frontier.adapters.bus.outbox import OutboxRelay
from frontier.adapters.bus.redis_bus import RedisBus
from frontier.adapters.clock import SeededRng, SystemClock, UuidFactory
from frontier.adapters.db import models
from frontier.adapters.db.uow import SqlUnitOfWork
from frontier.adapters.registrar import SqlRegistrar
from frontier.adapters.rules_loader import load_ruleset
from frontier.application.commands.send_message import Channel, SendMessageCommand
from frontier.application.executor import Executor
from frontier.domain.events.model import Visibility

pytestmark = pytest.mark.integration


@pytest.fixture
def rules_(clean):
    return load_ruleset(clean.ruleset_root, clean.ruleset_version)


@pytest.fixture
def executor(sessions, clean, rules_):
    clock = SystemClock()
    return Executor(
        uow_factory=partial(SqlUnitOfWork, sessions),
        clock=clock,
        rng=SeededRng(clean.world_seed),
        ids=UuidFactory(clock),
        rules=rules_,
    )


@pytest.fixture
async def player(sessions, rules_):
    registrar = SqlRegistrar(sessions, rules_.ap.daily_grant, rules_.world.jump_range_default_ly)
    return await registrar.register(f"{uuid4().hex}@x.io", "correct horse battery", uuid4().hex[:12])


def say(channel=Channel.LOCAL, text_="Pirates in Sirius."):
    return SendMessageCommand(id=uuid4(), idempotency_key=uuid4(), channel=channel, text=text_)


async def test_twelve_partitions_are_pre_created(sessions):
    """A forgotten partition job must not be able to stop the tick — SDD §4.4."""
    async with sessions() as session:
        names = (
            (
                await session.execute(
                    text(
                        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'evt' AND c.relkind = 'r' AND c.relname LIKE 'events_d%' "
                        "ORDER BY c.relname"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(names) == 12
    assert names[0] == "events_d00000"


async def test_an_event_its_delivery_and_its_outbox_row_commit_together(executor, sessions, player):
    await executor.execute(say(), player)

    async with sessions() as session:
        events = (await session.execute(select(models.Event))).scalars().all()
        outbox = (await session.execute(select(models.EventOutbox))).scalars().all()

    assert len(events) == 1 and len(outbox) == 1
    assert events[0].type == "MESSAGE"
    assert outbox[0].event_id == events[0].id


async def test_a_public_event_writes_no_delivery_rows(executor, sessions, player):
    """Broad audiences fan out on read — ARCH §7.4."""
    await executor.execute(say(Channel.LOCAL), player)
    async with sessions() as session:
        deliveries = (
            await session.execute(select(func.count()).select_from(models.EventDelivery))
        ).scalar_one()
    assert deliveries == 0


async def test_a_team_event_fans_out_on_write(executor, sessions, player):
    async with sessions() as session, session.begin():
        team = models.Team(id=uuid4(), name=uuid4().hex[:12], faction_id=1, founded_on=0)
        session.add(team)
        row = (await session.execute(select(models.Player).where(models.Player.id == player))).scalar_one()
        row.team_id, row.faction_id = team.id, 1

    await executor.execute(say(Channel.TEAM), player)

    async with sessions() as session:
        deliveries = (await session.execute(select(models.EventDelivery))).scalars().all()
        event = (await session.execute(select(models.Event))).scalar_one()
    assert event.visibility == Visibility.TEAM.value
    assert [d.recipient_id for d in deliveries] == [player]


async def test_a_rejected_command_leaves_no_event(executor, sessions, player):
    result = await executor.execute(say(text_="   "), player)
    async with sessions() as session:
        events = (await session.execute(select(func.count()).select_from(models.Event))).scalar_one()
    assert result.status == "rejected"
    assert events == 0


async def test_the_relay_publishes_and_clears_the_outbox(executor, sessions, clean, player):
    """Task 2.4: an event reaches Redis, and only after its transaction committed."""
    await executor.execute(say(), player)
    bus = RedisBus(clean.redis_url)
    received: list[dict] = []
    ready = asyncio.Event()

    async def listen() -> None:
        async for message in bus.listen(ready):
            received.append(message)
            break

    listener = asyncio.create_task(listen())
    await asyncio.wait_for(ready.wait(), timeout=5)
    published = await OutboxRelay(sessions, bus).drain_once()
    await asyncio.wait_for(listener, timeout=5)
    await bus.close()

    async with sessions() as session:
        depth = (await session.execute(select(func.count()).select_from(models.EventOutbox))).scalar_one()

    assert published == 1
    assert depth == 0
    assert received[0]["type"] == "MESSAGE"
    assert received[0]["payload"]["text"] == "Pirates in Sirius."


async def test_draining_an_empty_outbox_is_free(sessions, clean):
    bus = RedisBus(clean.redis_url)
    assert await OutboxRelay(sessions, bus).drain_once() == 0
    await bus.close()
