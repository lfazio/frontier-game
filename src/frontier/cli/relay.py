"""`make relay` — publish committed events to Redis."""

from __future__ import annotations

import asyncio
import logging

from frontier.adapters.bus.outbox import OutboxRelay
from frontier.adapters.bus.redis_bus import RedisBus
from frontier.adapters.db.engine import make_engine, make_sessionmaker
from frontier.config.settings import Settings


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    engine = make_engine(settings.database_url)
    bus = RedisBus(settings.redis_url)
    try:
        await OutboxRelay(make_sessionmaker(engine), bus).run_forever()
    finally:
        await bus.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
