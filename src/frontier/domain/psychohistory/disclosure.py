"""What a reader is told, and how precisely — GDD §8.3, Q2.

Forecasts are a public good: anyone may read one. What Knowledge buys is *resolution*, never
access, so a forecast can never gate content or be sold.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from frontier.domain.psychohistory.model import Forecast


class Detail(IntEnum):
    HEADLINE = 0
    NARROWED = 1
    PRECISE = 2
    REASONED = 3


THRESHOLDS = ((60, Detail.REASONED), (30, Detail.PRECISE), (10, Detail.NARROWED))
BANDS = {Detail.HEADLINE: 0.20, Detail.NARROWED: 0.10, Detail.PRECISE: 0.05, Detail.REASONED: 0.02}


def detail_for(knowledge: int) -> Detail:
    for floor, detail in THRESHOLDS:
        if knowledge >= floor:
            return detail
    return Detail.HEADLINE


@dataclass(frozen=True, slots=True)
class Disclosed:
    kind: str
    probability: float
    interval: tuple[float, float]
    confidence: float
    detail: str
    reasoning: dict[str, float] | None


def disclose(prediction: Forecast, knowledge: int, drivers: dict[str, float] | None = None) -> Disclosed:
    detail = detail_for(knowledge)
    band = BANDS[detail]
    rounded = round(prediction.probability / band) * band
    return Disclosed(
        kind=prediction.kind.value,
        probability=round(min(1.0, max(0.0, rounded)), 3),
        interval=(round(max(0.0, rounded - band), 3), round(min(1.0, rounded + band), 3)),
        confidence=round(prediction.confidence, 3),
        detail=detail.name.lower(),
        reasoning=drivers if detail is Detail.REASONED else None,
    )
