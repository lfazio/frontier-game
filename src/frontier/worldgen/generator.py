"""World generation — SDD §7. Pure: it returns rows, it does not write them.

Every draw comes from the seeded RNG, so a seed reproduces a world exactly. That is what makes
the simulation soak test meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Any, Final
from uuid import UUID, uuid5

from frontier.domain.hex.coordinates import Axial, HexAddr, Level
from frontier.domain.hex.geometry import distance, within

NAMESPACE: Final = UUID("2f9c0a5e-2b7a-4c31-9d1a-4a0d5f1e7b00")

REGIONS: Final = 4
SYSTEMS_PER_REGION: Final = (10, 14)
SYSTEM_RADIUS: Final = 8
PLANETS_PER_SYSTEM: Final = (3, 8)
STATIONS_PER_SYSTEM: Final = (1, 3)
MIN_SYSTEM_SEPARATION: Final = 2
STATION_TYPES: Final = ("agricultural", "industrial", "mining", "refinery", "trade_hub")
FACTIONS: Final = ("empire", "republic", "pirates")


@dataclass(slots=True)
class GeneratedLocation:
    id: UUID
    parent_id: UUID | None
    level: int
    q: int
    r: int
    path: HexAddr
    kind: str
    name: str | None = None
    discovered_on: int | None = None
    attrs: dict[str, Any] = field(default_factory=dict)


def _id(path: HexAddr) -> UUID:
    """Identity follows the address, so regeneration from a seed is stable."""
    return uuid5(NAMESPACE, path.ltree())


def _node(parent: GeneratedLocation | None, step: Axial, kind: str, **extra: Any) -> GeneratedLocation:
    path = parent.path.child(step) if parent else HexAddr((step,))
    return GeneratedLocation(
        id=_id(path),
        parent_id=parent.id if parent else None,
        level=path.level,
        q=step.q,
        r=step.r,
        path=path,
        kind=kind,
        **extra,
    )


def generate(rng_for: Any) -> list[GeneratedLocation]:
    galaxy = _node(None, Axial(0, 0), "galaxy", name="Frontier")
    out: list[GeneratedLocation] = [galaxy]

    for region_index in range(REGIONS):
        rng: Random = rng_for("worldgen", "region", region_index)
        region = _node(galaxy, _ring_slot(region_index), "region", name=f"Region {region_index + 1}")
        out.append(region)
        out.extend(_systems(region, rng, region_index))
    return out


def _ring_slot(index: int) -> Axial:
    spread = [Axial(1, 0), Axial(-1, 1), Axial(0, -1), Axial(0, 1)]
    return spread[index % len(spread)]


def _systems(region: GeneratedLocation, rng: Random, region_index: int) -> list[GeneratedLocation]:
    count = rng.randint(*SYSTEMS_PER_REGION)
    placed: list[Axial] = []
    candidates = list(within(Axial(0, 0), 6))
    rng.shuffle(candidates)
    for candidate in candidates:
        if len(placed) == count:
            break
        if all(distance(candidate, p) >= MIN_SYSTEM_SEPARATION for p in placed):
            placed.append(candidate)

    rows: list[GeneratedLocation] = []
    for index, slot in enumerate(placed):
        system = _node(region, slot, "system", name=f"R{region_index + 1}-S{index + 1}")
        home_for = FACTIONS[region_index] if region_index < len(FACTIONS) and index == 0 else None
        if home_for:
            system.attrs["home_for"] = home_for
        rows.append(system)
        rows.extend(_system_contents(system, Random(rng.random()), bool(home_for)))
    return rows


def _system_contents(system: GeneratedLocation, rng: Random, is_home: bool) -> list[GeneratedLocation]:
    """Every in-system hex is a row, so a destination check is a lookup — see D-17."""
    occupied: dict[tuple[int, int], tuple[str, dict[str, Any]]] = {(0, 0): ("star", {})}

    for _ in range(rng.randint(*PLANETS_PER_SYSTEM)):
        slot = _free_slot(rng, occupied, low=2)
        occupied[slot] = ("planet", {})
    for _ in range(rng.randint(*STATIONS_PER_SYSTEM)):
        slot = _free_slot(rng, occupied, low=1, high=5)
        occupied[slot] = ("station", {"station_type": rng.choice(STATION_TYPES)})

    rows: list[GeneratedLocation] = []
    spawn_chosen = False
    for hex_ in within(Axial(0, 0), SYSTEM_RADIUS):
        kind, attrs = occupied.get((hex_.q, hex_.r), ("void", {}))
        node = _node(system, hex_, kind, attrs=dict(attrs))
        if is_home:
            node.discovered_on = 0
            if kind == "station" and not spawn_chosen:
                node.attrs["spawn"] = system.attrs.get("home_for")
                spawn_chosen = True
        rows.append(node)
    return rows


def _free_slot(
    rng: Random, taken: dict[tuple[int, int], Any], low: int, high: int = SYSTEM_RADIUS
) -> tuple[int, int]:
    while True:
        radius = rng.randint(low, high)
        angle = rng.randrange(max(1, 6 * radius))
        from frontier.domain.hex.geometry import ring

        candidate = ring(Axial(0, 0), radius)[angle]
        key = (candidate.q, candidate.r)
        if key not in taken:
            return key


def summarise(rows: list[GeneratedLocation]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.kind] = counts.get(row.kind, 0) + 1
    counts["total"] = len(rows)
    counts["levels"] = len({r.level for r in rows})
    return counts


def levels_used(rows: list[GeneratedLocation]) -> set[Level]:
    return {Level(r.level) for r in rows}
