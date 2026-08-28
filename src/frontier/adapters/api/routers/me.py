"""The daily overview — the first screen after login. GDD §3.4, SDD §9.2."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer
from frontier.adapters.db import models
from frontier.adapters.db.feed import FeedRepo

router = APIRouter(prefix="/v1", tags=["player"])


@router.get("/me")
async def me(player_id: CurrentPlayer, c: ContainerDep) -> dict[str, Any]:
    unread, digest = 0, None
    hold: list[dict[str, Any]] = []
    if c.sessions is not None:
        async with c.sessions() as session:
            unread = await FeedRepo(session).unread(player_id)
            hold = [
                {"commodity": row.commodity, "qty": row.qty, "avg_paid": row.avg_unit_cost}
                for row in (
                    await session.execute(
                        select(models.Cargo)
                        .join(models.Ship, models.Cargo.ship_id == models.Ship.id)
                        .where(
                            models.Ship.player_id == player_id,
                            models.Ship.destroyed_on.is_(None),
                            models.Cargo.qty > 0,
                        )
                        .order_by(models.Cargo.commodity)
                    )
                ).scalars()
            ]
            row = (
                await session.execute(
                    select(models.Digest)
                    .where(models.Digest.player_id == player_id)
                    .order_by(models.Digest.world_day.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            digest = row.summary if row else None
    async with c.executor.uow_factory() as uow:
        player = await uow.players.get_for_update(player_id)
        ship = await uow.ships.of_player(player_id)
        return {
            "world_day": await uow.world.world_day(),
            "phase": await uow.world.phase(),
            "player": {
                "id": str(player_id),
                "callsign": player.callsign,
                "ap": player.ap_balance,
                "credits": player.credits,
                "knowledge": player.knowledge,
            },
            "cargo": hold,
            "unread": unread,
            "digest": digest,
            "ship": {
                "id": str(ship.id),
                "position": str(ship.position),
                "hull": ship.hull,
                "fuel": ship.fuel,
                "docked": ship.docked_at is not None,
                "docked_at": str(ship.docked_at) if ship.docked_at else None,
                "jump_range_ly": ship.jump_range_ly,
                "in_transit": ship.in_transit,
                "hull_max": ship.hull_max,
                "fuel_max": ship.fuel_max,
                "cargo_max": ship.cargo_max,
            },
        }
