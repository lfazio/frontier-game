"""The only place the wall clock is read — ARCH ADR-6."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import blake2b
from os import urandom
from random import Random
from uuid import UUID


class SystemClock:
    """The world day is world state, not clock state: it comes from `core.world_state`."""

    def now(self) -> datetime:
        return datetime.now(UTC)  # noqa: TID251 — the adapter is the exception ARCH ADR-6 allows


class SeededRng:
    """Deterministic randomness. Callers pass the world day as the first part — ARCH §9.3."""

    def __init__(self, world_seed: str) -> None:
        self._seed = world_seed

    def for_(self, *parts: str | int) -> Random:
        material = "|".join([self._seed, *map(str, parts)])
        return Random(blake2b(material.encode(), digest_size=8).hexdigest())


class UuidFactory:
    """UUIDv7: time-ordered, so an id doubles as a feed cursor — SDD §10.3."""

    def __init__(self, clock: SystemClock) -> None:
        self._clock = clock

    def new(self) -> UUID:
        millis = int(self._clock.now().timestamp() * 1000)
        rand = urandom(10)
        value = (
            (millis & 0xFFFFFFFFFFFF) << 80
            | 0x7 << 76
            | (rand[0] & 0x0F) << 72
            | rand[1] << 64
            | 0b10 << 62
            | int.from_bytes(rand[2:], "big") & ((1 << 62) - 1)
        )
        return UUID(int=value)
