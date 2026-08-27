"""The Model against the database — GDD §8, ARCH ADR-12.

The important test here is not that forecasts appear. It is that the Model's reader role
*cannot* read a player, whatever the code does.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update

from frontier.adapters.api.app import create_app
from frontier.adapters.clock import SeededRng, SystemClock
from frontier.adapters.db import models
from frontier.adapters.rules_loader import load_ruleset
from frontier.config.container import build_sql
from frontier.simulation.stages.base import Features
from frontier.simulation.tick import TickRunner

pytestmark = pytest.mark.integration

FORBIDDEN = (
    "SELECT count(*) FROM core.players",
    "SELECT count(*) FROM core.ships",
    "SELECT count(*) FROM evt.events",
    "SELECT count(*) FROM core.reputation",
)


def runner(sessions, settings, psychohistory: bool = True) -> TickRunner:
    return TickRunner(
        sessions=sessions,
        rules=load_ruleset(settings.ruleset_root, settings.ruleset_version),
        clock=SystemClock(),
        rng_for=SeededRng(settings.world_seed).for_,
        features=Features(psychohistory=psychohistory),
    )


@pytest.mark.parametrize("statement", FORBIDDEN)
async def test_the_models_reader_cannot_see_individuals(sessions, clean, statement):
    """GDD §8.4 enforced by grants, not by code review — ARCH ADR-12."""
    async with sessions() as session:
        await session.execute(text("SET ROLE psycho_reader"))
        with pytest.raises(Exception) as refused:
            await session.execute(text(statement))
    assert "permission denied" in str(refused.value).lower()


async def test_the_models_reader_can_read_its_own_aggregates(sessions, clean):
    async with sessions() as session:
        await session.execute(text("SET ROLE psycho_reader"))
        total = (await session.execute(text("SELECT count(*) FROM psycho.v_region_population"))).scalar_one()
    assert total > 0


async def test_no_aggregate_view_exposes_an_identifying_column(sessions, clean):
    """A view is the Model's only window; a player column in one would be the leak."""
    async with sessions() as session:
        columns = (
            await session.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = 'psycho'"
                )
            )
        ).all()
    offenders = [
        f"{table}.{column}"
        for table, column in columns
        if column in {"player_id", "callsign", "account_id", "ship_id", "participants"}
    ]
    assert not offenders, offenders


async def test_the_model_ships_dark(sessions, clean):
    """GDD §10.3: it cannot be tuned against a world with no history, so it stays off."""
    report = await runner(sessions, clean, psychohistory=False).run()
    assert report.stages["psychohistory"] == {"disabled": 1}

    async with sessions() as session:
        published = (await session.execute(select(func.count()).select_from(models.ForecastRow))).scalar_one()
    assert published == 0


async def test_enabling_it_publishes_a_forecast_per_region(sessions, clean):
    report = await runner(sessions, clean).run()

    async with sessions() as session:
        rows = (await session.execute(select(models.ForecastRow))).scalars().all()
        variables = (await session.execute(select(models.HistoryVariable))).scalars().all()

    assert report.stages["psychohistory"]["regions"] == 4
    assert len(rows) == 12  # three outlooks per region
    assert {v.variable for v in variables} >= {"stability", "economic_health"}
    assert all(0 <= float(r.probability) <= 1 for r in rows)


async def test_running_the_stage_twice_in_a_day_does_not_duplicate(sessions, clean):
    tick = runner(sessions, clean)
    await tick.run()
    async with sessions() as session, session.begin():
        await session.execute(text("DELETE FROM hist.tick_stages"))
        await session.execute(update(models.TickRun).values(finished_at=None))
    await tick.run()

    async with sessions() as session:
        rows = (await session.execute(select(func.count()).select_from(models.ForecastRow))).scalar_one()
    assert rows == 12


async def test_confidence_falls_as_the_world_diverges(sessions, clean):
    tick = runner(sessions, clean)
    await tick.run()
    async with sessions() as session:
        first = (await session.execute(select(func.avg(models.ForecastRow.confidence)))).scalar_one()

    for _ in range(6):
        await tick.run()

    async with sessions() as session:
        latest_day = (await session.execute(select(func.max(models.ForecastRow.world_day)))).scalar_one()
        later = (
            await session.execute(
                select(func.avg(models.ForecastRow.confidence)).where(
                    models.ForecastRow.world_day == latest_day
                )
            )
        ).scalar_one()
    assert later <= first


class TestOverHttp:
    @pytest.fixture
    def dark_client(self, clean):
        with TestClient(create_app(build_sql(clean))) as client:
            yield client

    @pytest.fixture
    def client(self, clean):
        lit = clean.model_copy(update={"features_psychohistory": True})
        with TestClient(create_app(build_sql(lit))) as client:
            yield client

    @staticmethod
    def register(client) -> dict[str, str]:
        response = client.post(
            "/v1/auth/register",
            json={
                "email": f"{uuid4().hex}@x.io",
                "password": "correct horse battery",
                "callsign": uuid4().hex[:12],
            },
        )
        assert response.status_code == 201
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_a_dark_model_has_no_endpoint_at_all(self, dark_client):
        headers = self.register(dark_client)
        assert dark_client.get("/v1/forecasts", headers=headers).status_code == 404

    def test_a_forecast_is_readable_by_anyone(self, client, clean):
        import asyncio

        from frontier.adapters.db.engine import make_engine, make_sessionmaker

        headers = self.register(client)

        async def tick_once() -> None:
            engine = make_engine(clean.database_url)
            await runner(make_sessionmaker(engine), clean).run()
            await engine.dispose()

        asyncio.run(tick_once())

        body = client.get("/v1/forecasts", headers=headers).json()

        assert body["knowledge"] == 0
        assert len(body["regions"]) == 4
        prediction = body["regions"][0]["predictions"][0]
        assert prediction["detail"] == "headline"
        assert prediction["reasoning"] is None
        assert 0.0 <= prediction["probability"] <= 1.0

    def test_no_forecast_payload_can_name_a_player(self, client, clean):
        import asyncio
        import json

        from frontier.adapters.db.engine import make_engine, make_sessionmaker

        headers = self.register(client)
        callsign = client.get("/v1/me", headers=headers).json()["player"]["callsign"]

        async def tick_once() -> None:
            engine = make_engine(clean.database_url)
            await runner(make_sessionmaker(engine), clean).run()
            await engine.dispose()

        asyncio.run(tick_once())
        raw = json.dumps(client.get("/v1/forecasts", headers=headers).json())

        assert callsign not in raw
        assert "player" not in raw
