"""Historical forecasts — a public good of variable quality. GDD §8.3, design Q2.

Anyone may read a forecast; nobody buys the right to one. What Knowledge buys is resolution:
narrower intervals, more variables, and eventually the Model's reasoning rather than only its
output. Nothing here may name a player (GDD §8.4).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer
from frontier.adapters.db import models
from frontier.domain.psychohistory.disclosure import disclose
from frontier.domain.psychohistory.model import Forecast, Outlook

router = APIRouter(prefix="/v1", tags=["history"])


@router.get("/forecasts")
async def forecasts(player_id: CurrentPlayer, c: ContainerDep) -> dict[str, Any]:
    if not c.settings.features_psychohistory:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    async with c.sessions() as session:
        knowledge = (
            await session.execute(select(models.Player.knowledge).where(models.Player.id == player_id))
        ).scalar_one()
        latest = (
            await session.execute(
                select(models.ForecastRow.world_day).order_by(models.ForecastRow.world_day.desc()).limit(1)
            )
        ).scalar_one_or_none()
        if latest is None:
            return {"world_day": None, "knowledge": knowledge, "regions": []}

        rows = (
            await session.execute(
                select(models.ForecastRow, models.Location.name, models.Location.path)
                .join(models.Location, models.Location.id == models.ForecastRow.region_id)
                .where(models.ForecastRow.world_day == latest)
                .order_by(models.Location.path, models.ForecastRow.kind)
            )
        ).all()
        variables = (
            (
                await session.execute(
                    select(models.HistoryVariable).where(models.HistoryVariable.world_day == latest)
                )
            )
            .scalars()
            .all()
        )

    drivers: dict[Any, dict[str, float]] = {}
    for row in variables:
        drivers.setdefault(row.region_id, {})[row.variable] = round(float(row.observed), 3)

    regions: dict[Any, dict[str, Any]] = {}
    for row, name, path in rows:
        entry = regions.setdefault(
            str(path),
            {
                "region": str(path),
                "name": name,
                "deviation": round(float(row.deviation), 4),
                "predictions": [],
            },
        )
        prediction = Forecast(
            kind=Outlook(row.kind), probability=float(row.probability), confidence=float(row.confidence)
        )
        entry["predictions"].append(asdict(disclose(prediction, knowledge, drivers.get(row.region_id))))

    return {"world_day": latest, "knowledge": knowledge, "regions": list(regions.values())}
