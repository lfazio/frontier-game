"""Redis pub/sub carries committed events to the WebSocket gateways."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis

CHANNEL = "frontier:events"


class RedisBus:
    def __init__(self, url: str) -> None:
        self._redis: Redis = Redis.from_url(url)

    async def claim(self, key: str, seconds: int) -> bool:
        """Take a ration if it is going. `SET NX EX` is atomic, so two callers cannot both win."""
        taken = await self._redis.set(key, "1", nx=True, ex=seconds)
        return bool(taken)

    async def publish(self, payloads: list[dict[str, Any]]) -> None:
        for payload in payloads:
            await self._redis.publish(CHANNEL, json.dumps(payload))

    async def listen(self, ready: asyncio.Event | None = None) -> AsyncIterator[dict[str, Any]]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(CHANNEL)
        if ready is not None:
            ready.set()
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield json.loads(message["data"])
        finally:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()  # type: ignore[no-untyped-call]

    async def close(self) -> None:
        await self._redis.aclose()
