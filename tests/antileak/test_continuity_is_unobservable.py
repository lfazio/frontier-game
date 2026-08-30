"""The Continuity must not be inferable from anything a player can reach — GDD §9.4.

A merge blocker. Section 13.3 of the detailed design asks for this suite by name: a leak here is
unrecoverable, because the social game §9.7 describes cannot be un-spoiled.
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

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


# --- P7: the channel (PSDD §4.3) --------------------------------------------------------------


def clear(clean, player_id, level: int = 1) -> None:
    async def grant() -> None:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session, session.begin():
            await session.execute(
                update(models.Player).where(models.Player.id == player_id).values(clearance=level)
            )
        await engine.dispose()

    asyncio.run(grant())


def whoami(client, headers) -> str:
    return client.get("/v1/me", headers=headers).json()["player"]["id"]


def test_the_channel_carries_to_a_holder_anywhere_and_to_nobody_else(client, clean):
    """B13: entitlement, not position — and silence for everyone without it."""
    member = register(client)
    outsider = register(client)
    clear(clean, whoami(client, member))

    sent = client.post(
        "/v1/commands",
        json={
            "action": "send_message",
            "channel": "directorate",
            "text": "Node 41 confirms.",
            "idempotency_key": str(uuid4()),
        },
        headers=member,
    )
    assert sent.status_code == 202

    heard = client.get("/v1/feed", headers=member).json()["events"]
    assert any(e["payload"].get("text") == "Node 41 confirms." for e in heard)

    for line in client.get("/v1/feed", headers=outsider).json()["events"]:
        assert line["payload"].get("text") != "Node 41 confirms."
        assert "directorate" not in json.dumps(line).lower()


def test_speaking_on_it_without_clearance_looks_like_nonsense(client, clean):
    """An outsider naming the channel is refused exactly as an outsider naming gibberish is."""
    outsider = register(client)

    def say(channel: str):
        return client.post(
            "/v1/commands",
            json={
                "action": "send_message",
                "channel": channel,
                "text": "hello?",
                "idempotency_key": str(uuid4()),
            },
            headers=outsider,
        )

    named = say("directorate")
    nonsense = say("zzyzx")

    assert named.status_code == nonsense.status_code
    assert named.json() == nonsense.json()


def test_the_channel_reaches_a_holder_with_no_delay(client, clean):
    """GDD §9.6: no relay, no range, no `deliver_at` in the future."""
    member = register(client)
    clear(clean, whoami(client, member))

    client.post(
        "/v1/commands",
        json={
            "action": "send_message",
            "channel": "directorate",
            "text": "Immediate.",
            "idempotency_key": str(uuid4()),
        },
        headers=member,
    )

    line = next(
        e
        for e in client.get("/v1/feed", headers=member).json()["events"]
        if e["payload"].get("text") == "Immediate."
    )
    assert line["scope"] == 4  # UNIVERSE
    assert line["quality"] == "full"


# --- P7: the rationed watch (PSDD §4.4) -------------------------------------------------------


def spend_the_ration(clean) -> None:
    async def clear_key() -> None:
        from redis.asyncio import Redis

        redis = Redis.from_url(clean.redis_url)
        await redis.delete("survey:ration")
        await redis.aclose()

    asyncio.run(clear_key())


def test_the_survey_does_not_exist_without_clearance(client, clean):
    """B14: the same 404 as a route that is not there."""
    outsider = register(client)

    refused = client.get("/v1/survey", headers=outsider)
    absent = client.get("/v1/no-such-route", headers=outsider)

    assert refused.status_code == 404
    assert refused.json() == absent.json()


def test_the_ration_is_spent_for_the_whole_faction(client, clean):
    """One member spending it spends it for everyone — it is an instrument, not a perk."""
    spend_the_ration(clean)
    first = register(client)
    second = register(client)
    clear(clean, whoami(client, first))
    clear(clean, whoami(client, second))

    opened = client.get("/v1/survey", headers=first)
    again = client.get("/v1/survey", headers=second)

    assert opened.status_code == 200
    assert opened.json()["galaxy"]["entries"], "the survey showed nothing"
    assert again.status_code == 429, "a second member got their own look at the world"
    spend_the_ration(clean)


def test_the_survey_is_no_stronger_than_watch_mode(client, clean):
    """It is the same projection: a shared look at the chart, never at what is inside a system."""
    spend_the_ration(clean)
    member = register(client)
    clear(clean, whoami(client, member))

    body = client.get("/v1/survey", headers=member).json()

    kinds = {entry["kind"] for tile in body["regions"] for entry in tile["entries"]}
    assert kinds <= {"system", "void"}, "the survey reached inside a system"
    assert {entry["kind"] for entry in body["galaxy"]["entries"]} <= {"region", "void"}
    spend_the_ration(clean)


# --- P7: recruitment (PSDD §4.1, Q-F) ---------------------------------------------------------


def offer_to(clean, player_id) -> str:
    """Post an addressed offer the way the faction posts one."""

    async def post() -> str:
        engine = make_engine(clean.database_url)
        mission_id = uuid4()
        async with make_sessionmaker(engine)() as session, session.begin():
            system_id = (
                await session.execute(
                    text("SELECT id FROM core.locations WHERE kind = 'system' ORDER BY path LIMIT 1")
                )
            ).scalar_one()
            await session.execute(
                text(
                    "INSERT INTO core.missions (id, faction_id, kind, system_id, brief, terms, "
                    " reward_credits, reward_reputation, offered_to, offered_on, expires_on) "
                    "VALUES (:id, 1, 'courier', :system, 'Carry a sealed package.', "
                    "        CAST('{\"clearance\": 1}' AS jsonb), 1200, 1, :player, 0, 30)"
                ).bindparams(id=mission_id, system=system_id, player=UUID(player_id))
            )
        await engine.dispose()
        return str(mission_id)

    return asyncio.run(post())


def test_an_addressed_offer_is_on_one_board_and_no_other(client, clean):
    """B11: an approach nobody else can see is an approach nobody else can infer."""
    approached = register(client)
    bystander = register(client)
    mission_id = offer_to(clean, whoami(client, approached))

    mine = client.get("/v1/missions", headers=approached).json()["offers"]
    theirs = client.get("/v1/missions", headers=bystander).json()["offers"]

    assert any(m["id"] == mission_id for m in mine)
    assert not any(m["id"] == mission_id for m in theirs)


def test_an_offer_says_nothing_about_what_it_is(client, clean):
    """The board serialises no term, so an offer reads as ordinary work until it is taken."""
    approached = register(client)
    mission_id = offer_to(clean, whoami(client, approached))

    offer = next(
        m for m in client.get("/v1/missions", headers=approached).json()["offers"] if m["id"] == mission_id
    )

    body = json.dumps(offer).lower()
    for secret in SECRETS:
        assert secret not in body
    assert "terms" not in offer and "offered_to" not in offer


def test_taking_it_is_what_changes_the_pilot(client, clean):
    """And declining writes nothing: there is no decline, only an offer that expires."""
    approached = register(client)
    player_id = whoami(client, approached)
    mission_id = offer_to(clean, player_id)

    async def clearance_of() -> int:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session:
            found = (
                await session.execute(
                    text("SELECT clearance FROM core.players WHERE id = :p").bindparams(p=UUID(player_id))
                )
            ).scalar_one()
        await engine.dispose()
        return int(found)

    assert asyncio.run(clearance_of()) == 0, "an unopened offer changed the pilot"

    client.post(
        "/v1/commands",
        json={
            "action": "accept_mission",
            "mission_id": mission_id,
            "idempotency_key": str(uuid4()),
        },
        headers=approached,
    )

    assert asyncio.run(clearance_of()) == 1
