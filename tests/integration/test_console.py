"""The operator console — ADMIN §2 and §6, delivery slice A0.

Two properties carry this suite: the console is a different application from the game, and
permission comes from another operator rather than from asking.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from frontier.adapters.api.app import create_app
from frontier.adapters.api.security import hash_password
from frontier.adapters.clock import SeededRng, SystemClock
from frontier.adapters.console.app import bootstrap, build, create_console
from frontier.adapters.db.engine import make_engine, make_sessionmaker
from frontier.adapters.rules_loader import load_ruleset
from frontier.config.container import build_sql
from frontier.simulation.stages.base import Features
from frontier.simulation.tick import TickRunner

pytestmark = pytest.mark.integration

ORIGIN = "ancients@frontier.test"
SECRET = "correct-horse-battery-staple"


def for_console(settings):
    return settings.model_copy(update={"admin_worlds": "kestrel,demo"})


@pytest.fixture
def console(clean):
    settings = for_console(clean)
    asyncio.run(_wipe(settings))
    asyncio.run(bootstrap(settings, ORIGIN, SECRET, "The Great Ancients"))
    with TestClient(create_console(build(settings))) as client:
        yield client


async def _wipe(settings) -> None:
    engine = make_engine(settings.database_url)
    async with make_sessionmaker(engine)() as session, session.begin():
        await session.execute(text("DELETE FROM admin.grants"))
        await session.execute(text("DELETE FROM admin.operators"))
    await engine.dispose()


def sign_in(console, email=ORIGIN, password=SECRET) -> dict[str, str]:
    token = console.post("/admin/auth/login", json={"email": email, "password": password})
    assert token.status_code == 200, token.text
    return {"Authorization": f"Bearer {token.json()['access_token']}"}


def add_operator(clean, email: str, name: str, password: str = SECRET) -> None:
    async def write() -> None:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO admin.operators (id, email, name, password_hash, created_on) "
                    "VALUES (:id, :email, :name, :hash, 0)"
                ).bindparams(id=uuid4(), email=email, name=name, hash=hash_password(password))
            )
        await engine.dispose()

    asyncio.run(write())


def test_the_console_serves_no_game_route(console):
    """A0: it is a different application, not a privileged corner of the player API."""
    assert console.get("/v1/me").status_code == 404
    assert console.get("/v1/feed").status_code == 404
    assert console.get("/v1/watch/overview").status_code == 404


def test_the_game_serves_no_console_route(clean):
    with TestClient(create_app(build_sql(clean))) as game:
        assert game.get("/admin/me").status_code == 404
        assert game.post("/admin/auth/login", json={}).status_code == 404
        assert game.get("/admin/operators?world=kestrel").status_code == 404


def test_a_player_token_is_not_an_operator_token(clean, console):
    """Different audiences, so it fails even where a deployment shares the secret."""
    with TestClient(create_app(build_sql(clean))) as game:
        registered = game.post(
            "/v1/auth/register",
            json={
                "email": f"{uuid4().hex}@x.io",
                "password": "correct horse battery",
                "callsign": uuid4().hex[:12],
            },
        )
        player = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        operator = sign_in(console)

        assert console.get("/admin/me", headers=player).status_code == 401
        assert game.get("/v1/me", headers=operator).status_code == 401
        assert console.get("/admin/me", headers=operator).status_code == 200


def test_the_origin_holds_every_world_and_nobody_granted_it(console):
    body = console.get("/admin/me", headers=sign_in(console)).json()

    assert body["name"] == "The Great Ancients"
    assert {w["name"] for w in body["worlds"]} == {"kestrel", "demo"}
    assert {w["permission"] for w in body["worlds"]} == {"origin"}

    roster = console.get("/admin/operators?world=kestrel", headers=sign_in(console)).json()
    origin = next(o for o in roster["operators"] if o["permission"] == "origin")
    assert origin["granted_by"] is None
    assert origin["removable"] is False


def test_permission_comes_from_another_operator(clean, console):
    """QA-1: nobody grants themselves this, and the console records who did."""
    add_operator(clean, "nadia@example.com", "nadia.okonkwo")
    origin = sign_in(console)

    # Before the grant, she cannot see the world at all.
    hers = sign_in(console, "nadia@example.com")
    assert console.get("/admin/worlds/kestrel", headers=hers).status_code == 404

    granted = console.post(
        "/admin/operators:grant",
        headers=origin,
        json={"email": "nadia@example.com", "world": "kestrel", "permission": "operate"},
    )
    assert granted.status_code == 201

    assert console.get("/admin/worlds/kestrel", headers=hers).status_code == 200
    # ...and only the world she was given.
    assert console.get("/admin/worlds/demo", headers=hers).status_code == 404

    roster = console.get("/admin/operators?world=kestrel", headers=origin).json()
    hers_row = next(o for o in roster["operators"] if o["name"] == "nadia.okonkwo")
    assert hers_row["granted_by"] == "The Great Ancients"


def test_nobody_grants_more_than_they_hold(clean, console):
    add_operator(clean, "watcher@example.com", "support.rota")
    origin = sign_in(console)
    console.post(
        "/admin/operators:grant",
        headers=origin,
        json={"email": "watcher@example.com", "world": "kestrel", "permission": "watch"},
    )

    theirs = sign_in(console, "watcher@example.com")
    add_operator(clean, "friend@example.com", "a.friend")
    refused = console.post(
        "/admin/operators:grant",
        headers=theirs,
        json={"email": "friend@example.com", "world": "kestrel", "permission": "operate"},
    )

    # `watch` cannot even reach the granting endpoint: it needs `operate` to hand anything out.
    assert refused.status_code == 404


def test_the_origin_cannot_be_revoked(console):
    """A world with no operator is a world nobody can rescue."""
    origin = sign_in(console)

    refused = console.post(
        "/admin/operators:revoke",
        headers=origin,
        json={"email": ORIGIN, "world": "kestrel", "permission": "origin"},
    )

    assert refused.status_code == 409
    assert refused.json()["detail"] == "ORIGIN_IS_FIXED"
    assert console.get("/admin/me", headers=origin).json()["worlds"]


def test_a_revoked_operator_loses_the_world(clean, console):
    add_operator(clean, "temp@example.com", "temp.cover")
    origin = sign_in(console)
    console.post(
        "/admin/operators:grant",
        headers=origin,
        json={"email": "temp@example.com", "world": "kestrel", "permission": "operate"},
    )
    theirs = sign_in(console, "temp@example.com")
    assert console.get("/admin/worlds/kestrel", headers=theirs).status_code == 200

    console.post(
        "/admin/operators:revoke",
        headers=origin,
        json={"email": "temp@example.com", "world": "kestrel", "permission": "operate"},
    )

    assert console.get("/admin/worlds/kestrel", headers=theirs).status_code == 404


def test_a_world_nobody_holds_answers_as_no_world_at_all(console):
    """The same 404 either way, so a deployment's worlds cannot be mapped by asking."""
    origin = sign_in(console)

    unknown = console.get("/admin/worlds/atlantis", headers=origin)
    unheld = console.get("/admin/worlds/kestrel")

    assert unknown.status_code == 404
    assert unheld.status_code == 401  # no token at all is a different question
    assert unknown.json() == {"detail": "Not Found"}


