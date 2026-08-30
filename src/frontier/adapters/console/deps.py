"""What a console request carries: an operator, a world, and a permission on it.

Nothing here imports the player API's dependencies. The two surfaces share password hashing and
JWT mechanics and nothing else, which is what keeps "an operator account is not a player
account" true in code as well as in prose (ADMIN §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from frontier.adapters.api.security import read_console_token
from frontier.adapters.db import models
from frontier.config.settings import Settings
from frontier.domain.rules.ruleset import RuleSet

bearer = HTTPBearer(auto_error=False)

# Ordered: a later permission carries everything an earlier one does. `origin` is not a rank —
# it is the operator a world falls back on, and it outranks everything by construction.
RANKS = ("watch", "operate", "directorate", "origin")


@dataclass(frozen=True, slots=True)
class Console:
    settings: Settings
    sessions: async_sessionmaker[AsyncSession]
    worlds: tuple[str, ...]
    # The console reads the same rule data the world runs on: it explains what a number means
    # (an age closes at this severity) and, later, what turning a dial would change.
    rules: RuleSet


def console(request: Request) -> Console:
    return request.app.state.console  # type: ignore[no-any-return]


Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
ConsoleDep = Annotated[Console, Depends(console)]


def current_operator(request: Request, credentials: Credentials) -> UUID:
    if credentials is None:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    try:
        return read_console_token(credentials.credentials, console(request).settings.admin_jwt_secret)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED") from exc


CurrentOperator = Annotated[UUID, Depends(current_operator)]


async def permission_on(session: AsyncSession, operator_id: UUID, world: str) -> str | None:
    return (
        await session.execute(
            select(models.Grant.permission).where(
                models.Grant.operator_id == operator_id, models.Grant.world == world
            )
        )
    ).scalar_one_or_none()


def at_least(held: str | None, wanted: str) -> bool:
    """`origin` clears everything; otherwise a permission carries the ones below it."""
    if held is None:
        return False
    if held == "origin":
        return True
    return RANKS.index(held) >= RANKS.index(wanted)


async def require(session: AsyncSession, operator_id: UUID, world: str, wanted: str) -> str:
    """A world this operator may not touch answers as a world that is not there.

    The same `404` an unknown world gets, so the set of worlds a deployment runs cannot be
    mapped by an operator who holds one of them.
    """
    held = await permission_on(session, operator_id, world)
    if not at_least(held, wanted):
        raise HTTPException(status_code=404, detail="Not Found")
    return held or ""
