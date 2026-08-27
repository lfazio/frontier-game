from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Response

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer
from frontier.adapters.api.errors import rejection
from frontier.adapters.api.schemas import CommandBody, MoveBody
from frontier.application.commands.base import Command
from frontier.application.commands.move import MoveCommand
from frontier.application.commands.send_message import Channel, SendMessageCommand
from frontier.domain.hex.coordinates import HexAddr

router = APIRouter(prefix="/v1", tags=["commands"])


@router.post("/commands", status_code=202)
async def submit(
    body: CommandBody,
    response: Response,
    player_id: CurrentPlayer,
    c: ContainerDep,
) -> object:
    result = await c.executor.execute(_build(body), player_id)
    if result.rejection is not None:
        return rejection(result.rejection)
    if result.replayed:
        response.headers["Idempotent-Replay"] = "true"
    return result.as_dict()


def _build(body: CommandBody) -> Command:
    if isinstance(body, MoveBody):
        return MoveCommand(id=uuid4(), idempotency_key=body.idempotency_key, to=HexAddr.parse(body.to))
    return SendMessageCommand(
        id=uuid4(),
        idempotency_key=body.idempotency_key,
        channel=Channel(body.channel),
        text=body.text,
    )
