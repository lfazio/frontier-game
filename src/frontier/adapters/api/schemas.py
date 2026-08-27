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


CommandBody = Annotated[MoveBody | SendMessageBody, Field(discriminator="action")]
