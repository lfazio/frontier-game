"""The station you are docked at — UX §6.

Prices are computed here on every view and never cached by the client (SDD D-9): a quote is a
function of stock, and stock moves under everyone's feet. Both sides of the spread are always
sent, so the cost of a round trip is legible rather than discovered.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer
from frontier.adapters.db import models
from frontier.domain.economy.pricing import quote

router = APIRouter(prefix="/v1", tags=["market"])


@router.get("/stations/{station_id}/market")
async def market(station_id: UUID, player_id: CurrentPlayer, c: ContainerDep) -> dict[str, Any]:
    rules = c.executor.rules
    async with c.sessions() as session:
        ship = (
            await session.execute(
                select(models.Ship).where(
                    models.Ship.player_id == player_id, models.Ship.destroyed_on.is_(None)
                )
            )
        ).scalar_one_or_none()
        station = (
            await session.execute(select(models.Location).where(models.Location.id == station_id))
        ).scalar_one_or_none()

        # A market is read from the berth, matching what trading itself requires. Not docked is
        # the same 404 as no such station, so the galaxy cannot be mapped by asking (D-52).
        if ship is None or station is None or ship.docked_at != station_id:
            raise HTTPException(status_code=404, detail="NOT_FOUND")

        lines = (
            (await session.execute(select(models.Market).where(models.Market.station_id == station_id)))
            .scalars()
            .all()
        )
        held = {
            row.commodity: row
            for row in (
                await session.execute(select(models.Cargo).where(models.Cargo.ship_id == ship.id))
            ).scalars()
        }
        player = (
            await session.execute(select(models.Player).where(models.Player.id == player_id))
        ).scalar_one()
        controller = await _controller(session, ship.system_id)

    profile = rules.economy.station_type.get(str(station.attrs.get("station_type", "")), {})
    commodities = []
    for line in sorted(lines, key=lambda row: row.commodity):
        prices = quote(line.stock, line.target_stock, line.base_price, rules.economy)
        mine = held.get(line.commodity)
        commodities.append(
            {
                "commodity": line.commodity,
                "stock": line.stock,
                "buy": prices.buy,
                "sell": prices.sell,
                "held": mine.qty if mine else 0,
                "avg_paid": mine.avg_unit_cost if mine else None,
            }
        )

    used = sum(row.qty for row in held.values())
    missing = ship.hull_max - ship.hull
    return {
        "station": {
            "id": str(station.id),
            "name": station.name,
            "kind": station.attrs.get("station_type"),
            "produces": profile.get("produces"),
            "consumes": profile.get("consumes"),
            "controller": controller,
        },
        "you": {
            "docked": ship.docked_at == station_id,
            "credits": player.credits,
            "ap": player.ap_balance,
            "hold_used": used,
            "hold_max": ship.cargo_max,
            "hull": ship.hull,
            "hull_max": ship.hull_max,
            "repair_cost": missing * rules.world.hull_repair_cost_per_point,
        },
        "commodities": commodities,
        "cargo": [
            {"commodity": row.commodity, "qty": row.qty, "avg_paid": row.avg_unit_cost}
            for row in sorted(held.values(), key=lambda row: row.commodity)
            if row.qty > 0
        ],
    }


async def _controller(session: Any, system_id: UUID) -> int | None:
    rows = (
        (await session.execute(select(models.Territory).where(models.Territory.system_id == system_id)))
        .scalars()
        .all()
    )
    best = max(rows, key=lambda row: float(row.influence), default=None)
    return best.faction_id if best and float(best.influence) >= 0.5 else None
