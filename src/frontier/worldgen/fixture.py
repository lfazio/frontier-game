"""The two-hex fixture world P0 is proved against — SDD §15 task 0.6.

Pure description only: the real generator (SDD §7) arrives in P1. This exists so the command
path can be exercised end to end before the location tree does.
"""

from __future__ import annotations

from typing import Any, Final

from frontier.domain.hex.coordinates import Axial, HexAddr

SYSTEM: Final = HexAddr((Axial(0, 0), Axial(1, 0), Axial(4, 2)))
HEXES: Final = (Axial(0, 0), Axial(1, 0), Axial(0, 1), Axial(-1, 1))

STARTING_SHIP: Final[dict[str, Any]] = {
    "hull": 100,
    "hull_max": 100,
    "fuel": 60,
    "fuel_max": 60,
    "cargo_max": 20,
    "sensor_range": 3,
}


def starting_position() -> HexAddr:
    return SYSTEM.child(HEXES[0])


def addresses() -> tuple[HexAddr, ...]:
    return tuple(SYSTEM.child(h) for h in HEXES)