# --- A1: the overview and the tick ------------------------------------------------------------


def tick_once(clean) -> int:
    """Run a real cycle, so the screens have something true to show."""

    async def run() -> int:
        engine = make_engine(clean.database_url)
        runner = TickRunner(
            sessions=make_sessionmaker(engine),
            rules=load_ruleset(clean.ruleset_root, clean.ruleset_version),
            clock=SystemClock(),
            rng_for=SeededRng(clean.world_seed).for_,
            features=Features(),
        )
        report = await runner.run()
        await engine.dispose()
        return report.world_day

    return asyncio.run(run())


def test_the_overview_answers_the_question_it_exists_for(clean, console):
    """A1: is the world turning, and what is it doing?"""
    day = tick_once(clean)

    body = console.get("/admin/worlds/kestrel", headers=sign_in(console)).json()

    assert body["world_day"] == day
    assert body["last_tick"]["world_day"] == day
    assert body["last_tick"]["finished"] is True
    assert body["last_tick"]["seconds"] > 0
    assert body["counts"]["systems"] > 0
    assert set(body["history"]) == {
        "era",
        "era_began_on",
        "open_crises",
        "soonest_expiry_in",
        "incursion_hulls",
    }


def test_a_world_that_never_ticked_says_so(console):
    """Never a blank screen: a world with no history reports none rather than showing zeroes."""
    body = console.get("/admin/worlds/kestrel", headers=sign_in(console)).json()

    assert body["last_tick"]["world_day"] is None
    assert body["last_tick"]["finished"] is False


