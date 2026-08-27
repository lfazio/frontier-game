"""Balance data as an immutable value — GDD §10.4 C7, ARCH §11.2, SDD §3.4."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ActionKind(StrEnum):
    MOVE_HEX = "move_hex"
    SCAN = "scan"
    TRADE = "trade"
    JUMP_INTRA_REGION = "jump_intra_region"
    JUMP_INTER_REGION = "jump_inter_region"
    COMBAT_ROUND = "combat_round"
    REPAIR = "repair"
    DOCK = "dock"
    LAUNCH = "launch"
    MESSAGE = "message"
    STANDING_ORDERS = "standing_orders"
    MISSION_STAGE = "mission_stage"


class RuleSetError(ValueError):
    """An unknown or out-of-range key. Raised at load time, never at play time."""


def _take(source: Mapping[str, Any], keys: set[str], where: str) -> dict[str, Any]:
    unknown = set(source) - keys
    if unknown:
        raise RuleSetError(f"unknown key(s) in {where}: {', '.join(sorted(unknown))}")
    missing = keys - set(source)
    if missing:
        raise RuleSetError(f"missing key(s) in {where}: {', '.join(sorted(missing))}")
    return dict(source)


@dataclass(frozen=True, slots=True)
class ApRules:
    daily_grant: int
    carry_over_fraction: float
    carry_ceiling: int
    cost: Mapping[str, int]

    def carry(self, unspent: int) -> int:
        """Half of unspent AP survives the boundary, to a ceiling — GDD §3.2."""
        return min(int(unspent * self.carry_over_fraction), self.carry_ceiling)


@dataclass(frozen=True, slots=True)
class WorldRules:
    sensor_range_base: int
    radio_range_base: int
    fuel_per_hex: int
    fuel_per_jump_ly: int
    jump_range_default_ly: int
    shield_regen_per_cycle: int
    hull_repair_cost_per_point: int
    territory_control_threshold: float
    territory_decay: float


@dataclass(frozen=True, slots=True)
class CombatRules:
    base_hit_chance: float
    sensor_hit_bonus_per_point: float
    shield_absorb_ratio: float
    escape_base_chance: float
    max_rounds_per_encounter: int
    destroyed_cargo_drop_ratio: float
    weapon_damage_min: int
    weapon_damage_max: int
    rescue_tax_fraction: float


@dataclass(frozen=True, slots=True)
class EconomyRules:
    elasticity: float
    price_floor_ratio: float
    price_ceiling_ratio: float
    relaxation_rate: float
    spread: float
    shift_report_threshold: float
    commodities: Mapping[str, int]
    station_type: Mapping[str, Mapping[str, str]]


@dataclass(frozen=True, slots=True)
class NpcRules:
    trade_relax: float
    patrol_relax: float
    raider_relax: float
    diffusion: float
    k_trade: float
    k_raider: float
    haul_capacity: int
    per_flow_unit: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class EventRules:
    promotion_window_cycles: int
    retention_local_days: int
    retention_planet_days: int
    retention_system_days: int
    chronicle_min_severity: int
    promotion_threshold: Mapping[str, int]

    def retention_days(self, scope: int) -> int | None:
        """Local noise expires; anything promoted to region or wider is kept — GDD §7.8."""
        return {
            0: self.retention_local_days,
            1: self.retention_planet_days,
            2: self.retention_system_days,
        }.get(scope)


@dataclass(frozen=True, slots=True)
class RuleSet:
    version: str
    ap: ApRules
    world: WorldRules
    combat: CombatRules
    economy: EconomyRules
    npc: NpcRules
    events: EventRules

    def ap_cost(self, action: ActionKind) -> int:
        return self.ap.cost[action.value]

    @classmethod
    def from_mapping(cls, version: str, files: Mapping[str, Mapping[str, Any]]) -> RuleSet:
        known = {"ap_costs", "world", "combat", "economy", "npc", "events"}
        unknown = set(files) - known
        if unknown:
            raise RuleSetError(f"unknown ruleset file(s): {', '.join(sorted(unknown))}")

        ap_raw = dict(files["ap_costs"])
        costs = ap_raw.pop("cost", None)
        if not isinstance(costs, Mapping):
            raise RuleSetError("ap_costs.toml must define a [cost] table")
        _take(costs, {a.value for a in ActionKind}, "ap_costs.cost")
        ap_fields = _take(ap_raw, {"daily_grant", "carry_over_fraction", "carry_ceiling"}, "ap_costs")
        if not 0.0 <= float(ap_fields["carry_over_fraction"]) <= 1.0:
            raise RuleSetError("carry_over_fraction must be between 0 and 1")

        world_keys = {f for f in WorldRules.__dataclass_fields__}
        world_fields = _take(files["world"], world_keys, "world")

        economy_raw = dict(files["economy"])
        commodities = economy_raw.pop("commodities", {})
        station_type = economy_raw.pop("station_type", {})
        economy_fields = _take(
            economy_raw,
            {f for f in EconomyRules.__dataclass_fields__} - {"commodities", "station_type"},
            "economy",
        )
        events_raw = dict(files["events"])
        npc_raw = dict(files["npc"])
        per_flow = npc_raw.pop("per_flow_unit", {})
        npc_fields = _take(
            npc_raw,
            {f for f in NpcRules.__dataclass_fields__} - {"per_flow_unit"},
            "npc",
        )

        return cls(
            version=version,
            ap=ApRules(cost=dict(costs), **ap_fields),
            world=WorldRules(**world_fields),
            combat=CombatRules(**_take(files["combat"], set(CombatRules.__dataclass_fields__), "combat")),
            economy=EconomyRules(
                commodities=dict(commodities),
                station_type={k: dict(v) for k, v in station_type.items()},
                **economy_fields,
            ),
            events=EventRules(
                promotion_threshold=dict(events_raw.pop("promotion_threshold", {})),
                **_take(
                    events_raw,
                    {f for f in EventRules.__dataclass_fields__} - {"promotion_threshold"},
                    "events",
                ),
            ),
            npc=NpcRules(per_flow_unit=dict(per_flow), **npc_fields),
        )
