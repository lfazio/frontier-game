"""What P4 adds: history that lasts, work to do, standing that follows you."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from frontier.adapters.api.app import create_app
from frontier.adapters.clock import SeededRng, SystemClock
from frontier.adapters.db import models
from frontier.adapters.rules_loader import load_ruleset
from frontier.config.container import build_sql
from frontier.domain.hex.coordinates import HexAddr
from frontier.simulation.stages.chronicle import ChronicleAndRetention
from frontier.simulation.stages.promotion import EventPromotion
from frontier.simulation.tick import TickRunner

pytestmark = pytest.mark.integration


def runner(sessions, settings) -> TickRunner:
    return TickRunner(
        sessions=sessions,
        rules=load_ruleset(settings.ruleset_root, settings.ruleset_version),
        clock=SystemClock(),
        rng_for=SeededRng(settings.world_seed).for_,
    )


@pytest.fixture
def client(clean):
    with TestClient(create_app(build_sql(clean))) as test_client:
        yield test_client


def register(client) -> dict[str, str]:
    response = client.post(
        "/v1/auth/register",
        json={
            "email": f"{uuid4().hex}@x.io",
            "password": "correct horse battery",
            "callsign": uuid4().hex[:12],
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def send(client, headers, **body):
    body.setdefault("idempotency_key", str(uuid4()))
    return client.post("/v1/commands", json=body, headers=headers)


async def noisy_system(sessions, severity: int, count: int, day: int = 1) -> HexAddr:
    async with sessions() as session, session.begin():
        hexes = (
            (
                await session.execute(
                    select(models.Location)
                    .where(models.Location.level == 3)
                    .order_by(models.Location.path)
                    .limit(count)
                )
            )
            .scalars()
            .all()
        )
        for row in hexes:
            session.add(
                models.Event(
                    id=uuid4(),
                    world_day=day,
                    occurred_at=datetime(2026, 8, 27, tzinfo=UTC),
                    type="COMBAT_RESOLVED",
                    origin_path=row.path,
                    scope=0,
                    visibility="public",
                    clearance=0,
                    severity=severity,
                    participants=[],
                    payload={"outcome": "attacker_won", "rounds": 1, "seed": "x"},
                    ruleset_version="2026.1",
                )
            )
    return hexes[0].path


async def test_enough_local_violence_becomes_a_system_event(sessions, clean):
    """A skirmish becomes a war because severity accumulated — GDD §7.7."""
    await noisy_system(sessions, severity=3, count=4)

    report = await runner(sessions, clean).run(stages=(EventPromotion(),))

    async with sessions() as session:
        promoted = (
            (await session.execute(select(models.Event).where(models.Event.type == "HISTORICAL_EVENT")))
            .scalars()
            .all()
        )
    assert report.stages["event_promotion"]["promoted"] >= 1
    assert promoted[0].scope >= 2
    assert promoted[0].causation_id is not None


async def test_quiet_days_promote_nothing(sessions, clean):
    await noisy_system(sessions, severity=1, count=1)
    report = await runner(sessions, clean).run(stages=(EventPromotion(),))
    assert report.stages["event_promotion"]["promoted"] == 0


async def test_a_major_event_becomes_a_permanent_record(sessions, clean):
    """Criterion: the universe has a collective memory — GDD §8.10."""
    await noisy_system(sessions, severity=4, count=1)

    await runner(sessions, clean).run(stages=(ChronicleAndRetention(),))

    async with sessions() as session:
        entries = (await session.execute(select(models.Chronicle))).scalars().all()
    assert len(entries) == 1
    assert entries[0].title
    assert entries[0].causation_id is not None


async def test_the_chronicle_is_written_before_events_expire(sessions, clean):
    """Retention must never be able to drop something history was about to keep."""
    await noisy_system(sessions, severity=4, count=1, day=1)
    tick = runner(sessions, clean)
    await tick.run()
    for _ in range(5):
        await tick.run()

    async with sessions() as session:
        kept = (await session.execute(select(func.count()).select_from(models.Chronicle))).scalar_one()
        local_left = (
            await session.execute(
                select(func.count()).select_from(models.Event).where(models.Event.scope == 0)
            )
        ).scalar_one()
    assert kept >= 1
    assert local_left == 0  # short-lived local noise is gone


async def test_missions_are_offered_and_expire(sessions, clean):
    tick = runner(sessions, clean)
    first = await tick.run()
    assert first.stages["missions"]["missions_offered"] > 0

    async with sessions() as session, session.begin():
        await session.execute(update(models.Mission).values(expires_on=0))

    second = await tick.run()
    assert second.stages["missions"]["missions_expired"] > 0


def test_a_player_can_take_a_mission_and_be_paid_for_it(client, clean):
    headers = register(client)
    send(client, headers, action="create_team", name=f"Team {uuid4().hex[:8]}", faction_id=1)

    import asyncio

    from frontier.adapters.db.engine import make_engine, make_sessionmaker

    async def offer_here() -> None:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session, session.begin():
            ship = (
                await session.execute(select(models.Ship).where(models.Ship.player_id.is_not(None)))
            ).scalar_one()
            session.add(
                models.Mission(
                    id=uuid4(),
                    faction_id=1,
                    kind="patrol",
                    system_id=ship.system_id,
                    brief="Patrol the approaches.",
                    terms={},
                    reward_credits=900,
                    reward_reputation=3,
                    offered_on=0,
                    expires_on=99,
                )
            )
        await engine.dispose()

    asyncio.run(offer_here())

    board = client.get("/v1/missions", headers=headers).json()
    assert board["offers"], board
    mission_id = board["offers"][0]["id"]

    assert send(client, headers, action="accept_mission", mission_id=mission_id).status_code == 202
    assert client.get("/v1/missions", headers=headers).json()["mine"]

    before = client.get("/v1/me", headers=headers).json()["player"]["credits"]
    completed = send(client, headers, action="complete_mission", mission_id=mission_id)

    assert completed.status_code == 202
    after = client.get("/v1/me", headers=headers).json()["player"]["credits"]
    assert after == before + 900
    assert client.get("/v1/missions", headers=headers).json()["reputation"] == {"1": 3}


def test_a_mission_cannot_be_completed_from_elsewhere(client, clean):
    headers = register(client)
    import asyncio

    from frontier.adapters.db.engine import make_engine, make_sessionmaker

    async def offer_far_away() -> str:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session, session.begin():
            ship = (
                await session.execute(select(models.Ship).where(models.Ship.player_id.is_not(None)))
            ).scalar_one()
            elsewhere = (
                await session.execute(
                    select(models.Location)
                    .where(models.Location.kind == "system", models.Location.id != ship.system_id)
                    .order_by(models.Location.path)
                    .limit(1)
                )
            ).scalar_one()
            mission = models.Mission(
                id=uuid4(),
                faction_id=1,
                kind="survey",
                system_id=elsewhere.id,
                brief="Survey it.",
                terms={},
                reward_credits=500,
                reward_reputation=1,
                offered_on=0,
                expires_on=99,
            )
            session.add(mission)
        await engine.dispose()
        return str(mission.id)

    mission_id = asyncio.run(offer_far_away())
    send(client, headers, action="accept_mission", mission_id=mission_id)
    response = send(client, headers, action="complete_mission", mission_id=mission_id)

    assert response.status_code == 409
    assert response.json()["code"] == "NOT_AT_MISSION_SITE"


def test_defection_moves_the_whole_team_and_is_announced(client, clean):
    """A political event, not a menu operation — GDD §6.7."""
    headers = register(client)
    send(client, headers, action="create_team", name=f"Team {uuid4().hex[:8]}", faction_id=1)

    response = send(client, headers, action="defect", to_faction_id=2)

    assert response.status_code == 202
    event = response.json()["events"][0]
    assert event["type"] == "TEAM_DEFECTED"
    assert event["payload"] == {"team_id": event["payload"]["team_id"], "from_faction": 1, "to_faction": 2}
    assert client.get("/v1/missions", headers=headers).json()["faction_id"] == 2


def test_defecting_costs_standing_with_the_faction_left_behind(client, clean):
    headers = register(client)
    send(client, headers, action="create_team", name=f"Team {uuid4().hex[:8]}", faction_id=3)
    send(client, headers, action="defect", to_faction_id=1)

    reputation = client.get("/v1/missions", headers=headers).json()["reputation"]

    assert reputation["3"] == -25
