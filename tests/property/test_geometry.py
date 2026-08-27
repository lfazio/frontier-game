from __future__ import annotations

from itertools import pairwise

from hypothesis import given
from hypothesis import strategies as st

from frontier.domain.hex.coordinates import Axial, HexAddr
from frontier.domain.hex.geometry import distance, line, neighbours, ring, within

axials = st.builds(Axial, st.integers(-60, 60), st.integers(-60, 60))


@given(a=axials, b=axials, c=axials)
def test_distance_is_a_metric(a, b, c):
    assert distance(a, a) == 0
    assert distance(a, b) == distance(b, a)
    assert distance(a, c) <= distance(a, b) + distance(b, c)


@given(a=axials)
def test_every_neighbour_is_distance_one(a):
    assert {distance(a, n) for n in neighbours(a)} == {1}


@given(centre=axials, radius=st.integers(0, 12))
def test_ring_size_and_radius(centre, radius):
    r = ring(centre, radius)
    assert len(r) == (6 * radius if radius else 1)
    assert {distance(centre, h) for h in r} == {radius}


@given(centre=axials, radius=st.integers(0, 8))
def test_within_covers_exactly_the_disc(centre, radius):
    disc = set(within(centre, radius))
    assert all(distance(centre, h) <= radius for h in disc)
    assert len(disc) == 1 + 3 * radius * (radius + 1)


@given(a=axials, b=axials)
def test_line_is_contiguous_and_ends_where_asked(a, b):
    path = line(a, b)
    assert path[0] == a and path[-1] == b
    assert all(distance(x, y) == 1 for x, y in pairwise(path))


@given(steps=st.lists(st.tuples(st.integers(-99, 99), st.integers(-99, 99)), min_size=1, max_size=6))
def test_ltree_round_trip(steps):
    a = HexAddr(tuple(Axial(q, r) for q, r in steps))
    assert HexAddr.parse(a.ltree().replace(".", "/")) == a
