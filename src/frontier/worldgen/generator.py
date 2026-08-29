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
from frontier.domain.hex.geometry import distance, spiral, within

NAMESPACE: Final = UUID("2f9c0a5e-2b7a-4c31-9d1a-4a0d5f1e7b00")

PLANETS_PER_SYSTEM: Final = (3, 8)
STATIONS_PER_SYSTEM: Final = (1, 3)
MIN_SYSTEM_SEPARATION: Final = 2
STATION_TYPES: Final = ("agricultural", "industrial", "mining", "refinery", "trade_hub")
FACTIONS: Final = ("empire", "republic", "pirates")


@dataclass(frozen=True, slots=True)
class Shape:
    """How big the world is, and how much of it is empty — all of it tunable rule data.

    Both levels are filled discs: every hex is a row, empty ones included (D-17). A region is
    therefore continuous space, and what lies between its systems is a place, not a gap.
    """

    regions: int = 4
    region_radius: int = 16
    system_radius: int = 8
    systems_per_region: tuple[int, int] = (10, 14)

    @classmethod
    def of(cls, world: Any) -> Shape:
        return cls(
            regions=world.regions,
            region_radius=world.region_radius,
            system_radius=world.system_radius,
            systems_per_region=(world.systems_per_region_min, world.systems_per_region_max),
        )


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


def generate(rng_for: Any, shape: Shape | None = None) -> list[GeneratedLocation]:
    shape = shape or Shape()
    galaxy = _node(None, Axial(0, 0), "galaxy", name="Frontier")
    out: list[GeneratedLocation] = [galaxy]

    for region_index in range(shape.regions):
        rng: Random = rng_for("worldgen", "region", region_index)
        region = _node(galaxy, _region_slot(region_index), "region", name=f"Region {region_index + 1}")
        out.append(region)
        out.extend(_systems(region, rng, region_index, shape))
    return out


def _region_slot(index: int) -> Axial:
    """Regions are packed from the centre outward, so the galaxy is one connected shape."""
    return spiral(Axial(0, 0), 2)[index]


def _systems(
    region: GeneratedLocation, rng: Random, region_index: int, shape: Shape
) -> list[GeneratedLocation]:
    count = rng.randint(*shape.systems_per_region)
    placed: list[Axial] = []
    candidates = list(within(Axial(0, 0), shape.region_radius))
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
        rows.extend(_system_contents(system, Random(rng.random()), bool(home_for), shape))

    # What lies between the systems is empty space, and empty space is somewhere — an address
    # a ship can be reported at and, once the Harrowing ships (GDD §8.12), something can arrive in.
    taken = {(slot.q, slot.r) for slot in placed}
    rows.extend(
        _node(region, hex_, "void")
        for hex_ in within(Axial(0, 0), shape.region_radius)
        if (hex_.q, hex_.r) not in taken
    )
    return rows


def _system_contents(
    system: GeneratedLocation, rng: Random, is_home: bool, shape: Shape
) -> list[GeneratedLocation]:
    """Every in-system hex is a row, so a destination check is a lookup — see D-17."""
    occupied: dict[tuple[int, int], tuple[str, dict[str, Any]]] = {(0, 0): ("star", {})}

    for _ in range(rng.randint(*PLANETS_PER_SYSTEM)):
        slot = _free_slot(rng, occupied, low=2, high=shape.system_radius)
        occupied[slot] = ("planet", {})
    for _ in range(rng.randint(*STATIONS_PER_SYSTEM)):
        slot = _free_slot(rng, occupied, low=1, high=5)
        occupied[slot] = ("station", {"station_type": rng.choice(STATION_TYPES)})

    rows: list[GeneratedLocation] = []
    spawn_chosen = False
    for hex_ in within(Axial(0, 0), shape.system_radius):
        kind, attrs = occupied.get((hex_.q, hex_.r), ("void", {}))
        node = _node(system, hex_, kind, attrs=dict(attrs))
        if is_home:
            node.discovered_on = 0
            if kind == "station" and not spawn_chosen:
                node.attrs["spawn"] = system.attrs.get("home_for")
                spawn_chosen = True
        rows.append(node)
    return rows


def _free_slot(rng: Random, taken: dict[tuple[int, int], Any], low: int, high: int) -> tuple[int, int]:
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
