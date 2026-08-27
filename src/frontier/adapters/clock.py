"""The only place the wall clock is read — ARCH ADR-6."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import blake2b
from os import urandom
from random import Random
from uuid import UUID


class SystemClock:
    def __init__(self, epoch: datetime, world_day: int | None = None) -> None:
        self._epoch = epoch
        self._forced_day = world_day

    def now(self) -> datetime:
        return datetime.now(UTC)  # noqa: TID251 — the adapter is the exception ARCH ADR-6 allows

    def world_day(self) -> int:
        if self._forced_day is not None:
            return self._forced_day
        return (self.now() - self._epoch).days


class SeededRng:
    """Deterministic per-entity randomness — ARCH §9.3."""

    def __init__(self, world_seed: str, world_day_source: SystemClock) -> None:
        self._seed = world_seed
        self._clock = world_day_source

    def for_(self, *parts: str | int) -> Random:
        material = "|".join([self._seed, str(self._clock.world_day()), *map(str, parts)])
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
