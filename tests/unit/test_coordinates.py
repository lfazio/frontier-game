from __future__ import annotations

import pytest

from frontier.domain.hex.coordinates import Axial, HexAddr, Level, ScaleMismatch
from frontier.domain.hex.geometry import addr_distance


def addr(*pairs: tuple[int, int]) -> HexAddr:
    return HexAddr(tuple(Axial(q, r) for q, r in pairs))


def test_level_comes_from_depth():
    assert addr((0, 0)).level is Level.GALAXY
    assert addr((0, 0), (1, 0), (4, 2)).level is Level.SYSTEM


def test_ltree_uses_two_letter_prefixes():
    assert addr((124, 87), (3, 1)).ltree() == "ga124_87.re3_1"


def test_negative_axials_encode_with_n():
    assert addr((-3, 1)).ltree() == "gan3_1"


def test_parse_round_trips():
    a = addr((124, 87), (-3, 1), (31, 14))
    assert HexAddr.parse(str(a)) == a


def test_parse_rejects_a_label_at_the_wrong_level():
    with pytest.raises(ValueError):
        HexAddr.parse("re3_1")


def test_containment_is_a_prefix_test():
    system = addr((0, 0), (1, 0), (4, 2))
    assert system.contains(system.child(Axial(9, 9)))
    assert not system.child(Axial(9, 9)).contains(system)


def test_distance_between_non_siblings_is_refused():
    with pytest.raises(ScaleMismatch):
        addr_distance(addr((0, 0), (1, 0)), addr((0, 0), (2, 0), (1, 1)))


def test_address_cannot_be_deeper_than_local():
    with pytest.raises(ValueError):
        HexAddr(tuple(Axial(0, 0) for _ in range(len(Level) + 1)))
