"""A seeded world run for many cycles — SDD §14.5, criteria A12 and A13.

Marked `soak`: it is the nightly job, not the commit gate. It is simultaneously the performance
test, the balance test and the regression net for slow drift.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from itertools import pairwise

import pytest
from sqlalchemy import func, select

from frontier.adapters.clock import SeededRng, SystemClock
from frontier.adapters.db import models
from frontier.adapters.rules_loader import load_ruleset
from frontier.simulation.tick import TickRunner

pytestmark = [pytest.mark.integration, pytest.mark.soak]

CYCLES = 60


async def test_the_world_stays_healthy_over_sixty_cycles(sessions, clean):
    runner = TickRunner(
        sessions=sessions,
        rules=load_ruleset(clean.ruleset_root, clean.ruleset_version),
        clock=SystemClock(),
        rng_for=SeededRng(clean.world_seed).for_,
    )

    history: list[dict[str, float]] = []
    slowest = 0.0
    for _ in range(CYCLES):
        started = time.monotonic()
        await runner.run()
        slowest = max(slowest, time.monotonic() - started)
        history.append(await _snapshot(sessions))

    assert slowest < 60, f"slowest cycle took {slowest:.1f}s"
    # An economy with no gradient left has stopped being a decision.
    assert history[-1]["price_spread"] > 0
    # Flows are bounded by construction; they must stay bounded in practice too.
    assert all(0 <= row["raider"] <= 1 for row in history)
    assert all(0 <= row["trade"] <= 1 for row in history)
    # A visibly pulsing world reads as machinery rather than a place — SDD §6.5.1.
    assert _shortest_period([row["trade"] for row in history]) >= 10


async def _snapshot(sessions) -> dict[str, float]:
    async with sessions() as session:
        spread = (
            await session.execute(select(func.max(models.Market.stock) - func.min(models.Market.stock)))
        ).scalar_one()
        trade = (await session.execute(select(func.avg(models.SystemActivity.trade_flow)))).scalar_one()
        raider = (await session.execute(select(func.avg(models.SystemActivity.raider_pressure)))).scalar_one()
    return {
        "price_spread": float(spread or 0),
        "trade": float(trade or 0),
        "raider": float(raider or 0),
    }


def _shortest_period(series: Iterable[float]) -> int:
    """Distance between direction changes. A short period means the series oscillates."""
    values = list(series)
    turns = [
        i for i in range(1, len(values) - 1) if (values[i] - values[i - 1]) * (values[i + 1] - values[i]) < 0
    ]
    if len(turns) < 2:
        return len(values)
    return min(b - a for a, b in pairwise(turns)) * 2
