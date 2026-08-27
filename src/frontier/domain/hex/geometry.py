"""Hex algebra — SDD §3.2. Flat-top axial layout, cube metric."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

from frontier.domain.hex.coordinates import Axial, HexAddr, ScaleMismatch

DIRECTIONS: Final[tuple[Axial, ...]] = (
    Axial(1, 0),
    Axial(1, -1),
    Axial(0, -1),
    Axial(-1, 0),
    Axial(-1, 1),
    Axial(0, 1),
)


def neighbours(a: Axial) -> tuple[Axial, ...]:
    return tuple(a + d for d in DIRECTIONS)


def distance(a: Axial, b: Axial) -> int:
    ax, ay, az = a.cube
    bx, by, bz = b.cube
    return (abs(ax - bx) + abs(ay - by) + abs(az - bz)) // 2


def addr_distance(a: HexAddr, b: HexAddr) -> int:
    """Distance is only meaningful between siblings — GDD §2.3."""
    if a.level != b.level or a.parent() != b.parent():
        raise ScaleMismatch(f"{a} and {b} are not siblings")
    return distance(a.tip, b.tip)


def ring(centre: Axial, radius: int) -> list[Axial]:
    if radius < 0:
        raise ValueError("radius must not be negative")
    if radius == 0:
        return [centre]
    results: list[Axial] = []
    current = centre + Axial(DIRECTIONS[4].q * radius, DIRECTIONS[4].r * radius)
    for direction in DIRECTIONS:
        for _ in range(radius):
            results.append(current)
            current = current + direction
    return results


def spiral(centre: Axial, radius: int) -> list[Axial]:
    return [hex_ for r in range(radius + 1) for hex_ in ring(centre, r)]


def within(centre: Axial, radius: int) -> Iterator[Axial]:
    for dq in range(-radius, radius + 1):
        low = max(-radius, -dq - radius)
        high = min(radius, -dq + radius)
        for dr in range(low, high + 1):
            yield centre + Axial(dq, dr)


def line(a: Axial, b: Axial) -> list[Axial]:
    """Cube interpolation with a fixed nudge so ties break deterministically, not by float accident."""
    n = distance(a, b)
    if n == 0:
        return [a]
    ax, ay, az = (c + e for c, e in zip(a.cube, (1e-6, 1e-6, -2e-6), strict=True))
    bx, by, bz = b.cube
    out: list[Axial] = []
    for step in range(n + 1):
        t = step / n
        out.append(_round_cube(ax + (bx - ax) * t, ay + (by - ay) * t, az + (bz - az) * t))
    return out


def _round_cube(x: float, y: float, z: float) -> Axial:
    rx, ry, rz = round(x), round(y), round(z)
    dx, dy, dz = abs(rx - x), abs(ry - y), abs(rz - z)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    return Axial(rx, ry)
