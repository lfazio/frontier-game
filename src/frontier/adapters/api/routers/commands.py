from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Response

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer
from frontier.adapters.api.errors import rejection
from frontier.adapters.api.schemas import CommandBody
from frontier.application.commands.move import MoveCommand
from frontier.domain.hex.coordinates import HexAddr

router = APIRouter(prefix="/v1", tags=["commands"])


@router.post("/commands", status_code=202)
async def submit(
    body: CommandBody,
    response: Response,
    player_id: CurrentPlayer,
    c: ContainerDep,
) -> object:
    command = MoveCommand(id=uuid4(), idempotency_key=body.idempotency_key, to=HexAddr.parse(body.to))
    result = await c.executor.execute(command, player_id)
    if result.rejection is not None:
        return rejection(result.rejection)
    if result.replayed:
        response.headers["Idempotent-Replay"] = "true"
    return result.as_dict()
