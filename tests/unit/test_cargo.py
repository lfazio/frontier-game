from __future__ import annotations

import pytest

from frontier.domain.fleet.cargo import Cargo


def test_adding_tracks_a_weighted_cost_basis():
    hold = Cargo()
    hold.add("grain", 10, 100)
    hold.add("grain", 10, 200)
    assert hold.qty("grain") == 20
    assert hold.cost_basis["grain"] == 150


def test_removing_everything_clears_the_line():
    hold = Cargo()
    hold.add("ore", 5, 60)
    hold.remove("ore", 5)
    assert hold.lines == {} and hold.cost_basis == {}


def test_removing_more_than_held_is_refused():
    hold = Cargo()
    hold.add("ore", 5, 60)
    with pytest.raises(ValueError, match="only 5 held"):
        hold.remove("ore", 6)


def test_used_space_is_the_sum_of_the_lines():
    hold = Cargo()
    hold.add("ore", 5, 60)
    hold.add("grain", 3, 40)
    assert hold.used == 8
    assert hold.value_at({"ore": 10, "grain": 20}) == 110
