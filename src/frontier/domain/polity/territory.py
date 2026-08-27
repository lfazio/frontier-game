"""Control is a consequence of sustained presence — GDD §6.6, SDD §6.6."""

from __future__ import annotations

from frontier.domain.rules.ruleset import WorldRules

CONTESTED = 0


def blend(previous: float, raw_share: float, rules: WorldRules) -> float:
    """Decay is what makes territory follow presence over cycles rather than at the instant."""
    return previous * (1 - rules.territory_decay) + raw_share * rules.territory_decay


def controller(influence: dict[int, float], rules: WorldRules) -> int:
    if not influence:
        return CONTESTED
    faction, highest = max(influence.items(), key=lambda kv: (kv[1], -kv[0]))
    return faction if highest >= rules.territory_control_threshold else CONTESTED


def normalise(raw: dict[int, float]) -> dict[int, float]:
    total = sum(raw.values())
    return {} if total <= 0 else {k: v / total for k, v in raw.items()}
