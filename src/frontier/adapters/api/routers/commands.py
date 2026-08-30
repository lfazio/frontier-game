from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Response

from frontier.adapters.api import schemas
from frontier.adapters.api.deps import ContainerDep, CurrentPlayer
from frontier.adapters.api.errors import rejection
from frontier.adapters.api.schemas import CommandBody
from frontier.application.commands.base import Command
from frontier.application.commands.combat import AttackCommand, SetStandingOrdersCommand
from frontier.application.commands.missions import (
    AcceptMissionCommand,
    CompleteMissionCommand,
)
from frontier.application.commands.move import MoveCommand
from frontier.application.commands.navigation import JumpCommand, ScanCommand
from frontier.application.commands.send_message import (
    SendMessageCommand,
    channel_or_none,
)
from frontier.application.commands.teams import (
    CreateTeamCommand,
    DefectCommand,
    JoinTeamCommand,
    LeaveTeamCommand,
)
from frontier.application.commands.trade import (
    DockCommand,
    LaunchCommand,
    ReadCommand,
    RepairCommand,
    TradeCommand,
)
from frontier.domain.fleet.standing_orders import Posture, StandingOrders
from frontier.domain.hex.coordinates import HexAddr

router = APIRouter(prefix="/v1", tags=["commands"])


@router.post("/commands", status_code=202)
async def submit(
    body: CommandBody,
    response: Response,
    player_id: CurrentPlayer,
    c: ContainerDep,
) -> object:
    result = await c.executor.execute(build(body), player_id)
    if result.rejection is not None:
        return rejection(result.rejection)
    if result.replayed:
        response.headers["Idempotent-Replay"] = "true"
    return result.as_dict()


@router.post("/commands:batch", status_code=202)
async def submit_batch(
    body: schemas.BatchBody,
    player_id: CurrentPlayer,
    c: ContainerDep,
) -> dict[str, Any]:
    """Run a sequence, stopping at the first refusal.

    Every hop is still evaluated and charged on its own, so a route can end early. That is a
    result, not a failure: the caller is told how far it got and why it stopped, and the ship is
    somewhere real either way (UX §5.3).
    """
    events: list[dict[str, Any]] = []
    stopped: dict[str, Any] | None = None
    accepted = 0

    for item in body.commands:
        outcome = await c.executor.execute(build(item), player_id)
        if outcome.rejection is not None:
            stopped = {
                "code": outcome.rejection.code.value,
                "context": outcome.rejection.context,
                "at_step": accepted,
            }
            break
        accepted += 1
        events.extend(outcome.as_dict()["events"])

    return {
        "requested": len(body.commands),
        "accepted": accepted,
        "stopped": stopped,
        "events": events,
    }


def build(body: CommandBody) -> Command:
    """One place turns a validated request into a command; the union keeps it exhaustive."""
    new_id, key = uuid4(), body.idempotency_key
    match body:
        case schemas.MoveBody():
            return MoveCommand(id=new_id, idempotency_key=key, to=HexAddr.parse(body.to))
        case schemas.JumpBody():
            return JumpCommand(id=new_id, idempotency_key=key, to_system=HexAddr.parse(body.to_system))
        case schemas.ScanBody():
            return ScanCommand(id=new_id, idempotency_key=key)
        case schemas.DockBody():
            return DockCommand(id=new_id, idempotency_key=key, station_id=body.station_id)
        case schemas.LaunchBody():
            return LaunchCommand(id=new_id, idempotency_key=key)
        case schemas.TradeBody():
            return TradeCommand(
                id=new_id,
                idempotency_key=key,
                commodity=body.commodity,
                qty=body.qty,
                selling=body.action == "sell",
            )
        case schemas.ReadBody():
            return ReadCommand(id=new_id, idempotency_key=key, commodity=body.commodity)
        case schemas.RepairBody():
            return RepairCommand(id=new_id, idempotency_key=key)
        case schemas.AttackBody():
            return AttackCommand(id=new_id, idempotency_key=key, target_ship_id=body.target_ship_id)
        case schemas.SendMessageBody():
            return SendMessageCommand(
                id=new_id,
                idempotency_key=key,
                channel=channel_or_none(body.channel),
                text=body.text,
            )
        case schemas.StandingOrdersBody():
            return SetStandingOrdersCommand(
                id=new_id,
                idempotency_key=key,
                orders=StandingOrders(
                    posture=Posture(body.posture),
                    engage_hostile=body.engage_hostile,
                    engage_above_cargo=body.engage_above_cargo,
                    retreat_at_hull_pct=body.retreat_at_hull_pct,
                    auto_reply=body.auto_reply,
                ),
            )
        case schemas.MissionBody():
            if body.action == "accept_mission":
                return AcceptMissionCommand(id=new_id, idempotency_key=key, mission_id=body.mission_id)
            return CompleteMissionCommand(id=new_id, idempotency_key=key, mission_id=body.mission_id)
        case schemas.DefectBody():
            return DefectCommand(id=new_id, idempotency_key=key, to_faction_id=body.to_faction_id)
        case schemas.CreateTeamBody():
            return CreateTeamCommand(
                id=new_id, idempotency_key=key, name=body.name, faction_id=body.faction_id
            )
        case schemas.JoinTeamBody():
            return JoinTeamCommand(id=new_id, idempotency_key=key, team_id=body.team_id)
        case _:
            return LeaveTeamCommand(id=new_id, idempotency_key=key)
