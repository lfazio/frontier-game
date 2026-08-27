"""What a ship does while its player is offline — GDD §4.4, §3.5."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Posture(StrEnum):
    EVADE = "evade"
    DEFEND = "defend"
    AGGRESSIVE = "aggressive"
    SURRENDER_CARGO = "surrender_cargo"


@dataclass(frozen=True, slots=True)
class StandingOrders:
    posture: Posture = Posture.EVADE
    engage_hostile: bool = False
    engage_above_cargo: int | None = None
    retreat_at_hull_pct: int = 50
    auto_reply: str | None = None

    @classmethod
    def default(cls) -> StandingOrders:
        """A player who never opens the screen loses cargo, not a ship."""
        return cls()