def test_a_stage_time_is_the_gap_since_the_one_before(clean, console):
    """The tick stores no durations; the console derives them and they add up."""
    day = tick_once(clean)

    body = console.get(f"/admin/worlds/kestrel/ticks/{day}", headers=sign_in(console)).json()

    assert len(body["stages"]) >= 12
    assert all(s["seconds"] >= 0 for s in body["stages"])
    assert body["stopped_after"] is None
    # Shares are a share of something: they sum to about the whole run.
    assert 0.9 <= sum(s["share"] for s in body["stages"]) <= 1.01
    assert {"stage", "seconds", "metrics", "share"} == set(body["stages"][0])


def test_a_run_that_never_finished_names_where_it_stopped(clean, console):
    day = tick_once(clean)

    async def unfinish() -> None:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session, session.begin():
            await session.execute(
                text("UPDATE hist.tick_runs SET finished_at = NULL WHERE world_day = :d").bindparams(d=day)
            )
            await session.execute(
                text(
                    "DELETE FROM hist.tick_stages WHERE world_day = :d AND stage = 'build_digests'"
                ).bindparams(d=day)
            )
        await engine.dispose()

    asyncio.run(unfinish())

    body = console.get(f"/admin/worlds/kestrel/ticks/{day}", headers=sign_in(console)).json()
    assert body["finished"] is False
    assert body["stopped_after"] == "grant_action_points"


def test_asking_for_a_retry_needs_operate_and_leaves_a_name(clean, console):
    """The console does not run the tick; it asks the worker to come round sooner."""
    day = tick_once(clean)
    origin = sign_in(console)

    # A finished run has nothing to resume.
    assert console.post(f"/admin/worlds/kestrel/ticks/{day}:retry", headers=origin).status_code == 409

    async def unfinish() -> None:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session, session.begin():
            await session.execute(
                text("UPDATE hist.tick_runs SET finished_at = NULL WHERE world_day = :d").bindparams(d=day)
            )
        await engine.dispose()

    asyncio.run(unfinish())

    add_operator(clean, "watcher2@example.com", "support.rota")
    console.post(
        "/admin/operators:grant",
        headers=origin,
        json={"email": "watcher2@example.com", "world": "kestrel", "permission": "watch"},
    )
    watcher = sign_in(console, "watcher2@example.com")

    # Watching is not operating.
    assert console.post(f"/admin/worlds/kestrel/ticks/{day}:retry", headers=watcher).status_code == 404
    assert console.post(f"/admin/worlds/kestrel/ticks/{day}:retry", headers=origin).status_code == 200

    body = console.get(f"/admin/worlds/kestrel/ticks/{day}", headers=origin).json()
    assert body["retry_requested"] is True


