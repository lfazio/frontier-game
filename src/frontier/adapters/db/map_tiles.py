"""Map tiles — the client never receives the whole world. GDD §10.4 C5, SDD §9.1.

A read model lives with the other SQL adapters, beside the feed: it is built by querying the
database, so putting it in its own layer above `adapters` would only invert the dependency
(*ARCH §16* sketches a separate `projections/` package; see SDD D-34).

An undiscovered location is **absent** from the payload, not marked hidden: the payload itself
must not reveal that something is there.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from frontier.adapters.db import models
from frontier.domain.hex.coordinates import HexAddr, Level
from frontier.domain.hex.geometry import addr_distance

# The shape of the galaxy is common knowledge — a spectator with no account sees every region
# and system (`public_tile`), so a player must never see fewer. Discovery gates what is *inside*
# a system, which is the thing a player can actually learn by going there.
# Empty space is charted like anything else: the chart is a filled grid, not a scatter of points.
CHART_KINDS = ("region", "system", "void")
INTERIOR_KINDS = ("station", "planet", "star")


@dataclass(frozen=True, slots=True)
class Tile:
    path: str
    level: int
    world_day: int
    entries: list[dict[str, Any]]

    def etag(self) -> str:
        material = json.dumps(
            {"p": self.path, "d": self.world_day, "e": self.entries},
            sort_keys=True,
            separators=(",", ":"),
        )
        return '"' + hashlib.blake2b(material.encode(), digest_size=16).hexdigest() + '"'

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "level": self.level, "world_day": self.world_day, "entries": self.entries}


class MapTiles:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def tile(
        self, prefix: HexAddr, player_id: UUID, world_day: int, sensor_range: int, position: HexAddr | None
    ) -> Tile:
        chart = int(prefix.level) < int(Level.SYSTEM)
        rows = (
            (
                await self._s.execute(
                    select(models.Location)
                    .where(text("path <@ CAST(:prefix AS ltree)").bindparams(prefix=prefix.ltree()))
                    .where(models.Location.level == int(prefix.level) + 1)
                    .where(models.Location.kind.in_(CHART_KINDS if chart else INTERIOR_KINDS))
                    .order_by(models.Location.path)
                )
            )
            .scalars()
            .all()
        )

        control = await self._control(prefix)
        if chart:
            entries = [self._entry(row, control) for row in rows]
        else:
            known = await self._known(player_id)
            entries = [
                self._entry(row, control)
                for row in rows
                if row.id in known or self._in_sensor_range(row, position, sensor_range)
            ]
        return Tile(path=str(prefix), level=int(prefix.level), world_day=world_day, entries=entries)

    def _entry(self, row: models.Location, control: dict[UUID, int]) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "id": str(row.id),
            "path": str(row.path),
            "kind": row.kind,
            "name": row.name,
            "q": row.q,
            "r": row.r,
        }
        if row.kind == "system" and row.id in control:
            entry["controller"] = control[row.id]
        if row.kind == "station" and "station_type" in row.attrs:
            entry["station_type"] = row.attrs["station_type"]
        return entry

    def _in_sensor_range(self, row: models.Location, position: HexAddr | None, reach: int) -> bool:
        if position is None or row.level != int(Level.PLANET):
            return False
        try:
            return addr_distance(position, row.path) <= reach
        except Exception:
            return False

    async def public_tile(self, prefix: HexAddr, world_day: int) -> Tile:
        """The star chart, and nothing inside a system — UX §9.

        A spectator has no sight (*UX §4.1*), so it sees the shape of the galaxy and who holds
        it, never what is flying around in it. Strictly weaker than any player's tile.
        """
        # The chart stops at the system: inside one, even the empty hexes are not a spectator's
        # to count. Sharing the kind list with `tile` is not enough — the level gate is the rule.
        if int(prefix.level) >= int(Level.SYSTEM):
            return Tile(path=str(prefix), level=int(prefix.level), world_day=world_day, entries=[])

        rows = (
            (
                await self._s.execute(
                    select(models.Location)
                    .where(text("path <@ CAST(:prefix AS ltree)").bindparams(prefix=prefix.ltree()))
                    .where(models.Location.level == int(prefix.level) + 1)
                    .where(models.Location.kind.in_(CHART_KINDS))
                    .order_by(models.Location.path)
                )
            )
            .scalars()
            .all()
        )
        control = await self._control(prefix)
        return Tile(
            path=str(prefix),
            level=int(prefix.level),
            world_day=world_day,
            entries=[self._entry(row, control) for row in rows],
        )

    async def _known(self, player_id: UUID) -> set[UUID]:
        rows = (
            (
                await self._s.execute(
                    select(models.PlayerDiscovery.location_id).where(
                        models.PlayerDiscovery.player_id == player_id
                    )
                )
            )
            .scalars()
            .all()
        )
        return set(rows)

    async def _control(self, prefix: HexAddr) -> dict[UUID, int]:
        rows = (
            (
                await self._s.execute(
                    select(models.Territory)
                    .join(models.Location, models.Location.id == models.Territory.system_id)
                    .where(text("path <@ CAST(:prefix AS ltree)").bindparams(prefix=prefix.ltree()))
                )
            )
            .scalars()
            .all()
        )
        best: dict[UUID, tuple[float, int]] = {}
        for row in rows:
            score = float(row.influence)
            if score > best.get(row.system_id, (0.0, 0))[0]:
                best[row.system_id] = (score, row.faction_id)
        return {k: v[1] for k, v in best.items() if v[0] >= 0.5}
