"""`make world` — generate a galaxy and write it. Idempotent: it refuses a populated world."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import delete, func, select

from frontier.adapters.clock import SeededRng
from frontier.adapters.db import models
from frontier.adapters.db.engine import make_engine, make_sessionmaker
from frontier.config.settings import Settings
from frontier.worldgen.generator import generate, summarise


async def build_world(settings: Settings, force: bool = False) -> dict[str, int]:
    engine = make_engine(settings.database_url)
    sessions = make_sessionmaker(engine)
    try:
        async with sessions() as session, session.begin():
            existing = (await session.execute(select(func.count()).select_from(models.Location))).scalar_one()
            if existing and not force:
                raise SystemExit(f"world already has {existing} locations; use --force")
            if existing:
                # Dependency order: journeys reference ships, ships reference locations.
                await session.execute(delete(models.Journey))
                await session.execute(delete(models.Ship))
                await session.execute(delete(models.Location))

            rows = generate(SeededRng(settings.world_seed).for_)
            session.add_all(
                [
                    models.Location(
                        id=r.id,
                        parent_id=r.parent_id,
                        level=r.level,
                        q=r.q,
                        r=r.r,
                        path=r.path,
                        kind=r.kind,
                        name=r.name,
                        discovered_on=r.discovered_on,
                        attrs=r.attrs,
                    )
                    for r in rows
                ]
            )
            state = (await session.execute(select(models.WorldState))).scalar_one_or_none()
            if state is None:
                session.add(
                    models.WorldState(id=True, world_day=0, world_seed=settings.world_seed, phase="open")
                )
        return summarise(rows)
    finally:
        await engine.dispose()


def main() -> None:
    summary = asyncio.run(build_world(Settings(), force="--force" in sys.argv))
    for key in sorted(summary):
        print(f"  {key:<10} {summary[key]}")


if __name__ == "__main__":
    main()
