"""The daily overview — the first screen after login. GDD §3.4, SDD §9.2."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer

router = APIRouter(prefix="/v1", tags=["player"])


@router.get("/me")
async def me(player_id: CurrentPlayer, c: ContainerDep) -> dict[str, Any]:
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
            },
            "ship": {
                "id": str(ship.id),
                "position": str(ship.position),
                "hull": ship.hull,
                "fuel": ship.fuel,
                "docked": ship.docked_at is not None,
            },
        }
