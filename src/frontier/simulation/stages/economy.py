"""Stage 3 — markets relax toward their target, and prices move — SDD §6.4.

Vectorised over one bulk query rather than per-row ORM traversal, so cost is a function of the
world's size and not of how it is stored.
"""

from __future__ import annotations

from sqlalchemy import select

from frontier.adapters.db import models
from frontier.domain.economy.pricing import mid_price, relax
from frontier.simulation.stages.base import TickContext

PRODUCTION = 12
CONSUMPTION = 9


class EconomyStep:
    name = "economy"
    role: str | None = None
    order = 3

    async def run(self, ctx: TickContext) -> dict[str, int]:
        economy = ctx.rules.economy
        rows = (
            await ctx.session.execute(
                select(models.Market, models.Location.attrs)
                .join(models.Location, models.Location.id == models.Market.station_id)
                .order_by(models.Market.station_id, models.Market.commodity)
            )
        ).all()

        shifted = 0
        for market, attrs in rows:
            profile = economy.station_type.get(str(attrs.get("station_type", "")), {})
            produces = PRODUCTION if market.commodity == profile.get("produces") else 0
            consumes = CONSUMPTION if market.commodity == profile.get("consumes") else 0

            before = mid_price(market.stock, market.target_stock, market.base_price, economy)
            market.stock = relax(market.stock, market.target_stock, produces, consumes, economy)
            after = mid_price(market.stock, market.target_stock, market.base_price, economy)

            if abs(after - before) >= before * economy.shift_report_threshold:
                shifted += 1
        return {"markets": len(rows), "price_shifts": shifted}
