"""Stage 11 — half of unspent AP carries to a ceiling. GDD §3.2, SDD §6.7.

Pilots and NPC crews are reset by the same rule and the same numbers: an NPC may not act more
cheaply than a human (GDD §2.7).

The ledger delta is signed: the stage computes a balance, it does not add to one.
`last_grant_day` is what makes re-running the stage a no-op.
"""

from __future__ import annotations

from sqlalchemy import select

from frontier.adapters.db import models
from frontier.simulation.stages.base import TickContext


class GrantActionPoints:
    name = "grant_action_points"
    role: str | None = None
    order = 11

    async def run(self, ctx: TickContext) -> dict[str, int]:
        players = (
            (
                await ctx.session.execute(
                    select(models.Player)
                    .where(models.Player.last_grant_day < ctx.world_day)
                    .order_by(models.Player.id)
                )
            )
            .scalars()
            .all()
        )

        ap = ctx.rules.ap
        for player in players:
            carry = ap.carry(player.ap_balance)
            new_balance = ap.daily_grant + carry
            ctx.session.add(
                models.ApLedger(
                    player_id=player.id,
                    world_day=ctx.world_day,
                    delta=new_balance - player.ap_balance,
                    reason="daily_reset",
                )
            )
            player.ap_balance = new_balance
            player.last_grant_day = ctx.world_day
        crews = (
            (
                await ctx.session.execute(
                    select(models.NpcAgent)
                    .where(models.NpcAgent.last_grant_day < ctx.world_day)
                    .order_by(models.NpcAgent.ship_id)
                )
            )
            .scalars()
            .all()
        )
        for crew in crews:
            crew.ap_balance = ap.daily_grant + ap.carry(crew.ap_balance)
            crew.last_grant_day = ctx.world_day

        return {"players_reset": len(players), "crews_reset": len(crews)}
