from __future__ import annotations

from fastapi import APIRouter, HTTPException

from frontier.adapters.api.deps import ContainerDep
from frontier.adapters.api.schemas import LoginRequest, RegisterRequest, TokenResponse
from frontier.adapters.api.security import issue_token
from frontier.adapters.registrar import Taken
from frontier.config.container import Container

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, c: ContainerDep) -> TokenResponse:
    try:
        player_id = await c.registrar.register(body.email, body.password, body.callsign)
    except Taken as taken:
        raise HTTPException(status_code=409, detail=f"{taken.field.upper()}_TAKEN") from taken
    return _token(c, player_id)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, c: ContainerDep) -> TokenResponse:
    player_id = await c.registrar.authenticate(body.email, body.password)
    if player_id is None:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    return _token(c, player_id)


def _token(c: Container, player_id: object) -> TokenResponse:
    ttl = c.settings.jwt_ttl_seconds
    return TokenResponse(
        access_token=issue_token(player_id, c.settings.jwt_secret, ttl, c.clock),  # type: ignore[arg-type]
        expires_in=ttl,
        player_id=player_id,  # type: ignore[arg-type]
    )
