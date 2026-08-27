"""`make tick` — advance the world one cycle, on demand.

The tick takes the world day as state, never from the wall clock, so a developer can watch a
cycle boundary without waiting a day. ARCH §14.1.
"""

from __future__ import annotations

import asyncio

from frontier.adapters.clock import SeededRng, SystemClock
from frontier.adapters.db.engine import make_engine, make_sessionmaker
from frontier.adapters.rules_loader import load_ruleset
from frontier.config.settings import Settings
from frontier.simulation.stages.base import Features
from frontier.simulation.tick import TickRunner


async def run_once(settings: Settings) -> None:
    engine = make_engine(settings.database_url)
    try:
        runner = TickRunner(
            sessions=make_sessionmaker(engine),
            rules=load_ruleset(settings.ruleset_root, settings.ruleset_version),
            clock=SystemClock(),
            rng_for=SeededRng(settings.world_seed).for_,
            features=Features(psychohistory=settings.features_psychohistory),
        )
        report = await runner.run()
        print(f"world day {report.world_day}" + ("  (resumed)" if report.resumed else ""))
        for stage, metrics in report.stages.items():
            print(f"  {stage:<22} {metrics}")
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(run_once(Settings()))


if __name__ == "__main__":
    main()
