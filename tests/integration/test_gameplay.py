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
from frontier.domain.hex.geometry import neighbours

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
