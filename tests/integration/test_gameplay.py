"""The MVP loop, end to end over HTTP — tasks 3.1 to 3.10."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from frontier.adapters.api.app import create_app
from frontier.adapters.db import models
from frontier.adapters.db.engine import make_engine, make_sessionmaker
from frontier.config.container import build_sql
from frontier.domain.hex.coordinates import HexAddr
from frontier.domain.hex.geometry import Axial, neighbours

pytestmark = pytest.mark.integration


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
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def send(client, headers, **body):
    body.setdefault("idempotency_key", str(uuid4()))
    return client.post("/v1/commands", json=body, headers=headers)


def me(client, headers):
    return client.get("/v1/me", headers=headers).json()


def home_station(client, headers) -> dict:
    position = HexAddr.parse(me(client, headers)["ship"]["position"])
    entries = client.get(f"/v1/map/tiles?path={position.parent()}", headers=headers).json()["entries"]
    return next(e for e in entries if e["path"] == str(position))


def test_a_new_account_gets_a_ship_at_a_station(client):
    """Criterion A1."""
    headers = register(client)
    dashboard = me(client, headers)
    assert dashboard["player"]["ap"] == 10
    assert dashboard["player"]["credits"] == 5000
    assert dashboard["ship"]["fuel"] == 60
    assert home_station(client, headers)["kind"] == "station"


def test_a_round_trip_through_a_market_loses_the_spread(client):
    """Criterion A5."""
    headers = register(client)
    station = home_station(client, headers)
    assert send(client, headers, action="dock", station_id=station["id"]).status_code == 202
    before = me(client, headers)["player"]["credits"]

    bought = send(client, headers, action="buy", commodity="grain", qty=5)
    sold = send(client, headers, action="sell", commodity="grain", qty=5)

    assert bought.status_code == 202 and sold.status_code == 202
    assert (
        bought.json()["events"][0]["payload"]["unit_price"]
        > sold.json()["events"][0]["payload"]["unit_price"]
    )
    assert me(client, headers)["player"]["credits"] < before


def test_selling_what_you_do_not_have_is_refused(client):
    headers = register(client)
    send(client, headers, action="dock", station_id=home_station(client, headers)["id"])
    response = send(client, headers, action="sell", commodity="grain", qty=1)
    assert response.status_code == 409
    assert response.json()["code"] == "INSUFFICIENT_CARGO"


def test_a_hold_cannot_be_overfilled(client):
    headers = register(client)
    send(client, headers, action="dock", station_id=home_station(client, headers)["id"])
    response = send(client, headers, action="buy", commodity="grain", qty=9999)
    assert response.status_code == 409
    assert response.json()["code"] in ("CARGO_FULL", "INSUFFICIENT_STOCK", "INSUFFICIENT_CREDITS")


def test_trading_requires_docking_first(client):
    headers = register(client)
    assert send(client, headers, action="buy", commodity="grain", qty=1).json()["code"] == "NOT_DOCKED"


def test_launching_frees_the_ship_to_move(client):
    headers = register(client)
    station = home_station(client, headers)
    send(client, headers, action="dock", station_id=station["id"])
    position = HexAddr.parse(me(client, headers)["ship"]["position"])
    blocked = send(client, headers, action="move", to=str(position.sibling(neighbours(position.tip)[0])))
    assert blocked.json()["code"] == "MUST_LAUNCH_FIRST"

    assert send(client, headers, action="launch").status_code == 202
    assert (
        send(
            client, headers, action="move", to=str(position.sibling(neighbours(position.tip)[0]))
        ).status_code
        == 202
    )


def test_a_jump_leaves_the_ship_in_transit_until_the_tick(client):
    headers = register(client)
    position = HexAddr.parse(me(client, headers)["ship"]["position"])
    region = position.parent().parent()
    systems = client.get(f"/v1/map/tiles?path={region}", headers=headers).json()["entries"]
    elsewhere = next(e for e in systems if e["path"] != str(position.parent()))

    response = send(client, headers, action="jump", to_system=elsewhere["path"])

    assert response.status_code == 202
    after = me(client, headers)
    assert after["ship"]["position"] == str(position)  # still here; stage 1 lands it
    assert after["player"]["ap"] < 10 and after["ship"]["fuel"] < 60


def test_the_star_chart_is_public_but_system_contents_are_not(client):
    """Criterion A11: an unscanned system reveals nothing about what is inside it."""
    headers = register(client)
    position = HexAddr.parse(me(client, headers)["ship"]["position"])
    region = position.parent().parent()
    systems = client.get(f"/v1/map/tiles?path={region}", headers=headers).json()["entries"]
    elsewhere = next(e for e in systems if e["path"] != str(position.parent()))

    assert len(systems) > 1
    assert client.get(f"/v1/map/tiles?path={elsewhere['path']}", headers=headers).json()["entries"] == []
    assert client.get(f"/v1/map/tiles?path={position.parent()}", headers=headers).json()["entries"]


def test_an_unchanged_tile_is_a_304(client):
    headers = register(client)
    position = HexAddr.parse(me(client, headers)["ship"]["position"])
    first = client.get(f"/v1/map/tiles?path={position.parent()}", headers=headers)
    again = client.get(
        f"/v1/map/tiles?path={position.parent()}", headers={**headers, "If-None-Match": first.headers["ETag"]}
    )
    assert first.status_code == 200 and again.status_code == 304


def test_scanning_costs_a_point_and_reports_what_it_found(client):
    headers = register(client)
    before = me(client, headers)["player"]["ap"]
    response = send(client, headers, action="scan")
    assert response.status_code == 202
    assert response.json()["events"][0]["type"] == "SCAN_PERFORMED"
    assert me(client, headers)["player"]["ap"] == before - 1


def test_a_team_gives_the_player_a_faction(client, clean):
    """Criterion A1, second half."""
    headers = register(client)
    assert me(client, headers).get("player", {}).get("faction") in (None, 0, "")
    response = send(client, headers, action="create_team", name=f"Team {uuid4().hex[:8]}", faction_id=2)
    assert response.status_code == 202

    async def read() -> tuple:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session:
            row = (
                await session.execute(select(models.Player).order_by(models.Player.callsign).limit(1))
            ).scalar_one()
            result = (row.team_id, row.faction_id)
        await engine.dispose()
        return result

    team_id, faction_id = asyncio.run(read())
    assert team_id is not None and faction_id == 2


def test_standing_orders_can_be_changed_for_free(client, clean):
    headers = register(client)
    before = me(client, headers)["player"]["ap"]
    assert (
        send(
            client, headers, action="set_standing_orders", posture="aggressive", retreat_at_hull_pct=25
        ).status_code
        == 202
    )
    assert me(client, headers)["player"]["ap"] == before

    async def read() -> tuple:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session:
            row = (await session.execute(select(models.StandingOrders))).scalar_one()
            result = (row.posture, row.retreat_at_hull_pct)
        await engine.dispose()
        return result

    assert asyncio.run(read()) == ("aggressive", 25)


def test_repair_is_refused_away_from_a_station(client, clean):
    headers = register(client)

    async def damage() -> None:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session, session.begin():
            await session.execute(update(models.Ship).values(hull=40))
        await engine.dispose()

    asyncio.run(damage())
    assert send(client, headers, action="repair").json()["code"] == "NOT_DOCKED"

    send(client, headers, action="dock", station_id=home_station(client, headers)["id"])
    assert send(client, headers, action="repair").status_code == 202
    assert me(client, headers)["ship"]["hull"] == 100


def test_a_jump_beyond_the_hulls_range_is_refused(client, clean):
    """S3: a full tank does not make a distant system reachable."""
    import asyncio

    from frontier.adapters.db.engine import make_engine, make_sessionmaker

    headers = register(client)

    async def clip_the_range() -> None:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session, session.begin():
            await session.execute(update(models.Ship).values(jump_range_ly=1, fuel=60))
        await engine.dispose()

    asyncio.run(clip_the_range())

    position = HexAddr.parse(me(client, headers)["ship"]["position"])
    region = position.parent().parent()
    systems = client.get(f"/v1/map/tiles?path={region}", headers=headers).json()["entries"]
    elsewhere = next(e for e in systems if e["path"] != str(position.parent()))

    response = send(client, headers, action="jump", to_system=elsewhere["path"])

    assert response.status_code == 409
    assert response.json()["code"] == "BEYOND_JUMP_RANGE"
    assert me(client, headers)["ship"]["fuel"] == 60


def test_the_system_view_shows_what_is_in_sight_and_what_was_charted(client, clean):
    """UX §4.1: three layers, and the server decides all three."""
    headers = register(client)
    dashboard = me(client, headers)
    position = HexAddr.parse(dashboard["ship"]["position"])

    import asyncio

    from frontier.adapters.db.engine import make_engine, make_sessionmaker

    async def system_id() -> str:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session:
            ship = (
                await session.execute(select(models.Ship).where(models.Ship.player_id.is_not(None)))
            ).scalar_one()
            found = str(ship.system_id)
        await engine.dispose()
        return found

    body = client.get(f"/v1/systems/{asyncio.run(system_id())}", headers=headers).json()

    assert body["you"]["position"] == str(position)
    assert body["you"]["sensor_range"] >= 1
    assert body["system"]["path"] == str(position.parent())
    # Nothing void is ever listed, and every body is either in sight or previously charted.
    assert all(b["kind"] != "void" for b in body["bodies"])
    assert all(b["in_sight"] or b["charted_on"] is not None for b in body["bodies"])


def test_another_system_is_not_yours_to_look_inside(client, clean):
    headers = register(client)
    import asyncio

    from frontier.adapters.db.engine import make_engine, make_sessionmaker

    async def elsewhere() -> str:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session:
            ship = (
                await session.execute(select(models.Ship).where(models.Ship.player_id.is_not(None)))
            ).scalar_one()
            other = (
                await session.execute(
                    select(models.Location)
                    .where(models.Location.kind == "system", models.Location.id != ship.system_id)
                    .order_by(models.Location.path)
                    .limit(1)
                )
            ).scalar_one()
            found = str(other.id)
        await engine.dispose()
        return found

    assert client.get(f"/v1/systems/{asyncio.run(elsewhere())}", headers=headers).status_code == 404
    assert client.get(f"/v1/systems/{uuid4()}", headers=headers).status_code == 404


def test_a_distant_ship_is_a_contact_without_a_name(client, clean):
    """UX §4.2: partial means something is out there — not who, not what, not exactly where."""
    headers = register(client)
    import asyncio

    from frontier.adapters.db.engine import make_engine, make_sessionmaker
    from frontier.domain.hex.geometry import neighbours

    async def place_a_stranger() -> str:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session, session.begin():
            mine = (
                await session.execute(select(models.Ship).where(models.Ship.player_id.is_not(None)))
            ).scalar_one()
            # Three hexes out: inside a sensor range of 3, outside the half-range that names it.
            step = mine.position_path.tip
            for _ in range(3):
                step = neighbours(step)[0]
            session.add(
                models.Ship(
                    id=uuid4(),
                    player_id=None,
                    hull=80,
                    hull_max=80,
                    shields=0,
                    shields_max=0,
                    fuel=60,
                    fuel_max=60,
                    cargo_max=20,
                    sensor_range=2,
                    system_id=mine.system_id,
                    position_path=mine.position_path.sibling(step),
                )
            )
            found = str(mine.system_id)
        await engine.dispose()
        return found

    body = client.get(f"/v1/systems/{asyncio.run(place_a_stranger())}", headers=headers).json()

    assert body["contacts"], body
    partial = [c for c in body["contacts"] if c["quality"] == "partial"]
    assert partial
    for contact in partial:
        assert contact["name"] is None and contact["kind"] is None
        # The reported position is the system, not the hex it is really in.
        assert contact["position"] == body["system"]["path"]


def test_a_route_is_one_request_and_every_hop_is_charged(client, clean):
    """UX §5.3 / U4: one decision for the player, a sequence for the server."""
    headers = register(client)
    position = HexAddr.parse(me(client, headers)["ship"]["position"])
    hops = []
    walk = position
    for i in range(3):
        walk = walk.sibling(neighbours(walk.tip)[i % 6])
        hops.append({"action": "move", "to": str(walk), "idempotency_key": str(uuid4())})

    response = client.post("/v1/commands:batch", json={"commands": hops}, headers=headers)

    assert response.status_code == 202
    body = response.json()
    assert body["requested"] == 3 and body["accepted"] == 3
    assert body["stopped"] is None
    assert me(client, headers)["player"]["ap"] == 7
    assert me(client, headers)["ship"]["position"] == str(walk)


def test_a_route_that_runs_out_stops_and_says_where(client, clean):
    """A partial route is a result, not an error — the ship is somewhere real."""
    headers = register(client)
    position = HexAddr.parse(me(client, headers)["ship"]["position"])

    # Twelve hops on ten Action Points: it cannot finish, and must say so honestly.
    hops = []
    walk = position
    for i in range(12):
        walk = walk.sibling(neighbours(walk.tip)[i % 6])
        hops.append({"action": "move", "to": str(walk), "idempotency_key": str(uuid4())})

    body = client.post("/v1/commands:batch", json={"commands": hops}, headers=headers).json()

    assert body["accepted"] < body["requested"]
    assert body["stopped"]["code"] == "INSUFFICIENT_AP"
    assert body["stopped"]["at_step"] == body["accepted"]
    assert me(client, headers)["player"]["ap"] == 0


def test_a_batch_is_capped(client, clean):
    headers = register(client)
    position = HexAddr.parse(me(client, headers)["ship"]["position"])
    one = {
        "action": "move",
        "to": str(position.sibling(neighbours(position.tip)[0])),
        "idempotency_key": str(uuid4()),
    }
    assert (
        client.post("/v1/commands:batch", json={"commands": [one] * 21}, headers=headers).status_code == 422
    )
    assert client.post("/v1/commands:batch", json={"commands": []}, headers=headers).status_code == 422


def test_replaying_a_route_charges_nothing_twice(client, clean):
    """The keys are minted once per intent, so a retry finishes the route (UX §5.5)."""
    headers = register(client)
    walk = HexAddr.parse(me(client, headers)["ship"]["position"])
    hops = []
    for i in range(3):
        walk = walk.sibling(neighbours(walk.tip)[i % 6])
        hops.append({"action": "move", "to": str(walk), "idempotency_key": str(uuid4())})

    client.post("/v1/commands:batch", json={"commands": hops}, headers=headers)
    again = client.post("/v1/commands:batch", json={"commands": hops}, headers=headers).json()

    assert again["accepted"] == 3 and again["stopped"] is None
    assert me(client, headers)["player"]["ap"] == 7
    assert me(client, headers)["ship"]["position"] == str(walk)


def test_rules_serve_costs_without_leaking_the_tuning(client, clean):
    """The client shows a cost before commitment, so it must read costs, not invent them (C4)."""
    headers = register(client)

    body = client.get("/v1/rules", headers=headers).json()

    assert body["ap"]["cost"]["move_hex"] >= 0
    assert body["ap"]["daily_grant"] == 10
    assert body["world"]["fuel_per_jump_ly"] >= 0
    assert "continuity" not in body and "combat" not in body and "npc" not in body


def test_rules_need_an_account(client, clean):
    assert client.get("/v1/rules").status_code == 401


def test_a_system_reports_its_extent(client, clean):
    """The board clips to the rim, so it must be told where the rim is — UX §4.1."""
    headers = register(client)
    position = HexAddr.parse(me(client, headers)["ship"]["position"])
    system_path = position.parent()
    assert system_path is not None

    tile = client.get("/v1/map/tiles", params={"path": str(system_path.parent())}, headers=headers).json()
    entry = next(e for e in tile["entries"] if e["path"] == str(system_path))
    view = client.get(f"/v1/systems/{entry['id']}", headers=headers).json()

    radius = view["system"]["radius"]
    assert radius > 0
    # Every charted body sits inside the rim the client is told about.
    for body in view["bodies"]:
        assert max(abs(body["q"]), abs(body["r"]), abs(body["q"] + body["r"])) <= radius


def test_moving_past_the_rim_is_refused(client, clean):
    """What the board must never offer: the refusal the clipping exists to prevent."""
    headers = register(client)
    position = HexAddr.parse(me(client, headers)["ship"]["position"])
    far = position.sibling(Axial(99, 0))

    outcome = client.post(
        "/v1/commands",
        json={"action": "move", "to": str(far), "idempotency_key": str(uuid4())},
        headers=headers,
    )

    assert outcome.status_code == 409
    assert outcome.json()["code"] == "UNKNOWN_DESTINATION"


def _dock(client, headers) -> str:
    """Berth at the station a new account spawns on. Returns its id."""
    station = home_station(client, headers)
    send(client, headers, action="dock", station_id=station["id"])
    return str(station["id"])


def test_a_market_shows_both_sides_of_the_spread(client, clean):
    """The cost of a round trip must be legible, not discovered — UX §6."""
    headers = register(client)
    station_id = _dock(client, headers)

    body = client.get(f"/v1/stations/{station_id}/market", headers=headers).json()

    assert body["you"]["docked"] is True
    assert body["you"]["hold_max"] > 0
    assert body["commodities"], "a station with no market is not a station"
    for line in body["commodities"]:
        assert line["buy"] > line["sell"], "buying must cost more than selling returns"
        assert line["stock"] >= 0


def test_a_market_you_are_not_docked_at_is_not_yours_to_read(client, clean):
    headers = register(client)
    other = register(client)  # standing on the same station hex, but not berthed
    station_id = _dock(client, headers)

    # Standing beside a berth is not standing in it, and both answers match an id that does
    # not exist at all (D-52).
    away = client.get(f"/v1/stations/{station_id}/market", headers=other)
    missing = client.get(f"/v1/stations/{uuid4()}/market", headers=headers)

    assert away.status_code == 404
    assert missing.status_code == 404
    assert away.json() == missing.json()


def test_buying_moves_credits_stock_and_the_hold(client, clean):
    headers = register(client)
    station_id = _dock(client, headers)
    before = client.get(f"/v1/stations/{station_id}/market", headers=headers).json()
    line = next(c for c in before["commodities"] if c["stock"] >= 2)

    send(client, headers, action="buy", commodity=line["commodity"], qty=2)

    after = client.get(f"/v1/stations/{station_id}/market", headers=headers).json()
    bought = next(c for c in after["commodities"] if c["commodity"] == line["commodity"])
    assert bought["held"] == 2
    assert bought["avg_paid"] == line["buy"]
    assert bought["stock"] == line["stock"] - 2
    assert after["you"]["credits"] == before["you"]["credits"] - line["buy"] * 2
    assert after["you"]["hold_used"] == before["you"]["hold_used"] + 2

    # The hold travels with the ship, so it is readable away from the station too.
    assert {"commodity": line["commodity"], "qty": 2, "avg_paid": line["buy"]} in me(client, headers)["cargo"]


def test_buying_more_than_the_hold_takes_is_refused(client, clean):
    headers = register(client)
    station_id = _dock(client, headers)
    body = client.get(f"/v1/stations/{station_id}/market", headers=headers).json()
    line = next(c for c in body["commodities"] if c["stock"] > 0)

    refusal = send(
        client, headers, action="buy", commodity=line["commodity"], qty=body["you"]["hold_max"] + 1
    )

    assert refusal.status_code == 409
    assert refusal.json()["code"] in {"CARGO_FULL", "INSUFFICIENT_STOCK", "INSUFFICIENT_CREDITS"}


def test_the_repair_quote_is_what_is_charged(client, clean):
    """The station screen shows a price before commitment, so it must be the real one."""
    headers = register(client)
    station_id = _dock(client, headers)

    async def damage() -> None:
        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session, session.begin():
            await session.execute(update(models.Ship).values(hull=60))
        await engine.dispose()

    asyncio.run(damage())
    quoted = client.get(f"/v1/stations/{station_id}/market", headers=headers).json()
    before = quoted["you"]["credits"]

    send(client, headers, action="repair")

    after = client.get(f"/v1/stations/{station_id}/market", headers=headers).json()
    assert quoted["you"]["repair_cost"] > 0
    assert after["you"]["hull"] == after["you"]["hull_max"]
    assert after["you"]["credits"] == before - quoted["you"]["repair_cost"]
    assert after["you"]["repair_cost"] == 0


def test_a_player_can_find_a_crew_to_join(client, clean):
    """`join_team` needs an id, so there must be a way to learn one — GDD §6."""
    founder = register(client)
    send(client, founder, action="create_team", name="The Long Haul", faction_id=2)

    joiner = register(client)
    listing = client.get("/v1/teams", headers=joiner).json()

    crew = next(t for t in listing["teams"] if t["name"] == "The Long Haul")
    assert listing["yours"] is None
    assert crew["faction_id"] == 2 and crew["members"] == 1

    assert send(client, joiner, action="join_team", team_id=crew["id"]).status_code == 202
    after = me(client, joiner)["player"]
    assert after["team_id"] == crew["id"]
    assert after["team_name"] == "The Long Haul"
    assert client.get("/v1/teams", headers=joiner).json()["yours"] == crew["id"]


def test_an_independent_player_has_no_crew_and_no_faction(client, clean):
    """A player is independent until they join something — GDD §6, decision S2."""
    headers = register(client)

    player = me(client, headers)["player"]

    assert player["team_id"] is None
    assert player["team_name"] is None
    assert player["faction_id"] is None


def test_every_event_is_stamped_with_the_channel_it_arrived_on(client, clean):
    """The client filters by channel, so the server must say which one — UX §7."""
    headers = register(client)
    send(client, headers, action="send_message", channel="local", text="Anyone out here?")

    events = client.get("/v1/feed", headers=headers).json()["events"]

    assert events, "a message the player just sent must be in their own feed"
    assert all("channel" in event for event in events)
    spoken = next(e for e in events if e["type"] == "MESSAGE")
    assert spoken["channel"] in {"local", "system", "personal", "team", "universe"}


def test_a_message_carries_to_a_pilot_standing_alongside(client, clean):
    headers = register(client)
    neighbour = register(client)

    send(client, headers, action="send_message", channel="local", text="Mind the rocks.")

    heard = client.get("/v1/feed", headers=neighbour).json()["events"]
    assert any(e["type"] == "MESSAGE" for e in heard)


def test_a_message_names_who_said_it(client, clean):
    """A chat line with no speaker is not chat — UX §7."""
    headers = register(client)
    mine = me(client, headers)["player"]["callsign"]

    send(client, headers, action="send_message", channel="local", text="Rocks ahead.")

    spoken = next(
        e for e in client.get("/v1/feed", headers=headers).json()["events"] if e["type"] == "MESSAGE"
    )
    assert spoken["payload"]["from"] == mine
    assert spoken["payload"]["text"] == "Rocks ahead."


def my_system(client, headers) -> str:
    """The id of the system the player is in, found the way the client finds it."""
    position = HexAddr.parse(me(client, headers)["ship"]["position"])
    system = position.parent()
    assert system is not None
    tile = client.get("/v1/map/tiles", params={"path": str(system.parent())}, headers=headers).json()
    return str(next(e for e in tile["entries"] if e["path"] == str(system))["id"])


def test_only_a_resolved_contact_hands_out_a_ship_id(client, clean):
    """`attack` targets an id, so the id is the thing that must not leak — UX §4.2."""
    headers = register(client)
    system = client.get(f"/v1/systems/{my_system(client, headers)}", headers=headers).json()

    for contact in system["contacts"]:
        if contact["quality"] == "full":
            assert contact["ship_id"], "a resolved contact can be targeted"
        else:
            assert contact["ship_id"] is None, "a vague sighting is not a handle on a ship"


def test_standing_orders_can_be_read_before_they_are_written(client, clean):
    """A form that opens blank would overwrite orders the player set weeks ago — GDD §4.4."""
    headers = register(client)

    # A new account starts cautious: it loses cargo, not a ship (GDD §4.4).
    untouched = client.get("/v1/orders", headers=headers).json()
    assert untouched["posture"] == "evade"
    assert untouched["retreat_at_hull_pct"] == 50

    send(
        client,
        headers,
        action="set_standing_orders",
        posture="aggressive",
        engage_hostile=True,
        retreat_at_hull_pct=25,
        auto_reply="Not today.",
    )

    written = client.get("/v1/orders", headers=headers).json()
    assert written["posture"] == "aggressive"
    assert written["engage_hostile"] is True
    assert written["retreat_at_hull_pct"] == 25
    assert written["auto_reply"] == "Not today."


def test_the_ship_reports_its_shields(client, clean):
    ship = me(client, register(client))["ship"]
    assert "shields" in ship and "shields_max" in ship


def test_a_contact_can_be_carried_into_an_attack(client, clean):
    """The whole client path: see a ship, take its id, fire at it — nothing else is needed."""
    attacker = register(client)
    register(client)  # spawns alongside, in weapons reach

    seen = client.get(f"/v1/systems/{my_system(client, attacker)}", headers=attacker).json()
    target = next(c for c in seen["contacts"] if c["quality"] == "full")

    fired = send(client, attacker, action="attack", target_ship_id=target["ship_id"])

    assert fired.status_code == 202
    assert any(e["type"] == "COMBAT_STARTED" for e in fired.json()["events"])
    # Player against player is queued, so neither side is punished for being the one asleep.
    assert me(client, attacker)["player"]["ap"] == 8


def test_firing_on_yourself_is_refused(client, clean):
    headers = register(client)
    own = me(client, headers)["ship"]["id"]

    assert send(client, headers, action="attack", target_ship_id=own).json()["code"] == "SELF_TARGET"
