from __future__ import annotations

from fastapi import FastAPI

from frontier.adapters.api.errors import world_ticking_handler
from frontier.adapters.api.routers import auth, commands
from frontier.adapters.memory.fixture import seed_fixture_world
from frontier.application.executor import WorldTicking
from frontier.config.container import Container, build


def create_app(container: Container | None = None) -> FastAPI:
    app = FastAPI(title="Frontier: The Seldon Era", version="0.1.0")
    app.state.container = container or build()
    seed_fixture_world(app.state.container.world)
    app.add_exception_handler(WorldTicking, world_ticking_handler)
    app.include_router(auth.router)
    app.include_router(commands.router)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "ruleset": app.state.container.executor.rules.version}

    return app


app = create_app()
