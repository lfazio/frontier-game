"""The live feed — SDD §8.3.

Two rules govern this file. A client may *ask* for a channel; it may never assert entitlement to
one. And every frame passes through `render_for` before serialisation, so the socket cannot leak
what the HTTP feed would redact.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from frontier.adapters.api.security import read_token
from frontier.adapters.db.feed import viewer_for
from frontier.application.visibility import render_for, stamp_view
from frontier.domain.events.model import Event, Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.domain.hex.coordinates import HexAddr

log = logging.getLogger(__name__)
router = APIRouter(tags=["stream"])

ALLOWED_CHANNELS = frozenset({"local", "system", "team", "personal", "universe"})


def from_wire(message: dict[str, Any]) -> Event:
    return Event(
        id=UUID(message["id"]),
        world_day=message["world_day"],
        occurred_at=datetime.fromisoformat(message["occurred_at"]),
        type=EventType(message["type"]),
        origin=HexAddr.parse(message["origin"]),
        scope=Scope(message["scope"]),
        visibility=Visibility(message["visibility"]),
        severity=Severity(message["severity"]),
        participants=frozenset(UUID(p) for p in message["participants"]),
        payload=message["payload"],
        ruleset_version=message["ruleset_version"],
    )


def channel_of(event: Event) -> str:
    if event.visibility is Visibility.TEAM:
        return "team"
    if event.visibility is Visibility.PARTICIPANTS:
        return "personal"
    if event.scope >= Scope.REGION:
        return "universe"
    if event.scope >= Scope.SYSTEM:
        return "system"
    return "local"


@router.websocket("/v1/stream")
async def stream(websocket: WebSocket, token: str = Query(...)) -> None:
    container = websocket.app.state.container
    try:
        player_id = read_token(token, container.settings.jwt_secret)
    except jwt.PyJWTError:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    channels = set(ALLOWED_CHANNELS)
    ready = asyncio.Event()
    pump = asyncio.create_task(_pump(websocket, container, player_id, channels, ready))
    # Live delivery starts only once the subscription exists; until then a client that fetched
    # its gap over HTTP could miss events published in between. Waiting on the event alone would
    # hang forever if the pump died before setting it, so wait on whichever happens first.
    waiter = asyncio.ensure_future(ready.wait())
    done, _ = await asyncio.wait({pump, waiter}, return_when=asyncio.FIRST_COMPLETED)
    if pump in done:
        waiter.cancel()
        log.exception("event pump failed to start", exc_info=pump.exception())
        await websocket.close(code=1011)
        return
    await websocket.send_json({"op": "ready"})
    try:
        while True:
            message = await websocket.receive_json()
            op = message.get("op")
            if op == "subscribe":
                # The server decides entitlement; the client only expresses interest.
                channels.clear()
                channels.update(set(message.get("channels", [])) & ALLOWED_CHANNELS)
                await websocket.send_json({"op": "subscribed", "channels": sorted(channels)})
            elif op == "ping":
                await websocket.send_json({"op": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        pump.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump


async def _pump(
    websocket: WebSocket, container: Any, player_id: UUID, channels: set[str], ready: asyncio.Event
) -> None:
    rules = container.executor.rules
    async for message in container.bus.listen(ready):
        event = from_wire(message)
        if channel_of(event) not in channels:
            continue
        async with container.sessions() as session:
            viewer = await viewer_for(
                session, player_id, rules.world.sensor_range_base, rules.world.radio_range_base
            )
        view = render_for(viewer, event)
        if view is None:
            continue
        await websocket.send_json({"op": "event", "event": stamp_view(view)})
