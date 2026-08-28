"""Wire models. Untrusted input stops here — GDD §10.4 C1."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from frontier.domain.hex.coordinates import HexAddr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    callsign: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9 ._-]+$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    player_id: UUID


class MoveBody(BaseModel):
    action: Literal["move"]
    to: str
    idempotency_key: UUID

    @field_validator("to")
    @classmethod
    def _parsable(cls, value: str) -> str:
        HexAddr.parse(value)
        return value


class SendMessageBody(BaseModel):
    action: Literal["send_message"]
    channel: Literal["local", "system", "team"]
    text: str = Field(min_length=1, max_length=500)
    idempotency_key: UUID


class JumpBody(BaseModel):
    action: Literal["jump"]
    to_system: str
    idempotency_key: UUID

    @field_validator("to_system")
    @classmethod
    def _parsable(cls, value: str) -> str:
        HexAddr.parse(value)
        return value


class ScanBody(BaseModel):
    action: Literal["scan"]
    idempotency_key: UUID


class DockBody(BaseModel):
    action: Literal["dock"]
    station_id: UUID
    idempotency_key: UUID


class LaunchBody(BaseModel):
    action: Literal["launch"]
    idempotency_key: UUID


class TradeBody(BaseModel):
    action: Literal["buy", "sell"]
    commodity: str = Field(min_length=1, max_length=24)
    qty: int = Field(ge=1, le=10_000)
    idempotency_key: UUID


class RepairBody(BaseModel):
    action: Literal["repair"]
    idempotency_key: UUID


class AttackBody(BaseModel):
    action: Literal["attack"]
    target_ship_id: UUID
    idempotency_key: UUID


class StandingOrdersBody(BaseModel):
    action: Literal["set_standing_orders"]
    posture: Literal["evade", "defend", "aggressive", "surrender_cargo"]
    engage_hostile: bool = False
    engage_above_cargo: int | None = None
    retreat_at_hull_pct: int = Field(default=50, ge=0, le=100)
    auto_reply: str | None = Field(default=None, max_length=200)
    idempotency_key: UUID


class CreateTeamBody(BaseModel):
    action: Literal["create_team"]
    name: str = Field(min_length=3, max_length=64)
    faction_id: Literal[1, 2, 3]
    idempotency_key: UUID


class JoinTeamBody(BaseModel):
    action: Literal["join_team"]
    team_id: UUID
    idempotency_key: UUID


class LeaveTeamBody(BaseModel):
    action: Literal["leave_team"]
    idempotency_key: UUID


class MissionBody(BaseModel):
    action: Literal["accept_mission", "complete_mission"]
    mission_id: UUID
    idempotency_key: UUID


class DefectBody(BaseModel):
    action: Literal["defect"]
    to_faction_id: Literal[1, 2, 3]
    idempotency_key: UUID


class BatchBody(BaseModel):
    """A route is one decision for the player and a sequence for the server (UX §5.3)."""

    commands: list[CommandItem] = Field(min_length=1, max_length=20)


CommandBody = Annotated[
    MoveBody
    | JumpBody
    | ScanBody
    | DockBody
    | LaunchBody
    | TradeBody
    | RepairBody
    | AttackBody
    | SendMessageBody
    | StandingOrdersBody
    | CreateTeamBody
    | JoinTeamBody
    | LeaveTeamBody
    | MissionBody
    | DefectBody,
    Field(discriminator="action"),
]


CommandItem = CommandBody
BatchBody.model_rebuild()
