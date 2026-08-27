"""One merged feed, redacted per viewer, and the live socket — tasks 2.5 and 2.6."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from frontier.adapters.api.app import create_app
from frontier.adapters.bus.outbox import OutboxRelay
from frontier.adapters.bus.redis_bus import RedisBus
from frontier.adapters.db import models
from frontier.config.container import build_sql
from frontier.domain.hex.coordinates import HexAddr
from frontier.domain.hex.geometry import neighbours

pytestmark = pytest.mark.integration


@pytest.fixture
def client(clean):
    with TestClient(create_app(build_sql(clean))) as test_client:
        yield test_client


def register(client) -> tuple[dict[str, str], str]:
    response = client.post(
        "/v1/auth/register",
        json={
            "email": f"{uuid4().hex}@x.io",
            "password": "correct horse battery",
            "callsign": uuid4().hex[:12],
        },
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, token


def say(client, headers, text="Pirates in Sirius.", channel="local"):
    return client.post(
        "/v1/commands",
        json={
            "action": "send_message",
            "channel": channel,
            "text": text,
            "idempotency_key": str(uuid4()),
        },
        headers=headers,
    )


def test_chat_and_movement_share_one_ordered_feed(client):
    headers, _ = register(client)
    position = HexAddr.parse(client.get("/v1/me", headers=headers).json()["ship"]["position"])
    client.post(
        "/v1/commands",
        json={
            "action": "move",
            "to": str(position.sibling(neighbours(position.tip)[0])),
            "idempotency_key": str(uuid4()),
        },
        headers=headers,
    )
    say(client, headers)

    events = client.get("/v1/feed", headers=headers).json()["events"]

    assert [e["type"] for e in events] == ["MESSAGE", "SHIP_ENTERED"]
    assert events[0]["id"] > events[1]["id"]  # UUIDv7 orders the merge


def test_the_cursor_pages_backwards_without_repeating(client):
    headers, _ = register(client)
    for i in range(3):
        say(client, headers, text=f"message {i}")

    first = client.get("/v1/feed?limit=2", headers=headers).json()
    rest = client.get(f"/v1/feed?after={first['cursor']}", headers=headers).json()

    assert len(first["events"]) == 2
    assert all(e["id"] != first["cursor"] for e in rest["events"])


def test_a_distant_player_does_not_receive_the_message(client, clean):
    """Criterion A9 across the wire: out of range is absent, not filtered."""
    speaker, _ = register(client)
    listener, _ = register(client)

    async def move_listener_far_away() -> None:
        from frontier.adapters.db.engine import make_engine, make_sessionmaker

        engine = make_engine(clean.database_url)
        async with make_sessionmaker(engine)() as session, session.begin():
            far = (
                await session.execute(
                    select(models.Location)
                    .where(models.Location.kind == "system")
                    .order_by(models.Location.path.desc())
                    .limit(1)
                )
            ).scalar_one()
            hex_ = (
                await session.execute(
                    select(models.Location).where(models.Location.parent_id == far.id).limit(1)
                )
            ).scalar_one()
            ship = (
                await session.execute(select(models.Ship).order_by(models.Ship.id.desc()).limit(1))
            ).scalar_one()
            ship.system_id, ship.position_path = far.id, hex_.path
        await engine.dispose()

    asyncio.run(move_listener_far_away())
    say(client, speaker)

    assert client.get("/v1/feed", headers=listener).json()["events"] == []
    assert len(client.get("/v1/feed", headers=speaker).json()["events"]) == 1


def test_the_socket_delivers_a_committed_event(client, clean):
    """Task 2.5: subscribe, act, relay, receive — all rendered per viewer."""
    headers, token = register(client)

    with client.websocket_connect(f"/v1/stream?token={token}") as ws:
        assert ws.receive_json() == {"op": "ready"}
        ws.send_json({"op": "subscribe", "channels": ["local"]})
        assert ws.receive_json()["op"] == "subscribed"

        say(client, headers, text="Convoy departing.")

        async def relay() -> int:
            from frontier.adapters.db.engine import make_engine, make_sessionmaker

            engine = make_engine(clean.database_url)
            bus = RedisBus(clean.redis_url)
            count = await OutboxRelay(make_sessionmaker(engine), bus).drain_once()
            await bus.close()
            await engine.dispose()
            return count

        assert asyncio.run(relay()) == 1
        frame = ws.receive_json()

    assert frame["op"] == "event"
    assert frame["event"]["type"] == "MESSAGE"
    assert frame["event"]["payload"]["text"] == "Convoy departing."


def test_a_socket_without_a_valid_token_is_closed(client):
    with (
        pytest.raises(Exception),  # noqa: B017 — starlette raises on a 4401 close
        client.websocket_connect("/v1/stream?token=not-a-token") as ws,
    ):
        ws.receive_json()


def test_an_unknown_channel_is_dropped_not_honoured(client):
    """A client may ask for a channel; it may not assert entitlement to one."""
    _, token = register(client)
    with client.websocket_connect(f"/v1/stream?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"op": "subscribe", "channels": ["local", "continuity"]})
        assert ws.receive_json()["channels"] == ["local"]
