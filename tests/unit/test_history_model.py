"""The Model's arithmetic, and the boundary it may not cross — GDD §8.2 to §8.6."""

from __future__ import annotations

from dataclasses import fields

import pytest

from frontier.domain.psychohistory.disclosure import Detail, detail_for, disclose
from frontier.domain.psychohistory.model import (
    Forecast,
    Observation,
    Outlook,
    Variable,
    confidence,
    deviation,
    forecast,
    observe,
    project,
)


def sample(**overrides) -> Observation:
    base = {
        "stock_ratio": 1.0,
        "trade_flow": 0.3,
        "patrol_strength": 0.5,
        "raider_pressure": 0.2,
        "top_influence": 0.6,
        "combats": 0,
        "losses": 0,
    }
    return Observation(**{**base, **overrides})


def test_the_model_cannot_be_handed_a_player():
    """GDD §8.4 at the type level: no field of an observation identifies anyone."""
    names = {f.name for f in fields(Observation)}
    identifying = {n for n in names if n.endswith("_id") or n in {"id", "player", "callsign"}}
    assert not identifying, identifying
    assert names == {
        "stock_ratio",
        "trade_flow",
        "patrol_strength",
        "raider_pressure",
        "top_influence",
        "combats",
        "losses",
    }


def test_every_variable_stays_on_the_unit_interval():
    for value in observe(sample(stock_ratio=9.0, raider_pressure=1.0, combats=99)).values():
        assert 0.0 <= value <= 1.0


def test_violence_lowers_stability():
    calm = observe(sample())[Variable.STABILITY]
    war = observe(sample(combats=8, losses=3))[Variable.STABILITY]
    assert war < calm


def test_scarcity_lowers_economic_health():
    balanced = observe(sample(stock_ratio=1.0))[Variable.ECONOMIC_HEALTH]
    starved = observe(sample(stock_ratio=0.1))[Variable.ECONOMIC_HEALTH]
    assert starved < balanced


def test_expectation_moves_slowly():
    """Historical inertia: one surprising cycle does not rewrite the trajectory — GDD §8.2."""
    observed = {Variable.STABILITY: 0.0}
    expected = project({Variable.STABILITY: 1.0}, observed)
    assert 0.8 < expected[Variable.STABILITY] < 1.0


def test_deviation_is_zero_when_the_world_behaves():
    observed = observe(sample())
    assert deviation(observed, observed) == 0.0


def test_confidence_falls_as_the_world_surprises_the_model():
    assert confidence(0.0, 0.0) > confidence(0.3, 0.0) > confidence(0.3, 1.0)


def test_confidence_never_reaches_certainty_or_zero():
    assert 0.0 < confidence(9.0, 9.0) < confidence(0.0, 0.0) < 1.0


def test_a_forecast_is_probabilistic_and_never_names_anything():
    predictions = forecast(observe(sample(raider_pressure=0.9)), 0.1, 0.0)
    assert {p.kind for p in predictions} == set(Outlook)
    assert all(0.0 <= p.probability <= 1.0 for p in predictions)


def test_pirates_matter_more_where_nobody_is_guarding():
    guarded = forecast(observe(sample(raider_pressure=0.8, patrol_strength=0.9)), 0.0, 0.0)
    open_ = forecast(observe(sample(raider_pressure=0.8, patrol_strength=0.0)), 0.0, 0.0)
    takeover = Outlook.PIRATE_TAKEOVER
    assert (
        next(p for p in open_ if p.kind is takeover).probability
        > next(p for p in guarded if p.kind is takeover).probability
    )


@pytest.mark.parametrize(
    ("knowledge", "expected"),
    [(0, Detail.HEADLINE), (10, Detail.NARROWED), (30, Detail.PRECISE), (60, Detail.REASONED)],
)
def test_knowledge_buys_resolution(knowledge, expected):
    assert detail_for(knowledge) is expected


def test_everyone_can_read_a_forecast_but_not_at_the_same_resolution():
    """Q2: a public good of variable quality — access never varies, only precision."""
    prediction = Forecast(Outlook.ARMED_CONFLICT, 0.673, 0.8)
    novice = disclose(prediction, knowledge=0)
    scholar = disclose(prediction, knowledge=60, drivers={"stability": 0.3})

    assert novice.probability and scholar.probability
    novice_band = novice.interval[1] - novice.interval[0]
    scholar_band = scholar.interval[1] - scholar.interval[0]
    assert scholar_band < novice_band
    assert novice.reasoning is None
    assert scholar.reasoning == {"stability": 0.3}
