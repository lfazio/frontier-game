"""Stage 7 — the Model observes populations and publishes forecasts. GDD §8, ARCH §9.2.

Reads only the aggregate views of the `psycho` schema. Those views carry no player column and
the reader role holds no privilege on `core`, so the boundary of GDD §8.4 is enforced by the
database rather than by this file being careful (ARCH ADR-12).

Ships dark: GDD §10.3 puts the Model after months of live play, because its variables cannot be
tuned against a world with no history.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text

from frontier.adapters.db import models
from frontier.domain.psychohistory.model import (
    Observation,
    Variable,
    deviation,
    forecast,
    observe,
    project,
    severity_of,
    strains,
)
from frontier.simulation.stages.base import TickContext

SURPRISE_WINDOW = 10


class PsychohistoryUpdate:
    name = "psychohistory"
    role: str | None = None
    order = 7

    async def run(self, ctx: TickContext) -> dict[str, int]:
        if not ctx.features.psychohistory:
            return {"disabled": 1}

        samples = await self._sample(ctx)
        if not samples:
            return {"regions": 0, "forecasts": 0}

        previous = await self._previous_expected(ctx)
        surprise = await self._recent_surprise(ctx)
        # Clear this day's output first: a resumed tick must be able to re-run the stage
        # without duplicating what a crashed run had already written (SDD §6.1).
        await self._clear_day(ctx)

        published = 0
        strained: dict[UUID, dict[Variable, float]] = {}
        for region_id, sample in sorted(samples.items(), key=lambda kv: str(kv[0])):
            observed = observe(sample)
            expected = project(previous.get(region_id, {}), observed)
            drift = deviation(observed, expected)
            strained[region_id] = strains(observed, expected)

            for variable, value in observed.items():
                ctx.session.add(
                    models.HistoryVariable(
                        region_id=region_id,
                        world_day=ctx.world_day,
                        variable=variable.value,
                        observed=_dec(value),
                        expected=_dec(expected[variable]),
                    )
                )

            for prediction in forecast(observed, drift, surprise.get(region_id, 0.0)):
                ctx.session.add(
                    models.ForecastRow(
                        id=uuid4(),
                        region_id=region_id,
                        world_day=ctx.world_day,
                        kind=prediction.kind.value,
                        probability=_dec(prediction.probability),
                        confidence=_dec(prediction.confidence),
                        deviation=_dec(drift),
                    )
                )
                published += 1

        opened, resolved = await self._crises(ctx, strained)
        await self._prune(ctx)
        return {
            "regions": len(samples),
            "forecasts": published,
            "crises_opened": opened,
            "crises_resolved": resolved,
        }

    async def _crises(self, ctx: TickContext, strained: dict[UUID, dict[Variable, float]]) -> tuple[int, int]:
        """Open a crisis where a strain has held, and close one where it has let go.

        Detection reads the stored variables rather than this cycle's numbers alone: a crisis is
        a trend, and one bad cycle is not one (PSDD §2.2).
        """
        # This cycle's variables are still pending in the session, and the window is counted in
        # SQL: without the flush the newest day of the trend is invisible to the query.
        await ctx.session.flush()

        rules = ctx.rules.events
        open_now = {
            (row.region_id, row.variable): row
            for row in (
                await ctx.session.execute(select(models.Crisis).where(models.Crisis.resolved_on.is_(None)))
            ).scalars()
        }
        sustained = await self._sustained(ctx, rules.crisis_threshold, rules.crisis_window)

        opened = resolved = 0
        for region_id, per_variable in sorted(strained.items(), key=lambda kv: str(kv[0])):
            for variable, strain in sorted(per_variable.items(), key=lambda kv: kv[0].value):
                key = (region_id, variable.value)
                existing = open_now.get(key)
                if existing is not None:
                    # The world put it right: a strain back under the threshold closes it.
                    if strain < rules.crisis_threshold:
                        existing.resolved_on = ctx.world_day
                        resolved += 1
                    continue
                if key not in sustained:
                    continue
                ctx.session.add(
                    models.Crisis(
                        id=uuid4(),
                        region_id=region_id,
                        variable=variable.value,
                        opened_on=ctx.world_day,
                        expires_on=ctx.world_day + rules.crisis_duration,
                        resolved_on=None,
                        severity=severity_of(strain, rules.crisis_threshold),
                        magnitude=_dec(strain),
                    )
                )
                opened += 1
        return opened, resolved

    async def _sustained(self, ctx: TickContext, threshold: float, window: int) -> set[tuple[UUID, str]]:
        """Region and variable pairs strained beyond the threshold on every day of the window."""
        rows = (
            await ctx.session.execute(
                text(
                    "SELECT region_id, variable, count(*) AS days "
                    "FROM psycho.history_variables "
                    "WHERE world_day > :since AND abs(observed - expected) >= :threshold "
                    "GROUP BY region_id, variable"
                ).bindparams(since=ctx.world_day - window, threshold=threshold)
            )
        ).all()
        return {(row.region_id, row.variable) for row in rows if row.days >= window}

    async def _clear_day(self, ctx: TickContext) -> None:
        await ctx.session.execute(
            delete(models.ForecastRow).where(models.ForecastRow.world_day == ctx.world_day)
        )
        await ctx.session.execute(
            delete(models.HistoryVariable).where(models.HistoryVariable.world_day == ctx.world_day)
        )

    async def _sample(self, ctx: TickContext) -> dict[UUID, Observation]:
        economy = {
            row.region_id: row
            for row in (
                await ctx.session.execute(text("SELECT region_id, stock_ratio FROM psycho.v_region_economy"))
            ).all()
        }
        population = {
            row.region_id: row
            for row in (
                await ctx.session.execute(
                    text(
                        "SELECT region_id, trade_flow, patrol_strength, raider_pressure "
                        "FROM psycho.v_region_population"
                    )
                )
            ).all()
        }
        control: dict[UUID, float] = defaultdict(float)
        for row in (
            await ctx.session.execute(text("SELECT region_id, influence FROM psycho.v_region_control"))
        ).all():
            control[row.region_id] = max(control[row.region_id], float(row.influence or 0))

        conflict: dict[UUID, tuple[int, int]] = defaultdict(lambda: (0, 0))
        for row in (
            await ctx.session.execute(
                text(
                    "SELECT region_id, combats, losses FROM psycho.v_region_conflict WHERE world_day > :since"
                ).bindparams(since=ctx.world_day - SURPRISE_WINDOW)
            )
        ).all():
            combats, losses = conflict[row.region_id]
            conflict[row.region_id] = (combats + row.combats, losses + row.losses)

        out: dict[UUID, Observation] = {}
        for region_id, pop in population.items():
            combats, losses = conflict[region_id]
            out[region_id] = Observation(
                stock_ratio=float(getattr(economy.get(region_id), "stock_ratio", 1.0) or 1.0),
                trade_flow=float(pop.trade_flow or 0),
                patrol_strength=float(pop.patrol_strength or 0),
                raider_pressure=float(pop.raider_pressure or 0),
                top_influence=control[region_id],
                combats=combats,
                losses=losses,
            )
        return out

    async def _previous_expected(self, ctx: TickContext) -> dict[UUID, dict[Variable, float]]:
        rows = (
            (
                await ctx.session.execute(
                    select(models.HistoryVariable).where(
                        models.HistoryVariable.world_day == ctx.world_day - 1
                    )
                )
            )
            .scalars()
            .all()
        )
        out: dict[UUID, dict[Variable, float]] = defaultdict(dict)
        for row in rows:
            out[row.region_id][Variable(row.variable)] = float(row.expected)
        return out

    async def _recent_surprise(self, ctx: TickContext) -> dict[UUID, float]:
        """Accumulated drift: a world that keeps surprising the Model is one it trusts less."""
        rows = (
            await ctx.session.execute(
                select(models.ForecastRow.region_id, models.ForecastRow.deviation).where(
                    models.ForecastRow.world_day > ctx.world_day - SURPRISE_WINDOW
                )
            )
        ).all()
        totals: dict[UUID, float] = defaultdict(float)
        for region_id, drift in rows:
            totals[region_id] += float(drift)
        return totals

    async def _prune(self, ctx: TickContext) -> None:
        cutoff = ctx.world_day - 400
        if cutoff > 0:
            await ctx.session.execute(
                delete(models.HistoryVariable).where(models.HistoryVariable.world_day < cutoff)
            )


def _dec(value: float) -> Decimal:
    return Decimal(f"{value:.4f}")
