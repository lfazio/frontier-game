"""The balance data a player needs to see a cost before committing to it (UX §5).

Only the player-facing subset. Combat coefficients, NPC weights and anything under `continuity`
are not here: the client needs what an action costs, not how the world is tuned.
"""

from fastapi import APIRouter

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer

router = APIRouter(prefix="/v1", tags=["rules"])


@router.get("/rules")
async def read_rules(player_id: CurrentPlayer, c: ContainerDep) -> dict[str, object]:
    rules = c.executor.rules
    return {
        "version": rules.version,
        "ap": {
            "daily_grant": rules.ap.daily_grant,
            "carry_over_fraction": rules.ap.carry_over_fraction,
            "carry_ceiling": rules.ap.carry_ceiling,
            "cost": dict(rules.ap.cost),
        },
        "world": {
            "fuel_per_hex": rules.world.fuel_per_hex,
            "fuel_per_jump_ly": rules.world.fuel_per_jump_ly,
            "jump_range_default_ly": rules.world.jump_range_default_ly,
            "sensor_range_base": rules.world.sensor_range_base,
            "hull_repair_cost_per_point": rules.world.hull_repair_cost_per_point,
        },
    }
