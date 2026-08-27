"""The market formula — SDD §6.4, criterion A5."""

from __future__ import annotations

from frontier.domain.economy.pricing import mid_price, quote, relax


def test_scarcity_raises_the_price(rules):
    economy = rules.economy
    assert mid_price(10, 100, 100, economy) > mid_price(100, 100, 100, economy)


def test_glut_lowers_it(rules):
    economy = rules.economy
    assert mid_price(400, 100, 100, economy) < mid_price(100, 100, 100, economy)


def test_the_price_is_clamped_at_both_ends(rules):
    economy = rules.economy
    assert mid_price(1, 10_000, 100, economy) <= 100 * economy.price_ceiling_ratio
    assert mid_price(10_000, 1, 100, economy) >= 100 * economy.price_floor_ratio


def test_buying_then_selling_at_the_same_stock_loses_money(rules):
    """The spread is real, which is what makes trading a decision rather than arithmetic."""
    prices = quote(100, 100, 100, rules.economy)
    assert prices.buy > prices.mid >= prices.sell


def test_relaxation_pulls_stock_toward_its_target(rules):
    economy = rules.economy
    assert relax(0, 100, 0, 0, economy) > 0
    assert relax(200, 100, 0, 0, economy) < 200


def test_stock_never_goes_negative(rules):
    assert relax(1, 100, 0, 500, rules.economy) == 0
