"""The historical model — GDD §8.2 to §8.6, SDD §6.

Pure arithmetic over population-scale aggregates. Nothing here takes a player as input and
nothing here can name one: the type of `Observation` is the enforcement at this layer, and the
database grants are the enforcement below it (ARCH ADR-12).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

INERTIA = 0.85


class Variable(StrEnum):
    ECONOMIC_HEALTH = "economic_health"
    STABILITY = "stability"
    MILITARY_STRENGTH = "military_strength"
    LEGITIMACY = "legitimacy"
    PIRATE_INFLUENCE = "pirate_influence"
    TRADE_CONNECTIVITY = "trade_connectivity"


class Outlook(StrEnum):
    ARMED_CONFLICT = "armed_conflict"
    ECONOMIC_COLLAPSE = "economic_collapse"
    PIRATE_TAKEOVER = "pirate_takeover"


@dataclass(frozen=True, slots=True)
class Observation:
    """One region's aggregate state. There is deliberately no player-shaped field here."""

    stock_ratio: float
    trade_flow: float
    patrol_strength: float
    raider_pressure: float
    top_influence: float
    combats: int
    losses: int


@dataclass(frozen=True, slots=True)
class Forecast:
    kind: Outlook
    probability: float
    confidence: float


def observe(sample: Observation) -> dict[Variable, float]:
    """Aggregates in, variables out, all on 0..1."""
    scarcity = abs(1.0 - _clamp(sample.stock_ratio, 0.0, 3.0))
    violence = _saturate(sample.combats + sample.losses * 2, 12)
    return {
        Variable.ECONOMIC_HEALTH: _clamp(1.0 - scarcity / 2, 0.0, 1.0),
        Variable.STABILITY: _clamp(1.0 - violence * 0.6 - sample.raider_pressure * 0.4, 0.0, 1.0),
        Variable.MILITARY_STRENGTH: _clamp(sample.patrol_strength, 0.0, 1.0),
        Variable.LEGITIMACY: _clamp(sample.top_influence, 0.0, 1.0),
        Variable.PIRATE_INFLUENCE: _clamp(sample.raider_pressure, 0.0, 1.0),
        Variable.TRADE_CONNECTIVITY: _clamp(sample.trade_flow, 0.0, 1.0),
    }


def project(
    previous_expected: dict[Variable, float], observed: dict[Variable, float]
) -> dict[Variable, float]:
    """Historical inertia: the expected trajectory moves slowly, and reality tugs at it."""
    return {
        variable: _clamp(previous_expected.get(variable, value) * INERTIA + value * (1 - INERTIA), 0.0, 1.0)
        for variable, value in observed.items()
    }


def deviation(observed: dict[Variable, float], expected: dict[Variable, float]) -> float:
    """How far the world has drifted from what the Model expected — GDD §8.3."""
    if not observed:
        return 0.0
    gaps = [abs(value - expected.get(variable, value)) for variable, value in observed.items()]
    return sum(gaps) / len(gaps)


def confidence(drift: float, cumulative_surprise: float) -> float:
    """Confidence falls as players produce outcomes the Model did not expect — GDD §8.5."""
    return _clamp(1.0 - drift * 1.5 - cumulative_surprise * 0.25, 0.05, 0.99)


def forecast(observed: dict[Variable, float], drift: float, cumulative_surprise: float) -> list[Forecast]:
    certainty = confidence(drift, cumulative_surprise)
    unrest = 1.0 - observed.get(Variable.STABILITY, 1.0)
    poverty = 1.0 - observed.get(Variable.ECONOMIC_HEALTH, 1.0)
    pirates = observed.get(Variable.PIRATE_INFLUENCE, 0.0)
    guard = observed.get(Variable.MILITARY_STRENGTH, 0.0)

    return [
        Forecast(Outlook.ARMED_CONFLICT, _clamp(unrest * 0.7 + pirates * 0.3, 0.0, 1.0), certainty),
        Forecast(Outlook.ECONOMIC_COLLAPSE, _clamp(poverty * 0.8 + unrest * 0.2, 0.0, 1.0), certainty),
        Forecast(Outlook.PIRATE_TAKEOVER, _clamp(pirates * 0.8 * (1.0 - guard), 0.0, 1.0), certainty),
    ]


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _saturate(value: float, scale: float) -> float:
    return min(1.0, value / scale) if scale else 0.0
