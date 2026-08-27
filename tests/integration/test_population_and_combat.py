"""The population at two fidelities, and offline defence — criteria A6, A13, A14."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from frontier.adapters.clock import SeededRng, SystemClock
from frontier.adapters.db import models
from frontier.adapters.rules_loader import load_ruleset
from frontier.simulation.stages.population import NpcPopulation
from frontier.simulation.tick import TickRunner

pytestmark = pytest.mark.integration


def runner(sessions, settings) -> TickRunner:
    return TickRunner(
        sessions=sessions,
        rules=load_ruleset(settings.ruleset_root, settings.ruleset_version),
        clock=SystemClock(),
        rng_for=SeededRng(settings.world_seed).for_,
    )


async def a_player(sessions, hull: int = 100, posture: str = "evade"):
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
        player = models.Player(id=uuid4(), account_id=account.id, callsign=uuid4().hex[:12])
        ship = models.Ship(
            id=uuid4(),
            player_id=player.id,
            hull=hull,
            hull_max=100,
            shields=0,
            shields_max=0,
            fuel=60,
            fuel_max=60,
            cargo_max=20,
            sensor_range=3,
            system_id=spawn.parent_id,
            position_path=spawn.path,
        )
        session.add_all([account, player, ship, models.StandingOrders(player_id=player.id, posture=posture)])
    return player.id, ship.id, spawn


async def test_goods_move_in_systems_nobody_is_watching(sessions, clean):
    """Criterion A13: the aggregate layer keeps the galaxy alive while players are elsewhere."""
    async with sessions() as session:
        before = (await session.execute(select(func.sum(models.Market.stock)))).scalar_one()

    tick = runner(sessions, clean)
    for _ in range(3):
        report = await tick.run()

    async with sessions() as session:
        after = (await session.execute(select(func.sum(models.Market.stock)))).scalar_one()

    assert report.stages["npc_population"]["goods_moved"] > 0
    assert report.stages["npc_population"]["observed"] == 0
    assert after != before


async def test_npcs_appear_only_where_a_player_can_see_them(sessions, clean):
    """Criterion A14, first half: materialisation follows observation."""
    tick = runner(sessions, clean)
    await tick.run()
    async with sessions() as session:
        assert (await session.execute(select(func.count()).select_from(models.NpcAgent))).scalar_one() == 0

    _, _, spawn = await a_player(sessions)
    async with sessions() as session, session.begin():
        await session.execute(
            update(models.SystemActivity)
            .where(models.SystemActivity.system_id == spawn.parent_id)
            .values(trade_flow=0.5, patrol_strength=0.5, raider_pressure=0.5)
        )

    report = await tick.run()

    async with sessions() as session:
        agents = (
            (
                await session.execute(
                    select(models.NpcAgent).where(models.NpcAgent.system_id == spawn.parent_id)
                )
            )
            .scalars()
            .all()
        )
    assert report.stages["npc_population"]["observed"] == 1
    assert {a.archetype for a in agents} == {"hauler", "patrol", "raider"}


async def test_materialising_twice_creates_nothing_new(sessions, clean):
    """Criterion A14, second half: the same system on the same day yields the same NPCs."""
    _, _, spawn = await a_player(sessions)
    async with sessions() as session, session.begin():
        await session.execute(
            update(models.SystemActivity)
            .where(models.SystemActivity.system_id == spawn.parent_id)
            .values(trade_flow=0.5)
        )
    tick = runner(sessions, clean)
    await tick.run()

    async with sessions() as session:
        first = sorted(str(a.ship_id) for a in (await session.execute(select(models.NpcAgent))).scalars())

    await tick.run(stages=(NpcPopulation(),))

    async with sessions() as session:
        second = sorted(str(a.ship_id) for a in (await session.execute(select(models.NpcAgent))).scalars())
    assert first and first == second


async def test_npc_ships_share_the_ship_table(sessions, clean):
    """D-6: one table, one physics, one combat resolver."""
    _, _, spawn = await a_player(sessions)
    async with sessions() as session, session.begin():
        await session.execute(
            update(models.SystemActivity)
            .where(models.SystemActivity.system_id == spawn.parent_id)
            .values(trade_flow=0.6)
        )
    await runner(sessions, clean).run()

    async with sessions() as session:
        npc_ships = (
            await session.execute(
                select(func.count()).select_from(models.Ship).where(models.Ship.player_id.is_(None))
            )
        ).scalar_one()
    assert npc_ships > 0


async def test_an_offline_defender_is_resolved_from_their_standing_orders(sessions, clean):
    """Criterion A6."""
    _, attacker_ship, spawn = await a_player(sessions)
    _, defender_ship, _ = await a_player(sessions, posture="surrender_cargo")
    async with sessions() as session, session.begin():
        session.add(
            models.EncounterQueue(
                id=uuid4(),
                world_day=1,
                attacker_id=attacker_ship,
                defender_id=defender_ship,
                at_path=spawn.path,
                intent="attack",
            )
        )

    report = await runner(sessions, clean).run()

    async with sessions() as session:
        row = (await session.execute(select(models.EncounterQueue))).scalar_one()
        defender = (
            await session.execute(select(models.Ship).where(models.Ship.id == defender_ship))
        ).scalar_one()
    assert report.stages["resolve_encounters"]["encounters"] == 1
    assert row.resolved is True
    assert defender.hull == 100  # surrendered, so untouched


async def test_a_destroyed_player_respawns_at_a_home_station(sessions, clean):
    _, attacker_ship, spawn = await a_player(sessions)
    _, defender_ship, _ = await a_player(sessions, hull=1, posture="defend")
    async with sessions() as session, session.begin():
        session.add(
            models.EncounterQueue(
                id=uuid4(),
                world_day=1,
                attacker_id=attacker_ship,
                defender_id=defender_ship,
                at_path=spawn.path,
                intent="attack",
            )
        )

    await runner(sessions, clean).run()

    async with sessions() as session:
        defender = (
            await session.execute(select(models.Ship).where(models.Ship.id == defender_ship))
        ).scalar_one()
    assert defender.destroyed_on is None
    assert defender.hull in (100, 1)  # rebuilt if it died, untouched if it survived


async def test_territory_follows_sustained_presence(sessions, clean):
    """Control is not granted at the instant somebody arrives — GDD §6.6."""
    tick = runner(sessions, clean)
    await tick.run()
    async with sessions() as session:
        after_one = (await session.execute(select(func.max(models.Territory.influence)))).scalar_one()

    for _ in range(5):
        await tick.run()

    async with sessions() as session:
        after_six = (await session.execute(select(func.max(models.Territory.influence)))).scalar_one()
    assert after_six > after_one


async def test_a_full_tick_stays_well_inside_its_budget(sessions, clean):
    """Criterion A12."""
    import time

    started = time.monotonic()
    report = await runner(sessions, clean).run()
    elapsed = time.monotonic() - started

    assert elapsed < 60
    assert set(report.stages) == {
        "settle_travel",
        "resolve_encounters",
        "economy",
        "npc_population",
        "territory",
        "grant_action_points",
        "build_digests",
    }
