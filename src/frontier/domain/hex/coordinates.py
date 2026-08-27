"""Hierarchical hex addressing — GDD §2.2, §2.3; SDD §3.1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Final


class Level(IntEnum):
    GALAXY = 0
    REGION = 1
    SYSTEM = 2
    PLANET = 3
    SECTOR = 4
    LOCAL = 5


LEVEL_PREFIX: Final[tuple[str, ...]] = ("ga", "re", "sy", "pl", "se", "lo")
PREFIX_LEVEL: Final[dict[str, Level]] = {p: Level(i) for i, p in enumerate(LEVEL_PREFIX)}


class ScaleMismatch(ValueError):
    """Raised when two addresses are compared across levels or across parents."""


@dataclass(frozen=True, slots=True)
class Axial:
    q: int
    r: int

    @property
    def cube(self) -> tuple[int, int, int]:
        return self.q, self.r, -self.q - self.r

    def __add__(self, other: Axial) -> Axial:
        return Axial(self.q + other.q, self.r + other.r)

    def __sub__(self, other: Axial) -> Axial:
        return Axial(self.q - other.q, self.r - other.r)


def _encode(value: int) -> str:
    return f"n{-value}" if value < 0 else str(value)


def _decode(token: str) -> int:
    return -int(token[1:]) if token.startswith("n") else int(token)


@dataclass(frozen=True, slots=True)
class HexAddr:
    """One Axial per level, galaxy first. Position in the tuple determines the level."""

    steps: tuple[Axial, ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("an address needs at least a galaxy step")
        if len(self.steps) > len(Level):
            raise ValueError(f"address deeper than {Level.LOCAL.name}")

    @property
    def level(self) -> Level:
        return Level(len(self.steps) - 1)

    @property
    def tip(self) -> Axial:
        return self.steps[-1]

    def parent(self) -> HexAddr | None:
        return HexAddr(self.steps[:-1]) if len(self.steps) > 1 else None

    def child(self, step: Axial) -> HexAddr:
        return HexAddr((*self.steps, step))

    def sibling(self, step: Axial) -> HexAddr:
        return HexAddr((*self.steps[:-1], step))

    def contains(self, other: HexAddr) -> bool:
        return len(other.steps) >= len(self.steps) and other.steps[: len(self.steps)] == self.steps

    def ltree(self) -> str:
        return ".".join(f"{LEVEL_PREFIX[i]}{_encode(s.q)}_{_encode(s.r)}" for i, s in enumerate(self.steps))

    def __str__(self) -> str:
        return self.ltree().replace(".", "/")

    @classmethod
    def parse(cls, text: str) -> HexAddr:
        steps: list[Axial] = []
        for index, label in enumerate(text.replace("/", ".").split(".")):
            prefix, body = label[:2], label[2:]
            if PREFIX_LEVEL.get(prefix) != index:
                raise ValueError(f"label {label!r} is not valid at level {index}")
            q, _, r = body.partition("_")
            steps.append(Axial(_decode(q), _decode(r)))
        return cls(tuple(steps))
