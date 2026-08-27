from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException

from frontier.adapters.api.deps import ContainerDep
from frontier.adapters.api.schemas import LoginRequest, RegisterRequest, TokenResponse
from frontier.adapters.api.security import hash_password, issue_token, verify_password
from frontier.adapters.memory.store import Account, MemoryPlayer
from frontier.config.container import Container
from frontier.domain.fleet.ship import Ship
from frontier.worldgen.fixture import STARTING_SHIP, starting_position

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, c: ContainerDep) -> TokenResponse:
    world = c.world
    if any(a.email == body.email for a in world.accounts.values()):
        raise HTTPException(status_code=409, detail="EMAIL_TAKEN")
    if any(p.callsign == body.callsign for p in world.players.values()):
        raise HTTPException(status_code=409, detail="CALLSIGN_TAKEN")

    player = MemoryPlayer(id=uuid4(), callsign=body.callsign, ap_balance=c.executor.rules.ap.daily_grant)
    world.players[player.id] = player
    world.accounts[player.id] = Account(
        id=uuid4(), email=body.email, password_hash=hash_password(body.password), player_id=player.id
    )
    ship = Ship(id=uuid4(), player_id=player.id, position=starting_position(), **STARTING_SHIP)
    world.ships[ship.id] = ship
    return _token(c, player.id)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, c: ContainerDep) -> TokenResponse:
    account = next((a for a in c.world.accounts.values() if a.email == body.email), None)
    if account is None or not verify_password(account.password_hash, body.password):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    return _token(c, account.player_id)


def _token(c: Container, player_id: object) -> TokenResponse:
    ttl = c.settings.jwt_ttl_seconds
    return TokenResponse(
        access_token=issue_token(player_id, c.settings.jwt_secret, ttl, c.clock),  # type: ignore[arg-type]
        expires_in=ttl,
        player_id=player_id,  # type: ignore[arg-type]
    )
