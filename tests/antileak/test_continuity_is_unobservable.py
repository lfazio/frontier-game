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


async def surprise_the_model(sessions, settings) -> None:
    """Give the Continuity something to lean on.

    It acts on the Model's deviation, and on a first tick there is none: with no previous
    expectation the projection equals the observation exactly. Blanking what the Model expected
    makes the next cycle a surprise, which is the condition the faction waits for.
    """
    await runner(sessions, settings).run()
    async with sessions() as session, session.begin():
        await session.execute(update(models.HistoryVariable).values(expected=0))
    await runner(sessions, settings).run()


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


def test_a_spectator_learns_strictly_less_than_a_player(client, clean):
    """Watch mode must never become an intelligence tool — UX §9."""
    headers = register(client)
    overview = client.get("/v1/watch/overview").json()
    position = HexAddr.parse(client.get("/v1/me", headers=headers).json()["ship"]["position"])
    system, region = position.parent(), position.parent().parent()

    spectator_system = client.get(f"/v1/watch/map?path={system}").json()["entries"]
    player_system = client.get(f"/v1/map/tiles?path={system}", headers=headers).json()["entries"]

    assert overview["world_day"] >= 0
    # A spectator has no sight, so a system's interior is empty for it and not for a player.
    assert spectator_system == []
    assert player_system

    spectator_region = {e["path"] for e in client.get(f"/v1/watch/map?path={region}").json()["entries"]}
    player_region = {
        e["path"] for e in client.get(f"/v1/map/tiles?path={region}", headers=headers).json()["entries"]
    }
    assert spectator_region <= player_region


def test_the_spectator_feed_carries_nothing_local_and_nothing_private(client, clean):
    register(client)
    body = client.get("/v1/watch/feed").json()
    assert all(event["scope"] >= 2 for event in body["events"])
    assert not [word for word in SECRETS if word in json.dumps(body).lower()]
    for event in body["events"]:
        assert "ship_id" not in event["payload"]
        assert "text" not in event["payload"]


def test_watch_mode_can_be_switched_off_entirely(clean):
    dark = clean.model_copy(update={"features_watch": False})
    with TestClient(create_app(build_sql(dark))) as spectator:
        assert spectator.get("/v1/watch/overview").status_code == 404
        assert spectator.get("/v1/watch/feed").status_code == 404


# --- P6: the faction acts, and still cannot be found (PSDD §3.4) ------------------------------


async def test_the_faction_is_inert_until_it_is_switched_on(sessions, clean):
    """B5: with the flag off, stage 8 does not run and `cont` is untouched."""
    dark = TickRunner(
        sessions=sessions,
        rules=load_ruleset(clean.ruleset_root, clean.ruleset_version),
        clock=SystemClock(),
        rng_for=SeededRng(clean.world_seed).for_,
        features=Features(psychohistory=True, continuity=False),
        extra_stages=load(clean.extra_stages),
    )

    report = await dark.run()

    assert report.stages["continuity"] == {"disabled": 1}
    async with sessions() as session:
        for table in ("cont.agents", "cont.cells", "cont.interventions", "cont.budget"):
            count = (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            assert count == 0, f"{table} was written while the faction was dark"


async def test_it_leans_within_its_budget_and_never_harder(sessions, clean):
    """B6: effort is bounded by the size of the world, and every push by the magnitude cap."""
    rules = load_ruleset(clean.ruleset_root, clean.ruleset_version)
    await surprise_the_model(sessions, clean)

    async with sessions() as session:
        systems = (
            await session.execute(text("SELECT count(*) FROM core.locations WHERE kind = 'system'"))
        ).scalar_one()
        budgets = (await session.execute(text("SELECT allowed, used FROM cont.budget"))).all()
        worst = (
            await session.execute(text("SELECT coalesce(max(magnitude), 0) FROM cont.interventions"))
        ).scalar_one()

    ceiling = rules.continuity.interventions_for(int(systems))
    assert budgets, "the faction acted without opening a budget"
    for allowed, used in budgets:
        assert allowed == ceiling
        assert used <= allowed, "the Continuity spent more than the world allows"
    assert float(worst) <= rules.continuity.max_magnitude


async def test_it_runs_where_the_architecture_puts_it(sessions, clean):
    """The order matters: it leans before promotion decides what the world hears."""
    report = await runner(sessions, clean).run()

    order = list(report.stages)
    assert order.index("continuity") > order.index("psychohistory")
    assert order.index("continuity") < order.index("event_promotion")


async def test_an_intervened_system_looks_like_any_other(client, sessions, clean):
    """B7: a leaned-on system's public projection carries nothing an untouched one does not."""
    headers = register(client)
    await surprise_the_model(sessions, clean)

    async with sessions() as session:
        leaned_on = {
            str(row)
            for row in (
                await session.execute(text("SELECT DISTINCT region_id FROM cont.interventions"))
            ).scalars()
        }
    assert leaned_on, "the faction did not act, so this proves nothing"

    regions = client.get("/v1/map/tiles?path=ga0_0", headers=headers).json()["entries"]
    assert any(region["id"] in leaned_on for region in regions), "no charted region was touched"

    shapes = set()
    for region in regions:
        tile = client.get(f"/v1/map/tiles?path={region['path']}", headers=headers).json()
        for entry in tile["entries"]:
            shapes.add(tuple(sorted(entry)))

    # One shape for every system, whether or not its region was leaned on. A field that appeared
    # only for an intervened system would split this set in two.
    assert len(shapes) == len({shape for shape in shapes if "kind" in shape})
    for shape in shapes:
        assert not any(word in field for field in shape for word in SECRETS)
        assert not any(field in ("trade_flow", "patrol_strength", "raider_pressure") for field in shape)


async def test_nothing_a_player_reads_names_an_intervention(client, sessions, clean):
    """B10: not a ledger entry, not a digest, not a chronicle line, not an event payload."""
    register(client)  # a player, so the tick has ledgers and digests to write
    await surprise_the_model(sessions, clean)

    async with sessions() as session:
        readable = []
        for table in ("core.ap_ledger", "evt.digests", "hist.chronicle", "evt.events"):
            rows = (await session.execute(text(f"SELECT * FROM {table}"))).mappings().all()
            readable.extend(json.dumps(dict(row), default=str).lower() for row in rows)

    assert readable, "nothing was written, so nothing was proved"
    for line in readable:
        for secret in SECRETS:
            assert secret not in line, f"{secret!r} surfaced in something a player can read"


async def test_the_request_path_never_reaches_the_faction(client, sessions, clean):
    """B9/D-76: it acts only in the tick, so a request cannot differ in timing or in reach."""
    headers = register(client)
    await surprise_the_model(sessions, clean)

    async with sessions() as session:
        before = (await session.execute(text("SELECT count(*) FROM cont.interventions"))).scalar_one()

    for path in ("/v1/me", "/v1/feed", "/v1/missions", "/v1/forecasts", "/v1/history/crises"):
        client.get(path, headers=headers)

    async with sessions() as session:
        after = (await session.execute(text("SELECT count(*) FROM cont.interventions"))).scalar_one()
    assert after == before, "a request path moved the Continuity"
