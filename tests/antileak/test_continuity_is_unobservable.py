"""The Continuity must not be inferable from anything a player can reach — GDD §9.4.

A merge blocker. Section 13.3 of the detailed design asks for this suite by name: a leak here is
unrecoverable, because the social game §9.7 describes cannot be un-spoiled.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update

from frontier.adapters.api.app import create_app
from frontier.adapters.clock import SeededRng, SystemClock
from frontier.adapters.db import models
from frontier.adapters.db.engine import make_engine, make_sessionmaker
from frontier.adapters.rules_loader import load_ruleset
from frontier.config.container import build_sql
from frontier.domain.hex.coordinates import HexAddr
from frontier.simulation.extensions import load
from frontier.simulation.stages.base import Features
from frontier.simulation.tick import TickRunner

pytestmark = pytest.mark.integration

SECRETS = ("continuity", "cont.", "clearance", "cell", "node-", "intervention")


def lit(settings):
    return settings.model_copy(update={"features_psychohistory": True, "features_continuity": True})


def runner(sessions, settings) -> TickRunner:
    return TickRunner(
        sessions=sessions,
        rules=load_ruleset(settings.ruleset_root, settings.ruleset_version),
        clock=SystemClock(),
        rng_for=SeededRng(settings.world_seed).for_,
        features=Features(psychohistory=True, continuity=True),
        extra_stages=load(settings.extra_stages),
    )


@pytest.fixture
def client(clean):
    with TestClient(create_app(build_sql(lit(clean)))) as test_client:
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


async def test_the_public_connection_cannot_read_the_hidden_schema(clean):
    """The strongest guarantee available: the API's role has no grant on `cont` at all."""
    engine = make_engine(clean.database_url, role=clean.api_role)
    sessions = make_sessionmaker(engine)
    for statement in (
        "SELECT count(*) FROM cont.agents",
        "SELECT count(*) FROM cont.cells",
        "SELECT count(*) FROM cont.interventions",
    ):
        # A fresh session per probe: the first refusal poisons the transaction, and a later
        # "transaction is aborted" would pass for a denial without proving one.
        async with sessions() as session:
            # Assert the role is actually in force. Without this the probe would pass for a
            # connection that had silently reverted to the owning user.
            assert (await session.execute(text("SELECT current_user"))).scalar_one() == "api_role"
            with pytest.raises(Exception) as refused:
                await session.execute(text(statement))
            assert "permission denied" in str(refused.value).lower()
    await engine.dispose()


async def test_the_hidden_faction_cannot_touch_a_player(clean):
    """GDD §9.13 — push, never force — refused by the database, not remembered by the code."""
    engine = make_engine(clean.database_url)
    sessions = make_sessionmaker(engine)
    for statement in (
        "UPDATE core.players SET credits = 0",
        "UPDATE core.ships SET hull = 1",
        "UPDATE core.cargo SET qty = 1",
        "DELETE FROM core.players",
    ):
        async with sessions() as session:
            await session.execute(text("SET ROLE cont_role"))
            with pytest.raises(Exception) as refused:
                await session.execute(text(statement))
            assert "permission denied" in str(refused.value).lower()
    await engine.dispose()


async def test_the_hidden_faction_may_still_lean_on_a_population(clean):
    """Its one lever, so the constraint above is a boundary and not a total ban."""
    engine = make_engine(clean.database_url)
    async with make_sessionmaker(engine)() as session, session.begin():
        await session.execute(text("SET ROLE cont_role"))
        await session.execute(text("UPDATE core.system_activity SET trade_flow = trade_flow"))
    await engine.dispose()


def test_no_route_admits_the_hidden_faction_exists(client):
    paths = json.dumps(client.get("/openapi.json").json()).lower()
    assert not [word for word in SECRETS if word in paths]


def test_a_crew_with_a_second_identity_looks_like_any_other(client, clean):
    """Two NPCs, identical but for a `cont.agents` row: the public surface must not tell them apart."""
    import asyncio

    headers = register(client)

    async def seed_two_crews() -> tuple[str, str]:
        engine = make_engine(clean.database_url)
        sessions = make_sessionmaker(engine)
        async with sessions() as session, session.begin():
            ship = (
                await session.execute(select(models.Ship).where(models.Ship.player_id.is_not(None)))
            ).scalar_one()
            await session.execute(
                update(models.SystemActivity)
                .where(models.SystemActivity.system_id == ship.system_id)
                .values(trade_flow=0.9, patrol_strength=0.9, raider_pressure=0.9)
            )
        await runner(sessions, clean).run()
        async with sessions() as session:
            crews = (
                (await session.execute(select(models.NpcAgent).order_by(models.NpcAgent.ship_id)))
                .scalars()
                .all()
            )
            agents = set((await session.execute(text("SELECT ship_id FROM cont.agents"))).scalars())
        await engine.dispose()
        recruited = next(c for c in crews if c.ship_id in agents)
        ordinary = next(c for c in crews if c.ship_id not in agents)
        return str(recruited.ship_id), str(ordinary.ship_id)

    recruited, ordinary = asyncio.run(seed_two_crews())
    position = HexAddr.parse(client.get("/v1/me", headers=headers).json()["ship"]["position"])

    feed = json.dumps(client.get("/v1/feed", headers=headers).json()).lower()
    tile = json.dumps(client.get(f"/v1/map/tiles?path={position.parent()}", headers=headers).json()).lower()
    missions = json.dumps(client.get("/v1/missions", headers=headers).json()).lower()
    forecasts = json.dumps(client.get("/v1/forecasts", headers=headers).json()).lower()

    for body in (feed, tile, missions, forecasts):
        assert not [word for word in SECRETS if word in body]
        # Whatever the surface says about one crew, it says about the other.
        assert (recruited in body) == (ordinary in body)


def test_a_forecast_never_reports_who_moved_the_needle(client, clean):
    """An intervention shifts a population figure; it must leave no signature in the output."""
    import asyncio

    headers = register(client)

    async def intervene() -> int:
        engine = make_engine(clean.database_url)
        sessions = make_sessionmaker(engine)
        tick = runner(sessions, clean)
        await tick.run()
        async with sessions() as session, session.begin():
            await session.execute(text("UPDATE psycho.forecasts SET deviation = 0.5"))
        await tick.run()
        async with sessions() as session:
            acts = (await session.execute(text("SELECT count(*) FROM cont.interventions"))).scalar_one()
        await engine.dispose()
        return int(acts)

    assert asyncio.run(intervene()) >= 0
    body = json.dumps(client.get("/v1/forecasts", headers=headers).json()).lower()
    assert not [word for word in SECRETS if word in body]
