from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from frontier.adapters.api.errors import world_ticking_handler
from frontier.adapters.api.routers import auth, commands, feed, mapview, me, missions
from frontier.adapters.ws.gateway import router as stream_router
from frontier.application.executor import WorldTicking
from frontier.config.container import Container, build_sql


def create_app(container: Container | None = None) -> FastAPI:
    """A container built here is used as given; otherwise one is built at startup.

    The database engine must be created inside the loop that will serve requests — asyncpg
    binds its connections to a loop — which is why the default path waits for the lifespan.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if getattr(app.state, "container", None) is None:
            app.state.container = build_sql()
        yield
        bus = getattr(app.state.container, "bus", None)
        if bus is not None:
            await bus.close()
        engine = getattr(app.state.container, "engine", None)
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title="Frontier: The Seldon Era", version="0.1.0", lifespan=lifespan)
    app.state.container = container
    app.add_exception_handler(WorldTicking, world_ticking_handler)
    app.include_router(auth.router)
    app.include_router(commands.router)
    app.include_router(me.router)
    app.include_router(feed.router)
    app.include_router(mapview.router)
    app.include_router(missions.router)
    app.include_router(stream_router)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "ruleset": app.state.container.executor.rules.version}

    return app


app = create_app()
