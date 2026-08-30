"""The operator console — a separate application, on its own port. ADMIN §2.

It is not a privileged corner of the player API. Exposing the game does not expose this, and no
router here is reachable from `/v1`: they are different ASGI applications that happen to share a
database. A0 delivers the surface, the role and the permission model; the screens follow.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qs
from uuid import UUID, uuid4

import jwt
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from frontier.adapters.api.security import (
    hash_password,
    issue_console_token,
    read_console_token,
    verify_password,
)
from frontier.adapters.clock import SystemClock
from frontier.adapters.console import reads, render
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
from frontier.adapters.rules_loader import load_ruleset
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


COOKIE = "frontier_console"


def worlds_of(settings: Settings) -> tuple[str, ...]:
    return tuple(name.strip() for name in settings.admin_worlds.split(",") if name.strip())


def build(settings: Settings | None = None) -> Console:
    settings = settings or Settings()
    engine = make_engine(settings.database_url, role=settings.admin_role)
    return Console(
        settings=settings,
        sessions=make_sessionmaker(engine),
        worlds=worlds_of(settings),
        rules=load_ruleset(settings.ruleset_root, settings.ruleset_version),
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
            body = await reads.overview(session)
        return {"world": world, "permission": held, **body}

    @app.get("/admin/worlds/{world}/ticks", tags=["ticks"])
    async def ticks(world: str, operator_id: CurrentOperator, c: ConsoleDep) -> dict[str, Any]:
        async with c.sessions() as session:
            if world not in c.worlds:
                raise HTTPException(status_code=404, detail="Not Found")
            await require(session, operator_id, world, "watch")
            return {"world": world, "runs": await reads.runs(session)}

    @app.get("/admin/worlds/{world}/ticks/{day}", tags=["ticks"])
    async def tick(world: str, day: int, operator_id: CurrentOperator, c: ConsoleDep) -> dict[str, Any]:
        async with c.sessions() as session:
            if world not in c.worlds:
                raise HTTPException(status_code=404, detail="Not Found")
            await require(session, operator_id, world, "watch")
            found = await reads.stages_of(session, day)
        if found is None:
            raise HTTPException(status_code=404, detail="Not Found")
        return {"world": world, **found}

    @app.post("/admin/worlds/{world}/ticks/{day}:retry", tags=["ticks"])
    async def retry(world: str, day: int, operator_id: CurrentOperator, c: ConsoleDep) -> dict[str, Any]:
        """Ask the worker to come round sooner. The console does not run the tick itself."""
        async with c.sessions() as session, session.begin():
            if world not in c.worlds:
                raise HTTPException(status_code=404, detail="Not Found")
            await require(session, operator_id, world, "operate")
            run = (
                await session.execute(select(models.TickRun).where(models.TickRun.world_day == day))
            ).scalar_one_or_none()
            if run is None:
                raise HTTPException(status_code=404, detail="Not Found")
            if run.finished_at is not None:
                # A finished run has nothing to resume, and asking would be a lie on the record.
                raise HTTPException(status_code=409, detail="ALREADY_FINISHED")
            run.retry_requested_at = func.now()
            run.retry_requested_by = operator_id
        return {"world": world, "world_day": day, "retry_requested": True}

    @app.get("/admin/worlds/{world}/history", tags=["history"])
    async def history(world: str, operator_id: CurrentOperator, c: ConsoleDep) -> dict[str, Any]:
        async with c.sessions() as session:
            if world not in c.worlds:
                raise HTTPException(status_code=404, detail="Not Found")
            await require(session, operator_id, world, "watch")
            state = (await session.execute(select(models.WorldState))).scalar_one_or_none()
            body = await reads.history(session, state.world_day if state else None)
        body["era_threshold"] = c.rules.events.era_threshold
        return {"world": world, **body}

    @app.get("/admin/worlds/{world}/pilots", tags=["pilots"])
    async def pilots(world: str, operator_id: CurrentOperator, c: ConsoleDep, q: str = "") -> dict[str, Any]:
        async with c.sessions() as session:
            if world not in c.worlds:
                raise HTTPException(status_code=404, detail="Not Found")
            await require(session, operator_id, world, "watch")
            return {"world": world, "pilots": await reads.pilots(session, q)}

    @app.get("/admin/worlds/{world}/pilots/{player_id}", tags=["pilots"])
    async def pilot(
        world: str, player_id: UUID, operator_id: CurrentOperator, c: ConsoleDep
    ) -> dict[str, Any]:
        async with c.sessions() as session:
            if world not in c.worlds:
                raise HTTPException(status_code=404, detail="Not Found")
            await require(session, operator_id, world, "watch")
            found = await reads.pilot(session, player_id)
        if found is None:
            raise HTTPException(status_code=404, detail="Not Found")
        return {"world": world, **found}

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

    # --- the screens (ADMIN §3.1, §3.2) --------------------------------------------------
    # Server-rendered, and reading through the same functions the JSON routes use. The browser
    # carries the same console token, in a cookie the page cannot read.

    async def operator_of(request: Request) -> UUID | None:
        token = request.cookies.get(COOKIE)
        if not token:
            return None
        try:
            return read_console_token(token, app.state.console.settings.admin_jwt_secret)
        except jwt.PyJWTError:
            return None

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/console", status_code=303)

    @app.get("/console", include_in_schema=False)
    async def console_home(request: Request) -> Response:
        operator_id = await operator_of(request)
        if operator_id is None:
            return HTMLResponse(render.login())
        c: Console = app.state.console
        async with c.sessions() as session:
            held = [w for w in c.worlds if await permission_on(session, operator_id, w)]
        if not held:
            return HTMLResponse(render.login("That account holds no world yet."))
        return RedirectResponse(f"/console/{held[0]}/overview", status_code=303)

    @app.post("/console/login", include_in_schema=False)
    async def console_login(request: Request) -> Response:
        # Parsed here rather than with `request.form()`, which would pull in a multipart
        # library for one URL-encoded login form.
        form = parse_qs((await request.body()).decode("utf-8", "replace"))
        email = (form.get("email") or [""])[0]
        password = (form.get("password") or [""])[0]
        c: Console = app.state.console
        async with c.sessions() as session:
            row = (
                await session.execute(select(models.Operator).where(models.Operator.email == email))
            ).scalar_one_or_none()
        if row is None or not verify_password(row.password_hash, password):
            # One message for a wrong password and an account that does not exist.
            return HTMLResponse(render.login("Those details were not accepted."), status_code=401)
        token = issue_console_token(
            row.id, c.settings.admin_jwt_secret, c.settings.admin_jwt_ttl_seconds, SystemClock()
        )
        response = RedirectResponse("/console", status_code=303)
        response.set_cookie(
            COOKIE, token, httponly=True, samesite="lax", max_age=c.settings.admin_jwt_ttl_seconds
        )
        return response

    @app.get("/console/logout", include_in_schema=False)
    async def console_logout() -> Response:
        response = RedirectResponse("/console", status_code=303)
        response.delete_cookie(COOKIE)
        return response

    @app.get("/console/{world}/overview", include_in_schema=False)
    async def screen_overview(world: str, request: Request) -> Response:
        return await _screen(request, world, "overview")

    @app.get("/console/{world}/pilots", include_in_schema=False)
    async def screen_pilots(world: str, request: Request, q: str = "") -> Response:
        return await _screen(request, world, "pilots", query=q)

    @app.get("/console/{world}/pilots/{player_id}", include_in_schema=False)
    async def screen_pilot(world: str, player_id: UUID, request: Request) -> Response:
        return await _screen(request, world, "pilots", pilot_id=player_id)

    @app.get("/console/{world}/history", include_in_schema=False)
    async def screen_history(world: str, request: Request) -> Response:
        return await _screen(request, world, "history")

    @app.get("/console/{world}/ticks", include_in_schema=False)
    async def screen_ticks(world: str, request: Request) -> Response:
        return await _screen(request, world, "ticks")

    @app.get("/console/{world}/ticks/{day}", include_in_schema=False)
    async def screen_tick(world: str, day: int, request: Request) -> Response:
        return await _screen(request, world, "ticks", day=day)

    @app.post("/console/{world}/ticks/{day}/retry", include_in_schema=False)
    async def screen_retry(world: str, day: int, request: Request) -> Response:
        operator_id = await operator_of(request)
        if operator_id is None:
            return HTMLResponse(render.login(), status_code=401)
        c: Console = app.state.console
        async with c.sessions() as session, session.begin():
            if world not in c.worlds or not at_least(
                await permission_on(session, operator_id, world), "operate"
            ):
                return HTMLResponse(render.page("Not found", "<main>Not Found</main>"), status_code=404)
            run = (
                await session.execute(select(models.TickRun).where(models.TickRun.world_day == day))
            ).scalar_one_or_none()
            if run is not None and run.finished_at is None:
                run.retry_requested_at = func.now()
                run.retry_requested_by = operator_id
        return RedirectResponse(f"/console/{world}/ticks/{day}", status_code=303)

    async def _screen(
        request: Request,
        world: str,
        here: str,
        day: int | None = None,
        query: str = "",
        pilot_id: UUID | None = None,
    ) -> Response:
        operator_id = await operator_of(request)
        if operator_id is None:
            return HTMLResponse(render.login(), status_code=401)
        c: Console = app.state.console
        async with c.sessions() as session:
            held = await permission_on(session, operator_id, world)
            if world not in c.worlds or not at_least(held, "watch"):
                return HTMLResponse(render.page("Not found", "<main>Not Found</main>"), status_code=404)
            mine = [w for w in c.worlds if await permission_on(session, operator_id, w)]
            summary = await reads.overview(session)
            if here == "overview":
                body = render.overview(summary).replace("{world}", world)
            elif here == "pilots":
                listing = await reads.pilots(session, query)
                chosen = await reads.pilot(session, pilot_id) if pilot_id else None
                body = render.pilots(world, listing, chosen, query)
            elif here == "history":
                past = await reads.history(session, summary["world_day"])
                past["era_threshold"] = c.rules.events.era_threshold
                body = render.history(past)
            elif day is None:
                body = render.ticks(world, await reads.runs(session))
            else:
                found = await reads.stages_of(session, day)
                if found is None:
                    return HTMLResponse(render.page("Not found", "<main>Not Found</main>"), status_code=404)
                body = render.tick(world, found, may_retry=at_least(held, "operate"))
        return HTMLResponse(render.shell(world, mine, here, body, summary["world_day"], summary["phase"]))

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