def test_the_screens_render_for_a_signed_in_operator(clean, console):
    tick_once(clean)
    login = console.post(
        "/console/login",
        content="email=ancients%40frontier.test&password=correct-horse-battery-staple",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert "frontier_console" in login.cookies

    overview = console.get("/console/kestrel/overview")
    ticks = console.get("/console/kestrel/ticks")

    assert overview.status_code == 200
    assert "LAST TICK" in overview.text and "systems" in overview.text
    assert ticks.status_code == 200 and "day" in ticks.text
    # A world this operator does not hold is not there.
    assert console.get("/console/atlantis/overview").status_code == 404


def test_the_screens_are_shut_to_anyone_not_signed_in(console):
    for path in ("/console/kestrel/overview", "/console/kestrel/ticks", "/console/kestrel/ticks/1"):
        answer = console.get(path)
        assert answer.status_code == 401
        assert "Sign in" in answer.text


# --- A2: history ------------------------------------------------------------------------------


def strained(clean, **events) -> int:
    """A world that has surprised the model, so it has crises worth showing."""

    async def run() -> int:
        engine = make_engine(clean.database_url)
        sessions = make_sessionmaker(engine)
        rules = load_ruleset(clean.ruleset_root, clean.ruleset_version)
        tuned = replace(rules, events=replace(rules.events, **events)) if events else rules
        runner = TickRunner(
            sessions=sessions,
            rules=tuned,
            clock=SystemClock(),
            rng_for=SeededRng(clean.world_seed).for_,
            features=Features(psychohistory=True),
        )
        await runner.run()
        async with sessions() as session, session.begin():
            await session.execute(text("UPDATE psycho.history_variables SET expected = 0"))
        report = await runner.run()
        await engine.dispose()
        return report.world_day

    return asyncio.run(run())


def test_history_is_empty_and_says_so_before_anything_happens(clean, console):
    tick_once(clean)

    body = console.get("/admin/worlds/kestrel/history", headers=sign_in(console)).json()

    assert body["era"] is None
    assert body["open"] == [] and body["answered"] == []
    assert body["era_threshold"] == 3


def test_an_open_crisis_carries_its_countdown(clean, console):
    """A2: the point of the screen is seeing an invasion coming before it arrives."""
    day = strained(clean, crisis_window=1)

    body = console.get("/admin/worlds/kestrel/history", headers=sign_in(console)).json()

    assert body["era"]["name"] == "The First Age"
    assert body["open"], "a strained world showed no crisis"
    for crisis in body["open"]:
        assert crisis["region"].startswith("Region")
        assert 1 <= crisis["severity"] <= 5
        assert crisis["days_left"] == crisis["expires_on"] - day
        assert crisis["incursion"] is None


def test_an_answered_crisis_carries_the_incursion_it_raised(clean, console):
    """The crisis and its hulls are one row: what came, and what it came from."""
    strained(clean, crisis_window=1, crisis_duration=0)

    body = console.get("/admin/worlds/kestrel/history", headers=sign_in(console)).json()

    answered = [c for c in body["answered"] if c["incursion"]]
    assert answered, "a crisis expired and the console showed no incursion"
    raid = answered[0]["incursion"]
    assert raid["hulls"] >= 1
    assert raid["still_flying"] <= raid["hulls"]
    assert raid["region"] and raid["raised_on"] is not None


def test_the_history_screen_renders_what_the_json_says(clean, console):
    strained(clean, crisis_window=1, crisis_duration=0)
    console.post(
        "/console/login",
        content="email=ancients%40frontier.test&password=correct-horse-battery-staple",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )

    screen = console.get("/console/kestrel/history")
    body = console.get("/admin/worlds/kestrel/history", headers=sign_in(console)).json()

    assert screen.status_code == 200
    assert "The First Age" in screen.text
    assert "hulls still flying" in screen.text
    # One severity strip per open crisis, five marks each.
    assert screen.text.count("width:7px;height:13px") == len(body["open"]) * 5


def test_history_needs_a_world_you_hold(console):
    assert console.get("/admin/worlds/atlantis/history", headers=sign_in(console)).status_code == 404
    assert console.get("/admin/worlds/kestrel/history").status_code == 401
