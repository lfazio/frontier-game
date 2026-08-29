"""Stage 5 — control follows sustained presence, not who happened to be there. SDD §6.6."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from frontier.adapters.db import models
from frontier.domain.events.model import EventDraft, Scope, Severity, Visibility
from frontier.domain.events.types import EventType
from frontier.domain.polity.territory import blend, controller, normalise
from frontier.simulation.stages.base import TickContext

SHIP_WEIGHT = 1.0
STATION_WEIGHT = 2.0


class TerritoryRecompute:
    name = "territory"
    role: str | None = None
    order = 5

    async def run(self, ctx: TickContext) -> dict[str, int]:
        raw = await self._presence(ctx)
        existing = {
            (row.system_id, row.faction_id): row
            for row in (await ctx.session.execute(select(models.Territory))).scalars()
        }
        rows = (
            await ctx.session.execute(
                select(models.Location.id, models.Location.path)
                .where(models.Location.kind == "system")
                .order_by(models.Location.path)
            )
        ).all()
        systems = [row[0] for row in rows]
        paths = {row[0]: row[1] for row in rows}

        changes = 0
        for system_id in systems:
            share = normalise(raw.get(system_id, {}))
            before = {f: float(r.influence) for (s, f), r in existing.items() if s == system_id}
            after: dict[int, float] = {}
            for faction_id in (1, 2, 3):
                value = blend(before.get(faction_id, 0.0), share.get(faction_id, 0.0), ctx.rules.world)
                after[faction_id] = value
                row = existing.get((system_id, faction_id))
                if row is None:
                    ctx.session.add(
                        models.Territory(
                            system_id=system_id, faction_id=faction_id, influence=Decimal(str(value))
                        )
                    )
                else:
                    row.influence = Decimal(f"{value:.4f}")
            was, now = controller(before, ctx.rules.world), controller(after, ctx.rules.world)
            if was != now:
                changes += 1
                ctx.emit(
                    EventDraft(
                        type=EventType.TERRITORY_CHANGE,
                        origin=paths[system_id],
                        scope=Scope.SYSTEM,
                        visibility=Visibility.PUBLIC,
                        severity=Severity.NOTABLE,
                        payload={
                            "system_id": str(system_id),
                            "from_faction": was,
                            "to_faction": now,
                        },
                    )
                )
        return {"systems": len(systems), "controller_changes": changes}

    async def _presence(self, ctx: TickContext) -> dict[UUID, dict[int, float]]:
        raw: dict[UUID, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        ships = (
            await ctx.session.execute(
                select(models.Ship.system_id, models.Player.faction_id)
                .join(models.Player, models.Player.id == models.Ship.player_id)
                .where(models.Ship.destroyed_on.is_(None), models.Player.faction_id.is_not(None))
            )
        ).all()
        for system_id, faction_id in ships:
            raw[system_id][faction_id] += SHIP_WEIGHT

        agents = (
            await ctx.session.execute(
                select(models.NpcAgent.system_id, models.NpcAgent.faction_id).where(
                    models.NpcAgent.faction_id.is_not(None)
                )
            )
        ).all()
        for system_id, faction_id in agents:
            raw[system_id][faction_id] += SHIP_WEIGHT

        homes = (
            (
                await ctx.session.execute(
                    select(models.Location).where(models.Location.attrs.has_key("home_for"))
                )
            )
            .scalars()
            .all()
        )
        codes = {"empire": 1, "republic": 2, "pirates": 3}
        for home in homes:
            faction_id = codes.get(str(home.attrs.get("home_for")))
            if faction_id:
                raw[home.id][faction_id] += STATION_WEIGHT
        return raw
