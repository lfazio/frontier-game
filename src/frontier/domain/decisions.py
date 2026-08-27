"""Command decisions — expected refusals are values, not exceptions. ARCH §11.4, SDD §3.3."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RejectionCode(StrEnum):
    INSUFFICIENT_AP = "INSUFFICIENT_AP"
    INSUFFICIENT_FUEL = "INSUFFICIENT_FUEL"
    INSUFFICIENT_CREDITS = "INSUFFICIENT_CREDITS"
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    INSUFFICIENT_CARGO = "INSUFFICIENT_CARGO"
    CARGO_FULL = "CARGO_FULL"
    NOT_ADJACENT = "NOT_ADJACENT"
    SCALE_MISMATCH = "SCALE_MISMATCH"
    NOT_DOCKED = "NOT_DOCKED"
    MUST_LAUNCH_FIRST = "MUST_LAUNCH_FIRST"
    IN_TRANSIT = "IN_TRANSIT"
    TARGET_NOT_VISIBLE = "TARGET_NOT_VISIBLE"
    TARGET_UNKNOWN = "TARGET_UNKNOWN"
    TARGET_DOCKED = "TARGET_DOCKED"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    UNKNOWN_DESTINATION = "UNKNOWN_DESTINATION"


@dataclass(frozen=True, slots=True)
class Rejected:
    code: RejectionCode
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Accepted:
    ap_cost: int
    fuel_cost: int = 0


type Decision = Accepted | Rejected
