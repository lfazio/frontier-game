"""Password hashing and bearer tokens."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from frontier.adapters.clock import SystemClock

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(hashed: str, password: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except VerifyMismatchError:
        return False


def issue_token(player_id: UUID, secret: str, ttl_seconds: int, clock: SystemClock) -> str:
    now = clock.now()
    payload = {"sub": str(player_id), "iat": now, "exp": now + timedelta(seconds=ttl_seconds)}
    return jwt.encode(payload, secret, algorithm="HS256")


def read_token(token: str, secret: str) -> UUID:
    claims = jwt.decode(token, secret, algorithms=["HS256"])
    return UUID(claims["sub"])
