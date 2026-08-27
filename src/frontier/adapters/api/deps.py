from __future__ import annotations

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from frontier.adapters.api.security import read_token
from frontier.config.container import Container

bearer = HTTPBearer(auto_error=False)


def container(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]


Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def current_player(request: Request, credentials: Credentials) -> UUID:
    if credentials is None:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    try:
        return read_token(credentials.credentials, container(request).settings.jwt_secret)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED") from exc


CurrentPlayer = Annotated[UUID, Depends(current_player)]
ContainerDep = Annotated[Container, Depends(container)]
