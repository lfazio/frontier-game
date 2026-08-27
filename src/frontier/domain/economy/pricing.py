"""Price from stock, with mean reversion — SDD §6.4.

Scarcity raises the price, glut lowers it, and the clamp stops an emptied station charging
infinity. The spread is what makes buying and selling at the same stock a loss (criterion A5).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

from frontier.domain.rules.ruleset import EconomyRules


@dataclass(frozen=True, slots=True)
class Quote:
    buy: int
    sell: int
    mid: int
    stock: int


def mid_price(stock: int, target_stock: int, base_price: int, rules: EconomyRules) -> int:
    ratio = max(stock, 1) / max(target_stock, 1)
    factor = ratio**-rules.elasticity
    clamped = min(max(factor, rules.price_floor_ratio), rules.price_ceiling_ratio)
    price: int = max(1, round(base_price * clamped))
    return price


def quote(stock: int, target_stock: int, base_price: int, rules: EconomyRules) -> Quote:
    mid = mid_price(stock, target_stock, base_price, rules)
    return Quote(
        buy=ceil(mid * (1 + rules.spread)),
        sell=max(1, floor(mid * (1 - rules.spread))),
        mid=mid,
        stock=stock,
    )


def relax(stock: int, target_stock: int, production: int, consumption: int, rules: EconomyRules) -> int:
    drift = round((target_stock - stock) * rules.relaxation_rate)
    return max(0, stock + drift + production - consumption)
