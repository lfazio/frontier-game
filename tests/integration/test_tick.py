"""The daily tick: exactly once, resumable, idempotent — SDD §6.1, tasks 1.6 and 1.7."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update

from frontier.adapters.clock import SeededRng, SystemClock
from frontier.adapters.db import models
from frontier.adapters.rules_loader import load_ruleset
from frontier.domain.hex.coordinates import HexAddr
from frontier.simulation.stages.grant_ap import GrantActionPoints
from frontier.simulation.stages.settle_travel import SettleTravel
from frontier.simulation.tick import TickRunner

pytestmark = pytest.mark.integration


def runner(sessions, settings) -> TickRunner:
    return TickRunner(
        sessions=sessions,
        rules=load_ruleset(settings.ruleset_root, settings.ruleset_version),
        clock=SystemClock(),
        rng_for=SeededRng(settings.world_seed).for_,
    )


async def make_player(sessions, ap: int = 0, last_grant_day: int = -1):
    async with sessions() as session, session.begin():
        spawn = (
            await session.execute(
                select(models.Location)
                .where(models.Location.attrs.has_key("spawn"))
                .order_by(models.Location.path)
                .limit(1)
            )
        ).scalar_one()
        account = models.Account(id=uuid4(), email=f"{uuid4().hex}@x.io", password_hash="x")
        player = models.Player(
            id=uuid4(),
            account_id=account.id,
            callsign=uuid4().hex[:12],
            ap_balance=ap,
            last_grant_day=last_grant_day,
        )
        ship = models.Ship(
            id=uuid4(),
            player_id=player.id,
            hull=100,
            hull_max=100,
            fuel=60,
            fuel_max=60,
            cargo_max=20,
            sensor_range=3,
            system_id=spawn.parent_id,
            position_path=spawn.path,
        )
        session.add_all([account, player, ship])
    return player.id, ship.id, spawn


async def test_a_tick_advances_the_world_day(sessions, clean):
    report = await runner(sessions, clean).run()
    async with sessions() as session:
        state = (await session.execute(select(models.WorldState))).scalar_one()
    assert report.world_day == 1
    assert state.world_day == 1
    assert state.phase == "open"


async def test_every_stage_is_checkpointed(sessions, clean):
    await runner(sessions, clean).run()
    async with sessions() as session:
        stages = (
            (await session.execute(select(models.TickStage.stage).order_by(models.TickStage.stage)))
            .scalars()
            .all()
        )
    assert stages == [
        "build_digests",
        "chronicle",
        "economy",
        "event_promotion",
        "grant_action_points",
        "missions",
        "npc_population",
        "resolve_encounters",
        "settle_travel",
        "territory",
    ]


async def test_a_completed_stage_is_skipped_on_a_resumed_run(sessions, clean):
    """The crash case: the day is open, some stages are done, the runner picks up where it stopped."""
    await runner(sessions, clean).run(stages=(SettleTravel(),))
    async with sessions() as session, session.begin():
        await session.execute(update(models.TickRun).values(finished_at=None))

    report = await runner(sessions, clean).run()

    assert report.resumed is True
    assert report.world_day == 1
    assert report.stages["settle_travel"]["skipped"] == 1
    assert "skipped" not in report.stages["grant_action_points"]


async def test_action_points_reset_with_half_of_what_is_left(sessions, clean):
    """Criterion A15 — GDD §3.2."""
    player_id, _, _ = await make_player(sessions, ap=7)

    await runner(sessions, clean).run()

    async with sessions() as session:
        player = (
            await session.execute(select(models.Player).where(models.Player.id == player_id))
        ).scalar_one()
        entries = (
            (await session.execute(select(models.ApLedger).where(models.ApLedger.player_id == player_id)))
            .scalars()
            .all()
        )

    assert player.ap_balance == 13  # daily_grant 10 + carry 3
    assert player.last_grant_day == 1
    assert [(e.delta, e.reason) for e in entries] == [(6, "daily_reset")]


async def test_the_carry_is_capped(sessions, clean):
    player_id, _, _ = await make_player(sessions, ap=40)
    await runner(sessions, clean).run()
    async with sessions() as session:
        player = (
            await session.execute(select(models.Player).where(models.Player.id == player_id))
        ).scalar_one()
    assert player.ap_balance == 15  # grant 10 + ceiling 5


async def test_re_running_a_stage_for_the_same_day_grants_nothing(sessions, clean):
    """`last_grant_day` is what makes a resumed tick safe — SDD §6.7."""
    player_id, _, _ = await make_player(sessions, ap=0)
    tick = runner(sessions, clean)
    await tick.run()

    async with sessions() as session, session.begin():
        await session.execute(delete(models.TickStage))
        await session.execute(update(models.TickRun).values(finished_at=None))

    report = await tick.run(stages=(GrantActionPoints(),))

    async with sessions() as session:
        rows = (
            await session.execute(
                select(func.count())
                .select_from(models.ApLedger)
                .where(models.ApLedger.player_id == player_id)
            )
        ).scalar_one()
    assert report.world_day == 1 and report.resumed is True
    assert rows == 1


async def test_a_two_cycle_journey_lands_on_the_second_tick(sessions, clean):
    """Criterion A4."""
    _, ship_id, spawn = await make_player(sessions)
    async with sessions() as session, session.begin():
        destination = (
            await session.execute(
                select(models.Location)
                .where(models.Location.kind == "station", models.Location.id != spawn.id)
                .order_by(models.Location.path)
                .limit(1)
            )
        ).scalar_one()
        session.add(
            models.Journey(
                id=uuid4(),
                ship_id=ship_id,
                from_path=spawn.path,
                to_path=destination.path,
                to_system_id=destination.parent_id,
                departed_on=0,
                arrives_on=2,
            )
        )

    tick = runner(sessions, clean)
    first = await tick.run()
    async with sessions() as session:
        mid = (await session.execute(select(models.Ship).where(models.Ship.id == ship_id))).scalar_one()
    assert first.stages["settle_travel"]["journeys_settled"] == 0
    assert mid.position_path == spawn.path

    second = await tick.run()
    async with sessions() as session:
        landed = (await session.execute(select(models.Ship).where(models.Ship.id == ship_id))).scalar_one()
        journey = (await session.execute(select(models.Journey))).scalar_one()

    assert second.world_day == 2
    assert second.stages["settle_travel"]["journeys_settled"] == 1
    assert landed.position_path == destination.path
    assert landed.system_id == destination.parent_id
    assert journey.settled is True


async def test_the_tick_builds_a_digest_for_every_player(sessions, clean):
    """Stage 12/13: the daily overview is ready before anyone logs in — GDD §3.4."""
    player_id, _, _ = await make_player(sessions)

    await runner(sessions, clean).run()

    async with sessions() as session:
        digest = (
            await session.execute(select(models.Digest).where(models.Digest.player_id == player_id))
        ).scalar_one()
    assert digest.world_day == 1
    assert digest.summary == {"events": {}, "total": 0}


async def test_a_digest_counts_what_reached_the_player(sessions, clean):
    player_id, _, _ = await make_player(sessions)
    async with sessions() as session, session.begin():
        event_id = uuid4()
        session.add(
            models.Event(
                id=event_id,
                world_day=1,
                occurred_at=datetime(2026, 8, 27, tzinfo=UTC),
                type="MESSAGE",
                origin_path=HexAddr.parse("ga0_0"),
                scope=0,
                visibility="participants",
                severity=0,
                participants=[player_id],
                payload={"text": "x", "channel": "team"},
                ruleset_version="test",
            )
        )
        session.add(models.EventDelivery(recipient_id=player_id, event_id=event_id, world_day=1))

    await runner(sessions, clean).run()

    async with sessions() as session:
        digest = (
            await session.execute(select(models.Digest).where(models.Digest.player_id == player_id))
        ).scalar_one()
    assert digest.summary == {"events": {"MESSAGE": 1}, "total": 1}
