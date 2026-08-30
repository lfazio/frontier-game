"""The operator console — a separate application, on its own port. ADMIN §2.

It is not a privileged corner of the player API. Exposing the game does not expose this, and no
router here is reachable from `/v1`: they are different ASGI applications that happen to share a
database. A0 delivers the surface, the role and the permission model; the screens follow.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from frontier.adapters.api.security import hash_password, issue_console_token, verify_password
from frontier.adapters.clock import SystemClock
from frontier.adapters.console.deps import (
    RANKS,
    Console,
    ConsoleDep,
    CurrentOperator,
    at_least,
    permission_on,
    require,
)
from frontier.adapters.db import models
from frontier.adapters.db.engine import make_engine, make_sessionmaker
from frontier.config.settings import Settings


class Credentials(BaseModel):
    # A lookup key, not a registration. Validating it here would answer "that address could not
    # exist" with a different status than "no such operator", which is a difference worth not
    # offering — and it refuses addresses a deployment may legitimately use internally.
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=200)


class GrantBody(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    world: str = Field(min_length=1, max_length=64)
    permission: str = Field(min_length=1, max_length=16)


def worlds_of(settings: Settings) -> tuple[str, ...]:
    return tuple(name.strip() for name in settings.admin_worlds.split(",") if name.strip())


def build(settings: Settings | None = None) -> Console:
    settings = settings or Settings()
    engine = make_engine(settings.database_url, role=settings.admin_role)
    return Console(
        settings=settings,
        sessions=make_sessionmaker(engine),
        worlds=worlds_of(settings),
    )


def create_console(console: Console | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if getattr(app.state, "console", None) is None:
            app.state.console = build()
        yield

    app = FastAPI(title="Frontier Operator Console", version="0.1.0", lifespan=lifespan)
    app.state.console = console

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/admin/auth/login", tags=["auth"])
    async def login(body: Credentials, c: ConsoleDep) -> dict[str, Any]:
        async with c.sessions() as session:
            row = (
                await session.execute(select(models.Operator).where(models.Operator.email == body.email))
            ).scalar_one_or_none()
        if row is None or not verify_password(row.password_hash, body.password):
            raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
        token = issue_console_token(
            row.id, c.settings.admin_jwt_secret, c.settings.admin_jwt_ttl_seconds, SystemClock()
        )
        return {"access_token": token, "token_type": "bearer"}

    @app.get("/admin/me", tags=["auth"])
    async def me(operator_id: CurrentOperator, c: ConsoleDep) -> dict[str, Any]:
        async with c.sessions() as session:
            row = (
                await session.execute(select(models.Operator).where(models.Operator.id == operator_id))
            ).scalar_one_or_none()
            if row is None:
                raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
            held = {
                grant.world: grant.permission
                for grant in (
                    await session.execute(select(models.Grant).where(models.Grant.operator_id == operator_id))
                ).scalars()
            }
        return {
            "id": str(row.id),
            "name": row.name,
            "email": row.email,
            # Only the worlds this operator holds. A console may reach more; this one may not.
            "worlds": [{"name": world, "permission": held[world]} for world in c.worlds if world in held],
        }

    @app.get("/admin/worlds/{world}", tags=["worlds"])
    async def world(world: str, operator_id: CurrentOperator, c: ConsoleDep) -> dict[str, Any]:
        async with c.sessions() as session:
            if world not in c.worlds:
                raise HTTPException(status_code=404, detail="Not Found")
            held = await require(session, operator_id, world, "watch")
            state = (await session.execute(select(models.WorldState))).scalar_one_or_none()
        return {
            "world": world,
            "permission": held,
            "world_day": state.world_day if state else None,
            "phase": state.phase if state else None,
        }

    @app.get("/admin/operators", tags=["operators"])
    async def operators(world: str, operator_id: CurrentOperator, c: ConsoleDep) -> dict[str, Any]:
        async with c.sessions() as session:
            if world not in c.worlds:
                raise HTTPException(status_code=404, detail="Not Found")
            await require(session, operator_id, world, "watch")
            rows = (
                await session.execute(
                    select(models.Grant, models.Operator)
                    .join(models.Operator, models.Operator.id == models.Grant.operator_id)
                    .where(models.Grant.world == world)
                    .order_by(models.Grant.granted_at)
                )
            ).all()
            names = {row.id: row.name for row in (await session.execute(select(models.Operator))).scalars()}
        return {
            "world": world,
            "operators": [
                {
                    "id": str(who.id),
                    "name": who.name,
                    "permission": grant.permission,
                    "granted_by": names.get(grant.granted_by) if grant.granted_by else None,
                    "removable": grant.permission != "origin",
                }
                for grant, who in rows
            ],
        }

    @app.post("/admin/operators:grant", status_code=201, tags=["operators"])
    async def grant(body: GrantBody, operator_id: CurrentOperator, c: ConsoleDep) -> dict[str, Any]:
        if body.permission not in RANKS or body.permission == "origin":
            # The origin is made when a world is, never handed out.
            raise HTTPException(status_code=422, detail="UNKNOWN_PERMISSION")
        async with c.sessions() as session, session.begin():
            if body.world not in c.worlds:
                raise HTTPException(status_code=404, detail="Not Found")
            held = await require(session, operator_id, body.world, "operate")
            # Nobody hands out more than they hold.
            if not at_least(held, body.permission):
                raise HTTPException(status_code=403, detail="BEYOND_YOUR_OWN_PERMISSION")
            target = (
                await session.execute(select(models.Operator).where(models.Operator.email == body.email))
            ).scalar_one_or_none()
            if target is None:
                raise HTTPException(status_code=404, detail="NO_SUCH_OPERATOR")
            existing = await permission_on(session, target.id, body.world)
            if existing == "origin":
                raise HTTPException(status_code=409, detail="ORIGIN_IS_FIXED")
            if existing is not None:
                await session.execute(
                    delete(models.Grant).where(
                        models.Grant.operator_id == target.id, models.Grant.world == body.world
                    )
                )
            session.add(
                models.Grant(
                    operator_id=target.id,
                    world=body.world,
                    permission=body.permission,
                    granted_by=operator_id,
                )
            )
        return {"operator": body.email, "world": body.world, "permission": body.permission}

    @app.post("/admin/operators:revoke", tags=["operators"])
    async def revoke(body: GrantBody, operator_id: CurrentOperator, c: ConsoleDep) -> dict[str, Any]:
        async with c.sessions() as session, session.begin():
            if body.world not in c.worlds:
                raise HTTPException(status_code=404, detail="Not Found")
            await require(session, operator_id, body.world, "operate")
            target = (
                await session.execute(select(models.Operator).where(models.Operator.email == body.email))
            ).scalar_one_or_none()
            if target is None:
                raise HTTPException(status_code=404, detail="NO_SUCH_OPERATOR")
            if await permission_on(session, target.id, body.world) == "origin":
                # A world with no operator is a world nobody can rescue.
                raise HTTPException(status_code=409, detail="ORIGIN_IS_FIXED")
            await session.execute(
                delete(models.Grant).where(
                    models.Grant.operator_id == target.id, models.Grant.world == body.world
                )
            )
        return {"operator": body.email, "world": body.world, "permission": None}

    return app


async def bootstrap(settings: Settings, email: str, password: str, name: str) -> UUID:
    """Make the world's original operator — the one nobody granted.

    Idempotent per world: if an origin already holds it, this refuses rather than making a
    second. A world has exactly one account it falls back on.
    """
    engine = make_engine(settings.database_url)
    sessions = make_sessionmaker(engine)
    try:
        async with sessions() as session, session.begin():
            operator = (
                await session.execute(select(models.Operator).where(models.Operator.email == email))
            ).scalar_one_or_none()
            if operator is None:
                operator = models.Operator(
                    id=uuid4(), email=email, name=name, password_hash=hash_password(password)
                )
                session.add(operator)
                await session.flush()
            for world in worlds_of(settings):
                held = (
                    await session.execute(
                        select(models.Grant).where(
                            models.Grant.world == world, models.Grant.permission == "origin"
                        )
                    )
                ).scalar_one_or_none()
                if held is None:
                    session.add(
                        models.Grant(
                            operator_id=operator.id,
                            world=world,
                            permission="origin",
                            granted_by=None,
                        )
                    )
            return operator.id
    finally:
        await engine.dispose()
