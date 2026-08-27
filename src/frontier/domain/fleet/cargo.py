"""A ship's hold — GDD §4.2."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Cargo:
    lines: dict[str, int] = field(default_factory=dict)
    cost_basis: dict[str, int] = field(default_factory=dict)

    @property
    def used(self) -> int:
        return sum(self.lines.values())

    def qty(self, commodity: str) -> int:
        return self.lines.get(commodity, 0)

    def add(self, commodity: str, qty: int, unit_price: int) -> None:
        held, previous = self.lines.get(commodity, 0), self.cost_basis.get(commodity, 0)
        total = held * previous + qty * unit_price
        self.lines[commodity] = held + qty
        self.cost_basis[commodity] = total // max(1, held + qty)

    def remove(self, commodity: str, qty: int) -> None:
        held = self.lines.get(commodity, 0)
        if qty > held:
            raise ValueError(f"cannot remove {qty} of {commodity}: only {held} held")
        if qty == held:
            self.lines.pop(commodity, None)
            self.cost_basis.pop(commodity, None)
        else:
            self.lines[commodity] = held - qty

    def value_at(self, prices: dict[str, int]) -> int:
        return sum(qty * prices.get(commodity, 0) for commodity, qty in self.lines.items())
