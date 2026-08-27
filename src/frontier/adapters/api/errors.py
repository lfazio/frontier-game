"""RFC 9457 problem responses — SDD §8.1, §8.4."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from frontier.application.executor import WorldTicking
from frontier.domain.decisions import Rejected


def problem(status: int, code: str, detail: str, **extra: object) -> JSONResponse:
    body: dict[str, object] = {
        "type": "about:blank",
        "title": code,
        "status": status,
        "detail": detail,
        "code": code,
    }
    body.update(extra)
    return JSONResponse(status_code=status, content=body, media_type="application/problem+json")


def rejection(rejected: Rejected) -> JSONResponse:
    """409: a legal request that is illegal in the current world state. Gameplay, not a fault."""
    return problem(
        409, rejected.code.value, "the world does not allow this right now", context=rejected.context
    )


async def world_ticking_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, WorldTicking)
    response = problem(503, "WORLD_TICKING", "the galaxy is turning; retry shortly")
    response.headers["Retry-After"] = str(exc.retry_after)
    return response
