"""The command path against the real database — criteria A2, A3, A7, A8."""

from __future__ import annotations

import asyncio
from functools import partial
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from frontier.adapters.clock import SeededRng, SystemClock, UuidFactory
from frontier.adapters.db import models
from frontier.adapters.db.uow import SqlUnitOfWork
from frontier.adapters.registrar import SqlRegistrar
from frontier.adapters.rules_loader import load_ruleset
from frontier.application.commands.move import MoveCommand
from frontier.application.executor import Executor
from frontier.domain.hex.geometry import neighbours

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
async def player(sessions, clean, rules_):
    registrar = SqlRegistrar(sessions, rules_.ap.daily_grant, rules_.world.jump_range_default_ly)
    return await registrar.register(f"{uuid4().hex}@x.io", "correct horse battery", uuid4().hex[:12])


async def position(sessions, player_id):
    async with sessions() as session:
        ship = (
            await session.execute(select(models.Ship).where(models.Ship.player_id == player_id))
        ).scalar_one()
        return ship.position_path, ship.fuel


def step(addr, index: int = 0):
    return addr.sibling(neighbours(addr.tip)[index])


async def test_a_move_is_persisted_with_its_costs(executor, sessions, player):
    where, fuel = await position(sessions, player)
    result = await executor.execute(MoveCommand(id=uuid4(), idempotency_key=uuid4(), to=step(where)), player)
    moved, fuel_after = await position(sessions, player)

    assert result.status == "accepted"
    assert moved == step(where)
    assert fuel_after == fuel - 1


async def test_ap_runs_out_after_ten_moves(executor, sessions, player):
    """Criterion A2."""
    where, _ = await position(sessions, player)
    for i in range(10):
        result = await executor.execute(
            MoveCommand(id=uuid4(), idempotency_key=uuid4(), to=step(where, i % 6)), player
        )
        assert result.status == "accepted"
        where, _ = await position(sessions, player)

    eleventh = await executor.execute(
        MoveCommand(id=uuid4(), idempotency_key=uuid4(), to=step(where)), player
    )

    assert eleventh.rejection.code.value == "INSUFFICIENT_AP"
    assert (await position(sessions, player))[0] == where


async def test_the_ledger_reconciles_with_the_balance(executor, sessions, player, rules_):
    """Criterion A3."""
    where, _ = await position(sessions, player)
    for i in range(3):
        await executor.execute(
            MoveCommand(id=uuid4(), idempotency_key=uuid4(), to=step(where, i % 6)), player
        )
        where, _ = await position(sessions, player)

    async with sessions() as session:
        balance = (
            await session.execute(select(models.Player.ap_balance).where(models.Player.id == player))
        ).scalar_one()
        spent = (
            await session.execute(
                select(func.coalesce(func.sum(models.ApLedger.delta), 0)).where(
                    models.ApLedger.player_id == player
                )
            )
        ).scalar_one()

    assert balance == 7
    assert rules_.ap.daily_grant + spent == balance


async def test_a_replayed_key_debits_once(executor, sessions, player):
    """Criterion A8."""
    where, _ = await position(sessions, player)
    key = uuid4()
    command = partial(MoveCommand, idempotency_key=key, to=step(where))

    first = await executor.execute(command(id=uuid4()), player)
    replay = await executor.execute(command(id=uuid4()), player)

    async with sessions() as session:
        rows = (
            await session.execute(
                select(func.count()).select_from(models.ApLedger).where(models.ApLedger.player_id == player)
            )
        ).scalar_one()

    assert first.status == "accepted" and replay.replayed is True
    assert rows == 1


async def test_two_concurrent_commands_spend_the_last_point_once(executor, sessions, player, rules_):
    """Criterion A7 — `SELECT ... FOR UPDATE` is what makes this true."""
    async with sessions() as session, session.begin():
        row = (await session.execute(select(models.Player).where(models.Player.id == player))).scalar_one()
        row.ap_balance = 1

    where, _ = await position(sessions, player)
    outcomes = await asyncio.gather(
        *(
            executor.execute(MoveCommand(id=uuid4(), idempotency_key=uuid4(), to=step(where, i)), player)
            for i in range(2)
        )
    )

    async with sessions() as session:
        balance = (
            await session.execute(select(models.Player.ap_balance).where(models.Player.id == player))
        ).scalar_one()
        debits = (await session.execute(select(func.count()).select_from(models.ApLedger))).scalar_one()

    assert sorted(o.status for o in outcomes) == ["accepted", "rejected"]
    assert balance == 0
    assert debits == 1
