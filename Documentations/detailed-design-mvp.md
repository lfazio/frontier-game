# Software Detailed Design — MVP

## *Frontier: The Seldon Era*, Python implementation

| Field | Value |
| --- | --- |
| Status | Draft for review |
| Version | 0.14 |
| Date | 2026-08-27 |
| Supersedes | 0.1 |
| Scope | Delivery phases **P0–P3** (*ARCH §17*), realising the MVP of *GDD §10.1* |
| Depends on | `Documentations/game-design.md` v2.3, `Documentations/architecture.md` v0.2 |

### Reference convention

**GDD §n** — game design document (what the game does). **ARCH §n** — architecture document (how the system is
structured). **§n** — this document (how the MVP is built). Note that the architecture document, being older, cites
the design document as a bare `§n`.

This document adds detail; it never contradicts. Where implementation reveals that a design or architecture statement
is wrong, that document is amended and this one follows. Decisions taken *here* — because they are below the
architecture's altitude but still need a record — are numbered `[D-n]` and collected in §16.

---

# 1. What the MVP is

## 1.1 Scope contract

The MVP is a playable world with one loop: log in, read what happened, spend Action Points on movement, trade,
scanning and combat, talk to people, log out. Everything else is deferred.

| Area | In | Out (and why) |
| --- | --- | --- |
| World | Galaxy → Region → System → Planet, generated once; system hex maps | Sector and Local levels — no surface gameplay yet `[D-1]` |
| Player | Account, credits, AP, position, faction, team, standing orders | Reputation *scores* exist and move; no reputation *effects* |
| Ship | One ship: hull, shields, engine, fuel, cargo, one weapon, sensors | Fitting, modules market. Multiple ships are permanently out — *GDD §4.2* |
| Movement | In-system hex movement, inter-system jumps spanning cycles, dock/launch | Probes, advanced navigation, fuel scooping |
| Economy | Station markets, buy/sell, cargo, per-cycle price relaxation | Mining, production chains, player stations, smuggling |
| Exploration | Scan, permanent attributed discovery, per-player map knowledge | Anomalies, archives, deep survey |
| Combat | NPC encounters resolved live; PvP resolved at the tick from standing orders | Boarding, fleet battles, bounties |
| Population | Aggregate NPC simulation in every system; haulers, patrols and raiders materialised where observed | Faction strategic AI, named or persistent NPCs |
| Social | Three factions, teams, team chat, local/system chat, unified feed | Defection, faction chat ranks, relays, comms delay |
| Events | One event spine, four scopes, per-viewer redaction, live WebSocket feed | Promotion to history, Chronicle, retention jobs |
| Cycle | Tick stages 1, 2, 3, 4, 5, 11, 12, 13 | Stages 6, 7, 8, 9, 10 |
| Hidden layers | — | Psychohistory (*GDD §8*) and the Continuity (*GDD §9*) are not built, not stubbed, not referenced |

**Tick stage numbering.** *GDD §3.3* lists twelve player-visible steps; *ARCH §9.2* lists thirteen executable
stages, because the design's step 12 ("prepares each player's daily overview and digest") splits into
`RebuildProjections` and `DispatchDigests`. The MVP runs ARCH stages **1, 2, 3, 4, 5, 11, 12, 13** — stage 4
restricted to its NPC half (§6.5); faction strategic AI is deferred.

## 1.2 Acceptance criteria

The MVP is done when all of the following hold against a generated world with ≥ 50 seeded accounts. Each maps to a
test in §14 and is verified in CI, not by inspection.

| # | Criterion |
| --- | --- |
| A1 | A new account can register, choose a faction, create or join a team, and receive a ship at a starting station. |
| A2 | A player with 10 AP can move ten hexes, and the eleventh move is rejected with `INSUFFICIENT_AP` and no state change. |
| A3 | AP, credits, cargo, hull and position change **only** through a committed command or tick stage; the ledger reconciles exactly. |
| A4 | A jump issued on day *N* with a two-cycle duration lands during stage 1 of day *N+2* and emits `JOURNEY_COMPLETED`. |
| A5 | Buying then selling the same cargo at the same station at the same stock level loses money (the spread is real). |
| A6 | A player attacked while offline is resolved from their standing orders, and sees the outcome in their feed at next login. |
| A7 | Two browser tabs spending the last AP simultaneously produce exactly one successful command. |
| A8 | A retried command with the same idempotency key returns the original result and debits AP once. |
| A9 | A scan reveals only what sensors allow; an out-of-range observer receives no event, not a filtered one. |
| A10 | Re-running a tick for the same world day against a restored snapshot produces byte-identical events. |
| A11 | The client can render galaxy, region and system views without ever requesting the whole world. |
| A12 | A full tick over the generated world completes in under 60 seconds on a developer machine. |
| A13 | A system no player has visited since generation has different market stock after seven cycles — the aggregate population moved goods. |
| A14 | Entering an unobserved system materialises NPCs deterministically: the same system on the same world day yields identical NPCs however often it is observed. |
| A15 | A player ending a cycle with 7 unspent AP starts the next with `daily_grant + 3`, capped by `carry_ceiling`, and the ledger still reconciles exactly. |

## 1.3 Explicitly not in the MVP

Stated so that nobody builds them "while they are in there": missions, reputation effects, defection, relays,
communication delay, bounties, mining, player stations, the Chronicle, forecasts, the Continuity, the Harrowing
(*GDD §8.12*). *ARCH §18* holds
the seam for each.

---

# 2. Module map

Only the packages the MVP touches. The full target layout is *ARCH §16*; nothing here contradicts it, and no
directory is created before it has content.

```text
src/frontier/
├── domain/
│   ├── hex/{coordinates,geometry}.py        §3.1, §3.2
│   ├── events/{model,types}.py              §3.5
│   ├── rules/{ruleset,ap,combat,economy}.py §3.4
│   ├── world/{location,planet}.py             §3.3
│   ├── fleet/{ship,cargo,standing_orders}.py
│   ├── economy/{market,pricing}.py          §6.4
│   ├── encounter/{resolution}.py            §6.3
│   ├── polity/{faction,team,territory}.py   §6.6
│   └── npc/{archetype,behaviour,population}.py §6.5, §10
├── application/
│   ├── ports.py                             §5.1
│   ├── unit_of_work.py                      §5.2
│   ├── visibility.py                        §5.5
│   └── commands/                            §5.4 — one module per intent
├── simulation/
│   ├── tick.py                              §6.1
│   └── stages/{settle_travel,resolve_encounters,economy,npc_population,
│              territory,grant_ap,projections,digests}.py
├── worldgen/generator.py                    §7
├── projections/{map_tiles,feed,dashboard}.py §9
├── adapters/
│   ├── db/{models,repositories,mappers}.py  §4
│   ├── api/{routers,schemas,deps,errors}.py §8
│   ├── ws/gateway.py                        §8.3
│   └── bus/{outbox,redis_pub}.py
└── config/{settings,container,logging}.py
```

Import boundaries are enforced by `import-linter` contracts in CI, not by review (*ARCH §3.1*):

```toml
[[tool.importlinter.contracts]]
name = "domain is pure"
type = "forbidden"
source_modules = ["frontier.domain"]
forbidden_modules = ["frontier.application", "frontier.adapters", "frontier.simulation",
                     "sqlalchemy", "fastapi", "redis", "httpx"]

[[tool.importlinter.contracts]]
name = "layers"
type = "layers"
layers = ["frontier.adapters", "frontier.simulation", "frontier.application", "frontier.domain"]
```

---

# 3. Domain design

## 3.1 Coordinates

Extends the sketch in *ARCH §7.1* to the full MVP surface.

```python
class Level(IntEnum):
    GALAXY = 0
    REGION = 1
    SYSTEM = 2
    PLANET = 3
    SECTOR = 4
    LOCAL = 5

MVP_LEVELS = frozenset({Level.GALAXY, Level.REGION, Level.SYSTEM, Level.PLANET})

@dataclass(frozen=True, slots=True)
class Axial:
    q: int
    r: int

    def __add__(self, other: Axial) -> Axial: ...
    def __sub__(self, other: Axial) -> Axial: ...

    @property
    def cube(self) -> tuple[int, int, int]:
        return self.q, self.r, -self.q - self.r

@dataclass(frozen=True, slots=True)
class HexAddr:
    steps: tuple[Axial, ...]

    @property
    def level(self) -> Level: ...
    def parent(self) -> HexAddr | None: ...
    def child(self, step: Axial) -> HexAddr: ...
    def contains(self, other: HexAddr) -> bool: ...
    def ltree(self) -> str: ...

    @classmethod
    def parse(cls, s: str) -> HexAddr: ...
```

### Encoding

`ltree` labels accept only `[A-Za-z0-9_]`, so each step encodes as `<prefix><q><sep><r>` with negatives prefixed `n`:

| Level | Prefix | `Axial(124, 87)` | `Axial(-3, 1)` |
| --- | --- | --- | --- |
| Galaxy | `ga` | `ga124_87` | `gan3_1` |
| Region | `re` | `re124_87` | `ren3_1` |
| System | `sy` | `sy124_87` | `syn3_1` |
| Planet | `pl` | `pl124_87` | `pln3_1` |
| Sector | `se` | `se124_87` | `sen3_1` |
| Local | `lo` | `lo124_87` | `lon3_1` |

Prefixes are two letters because the level names collide on their first letter — **S**ystem and **S**ector,
**R**egion and… nothing yet, but the ladder is now fixed and a one-letter scheme has no room left. The prefix is for
human readability only; the level is determined by position in the path.

`HexAddr.parse` is the inverse and is round-trip tested (§14.2). The human-readable form used in the API and in
logs is `ga124_87/re3_1/sy31_14`, i.e. the ltree with `.` replaced by `/`.

### Invariants

| Invariant | Enforcement |
| --- | --- |
| `distance(a, b)` requires `a.level == b.level and a.parent() == b.parent()` | raises `ScaleMismatch` |
| `a.contains(b)` iff `a.steps` is a prefix of `b.steps` | prefix test; also the SQL `<@` operator (§4.2) |
| Depth never exceeds `Level.LOCAL` | constructor validation |
| Addresses are immutable and hashable | `frozen=True, slots=True` |

## 3.2 Hex geometry

Pure functions over `Axial`, in `domain/hex/geometry.py`. Flat-top axial layout; cube coordinates internally.

```python
DIRECTIONS: Final = (Axial(1,0), Axial(1,-1), Axial(0,-1), Axial(-1,0), Axial(-1,1), Axial(0,1))

def neighbours(a: Axial) -> tuple[Axial, ...]: ...
def distance(a: Axial, b: Axial) -> int: ...
def ring(centre: Axial, radius: int) -> list[Axial]: ...
def spiral(centre: Axial, radius: int) -> list[Axial]: ...
def line(a: Axial, b: Axial) -> list[Axial]: ...
def within(centre: Axial, radius: int) -> Iterator[Axial]: ...
```

`distance` is the cube metric:

```text
distance(a, b) = (|ax-bx| + |ay-by| + |az-bz|) / 2
```

`line` uses cube interpolation with a fixed epsilon nudge (`1e-6` on one axis) so that ties break deterministically
rather than by floating-point accident — determinism reaches even here, because line-of-sight feeds visibility.

**Pathfinding is not needed in the MVP.** In-system space is uniform: the cheapest route between two hexes is any
shortest line, and its cost is `distance × ap_per_hex`. A* arrives with obstacles, which arrive with hazards
(deferred). `[D-2]`

## 3.3 Entities

Aggregate roots and their invariants. Aggregates are loaded and saved whole; the row lock in §5.2 is taken on the
root.

| Aggregate | Root | Invariants |
| --- | --- | --- |
| **Player** | `Player` | `ap_balance >= 0`; `credits >= 0`; belongs to exactly one team; `faction == team.faction` |
| **Ship** | `Ship` | `0 <= hull <= hull_max`; `0 <= shields <= shields_max`; `0 <= fuel <= fuel_max`; `cargo_used <= cargo_max`; owned by exactly one player; `docked_at` is null or a station at the ship's position |
| **Location** | `Location` | Tree: `parent_id` consistent with `path`; `(parent_id, q, r)` unique |
| **Market** | `Market` | one per station; `stock >= 0` per commodity |
| **Team** | `Team` | exactly one faction; ≥ 1 member or deleted |

```python
@dataclass(slots=True)
class Ship:
    id: UUID
    player_id: UUID
    hull: int
    hull_max: int
    shields: int
    shields_max: int
    fuel: int
    fuel_max: int
    cargo_max: int
    cargo: Cargo
    weapon: WeaponSpec
    sensor_range: int
    position: HexAddr
    docked_at: UUID | None

    def can_move(self, to: HexAddr, rules: RuleSet) -> Decision: ...
    def apply_move(self, to: HexAddr, rules: RuleSet) -> None: ...
```

`can_move` returns a `Decision` value, never raises for an expected refusal (*ARCH §11.4*):

```python
@dataclass(frozen=True, slots=True)
class Rejected:
    code: RejectionCode
    context: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class Accepted:
    ap_cost: int
    fuel_cost: int

Decision: TypeAlias = Accepted | Rejected
```

### Standing orders

```python
class Posture(StrEnum):
    EVADE = "evade"
    DEFEND = "defend"
    AGGRESSIVE = "aggressive"
    SURRENDER_CARGO = "surrender_cargo"

@dataclass(frozen=True, slots=True)
class StandingOrders:
    posture: Posture
    engage_hostile_factions: bool
    engage_above_cargo_value: int | None
    retreat_at_hull_pct: int
    auto_reply: str | None
```

Every player has a row from registration; the default is `EVADE / retreat_at_hull_pct=50`, chosen so that a player
who never opens the screen loses cargo rather than a ship.

## 3.4 The rule set

Balance data lives in `data/rulesets/<version>/*.toml`, loaded once at startup into a frozen `RuleSet`
(*ARCH §11.2*, *GDD* C7). Every value below is `[BALANCE]`; these are starting points, not decisions.

```toml
# data/rulesets/2026.1/ap_costs.toml
daily_grant = 10
carry_over_fraction = 0.5     # GDD §3.2: half of unspent AP survives the boundary
carry_ceiling = 5

[cost]
move_hex = 1
scan = 1
trade = 1
jump_intra_region = 4
jump_inter_region = 6
combat_round = 2
repair = 2
dock = 0
launch = 0
message = 0
standing_orders = 0
```

```toml
# data/rulesets/2026.1/combat.toml
base_hit_chance = 0.70
sensor_hit_bonus_per_point = 0.02
shield_absorb_ratio = 0.60
escape_base_chance = 0.45
escape_engine_bonus = 0.05
max_rounds_per_encounter = 5
destroyed_cargo_drop_ratio = 0.50
```

```toml
# data/rulesets/2026.1/economy.toml
elasticity = 0.6
price_floor_ratio = 0.35
price_ceiling_ratio = 3.0
relaxation_rate = 0.15
spread = 0.08                  # buy price = mid × (1+spread); sell = mid × (1-spread)
```

```toml
# data/rulesets/2026.1/npc.toml
trade_relax = 0.20
patrol_relax = 0.15
raider_relax = 0.18
diffusion = 0.10
k_trade = 1.2
k_raider = 0.9
haul_capacity = 20
dissolve_after_cycles = 1

[per_flow_unit]
haulers = 6
patrols = 4
raiders = 4

[actions_per_cycle]
hauler = 4
patrol = 3
raider = 3
```

```toml
# data/rulesets/2026.1/world.toml
sensor_range_base = 3
radio_range_base = 5
fuel_per_hex = 1
fuel_per_jump_ly = 2
shield_regen_per_cycle = 10
hull_repair_cost_per_point = 12
territory_control_threshold = 0.50
territory_decay = 0.10
```

Loading validates with a Pydantic model and fails startup on an unknown or out-of-range key. `RuleSet.version` is
stamped on every command and every event.

```python
class RuleSet:
    version: str

    def ap_cost(self, action: ActionKind, ctx: CostContext) -> int: ...
    def fuel_cost(self, action: ActionKind, ctx: CostContext) -> int: ...
    def combat(self) -> CombatRules: ...
    def economy(self) -> EconomyRules: ...
```

## 3.5 Event catalogue

The generic model is *ARCH §7.2*. The MVP emits exactly these types; adding one requires a payload `TypedDict`, an
entry in this table, and a case in the feed renderer.

| Type | Emitted by | Scope | Visibility | Payload |
| --- | --- | --- | --- | --- |
| `SHIP_ENTERED` | move, jump arrival | LOCAL | PUBLIC | `ship_id, actor_kind, from, to` |
| `JOURNEY_COMPLETED` | stage 1 | LOCAL | PARTICIPANTS | `journey_id, arrived_at` |
| `SCAN_PERFORMED` | scan | LOCAL | PARTICIPANTS | `range, contacts_found` |
| `DISCOVERY` | scan | SYSTEM | PUBLIC | `location_id, kind, first_by` |
| `TRADE_EXECUTED` | buy, sell | LOCAL | PARTICIPANTS | `station_id, commodity, qty, unit_price` |
| `MARKET_SHIFT` | stage 3 | PLANET | PUBLIC | `station_id, commodity, old, new` |
| `COMBAT_STARTED` | attack, stage 2 | LOCAL | PUBLIC | `attacker, defender, initiator_intent` |
| `COMBAT_ROUND` | encounter resolution | LOCAL | PARTICIPANTS | `round, rolls, damage` |
| `COMBAT_RESOLVED` | encounter resolution | LOCAL | PUBLIC | `outcome, survivors, cargo_lost` |
| `SHIP_DESTROYED` | encounter resolution | SYSTEM | PUBLIC | `ship_id, player_id, by` |
| `MESSAGE` | send_message | channel scope | channel visibility | `text, channel` |
| `TERRITORY_CHANGE` | stage 5 | SYSTEM | PUBLIC | `system_id, from_faction, to_faction, influence` |
| `AP_GRANTED` | stage 11 | LOCAL | PARTICIPANTS | `amount, balance` |
| `TEAM_JOINED` / `TEAM_LEFT` | team commands | TEAM | TEAM | `player_id, team_id` |

Payloads are `TypedDict`s validated on write and stored as `jsonb`:

```python
class CombatResolvedPayload(TypedDict):
    outcome: Literal["attacker_won", "defender_won", "escaped", "stalemate"]
    rounds: int
    damage_dealt: dict[str, int]
    cargo_lost: list[CargoLine]
    seed: str
```

`seed` is present on every stochastic event so that a disputed outcome replays exactly (*GDD* C6).

**NPCs emit the same events as players.** There is no `NPC_*` family: a hauler docking emits `TRADE_EXECUTED`,
a raider attacking emits `COMBAT_STARTED`, and the `actor_kind` field distinguishes them where a reader needs to know
(§10.1). This is why the event named `SHIP_ENTERED` is not called `PLAYER_ENTERED`, which is the illustrative name in
*GDD §7.6*: half the ships in the galaxy are not players.

---

# 4. Persistence

## 4.1 Schemas and roles

The MVP creates three of the five schemas of *ARCH §10.1*: `core`, `evt`, `hist`. `psycho` and `cont` are not
created — an empty schema for an unbuilt feature is an invitation to put something in it.

| Role | `core` | `evt` | `hist` |
| --- | --- | --- | --- |
| `api_role` | RW | RW | R |
| `tick_role` | RW | RW | RW |
| `migrate_role` | owner | owner | owner |

## 4.2 Tables

Abridged to columns that carry design meaning; `created_at`/`updated_at` are on every table and omitted below.

```sql
CREATE TABLE core.accounts (
    id            uuid PRIMARY KEY,
    email         citext NOT NULL UNIQUE,
    password_hash text NOT NULL,
    status        text NOT NULL DEFAULT 'active'
);

CREATE TABLE core.factions (
    id   smallint PRIMARY KEY,          -- 1 Empire, 2 Republic, 3 Pirates
    code text NOT NULL UNIQUE
);

CREATE TABLE core.teams (
    id         uuid PRIMARY KEY,
    name       citext NOT NULL UNIQUE,
    faction_id smallint NOT NULL REFERENCES core.factions(id),
    founded_on int NOT NULL
);

CREATE TABLE core.players (
    id            uuid PRIMARY KEY,
    account_id    uuid NOT NULL REFERENCES core.accounts(id),
    callsign      citext NOT NULL UNIQUE,
    team_id       uuid REFERENCES core.teams(id),
    faction_id    smallint REFERENCES core.factions(id),
    credits       bigint NOT NULL DEFAULT 0 CHECK (credits >= 0),
    ap_balance    int    NOT NULL DEFAULT 0 CHECK (ap_balance >= 0),
    last_grant_day int   NOT NULL DEFAULT -1,
    CONSTRAINT faction_matches_team CHECK (
        (team_id IS NULL AND faction_id IS NULL) OR (team_id IS NOT NULL AND faction_id IS NOT NULL))
);

CREATE TABLE core.locations (
    id         uuid PRIMARY KEY,
    parent_id  uuid REFERENCES core.locations(id),
    level      smallint NOT NULL,
    q          int NOT NULL,
    r          int NOT NULL,
    path       ltree NOT NULL,
    kind       text NOT NULL,           -- region, system, star, planet, moon, station, belt
    name       text,
    discovered_on   int,
    discovered_by   uuid REFERENCES core.players(id),
    attrs      jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX locations_path_gist ON core.locations USING gist (path);
CREATE UNIQUE INDEX locations_parent_hex ON core.locations (parent_id, q, r);
CREATE INDEX locations_kind ON core.locations (kind) WHERE kind = 'station';

CREATE TABLE core.ships (
    id            uuid PRIMARY KEY,
    player_id     uuid REFERENCES core.players(id),      -- null for NPCs; exactly one per player, GDD §4.2
    hull          int NOT NULL CHECK (hull >= 0),
    hull_max      int NOT NULL,
    shields       int NOT NULL CHECK (shields >= 0),
    shields_max   int NOT NULL,
    fuel          int NOT NULL CHECK (fuel >= 0),
    fuel_max      int NOT NULL,
    cargo_max     int NOT NULL,
    weapon_code   text NOT NULL,
    sensor_range  int NOT NULL,
    system_id     uuid NOT NULL REFERENCES core.locations(id),
    position_path ltree NOT NULL,
    docked_at     uuid REFERENCES core.locations(id),
    destroyed_on  int
);
CREATE UNIQUE INDEX ships_one_per_player ON core.ships (player_id)
    WHERE player_id IS NOT NULL AND destroyed_on IS NULL;
CREATE INDEX ships_position_gist ON core.ships USING gist (position_path);
CREATE INDEX ships_system ON core.ships (system_id) WHERE destroyed_on IS NULL;

CREATE TABLE core.npc_agents (
    ship_id       uuid PRIMARY KEY REFERENCES core.ships(id) ON DELETE CASCADE,
    system_id     uuid NOT NULL REFERENCES core.locations(id),
    archetype     text NOT NULL,                 -- hauler, patrol, raider
    slot          smallint NOT NULL,
    faction_id    smallint REFERENCES core.factions(id),
    route         jsonb NOT NULL DEFAULT '{}',
    materialised_on int NOT NULL,
    last_seen_on  int NOT NULL,
    UNIQUE (system_id, archetype, slot)
);
CREATE INDEX npc_agents_stale ON core.npc_agents (last_seen_on);

CREATE TABLE core.system_activity (
    system_id            uuid PRIMARY KEY REFERENCES core.locations(id),
    trade_flow           numeric(6,4) NOT NULL DEFAULT 0,
    patrol_strength      numeric(6,4) NOT NULL DEFAULT 0,
    raider_pressure      numeric(6,4) NOT NULL DEFAULT 0,
    civilian_traffic     numeric(6,4) NOT NULL DEFAULT 0,
    patrol_losses        numeric(6,4) NOT NULL DEFAULT 0,
    raider_losses        numeric(6,4) NOT NULL DEFAULT 0,
    last_simulated_on    int NOT NULL DEFAULT -1
);

CREATE TABLE core.cargo (
    ship_id      uuid NOT NULL REFERENCES core.ships(id) ON DELETE CASCADE,
    commodity    text NOT NULL,
    qty          int NOT NULL CHECK (qty > 0),
    avg_unit_cost int NOT NULL,
    PRIMARY KEY (ship_id, commodity)
);

CREATE TABLE core.standing_orders (
    player_id             uuid PRIMARY KEY REFERENCES core.players(id),
    posture               text NOT NULL,
    engage_hostile        boolean NOT NULL DEFAULT false,
    engage_above_cargo    int,
    retreat_at_hull_pct   int NOT NULL DEFAULT 50 CHECK (retreat_at_hull_pct BETWEEN 0 AND 100),
    auto_reply            text
);

CREATE TABLE core.journeys (
    id             uuid PRIMARY KEY,
    ship_id        uuid NOT NULL REFERENCES core.ships(id),
    from_path      ltree NOT NULL,
    to_path        ltree NOT NULL,
    to_system_id   uuid NOT NULL REFERENCES core.locations(id),
    departed_on    int NOT NULL,
    arrives_on     int NOT NULL,
    settled        boolean NOT NULL DEFAULT false
);
CREATE INDEX journeys_pending ON core.journeys (arrives_on) WHERE NOT settled;

CREATE TABLE core.markets (
    station_id  uuid NOT NULL REFERENCES core.locations(id),
    commodity   text NOT NULL,
    stock       int NOT NULL CHECK (stock >= 0),
    target_stock int NOT NULL,
    base_price  int NOT NULL,
    PRIMARY KEY (station_id, commodity)
);

CREATE TABLE core.encounter_queue (
    id           uuid PRIMARY KEY,
    world_day    int NOT NULL,
    attacker_id  uuid NOT NULL REFERENCES core.players(id),
    defender_id  uuid NOT NULL REFERENCES core.players(id),
    at_path      ltree NOT NULL,
    intent       text NOT NULL,
    resolved     boolean NOT NULL DEFAULT false,
    UNIQUE (world_day, attacker_id, defender_id)
);

CREATE TABLE core.territory (
    system_id       uuid NOT NULL REFERENCES core.locations(id),
    faction_id      smallint NOT NULL REFERENCES core.factions(id),
    influence       numeric(6,4) NOT NULL DEFAULT 0,
    PRIMARY KEY (system_id, faction_id)
);

CREATE TABLE core.player_discoveries (
    player_id   uuid NOT NULL REFERENCES core.players(id),
    location_id uuid NOT NULL REFERENCES core.locations(id),
    seen_on     int NOT NULL,
    PRIMARY KEY (player_id, location_id)
);

CREATE TABLE core.ap_ledger (
    id         bigserial PRIMARY KEY,
    player_id  uuid NOT NULL REFERENCES core.players(id),
    world_day  int  NOT NULL,
    delta      int  NOT NULL,
    reason     text NOT NULL,
    command_id uuid
);
CREATE UNIQUE INDEX ap_ledger_command_uniq ON core.ap_ledger (command_id) WHERE command_id IS NOT NULL;
CREATE INDEX ap_ledger_player_day ON core.ap_ledger (player_id, world_day);

CREATE TABLE core.commands (
    id              uuid PRIMARY KEY,
    player_id       uuid NOT NULL REFERENCES core.players(id),
    idempotency_key uuid NOT NULL,
    action          text NOT NULL,
    request         jsonb NOT NULL,
    outcome         jsonb,
    status          text NOT NULL,
    ruleset_version text NOT NULL,
    world_day       int NOT NULL,
    UNIQUE (player_id, idempotency_key)
);

CREATE TABLE core.world_state (
    id            boolean PRIMARY KEY DEFAULT true CHECK (id),
    world_day     int NOT NULL,
    world_seed    text NOT NULL,
    phase         text NOT NULL DEFAULT 'open'    -- open | ticking
);
```

Event tables follow *ARCH §10.3* unchanged: `evt.events` partitioned by `world_day`, `evt.event_deliveries`,
`evt.events_outbox`. `hist.tick_runs` and `hist.tick_stages` record tick execution (§6.1).

## 4.3 Hot queries

The four queries that must stay fast; each has a matching index above and an `EXPLAIN` assertion in the integration
suite.

| Query | Shape | Index |
| --- | --- | --- |
| Feed page for a viewer | `origin_path <@ ANY($subscriptions) AND id > $cursor` on recent partitions | `events_path_gist`, PK `(world_day, id)` |
| Contacts in sensor range | `ships.position_path <@ $system AND destroyed_on IS NULL` then in-memory `distance ≤ range` | `ships_system` |
| System map tile | `locations.path <@ $system` | `locations_path_gist` |
| Pending arrivals | `journeys.arrives_on <= $day AND NOT settled` | `journeys_pending` |

Contact filtering is deliberately two-stage: PostgreSQL narrows to the system, Python applies hex distance. A GiST
index cannot express hex range, and a system holds a few hundred ships at most. `[D-3]`

## 4.4 Migrations

Alembic, forward-only, one revision per pull request. The MVP's revisions are ordered so each phase is deployable
alone:

| Revision | Phase | Contents |
| --- | --- | --- |
| `0001_core_identity` | P0 | accounts, players, teams, factions, world_state, commands, **ap_ledger** `[D-14]` |
| `0002_world_tree` | P1 | locations, ltree extension, indexes |
| `0004_fleet` | P1 | ships, journeys `[D-16]` |
| `0005_event_spine` | P2 | `evt` schema, partitioned events, deliveries, outbox, digests |
| `0006_economy` | P3 | cargo, standing_orders, markets |
| `0007_conflict` | P3 | encounter_queue, territory, player_discoveries |
| `0008_population` | P3 | system_activity, npc_agents |
| `0009_chronicle` | P4 | `hist.chronicle` |
| `0010_missions_and_reputation` | P4 | missions, mission_assignments, reputation, `teams.defected_on` |
| `0011_psychohistory` | P5 | `psycho` schema: aggregate views, history_variables, forecasts, the `psycho_reader` role |
| `0012_knowledge` | P5 | `players.knowledge` |
| `0013_jump_range` | P5 | `ships.jump_range_ly` |
| `0014_npc_action_points` | P6 | `npc_agents.ap_balance`, `last_grant_day` |
| `0015_continuity` | P6 | `cont` schema: cells, agents, interventions, budget; the `api_role` and `cont_role` grants |
| `0003_tick_bookkeeping` | P1 | `hist` schema, tick_runs, tick_stages |
| `0004_event_spine` | P2 | events (partitioned), deliveries, outbox, first partitions |
| `0006_economy` | P3 | markets |
| `0007_conflict` | P3 | encounter_queue, territory, player_discoveries |
| `0008_population` | P3 | npc_agents, system_activity; `ships.player_id` made nullable |

A partition-creation job runs monthly ahead of need; the MVP pre-creates twelve partitions so a forgotten job cannot
stop the tick.

Alembic's `alembic_version` table lives in `core`, so `alembic/env.py` creates the schema before Alembic bootstraps
it, and `0001`'s downgrade leaves the schema in place. Downgrades exist to make a revision reviewable, not to be run
in production: migrations are forward-only.

---

# 5. Application layer

## 5.1 Ports

```python
class ClockPort(Protocol):
    def now(self) -> datetime: ...
    def world_day(self) -> int: ...

class RngPort(Protocol):
    def for_(self, *parts: str | int) -> random.Random: ...

class IdPort(Protocol):
    def new(self) -> UUID: ...

class EventBusPort(Protocol):
    def emit(self, event: Event) -> None: ...

class PlayerRepo(Protocol):
    async def get_for_update(self, player_id: UUID) -> PlayerAggregate: ...
    async def save(self, aggregate: PlayerAggregate) -> None: ...
```

Commands emit `EventDraft`s carrying only what the rules decide — type, origin, scope, visibility,
participants, payload. The executor stamps identity, time, world day and ruleset version onto each draft to make an
`Event`. That is what keeps ids and clocks out of the domain, and it is why `IdPort` exists alongside `ClockPort`.

`RngPort.for_` returns a generator seeded by `blake2b(world_seed | world_day | parts)` (*ARCH §9.3*). No module-level
`random` and no `datetime.now()` exists anywhere below `adapters/`; both are banned by a `ruff` rule so the ban
survives new contributors.

## 5.2 Unit of work and the command path

Every command follows the sequence of *ARCH §8*, implemented once in a template that handlers fill in.

```python
async def execute(cmd: Command, ctx: RequestContext) -> CommandResult:
    async with uow.begin() as tx:
        if prior := await tx.commands.find(ctx.player_id, cmd.idempotency_key):
            return prior.outcome

        if await tx.world.phase() == "ticking":
            raise Retryable(WORLD_TICKING, retry_after=30)

        player = await tx.players.get_for_update(ctx.player_id)
        state = await tx.load_state_for(cmd, player)

        decision = cmd.check(state, ctx.rules)
        if isinstance(decision, Rejected):
            await tx.commands.record(cmd, status="rejected", outcome=decision)
            return decision

        events = cmd.apply(state, decision, ctx.rules, ctx.rng)
        await tx.ap.debit(player, decision.ap_cost, command_id=cmd.id)
        await tx.persist(state)
        await tx.events.append(events)
        await tx.outbox.enqueue(events)
        await tx.commands.record(cmd, status="accepted", outcome=Outcome(events))

    return Outcome(events)
```

Three properties this template guarantees, which is why no handler is allowed its own transaction:

- **Serialisation per player.** `get_for_update` takes `SELECT ... FOR UPDATE` on `core.players`, so a player's own
  commands are linearised (criterion A7). Commands touching two players lock both in ascending UUID order.
- **Atomic state and events.** The state change, the AP debit, the events and the outbox row commit together, so
  criterion A3 holds by construction and the dual-write anomaly cannot occur.
- **Idempotency.** The `(player_id, idempotency_key)` unique constraint plus the early return satisfy A8.

`check` is pure and reusable: tick stage 2 calls the same `EncounterCommand.check` that the API calls.

## 5.3 Handler contract

```python
class Command(Protocol):
    id: UUID
    idempotency_key: UUID

    def loads(self) -> StateSpec: ...
    def check(self, state: State, rules: RuleSet) -> Decision: ...
    def apply(self, state: State, accepted: Accepted, rules: RuleSet, rng: RngPort) -> list[Event]: ...
```

`loads` declares what the template must fetch, which keeps I/O in one place and makes the fetch set reviewable.

## 5.4 MVP commands

Each specification lists: preconditions in evaluation order, effects, events. Rejections are returned in the order
listed, so error messages are predictable and testable.

### `move`

```json
{"action": "move", "to": "ga0_0/re1_0/sy4_2/pl12_7", "idempotency_key": "..."}
```

| Order | Precondition | Rejection |
| --- | --- | --- |
| 1 | ship not in transit | `IN_TRANSIT` |
| 2 | ship not docked | `MUST_LAUNCH_FIRST` |
| 3 | `to` is in the same system as the ship | `SCALE_MISMATCH` |
| 4 | `distance(from, to) == 1` | `NOT_ADJACENT` |
| 5 | `ap_balance >= ap_cost` | `INSUFFICIENT_AP` |
| 6 | `fuel >= fuel_cost` | `INSUFFICIENT_FUEL` |

Effects: position updated, fuel debited, AP debited. Events: `SHIP_ENTERED` (LOCAL, PUBLIC).

Multi-hex movement is *n* `move` commands from the client, batched in one HTTP request via
`POST /v1/commands:batch` (§8.2). The server still evaluates and charges each hop, because a partial journey must
leave the ship in a real hex when AP runs out.

### `jump`

| Order | Precondition | Rejection |
| --- | --- | --- |
| 1 | not in transit, not docked | `IN_TRANSIT` / `MUST_LAUNCH_FIRST` |
| 2 | target system is discovered by this player | `TARGET_UNKNOWN` |
| 3 | AP ≥ cost (intra- or inter-region) | `INSUFFICIENT_AP` |
| 4 | fuel ≥ `fuel_per_jump_ly × ly` | `INSUFFICIENT_FUEL` |

Effects: AP and fuel debited immediately; a `journeys` row is created with

```text
arrives_on = world_day + ceil(distance_ly / jump_ly_per_cycle)      [BALANCE]
```

and the ship is marked in transit (`ships.system_id` unchanged until arrival, `journeys` is the source of truth).
Events: none at departure beyond the participants' `COMMAND_ACCEPTED`; `JOURNEY_COMPLETED` and `SHIP_ENTERED` fire
at stage 1 (criterion A4).

### `scan`

Preconditions: not in transit; AP ≥ cost. Effects: computes contacts (§5.5), inserts `player_discoveries` rows for
newly seen locations, sets `locations.discovered_on/by` where still null. Events: `SCAN_PERFORMED` (PARTICIPANTS),
plus one `DISCOVERY` (SYSTEM, PUBLIC) per location first identified by this player.

### `dock` / `launch`

Free (0 AP). `dock` requires a station at the ship's exact hex and the ship not in transit. `launch` requires
`docked_at IS NOT NULL`. Docking is a state, not a sub-map: the MVP has no Planet-level hex movement `[D-1]`.

### `buy` / `sell`

| Order | Precondition | Rejection |
| --- | --- | --- |
| 1 | docked at the station | `NOT_DOCKED` |
| 2 | commodity traded here | `COMMODITY_UNAVAILABLE` |
| 3 | buy: `stock >= qty`; sell: `cargo[commodity] >= qty` | `INSUFFICIENT_STOCK` / `INSUFFICIENT_CARGO` |
| 4 | buy: `credits >= total`; `cargo_used + qty <= cargo_max` | `INSUFFICIENT_CREDITS` / `CARGO_FULL` |
| 5 | AP ≥ cost | `INSUFFICIENT_AP` |

Price is computed **inside the transaction** from current stock (§6.4), never from a value the client sent. Effects:
credits, cargo, market stock. Events: `TRADE_EXECUTED` (PARTICIPANTS).

The buy/sell spread guarantees criterion A5: `buy = mid × (1 + spread)`, `sell = mid × (1 - spread)`.

### `attack`

| Order | Precondition | Rejection |
| --- | --- | --- |
| 1 | target is visible to the attacker | `TARGET_NOT_VISIBLE` |
| 2 | target within weapon range (same hex or adjacent) | `OUT_OF_RANGE` |
| 3 | neither party docked | `TARGET_DOCKED` |
| 4 | AP ≥ combat cost | `INSUFFICIENT_AP` |

Two paths `[D-4]`:

- **Target is an NPC** — resolved immediately, in the command transaction, using `encounter.resolve` (§6.3). The
  player sees the result in the command response.
- **Target is a player** — a row is written to `core.encounter_queue` and resolved at stage 2 of the next tick,
  from both sides' standing orders. AP is debited at declaration.

PvP is *always* deferred to the tick, even when the defender is online. One code path resolves every player-versus-
player encounter, so an offline defender can never be treated differently from an online one (*GDD §3.5*, criterion
A6). The cost is that a duel takes a day; that is the game's format, not a limitation.

### `repair`

Docked at a station; `credits >= hull_missing × cost_per_point`; AP ≥ cost. Restores hull to max.

### `set_standing_orders`

Free, always available, validated against the `StandingOrders` schema.

### `send_message`

Free. Channel must be one the player may write to: `LOCAL`, `SYSTEM`, `TEAM`. Emits `MESSAGE` with the channel's
scope and visibility. Text is length-limited and stored verbatim; moderation is out of MVP scope but the event log
makes retrospective action possible.

### `create_team` / `join_team` / `leave_team`

`create_team` sets the founder's faction. `join_team` requires the player to have no team; the player's faction is
set from the team. `leave_team` clears both and, if the team is now empty, deletes it. All emit `TEAM_JOINED` /
`TEAM_LEFT` on the TEAM channel.

## 5.5 Visibility

One implementation for sensors, chat range and feed filtering (*ARCH §7.4*).

```python
def resolve_audience(event: Event, world: WorldSnapshot) -> AudienceSpec:
    match event.visibility:
        case Visibility.PARTICIPANTS:
            return AudienceSpec.players(event.participants)
        case Visibility.TEAM:
            return AudienceSpec.team(world.team_of(event.participants))
        case Visibility.PUBLIC:
            return AudienceSpec.spatial(event.origin, event.scope)
```

```python
def render_for(viewer: ViewerContext, event: Event, world: WorldSnapshot) -> EventView | None:
    if not _entitled(viewer, event, world):
        return None
    quality = _observation_quality(viewer, event, world)
    if quality is Quality.NONE:
        return None
    return _redact(event, quality)
```

`_observation_quality` is the MVP's sensor model:

| Condition | Quality | Rendered |
| --- | --- | --- |
| viewer is a participant | `FULL` | everything |
| `distance ≤ sensor_range / 2` | `FULL` | actor identity, ship class, exact hex |
| `distance ≤ sensor_range` | `PARTIAL` | "unidentified contact", hex fuzzed to ring radius 2 |
| `distance ≤ radio_range` and event is a `MESSAGE` | `FULL` | messages carry over radio, not sensors |
| otherwise | `NONE` | nothing — the event does not exist for this viewer |

Redaction happens server-side before serialisation, so criterion A9 is a property of the code path rather than of any
particular endpoint. Both the command response and the WebSocket feed call `render_for`; there is no second
implementation to drift.

### Fan-out

MVP follows *ARCH §7.4*: `PARTICIPANTS` and `TEAM` events are written to `evt.event_deliveries` at commit time;
`LOCAL`, `PLANET` and `SYSTEM` events are queried on read by path prefix. `UNIVERSE` exists but nothing in the MVP
emits it.

---

# 6. The daily tick

## 6.1 Runner

```python
MVP_STAGES: Final = (
    SettleTravel(),          # ARCH stage 1
    ResolveEncounters(),     # ARCH stage 2
    EconomyStep(),           # ARCH stage 3
    NpcPopulation(),         # ARCH stage 4, NPC half only
    TerritoryRecompute(),    # ARCH stage 5
    GrantActionPoints(),     # ARCH stage 11
    RebuildProjections(),    # ARCH stage 12
    DispatchDigests(),       # ARCH stage 13
)
```

Execution follows *ARCH §9.3* exactly: advisory lock, `hist.tick_runs` row, per-stage transaction, checkpoint in
`hist.tick_stages`, resume from the first incomplete stage. Two MVP specifics:

- The runner sets `core.world_state.phase = 'ticking'` for the duration; commands arriving in that window get
  `503` with `Retry-After` (§5.2). On a world this size the window is seconds.
- Stage order is fixed in code, not configuration. A designer who wants a different order is making a design change,
  and it belongs in *GDD §3.3*.

```python
class Stage(Protocol):
    name: str
    async def run(self, ctx: TickContext) -> StageMetrics: ...
```

Every stage is idempotent: re-running a completed stage against the same world day is a no-op. That property is
tested directly (§14.4), because it is what makes crash recovery safe.

## 6.2 Stage 1 — Settle travel

```text
for journey in journeys where arrives_on <= world_day and not settled:
    ship.system_id    := journey.to_system_id
    ship.position_path := journey.to_path
    journey.settled   := true
    emit JOURNEY_COMPLETED (participants)
    emit SHIP_ENTERED    (local, public)
```

Idempotent through the `settled` flag. Runs before everything else so that arrivals participate in the same cycle's
encounters and economy.

## 6.3 Stage 2 — Resolve encounters

Consumes `core.encounter_queue` for the current world day, in a deterministic order (`ORDER BY id`), and calls the
same resolver used for live NPC combat.

```python
def resolve(attacker: Combatant, defender: Combatant, rules: CombatRules, rng: Random) -> EncounterOutcome:
    intents = (attacker.intent, defender_intent_from(defender.standing_orders, attacker))
    for round_no in range(1, rules.max_rounds + 1):
        if _tries_escape(intents):
            if rng.random() < _escape_chance(escaper, rules):
                return EncounterOutcome.escaped(escaper, round_no)
        for shooter, target in _firing_order(attacker, defender, intents):
            if rng.random() < _hit_chance(shooter, target, rules):
                _apply_damage(target, _roll_damage(shooter, rng), rules)
        if _destroyed(attacker) or _destroyed(defender):
            return EncounterOutcome.destroyed(...)
        intents = _reassess(attacker, defender, intents, rules)
    return EncounterOutcome.stalemate()
```

| Element | MVP rule |
| --- | --- |
| Hit chance | `base_hit_chance + (shooter.sensor_range - target.sensor_range) × sensor_hit_bonus_per_point`, clamped to `[0.05, 0.95]` |
| Damage | `rng.randint(weapon.min, weapon.max)`; shields absorb `shield_absorb_ratio` until depleted, hull takes the rest |
| Escape | attempted when posture is `EVADE`, or when hull drops below `retreat_at_hull_pct`; succeeds on `escape_base_chance + engine bonus` |
| Surrender | posture `SURRENDER_CARGO` transfers cargo to the attacker and ends the encounter in round 1 |
| Destruction | hull ≤ 0; `destroyed_cargo_drop_ratio` of cargo is destroyed, the remainder goes to the victor |
| Respawn | destroyed ships respawn at the player's faction home station with a base hull, empty cargo, and a credit penalty `[BALANCE]` |

The RNG is seeded `("encounter", encounter_id)`, so the same encounter always resolves the same way and the seed is
recorded in `COMBAT_RESOLVED.payload.seed` (criterion A10, *GDD* C6).

Events: `COMBAT_STARTED`, one `COMBAT_ROUND` per round (participants only), `COMBAT_RESOLVED`, and `SHIP_DESTROYED`
at system scope when applicable.

## 6.4 Stage 3 — Economy

The MVP market is a stock-driven price with mean reversion. Vectorised with NumPy over a `(station × commodity)`
array loaded in one query (*ARCH §9.5*).

**Price from stock**, evaluated whenever a price is needed, including inside `buy`/`sell`:

```text
ratio = stock / target_stock
mid   = base_price × clamp(ratio ** (-elasticity), price_floor_ratio, price_ceiling_ratio)
buy   = ceil(mid × (1 + spread))
sell  = floor(mid × (1 - spread))
```

Scarcity raises the price, glut lowers it, and the clamp keeps a station that has been emptied from charging
infinity.

**Per-cycle relaxation**, the stage's only job:

```text
stock += round((target_stock - stock) × relaxation_rate) + production - consumption
stock  = max(stock, 0)
```

`production` and `consumption` come from the station's `attrs.station_type` (agricultural, industrial, mining,
refinery, trade hub), which is what makes routes profitable in a stable direction rather than randomly. Where the
resulting price moves more than a threshold `[BALANCE]`, a `MARKET_SHIFT` event is emitted at PLANET scope so that
traders in the system learn about it without a scripted news system (*GDD §5.3*).

## 6.5 Stage 4 — The NPC population

Realises *GDD §2.7*. *ARCH* stage 4 is "NPC and faction AI"; the MVP builds the NPC half. Faction-level strategic
posture stays deferred, and nothing here assumes it.

The stage has two halves with deliberately different cost profiles: **4a** runs over every system in the galaxy,
**4b** only over systems a player can currently see.

### 6.5.1 Sub-stage 4a — Aggregate flows, every system

One row per system in `core.system_activity`, updated as vectorised arithmetic over arrays loaded in a single query.
The MVP has 48 systems; the code is written linear in system count so a 5 000-system world runs the same path.

| Variable | Range | Meaning | Driven by |
| --- | --- | --- | --- |
| `trade_flow` | 0–1 | Density of hauler traffic | Price gradient against neighbours, connectivity, raider pressure |
| `patrol_strength` | 0–1 | Armed presence of the controlling faction | Territory influence × faction military baseline, minus losses |
| `raider_pressure` | 0–1 | Predation on trade | Trade flow, weak patrols, spillover from adjacent systems |
| `civilian_traffic` | 0–1 | Background population | Planet and station count, stability |

```text
demand_gradient  = Σ over neighbours |price_index(self) − price_index(neighbour)|
trade_target     = clamp(k_t × demand_gradient × connectivity × (1 − raider_pressure), 0, 1)
trade_flow      += (trade_target − trade_flow) × trade_relax

patrol_target    = influence[controller] × faction_military[controller]
patrol_strength += (patrol_target − patrol_strength) × patrol_relax − patrol_losses

spillover        = mean(raider_pressure of adjacent systems) × diffusion
raider_target    = clamp(k_r × trade_flow × (1 − patrol_strength) + spillover, 0, 1)
raider_pressure += (raider_target − raider_pressure) × raider_relax − raider_losses
```

All coefficients are `[BALANCE]`. This is a predator–prey system with a diffusion term, and it produces the chain
*GDD §5.3* asks for without anybody scripting it:

```text
shortage → price gradient rises → trade_flow rises → raider_pressure rises →
patrols take losses → patrol_strength falls → trade_flow falls → shortage deepens
→ gradient rises further …
```

Relaxation rates below `0.25` keep the system damped; §14.5 asserts that no variable oscillates with a period under
ten cycles, because an economy that visibly pulses on a fixed rhythm reads as machinery rather than as a world.

**Unobserved trade moves real goods.** Where `trade_flow > 0` and no haulers were materialised, 4a applies the net
cargo movement directly:

```text
moved = round(trade_flow × haul_capacity × cycles_since_simulated)
stock[surplus_station][commodity] -= moved
stock[deficit_station][commodity] += moved
```

A player returning to a system after a week finds the shortage partly resolved — by someone. That is the entire
point of the aggregate layer, and the reason it is not merely an optimisation.

### 6.5.2 Sub-stage 4b — Individuals, observed systems only

A system is **observed** when it holds at least one non-destroyed player ship, or a player is docked at one of its
stations. At MVP player counts that is well under half the galaxy.

Materialisation is deterministic and idempotent:

```text
for system in observed_systems:
    want = {hauler:  round(trade_flow      × k_h),
            patrol:  round(patrol_strength × k_p),
            raider:  round(raider_pressure × k_r)}      # each clamped to an archetype cap
    for archetype, n in want:
        for slot in range(n):
            ensure_npc(system_id, archetype, slot)
```

`ensure_npc` is keyed `(system_id, archetype, slot)` and seeded `Rng.for_("npc", system_id, archetype, slot)`, so the
same slot always yields the same callsign, ship class and route. Observing a system twice in a cycle shows the same
NPCs; so does re-running the tick (criterion A10).

Each materialised NPC then acts, through the **same commands players use** (§5.4), with an `actions_per_cycle`
budget from its archetype instead of AP. Archetype behaviour is specified in §10.

**Arrival mid-cycle.** A player jumping into an unobserved system triggers the same materialisation inside the
arriving command's transaction. The unique key makes it a no-op if 4b already ran, so a system is never briefly
empty and never doubly populated.

**Dissolution.** An NPC whose system has had no observer for `dissolve_after_cycles` (default 1) is removed, and its
state folds back into the aggregate rather than vanishing:

| NPC state at dissolution | Folded into |
| --- | --- |
| Cargo in hold, mid-route | 4a's bulk movement completes the run in aggregate |
| Kills scored | `raider_losses` / `patrol_losses` for the next cycle |
| Ship destroyed | Corresponding pressure or strength reduced |

### 6.5.3 NPC-versus-NPC combat

| Situation | Resolution |
| --- | --- |
| Unobserved | Statistical attrition inside 4a: `patrol_losses` and `raider_losses` derived from the two variables |
| Observed | The real resolver (§6.3), with the outcome fed back into the aggregate |

A player can therefore watch a patrol destroy a raider and see raider pressure fall the next cycle. The two tiers
agree because the observed outcome is written back, not because they were computed the same way.

### 6.5.4 Cost

4a is one query and roughly ten array operations over an *N*-system array. 4b is `O(observed systems × NPCs per
system)` — at MVP scale about 20 × 8 = 160 NPC turns. Both are noise inside the 60-second tick budget (A12), and
neither grows with the number of registered players.

## 6.6 Stage 5 — Territory

For each system, influence per faction:

```text
raw[f]      = Σ presence_weight(ship)   for ships of faction f in the system
            + Σ station_weight(station) for stations aligned to f
influence[f] = influence[f] × (1 - territory_decay) + normalise(raw)[f] × territory_decay
controller   = argmax(influence) if max(influence) >= territory_control_threshold else CONTESTED
```

Decay is what makes territory a consequence of *sustained* presence rather than of who happened to be there at the
tick (*GDD §6.6*). A change of controller emits `TERRITORY_CHANGE` at SYSTEM scope and invalidates the affected map
tiles (§9.1).

## 6.7 Stage 11 — Grant Action Points

```text
for player in active players where last_grant_day < world_day:
    carry       = min(floor(ap_balance × carry_over_fraction), carry_ceiling)
    new_balance = daily_grant + carry
    insert ap_ledger(delta = new_balance - ap_balance, reason='daily_reset')
    ap_balance     := new_balance
    last_grant_day := world_day
    emit AP_GRANTED (participants)
```

The ledger delta is **signed**: a player who ends a cycle holding more than `daily_grant + carry` records a negative
entry. That keeps `sum(delta) = ap_balance` exact (criterion A3), which a separate "expiry" row would not, and it is
why the reason is `daily_reset` rather than `daily_grant` — the stage computes a balance, it does not add to one.

The `last_grant_day` guard makes the stage idempotent. It runs after encounters and the economy so that a player
logging in immediately after the tick acts against a fully simulated world (*GDD §3.3*).

## 6.8 Stages 12–13 — Projections and digests

Stage 12 rebuilds map tiles for every path prefix touched by the day's events and bumps their cache version. Stage 13
composes each player's daily overview from their `event_deliveries` plus scoped events and stores it as the
`player_dashboard` read model; email delivery is a P4 concern, but the dashboard content is MVP (*GDD §3.4*).

## 6.9 Determinism

| Source of variance | Handling |
| --- | --- |
| Randomness | `RngPort.for_(stage, entity_id)`, seeded from `world_seed`, `world_day` |
| Wall-clock time | `ClockPort`; stages take `world_day` as input and never read the clock |
| Row order | Every stage query carries an explicit `ORDER BY` on a unique key |
| Dict iteration | Sorted keys wherever an ordering can affect a roll |
| Float accumulation | Money and stock are integers; influence is `numeric`, rounded at defined points |

Criterion A10 is tested by running a tick twice against a restored snapshot and diffing the event stream.

---

# 7. World generation

Run once per world, offline, by `frontier-worldgen --seed <s>`; the output is ordinary rows, so a generated world is
indistinguishable from a hand-authored one.

| Parameter | MVP value `[BALANCE]` |
| --- | --- |
| Regions | 4 |
| Systems per region | 10–14 |
| System hex map radius | 8 (217 hexes) |
| Planets per system | 3–8 |
| Stations per system | 1–3 |
| Commodities | 8 |
| Faction home systems | 1 per faction |

```text
1. Create the galaxy root and 4 region hexes.
2. For each region, place systems on distinct galaxy-child hexes via Poisson-disc sampling.
3. For each system, place a star at (0,0) and planets on rings 2..8 with decreasing density.
4. Designate stations: faction homes first, then one station per 2 planets, biased toward the inner rings.
5. Assign each station a type; seed its market from the type's production and consumption profile.
6. Seed territory: home systems at influence 1.0 for their faction, all others at 0.
7. Mark faction home systems and their immediate neighbours discovered; everything else undiscovered.
```

Every step draws from `Rng.for_("worldgen", step, index)`, so a seed reproduces a world exactly — which is what makes
the simulation soak test (§14.5) meaningful.

Sizing check: roughly 47 systems × 217 hexes ≈ 10 200 addressable system hexes and about 250 planets. Small enough
to generate in seconds and to inspect by hand, large enough that map streaming (§9.1) is genuinely exercised rather
than accidentally satisfied.

**Every in-system hex is a row**, `kind = 'void'` where nothing sits there `[D-17]`. A destination check is then a
lookup rather than a radius calculation, and there is one source of truth for what exists.

---

# 8. HTTP and WebSocket API

## 8.1 Conventions

| Concern | Rule |
| --- | --- |
| Base path | `/v1` |
| Auth | Bearer access token (15 min) + rotating refresh token; `Authorization` header only |
| Content type | `application/json`; `snake_case` field names |
| Idempotency | Every command carries `idempotency_key` (client UUIDv4) |
| Cursors | Opaque, derived from event UUIDv7; `?after=<cursor>&limit=<n≤200>` |
| Caching | Map tiles carry `ETag`; clients send `If-None-Match` |
| Errors | RFC 9457 `application/problem+json` with a stable `code` |
| Time | Server sends `world_day` and ISO-8601 UTC; client-sent timestamps are ignored (*GDD* C1) |

## 8.2 Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/auth/register` | Create account and player, choose callsign |
| `POST` | `/v1/auth/login` | Issue tokens |
| `POST` | `/v1/auth/refresh` | Rotate tokens |
| `GET` | `/v1/me` | Dashboard read model: AP, credits, ship, position, unread counts, world_day |
| `POST` | `/v1/commands` | Execute one command (§5.4) |
| `POST` | `/v1/commands:batch` | Execute up to 20 commands in sequence, stopping at the first rejection |
| `GET` | `/v1/map/tiles` | `?path=&level=` — one tile at the requested level |
| `GET` | `/v1/systems/{id}` | System detail: planets, stations, visible contacts |
| `GET` | `/v1/stations/{id}/market` | Prices computed live from stock |
| `GET` | `/v1/feed` | `?channel=&after=&limit=` — merged events and messages |
| `GET` | `/v1/teams` `POST` `/v1/teams` | List and create |
| `GET` | `/v1/players/{id}` | Public profile: callsign, faction, team. Nothing else `[D-5]` |

The command envelope is a discriminated union, so one endpoint validates every intent and one place holds the
locking and idempotency logic:

```python
class MoveCommand(BaseModel):
    action: Literal["move"]
    to: str
    idempotency_key: UUID

CommandBody = Annotated[MoveCommand | JumpCommand | ScanCommand | BuyCommand | SellCommand
                        | AttackCommand | DockCommand | LaunchCommand | RepairCommand
                        | SetStandingOrdersCommand | SendMessageCommand,
                        Field(discriminator="action")]
```

`/commands:batch` exists because a ten-hex journey should be one round trip, not ten. It is a transport convenience
only: the server still evaluates every hop separately and stops at the first rejection, returning the events of the
hops that succeeded.

### Public profile

`GET /v1/players/{id}` returns an explicit allowlist — callsign, faction, team, and nothing computed from private
state `[D-5]`. This is the MVP's inheritance of *ARCH §12.1*: even with no hidden faction built, response models are
allowlists from the first line of code, because retrofitting that discipline later is what leaks.

## 8.3 WebSocket

`GET /v1/stream` (upgrade), authenticated with the same bearer token.

```text
client → {"op": "subscribe", "channels": ["local", "system", "team"], "after": "<cursor>"}
server → {"op": "event", "event": {...}}
server → {"op": "world", "phase": "ticking"}
client → {"op": "ping"} / server → {"op": "pong"}
```

Rules:

- The server validates every subscription against the player's actual position and memberships. A client may ask for
  a channel; it may not assert entitlement to one.
- Every frame passes through `render_for` (§5.5) before serialisation.
- Delivery is at-least-once; the client de-duplicates on `event.id`. On reconnect the client sends its last cursor
  and receives the gap over HTTP, then resumes live frames.
- No game state is ever *sent* to the server over the socket. Commands go over HTTP, where idempotency and
  transactions live.

## 8.4 Error codes

| HTTP | `code` | Meaning |
| --- | --- | --- |
| 400 | `MALFORMED` | Schema violation |
| 401 | `UNAUTHENTICATED` | Missing or expired token |
| 403 | `FORBIDDEN` | Authenticated but not entitled |
| 404 | `NOT_FOUND` | Unknown, or not visible to this viewer — the two are indistinguishable by design |
| 409 | `INSUFFICIENT_AP`, `INSUFFICIENT_FUEL`, `INSUFFICIENT_CREDITS`, `INSUFFICIENT_STOCK`, `INSUFFICIENT_CARGO`, `CARGO_FULL`, `NOT_ADJACENT`, `SCALE_MISMATCH`, `NOT_DOCKED`, `MUST_LAUNCH_FIRST`, `IN_TRANSIT`, `TARGET_NOT_VISIBLE`, `TARGET_UNKNOWN`, `TARGET_DOCKED`, `OUT_OF_RANGE` | Legal request, illegal in the current world state |
| 429 | `RATE_LIMITED` | Per-account command rate limit |
| 503 | `WORLD_TICKING` | Retry after the tick window |

409s are gameplay, not faults: they are counted, not alerted on, and never logged at error level (*ARCH §11.4*).

---

# 9. Read models and the client contract

## 9.1 Map tiles

A tile is the visible content of one path prefix at one level, rendered for one faction.

| Key | `{level}:{path}:{faction_id}:{world_day}:{revision}` |
| --- | --- |
| Galaxy tile | Regions, faction control colours, the viewer's position |
| Region tile | Systems (discovered only), control, trade-route hints |
| System tile | Planets, stations, contacts within sensor range, the viewer's ship |

Tiles are built by stage 12 and on demand on a cache miss, cached in Redis, and served with `ETag`. Undiscovered
locations are **absent**, not marked hidden — the payload itself must not reveal that something is there (*GDD* C4,
criterion A11).

## 9.2 Dashboard

`GET /v1/me` answers the five questions of *GDD §3.4* in one request: what happened to me, what changed near me, what
my team said, what I can afford, what expires today. It reads the `player_dashboard` model built by stage 13 and
patches in live AP and position.

## 9.3 Feed

Merged events and messages, newest first, cursor-paginated. Narrow-audience events come from `event_deliveries`;
spatial events come from `evt.events` by path prefix; the two are merged and sorted by UUIDv7 id, which is
monotonic, so the merge is a simple ordered zip with no timestamp comparison.

---

# 10. NPC archetypes

The population *process* is §6.5; this section is the *content* — what an NPC is, what it does, and how many of them
there are. Realises *GDD §2.7*.

## 10.1 Representation

NPC ships live in `core.ships` with a null `player_id`: the same table, the same physics, the same combat resolver,
the same events `[D-6]`. An NPC differs from a player in exactly two ways:

1. It has a `core.npc_agents` row carrying archetype, slot, route and lifecycle timestamps.
2. It spends an `actions_per_cycle` budget instead of Action Points, because AP is a fairness device for human
   attention, not a law of the world (*GDD §2.7*).

Everything else is shared. An NPC hauler that cannot afford its cargo is rejected with `INSUFFICIENT_CREDITS` by the
same `check` a player would hit, and that is the point: a second rule engine for NPCs is a second set of bugs and a
guaranteed drift between what players see and what the world does.

## 10.2 The three archetypes

| | **Hauler** | **Patrol** | **Raider** |
| --- | --- | --- | --- |
| Job (*GDD §2.7*) | Circulation | Territory | Opposition |
| Actions / cycle `[BALANCE]` | 4 | 3 | 3 |
| Ship class | Light freighter: high cargo, weak weapon | Corvette: strong shields and weapon, no cargo | Raider: fast, medium weapon, medium cargo |
| Spawn driver | `trade_flow` | `patrol_strength` | `raider_pressure` |
| Cap per system `[BALANCE]` | 6 | 4 | 4 |
| Standing orders equivalent | `EVADE`, retreat at 60 % | `AGGRESSIVE` against raiders and faction-hostiles | `AGGRESSIVE` above a cargo-value threshold, flee at 40 % |
| Faction | None | Controlling faction | Pirates |

### Hauler

Runs a route between a surplus station and a deficit station, chosen when the NPC is materialised from the largest
price gradient available in the system. The loop is `dock → buy → launch → fly → dock → sell`, executed as real
commands against `core.markets`, so a hauler visibly changes prices. A player can undercut one, follow one to find a
profitable pair, or rob one.

### Patrol

Holds position near the controlling faction's station and sweeps the busiest lane. Engages raiders on sight, and
players whose faction is hostile to the controller. Patrol presence contributes to territory influence at stage 5,
which is what makes a border cost something to hold (*GDD §6.6*).

### Raider

Loiters near the lane with the highest traffic, engages ships whose cargo value exceeds a threshold, and flees when
hurt. Raiders are the reason an unarmed trader is a choice rather than a default.

## 10.3 Legibility

*GDD §2.7* requires NPC behaviour to be predictable: a player who watches a hauler for three cycles should be able
to anticipate the fourth. Three rules deliver that:

- **Deterministic identity.** A slot's callsign, ship class and route come from `Rng.for_("npc", system_id,
  archetype, slot)`, so the same NPC is the same NPC across observations and across tick replays.
- **Published routes.** A hauler's route is derived from visible market data, so a player with the same information
  can work it out. Nothing about an NPC's decision depends on state the player cannot in principle see.
- **No rubber-banding.** Raider pressure rises because trade is rich and patrols are thin — never because a player is
  winning. This is a hard rule, and the soak test asserts no correlation between individual player wealth and local
  raider pressure (§14.5).

## 10.4 What is deliberately absent

| Absent | Why | Where it attaches |
| --- | --- | --- |
| Faction strategic AI | *ARCH* stage 4's other half; needs faction goals that do not exist yet | Stage 4, second sub-stage |
| Named, persistent NPCs | Politicians, officers and scientists are the Continuity's instruments (*GDD §9.5*) | `npc_agents` gains a `persistent` flag and survives dissolution |
| NPC missions and dialogue | Missions are P4 | Mission provider interface (*ARCH §18*) |
| Civilian ships as objects | `civilian_traffic` is an aggregate only; it colours the system view and feeds density, and materialises nothing | A fourth archetype |

# 11. Configuration and environments

| Setting | Source | Example |
| --- | --- | --- |
| `DATABASE_URL`, `REDIS_URL` | environment | — |
| `RULESET_VERSION` | environment | `2026.1` |
| `TICK_HOUR_UTC` | environment | `04` |
| `WORLD_SEED` | database (`world_state`) | set at generation |
| AP costs, prices, ranges | ruleset TOML | §3.4 |
| `FEATURES_*` | environment | all MVP-deferred features default off |

`pydantic-settings` loads environment configuration and fails fast on a missing value. Game balance never comes from
the environment, and infrastructure never comes from the ruleset: the two have different reviewers and different
blast radii (*ARCH §11.2*).

Local development is `docker compose up`: postgres, redis, api, ws, worker, plus `make world` to generate a world and
`make tick` to advance a day on demand. Nothing in the MVP requires the scheduler to be running for a developer to
see a cycle boundary — which is the single most important property of the development environment for a game whose
natural feedback loop is 24 hours (*ARCH §14.1*).

---

# 12. Observability

The MVP ships the minimum that makes the tick and the command path debuggable:

- **Logs** (structlog JSON) carrying `command_id`, `player_id`, `world_day`, `ruleset_version`, `causation_id`.
- **Metrics**: command latency by action; rejection counter by code; AP granted and spent per cycle; events by type
  and scope; per-stage tick duration and row counts; outbox depth; WebSocket connected clients.
- **Traces**: one span per command, one per tick stage.
- **A tick report**, written to `hist.tick_stages` and printed by `make tick`: rows touched, events emitted, duration
  per stage. This is what turns "day 12 felt wrong" into a query.

---

# 13. Security in the MVP

| Threat | MVP control |
| --- | --- |
| Client asserting state | Intent-only command API; server computes every outcome (*GDD* C1) |
| Replay / double submit | `idempotency_key` unique per player; unique `command_id` in the AP ledger |
| Credential theft | Argon2id hashing, short access tokens, rotating refresh tokens |
| Scripting | AP is the throttle; plus a per-account command rate limit of 120/min `[BALANCE]` |
| Map scraping | Map endpoints obey `render_for`; undiscovered locations are absent from payloads |
| Enumeration | Unknown and not-visible both return `404` |
| Chat abuse | Messages are events; retrospective moderation is possible from the log |

Out of MVP scope: multi-accounting detection, TOTP, moderation tooling. Each is a P4 item, not an oversight.

---

# 14. Test plan

## 14.1 Shape

| Layer | Runs in | Gate |
| --- | --- | --- |
| Unit — domain rules, decisions, redaction | milliseconds, no I/O | every commit |
| Property — hex algebra, AP and money invariants | Hypothesis | every commit |
| Integration — repositories, migrations, locking, `ltree` | testcontainers PostgreSQL + Redis | every commit |
| Contract — OpenAPI vs the generated TypeScript client | schemathesis | every commit |
| Tick — stage idempotency and determinism | seeded fixture world | every commit |
| Simulation — 90-cycle soak | nightly | nightly |

The domain is pure, so most coverage sits in the two fastest layers. A rule change must be provable without a
database; if it is not, the rule has leaked out of the domain.

## 14.2 Property tests

```python
@given(a=axials(), b=axials(), c=axials())
def test_distance_is_a_metric(a, b, c):
    assert distance(a, a) == 0
    assert distance(a, b) == distance(b, a)
    assert distance(a, c) <= distance(a, b) + distance(b, c)

@given(a=axials())
def test_every_neighbour_is_distance_one(a):
    assert all(distance(a, n) == 1 for n in neighbours(a))

@given(centre=axials(), radius=st.integers(0, 12))
def test_ring_size(centre, radius):
    assert len(ring(centre, radius)) == (6 * radius if radius else 1)

@given(addr=hex_addrs())
def test_ltree_round_trip(addr):
    assert HexAddr.parse(addr.ltree().replace(".", "/")) == addr

@given(a=hex_addrs(), b=hex_addrs())
def test_containment_is_prefix(a, b):
    assert a.contains(b) == b.ltree().startswith(a.ltree())

@given(plan=command_sequences())
def test_ap_never_negative(plan):
    assert run(plan).ap_balance >= 0

@given(plan=trade_sequences())
def test_credits_and_stock_are_conserved(plan):
    before, after = run(plan)
    assert before.credits + before.stock_value == after.credits + after.stock_value
```

## 14.3 Integration tests

| Test | Asserts |
| --- | --- |
| Concurrent last-AP commands | Exactly one succeeds; ledger has one debit (A7) |
| Retried idempotency key | Same response, one ledger row (A8) |
| Cross-player lock ordering | 200 interleaved two-party commands, no deadlock |
| `ltree` containment | System query returns exactly the seeded subtree |
| Migration rehearsal | `0001`…`0007` apply to a production-sized copy inside the CI budget |
| Every mutation emits an event | A session hook fails any transaction that writes state without appending to `evt.events` (A3) |

That last test is the enforcement of *ARCH §3.2*'s first principle, and it is cheap: a SQLAlchemy
`before_commit` listener comparing the dirty set against the event buffer.

## 14.4 Tick tests

| Test | Asserts |
| --- | --- |
| Stage idempotency | Each stage run twice on the same world day produces identical state and no duplicate events |
| Resume after crash | Killing the runner mid-stage and restarting completes the day exactly once |
| Determinism | Two runs from the same snapshot produce byte-identical event streams (A10) |
| Journey landing | A two-cycle jump lands on day *N+2*, not *N+1* or *N+3* (A4) |
| Offline defence | An offline defender's standing orders drive the outcome, and the result reaches their feed (A6) |
| Ordering | Cargo destroyed in stage 2 is reflected in stage 3 prices |
| AP carry-over | 7 unspent AP carries 3, capped at `carry_ceiling`; the ledger delta is signed and reconciles |
| Aggregate liveliness | Seven cycles with no players change market stock in unvisited systems (A13) |
| Materialisation | Observing a system twice on one world day yields identical NPCs; re-running stage 4b is a no-op (A14) |
| Dissolution | An NPC dissolved mid-route hands its cargo to the aggregate; total goods are conserved |
| Tier agreement | An observed patrol kill lowers `raider_pressure` next cycle by the same amount the statistical path would |

## 14.5 Simulation soak

A seeded world runs 90 cycles headless with scripted cohorts (30 traders, 10 pirates, 10 explorers). Assertions:

- No faction exceeds 80 % territory before cycle 60.
- No population variable oscillates with a period under ten cycles — a visibly pulsing economy reads as
  machinery rather than as a world (§6.5.1).
- `raider_pressure` shows no correlation with individual player wealth: pressure follows trade and patrols, never
  player success (§10.3).
- Commodity price dispersion stays within a configured band — a collapse means the economy has no gradient left and
  trading has stopped being a decision.
- Total credit supply grows within bounds; unbounded growth means a sink is missing.
- Tick duration stays under 60 s (A12).
- No unhandled exception, and every tick day has a complete `hist.tick_stages` set.

This is simultaneously the performance test, the balance test and the regression net. It is the only place a slow
drift becomes visible before players find it.

## 14.6 Acceptance mapping

| Criterion | Covered by |
| --- | --- |
| A1 | Integration: registration → team → ship |
| A2, A3 | Property `test_ap_never_negative`; integration mutation-emits-event hook |
| A4 | Tick: journey landing |
| A5 | Unit: spread; property: credits conserved |
| A6 | Tick: offline defence |
| A7, A8 | Integration: concurrency and idempotency |
| A9 | Unit: `render_for` quality matrix, all five rows |
| A10 | Tick: determinism |
| A11 | Contract: tile payload contains no undiscovered location |
| A12 | Simulation soak |
| A13 | Tick: aggregate liveliness |
| A14 | Tick: materialisation |
| A15 | Tick: AP carry-over; property `test_ap_never_negative` |

---

# 15. Work breakdown

Ordered by dependency. "Done" means merged with tests passing and the listed acceptance criteria met — not
"implemented".

## P0 — Skeleton

| # | Task | Done when |
| --- | --- | --- |
| 0.1 | Repo, `pyproject.toml`, uv, ruff, mypy strict on `domain`/`application` | `make check` is green |
| 0.2 | `import-linter` contracts (§2) | A domain file importing `sqlalchemy` fails CI |
| 0.3 | Docker Compose: postgres, redis; `make up` | Fresh clone reaches a running stack |
| 0.4 | Alembic wiring, revision `0001` | Migrations apply and roll forward in CI |
| 0.5 | `RuleSet` loader with validation | An unknown TOML key fails startup |
| 0.6 | Ports, unit of work, command template (§5.2) | `move` executes end to end against a two-hex fixture world |
| 0.7 | FastAPI skeleton, auth, `POST /v1/commands` | A1 partially; a token can move a ship |

## P1 — World and time

| # | Task | Done when |
| --- | --- | --- |
| 1.1 | `HexAddr`, `Axial`, encoding (§3.1) | Property tests in §14.2 pass |
| 1.2 | Hex geometry (§3.2) | Property tests pass |
| 1.3 | `core.locations` + `ltree` (§4.2) | Containment integration test passes |
| 1.4 | World generator (§7) | `make world` builds 48 systems reproducibly from a seed |
| 1.5 | AP ledger and balance invariant (§3.4, §4.2) | A2, A3 |
| 1.6 | Tick runner, advisory lock, checkpoints (§6.1) | Resume-after-crash test passes |
| 1.7 | Stages 1, 11, 12 | A4 (with a stub journey), daily reset visible in `GET /v1/me` |

## P2 — Event spine

| # | Task | Done when |
| --- | --- | --- |
| 2.1 | `Event`, payload `TypedDict`s, catalogue (§3.5) | Unknown event type fails validation |
| 2.2 | `evt.events` partitioned, deliveries, outbox (§4.2) | Twelve partitions pre-created |
| 2.3 | `resolve_audience` / `render_for` (§5.5) | A9; quality matrix fully covered |
| 2.4 | Outbox relay process | Event reaches Redis under 1 s after commit |
| 2.5 | WebSocket gateway, subscriptions, cursors (§8.3) | Reconnect replays the gap with no duplicates after de-dup |
| 2.6 | `send_message` as an event; `GET /v1/feed` | Chat and combat appear in one ordered feed |

## P3 — MVP gameplay

| # | Task | Done when |
| --- | --- | --- |
| 3.1 | Ships, cargo, fuel, dock/launch (§3.3, §5.4) | Ship state changes only through commands |
| 3.2 | `move`, `jump`, journeys, stage 1 (§5.4, §6.2) | A4 |
| 3.3 | `scan`, discovery, `player_discoveries` (§5.4) | A9, A11 |
| 3.4 | Markets, pricing, `buy`/`sell`, stage 3 (§5.4, §6.4) | A5 |
| 3.5 | Encounter resolver, NPC combat, `attack` (§6.3) | Deterministic replay of a seeded encounter |
| 3.6 | Standing orders, encounter queue, stage 2 (§3.3, §6.3) | A6 |
| 3.7 | Teams, factions, membership commands (§5.4) | A1 |
| 3.8 | Territory, stage 5 (§6.6) | Control changes after sustained presence, not instantly |
| 3.9a | `system_activity`, sub-stage 4a, aggregate goods movement (§6.5.1) | A13; soak shows no oscillation |
| 3.9b | Materialisation and dissolution, sub-stage 4b, lazy spawn on arrival (§6.5.2) | A14 |
| 3.9c | Archetype behaviour: hauler, patrol, raider (§10.2) | A generated world has visible traffic on day 1; a hauler visibly moves prices |
| 3.10 | Map tiles, dashboard, ETags (§9) | A11 |
| 3.11 | Simulation soak in CI nightly (§14.5) | A12 |

**Critical path:** 0.6 → 1.1 → 1.3 → 1.6 → 2.3 → 3.2 → 3.6. Everything else can proceed in parallel once its
dependency lands. The riskiest item is 2.3: visibility touches every later feature, and retrofitting it is the one
mistake in this plan that would cost a rewrite.

---

# 16. Decisions taken in this document

| ID | Decision | Rationale | Reversible? |
| --- | --- | --- | --- |
| D-1 | The MVP addresses four levels (Galaxy, Region, System, Planet); Sector and Local are generated by nothing and used by nothing. Docking is a state, not a sub-map. | Surface gameplay has no MVP content; generating empty levels invites accidental dependencies. | Yes — `Level` already carries all six |
| D-2 | No pathfinding. Route cost is `distance × ap_per_hex`. | In-system space is uniform in the MVP; A* arrives with hazards. | Yes |
| D-3 | Contact search narrows by system in SQL and filters by hex distance in Python. | GiST cannot express hex range; a system holds hundreds of ships, not millions. | Yes |
| D-4 | Player-versus-player encounters always resolve at tick stage 2, never live — even when both players are online. | One code path for offline and online defence, so they can never diverge (*GDD §3.5*). | Yes, but only by accepting two paths |
| D-5 | Public API responses are explicit allowlists from the first commit, not ORM dumps. | The MVP has no secrets to leak, but the discipline is what prevents leaking later (*ARCH §12.1*). | No — this is a standing rule |
| D-6 | NPCs share `core.ships`, the player command handlers and the combat resolver; they differ only by an `npc_agents` row and an action budget instead of AP. | A second rule engine for NPCs is a second set of bugs and guaranteed drift between what players see and what the world does. | No |
| D-7 | The NPC population is simulated at two fidelities: aggregate flows everywhere, individual ships only where observed, with materialisation and dissolution between them. | Keeps the tick independent of world size while letting the galaxy evolve everywhere; and the aggregate layer is the same quantity psychohistory will later measure (*GDD §2.7*, §8.5). | Yes, at the cost of either an empty galaxy or an unbounded tick |
| D-8 | One `POST /v1/commands` endpoint with a discriminated union, plus a batch variant. | Locking, idempotency and ledger writes exist once. | Yes |
| D-9 | Prices are computed inside the transaction from current stock; a client-sent price is ignored, not validated. | Validating a client price implies the client has one (*GDD* C1). | No |
| D-10 | The `psycho` and `cont` schemas are not created in the MVP. | An empty schema for an unbuilt feature attracts content. | Yes |
| D-11 | Tick stage 4 enters the MVP, restricted to its NPC half. | *GDD* Pillar 1 is false without it: a persistent universe in which nothing happens unless a player causes it is not persistent. | No |
| D-12 | `civilian_traffic` is an aggregate that never materialises. | It colours the system view and feeds density without adding a fourth archetype to build, balance and test. | Yes |
| D-13 | P0 runs the command path against in-memory repositories; the SQLAlchemy ones arrive with their tables in P1 and P3. | P0's job is to prove the ports, the layering and the command template. Building `locations` and `ships` repositories before the world tree and the fleet exist would mean writing them twice. | Yes — the ports do not change |
| D-14 | `ap_ledger` moves from migration `0003` into `0001`. | The command template cannot be demonstrated without the AP debit, and the ledger belongs with `commands` in any case: both are the command path's audit trail. | Yes |
| D-15 | Commands emit `EventDraft`s; the executor stamps id, time, world day and ruleset version. | Keeps clocks and identity generation out of the domain, so a command's `apply` stays pure and directly testable (§5.1). | No |
| D-16 | `ships` and `journeys` move from migration `0005` into `0004`, in P1. | A unit of work spanning Postgres for locations and memory for ships would be a worse intermediate architecture than reordering two migrations — and tick stage 1 needs journeys to settle. | Yes |
| D-17 | Every in-system hex is a `locations` row, `kind = 'void'` where empty. | A destination check becomes a lookup instead of a radius rule held in two places. About 10 200 rows, which is nothing. | Yes |
| D-18 | The world day lives in `core.world_state`, not in the clock. `ClockPort` provides only `now()`; callers pass the day to `RngPort`. | The day is world state: the tick advances it, and a replay must be able to set it. A clock that derives it from wall time cannot be replayed or accelerated (*ARCH §14.1*). | No |
| D-19 | Tick stage 12 (`RebuildProjections`) is deferred to P2; P1 ships stages 1 and 11, and `GET /v1/me` reads live. | There are no projections to rebuild until the event spine exists. Building a throwaway table to fill the slot would be worse than an honest gap. | Yes |
| D-20 | Entry points live in `frontier.cli`, a layer above `simulation` and `adapters`. | `make world` and `make tick` compose adapters, so they cannot sit inside `worldgen`, which the layer contract keeps pure. | Yes |
| D-21 | Scope decides reach before sensors do: an event at SYSTEM scope or wider reaches everyone inside its container, and only LOCAL/PLANET events are gated by sensor range. | *GDD §7.7* makes scope the mechanism by which an event carries. Ranking sensors first would have made a system-wide announcement audible only to whoever stood nearby. | No |
| D-22 | One Redis channel carries every event; each gateway renders per subscriber. | Filtering must happen server-side per viewer anyway (§5.5), so per-scope channels would optimise a step that cannot be skipped. Splitting by path prefix is a later change behind the same interface. | Yes |
| D-23 | The gateway sends `{"op": "ready"}` once its subscription exists, and never awaits readiness without also watching the pump task. | A client that fetched its gap over HTTP before the subscription existed would miss events published in between. Awaiting the event alone deadlocked when the pump died first — a bug this design prevents rather than detects. | No |
| D-24 | Stage 12/13 builds a per-player digest keyed `(player_id, world_day)`. | The daily overview must be ready before anyone logs in (*GDD §3.4*), and it is the first projection with a reader, which is what D-19 was waiting for. | Yes |
| D-25 | The in-memory adapter is retired in P3; every path runs on PostgreSQL. | D-13's scaffolding had done its job. Keeping it once the SQL repositories existed would have meant two rule paths and a standing risk of divergence — the same reason NPCs share the player command handlers (D-6). | No |
| D-26 | A command declares its fetch set as a `StateSpec`, and one `SqlStateStore` loads and saves it. | Handlers stay free of I/O, so `check` and `apply` remain pure and directly testable, and the query set for every command is reviewable in one file (§5.3). | No |
| D-27 | The star chart is public: every galaxy, region and system is known from registration. What is *inside* a system is not. | *GDD §2.5* shows systems on the region view, and §5.2 makes discovery about planets, stations and wrecks. Without this, jump has no legal destination and exploration has nothing to reveal. | Yes |
| D-28 | The respawn penalty is applied as `GREATEST(0, credits - penalty)` in one statement. | Subtracting and then clamping trips the `credits_non_negative` CHECK for a player poorer than the penalty — which is how the constraint caught the bug. | No |
| D-29 | Promotion accumulates severity per address prefix and emits a `HISTORICAL_EVENT` carrying a `causation_id` to one of its causes. | *GDD §7.7* wants a skirmish to become a war by weight of what happened, not by a bespoke pipeline per conflict, and a reader of history must be able to trace the chain back. | Yes |
| D-30 | The Chronicle is written **before** retention deletes anything, in the same stage. | Two stages, or the reverse order, would let the record lose something the retention job was about to drop. | No |
| D-31 | Missions are generated from where the world is under strain (raider pressure plus trade flow), not from a script. | *GDD §5.5*: the same situation should produce different work for different factions, without anyone authoring the conflict. | Yes |
| D-32 | Reputation is clamped to ±100 in SQL on every write. | It is a standing, not a currency: an unbounded score would make late players permanently unreachable and early ones untouchable. | Yes |
| D-33 | Defection moves the whole team, is a Universe-scope `HISTORIC` event, and costs 25 standing with the faction left behind. | *GDD §6.7* requires a major political event rather than a menu operation; the reputation cost is what makes it a decision. | Yes |
| D-39 | The wreck fee is `floor(credits × rescue_tax_fraction)`, not a flat sum, and is framed as salvage for the life capsule. | S1. A flat penalty is noise to a veteran and ruin to a newcomer; a share scales with means and can never leave a pilot unable to fly. The fraction is `[BALANCE]` inside a 3–10 % band. | Yes |
| D-40 | A jump is bounded by the hull's `jump_range_ly` as well as by fuel, refused with `BEYOND_JUMP_RANGE`. | S3. Range becomes a property of the ship a player chose, so hulls differ in reach and not merely in tank size. | Yes |
| D-41 | Materialised NPCs are never dissolved; every agent acts each cycle, observed or not. | S5. Dissolution made a system's inhabitants a function of who was watching, contradicting the persistence *GDD §2.7* promises. Cost now scales with the *explored* world; the per-system archetype caps bound it, and R1 is the trigger to revisit. | Yes |
| D-47 | Tick stages raise `EventDraft`s through `TickContext.emit`, and the runner stamps and writes them inside the stage's own transaction. | *ARCH §3.2* requires that no state change happen without an event, and the stages were the one place it did not hold: the catalogue (§3.5) said stage 1 emits `SHIP_ENTERED`, stage 2 `SHIP_DESTROYED` and stage 5 `TERRITORY_CHANGE`, and none of them did. Found by building watch mode, which had nothing to show. | No |
| D-48 | World generation seeds `core.territory` so each faction holds its home from the first cycle. | *SDD §7* step 6 specified it and the implementation omitted it, so a new galaxy was uncontrolled everywhere and took seven cycles of blending to show a single border. | Yes |
| D-51 | `sensor_quality(steps, range)` is one shared ladder: events read it through `observation_quality`, contacts read it directly. | A ship must never be more or less visible than the events it generates. Two ladders would drift, and the drift would be a leak in whichever direction was looser (*UX §4.2*). | No |
| D-52 | `GET /v1/systems/{id}` answers `404` for a system the player is not in — the same answer as for one that does not exist. | Distinguishing "not yours" from "not there" would let a player probe the galaxy by status code. | No |
| D-50 | The population's flow advance is guarded by `last_simulated_on == world_day`, not `>=`, and goods move only for systems advanced in that pass. | Flows and stock are cumulative, so a re-run must not move them twice. `>=` looked equivalent and is not: a world day can be rewound — a restored snapshot, a replay, a test fixture — and a `>=` guard would freeze the population permanently. | No |
| D-49 | Watch mode is served by its own `/v1/watch/*` routes rather than by relaxing the player endpoints. | A spectator's entitlement is different in kind, not degree: no ship, no sensors, public system-or-wider events only. Separate routes make "strictly weaker than any player" a property that can be tested rather than an argument about parameters. | No |
| D-44 | The public API connects as `api_role`, which holds no grant on `cont`; the Continuity's stage runs as `cont_role`, which may read the world, write its own records and update `core.system_activity` — and nothing else. | *ARCH ADR-13* and *GDD §9.13*. A serialisation mistake cannot leak what the connection cannot read, and "push, never force" becomes a privilege the database withholds rather than a rule this code remembers. | No |
| D-45 | The role is re-assumed with `SET LOCAL ROLE` on every transaction, not once per connection. | `SET ROLE` issued inside a transaction is undone when that transaction rolls back, so a pooled connection silently reverts to the owning user after the first failure — found by the anti-leak suite, which now asserts the effective role on every probe. | No |
| D-46 | Optional stages are resolved by dotted path at runtime (`frontier.simulation.extensions`), and an import contract forbids anything importing `frontier.continuity`. | A system whose existence must not be inferable cannot appear in the import graph of the thing that runs it, nor in a stack trace pasted into a public bug report (*GDD §9.4*). | No |
| D-43 | NPC crews hold an AP balance on `npc_agents`, granted by tick stage 11 under the same rule and the same numbers as players, and spent through `RuleSet.ap_cost`. | *GDD §2.7*: an NPC is a ship with a pilot who happens to be a program. A separate `actions_per_cycle` budget was a second economy that could drift from the players' — and it would have let the Continuity's NPC agents act without limit, which is exactly what §9.2 forbids. | No |
| D-42 | A player may hold no team; `players.team_id` and `faction_id` stay nullable and paired by a CHECK. | S2. Independence is a way to play, not an unfinished registration — so `leave_team` remains, and a player without a faction simply sees no faction missions. | No |
| D-35 | The Model reads only `psycho` views, and the `psycho_reader` role holds no privilege on `core` or `evt`. | *GDD §8.4* — populations, never individuals — becomes a property of the grants rather than of every future author remembering it (*ARCH ADR-12*). Proved by tests that assert `permission denied` for players, ships, events and reputation. | No |
| D-36 | `Observation` carries no identifying field, and a test asserts its exact field set. | The database boundary stops a query; this stops a *signature* from ever being widened to accept a player in the first place. | No |
| D-37 | Psychohistory ships behind `FEATURES_PSYCHOHISTORY`, default off, and `/v1/forecasts` returns 404 while dark. | *GDD §10.3*: the variables cannot be tuned against a world with no history. A 404 rather than a 403 keeps the unbuilt system from advertising itself. | Yes |
| D-38 | Forecast *access* is universal; only resolution varies with Knowledge (headline → narrowed → precise → reasoned). | Design Q2. Gating access would make forecasts purchasable content, which §8.3 forbids; gating precision keeps Knowledge worth accumulating. | No |
| D-34 | Read models live in `adapters/db/` beside the repositories, not in a separate `projections/` package. | Every MVP read model is built by querying the database, so a package layered *below* `adapters` inverts the real dependency — and because the API routers call the read models, the two packages formed an import cycle that `import-linter` rejected. Diverges from the sketch in *ARCH §16*, which should be amended. | Yes |

---

# 17. Open questions

**None outstanding.** Every question this document raised (S1–S6) and every *GDD §11.2* question that reaches the
MVP has been answered; the answers are recorded in §16 and in the sections they settle. New questions belong here as
they surface.

| Answered | Question | Answer |
| --- | --- | --- |
| S1 | What does a destroyed player lose? | The hull and its cargo, plus a **salvage tax** — a share of credits `[BALANCE]`, currently 5 % within an agreed 3–10 % band — charged for recovering the life capsule (D-39) |
| S2 | Can a player exist without a team? | Yes. Until they join or found one they are **independent**: no faction, no faction standing, no faction missions (*GDD §6.5*) |
| S3 | Is jump range limited by fuel alone? | No — also by the hull's own `jump_range_ly` (D-40) |
| S4 | Starting endowment | One light freighter, 5 000 cr, full tank `[BALANCE]` |
| S5 | How long does an NPC persist once unobserved? | Indefinitely. Materialisation is one-way and the server keeps playing them (D-41) |
| S6 | May a player see aggregate figures for a system they have not visited? | No. Density is qualitative; precise figures are a Knowledge matter (*GDD §8.9*) |

--- | --- | --- | --- |
| S1 | What does a destroyed player lose? | Respawn at faction home, base hull, empty cargo, credit penalty `[BALANCE]` | Task 3.5 |
| S2 | Can a player exist without a team? | No — registration requires creating or joining one | Task 3.7, faction denormalisation |
| S3 | Is jump range limited by fuel alone, or also by a maximum per jump? | Fuel alone in the MVP | Task 3.2 |
| S4 | Starting endowment: ship class, credits, fuel? | One light freighter, 5 000 cr, full tank `[BALANCE]` | Task 3.1 |
| S5 | How long does an NPC persist once its system is unobserved? | One cycle (`dissolve_after_cycles = 1`) | Task 3.9b |
| S6 | Should a player be able to *see* aggregate figures — traffic, danger — for a system they have not visited? | No in the MVP; the system view shows density qualitatively, and precise figures are a P5 Knowledge item (*GDD §8.9*) | Task 3.10 |

S1–S4 are design questions that surfaced during detailed design; they belong in *GDD §11.2* once answered.

---

# 18. Traceability

| MVP requirement (*GDD §10.1*) | Designed in | Verified by |
| --- | --- | --- |
| Hierarchical hex map, galaxy, systems, zoom | §3.1, §3.2, §4.2, §7, §9.1 | A11, property tests |
| Basic faction territories | §6.6 | Tick tests, soak |
| Account, credits, AP, location, reputation | §3.3, §4.2, §6.7 | A1, A2, A3 |
| Standing orders | §3.3, §5.4 | A6 |
| Ship: hull, shields, fuel, cargo, weapon, equipment | §3.3, §4.2 | A1, A5 |
| Hex movement, AP and fuel consumption | §5.4, §3.4 | A2 |
| Journeys across cycle boundaries | §5.4, §6.2 | A4 |
| Buy, sell, cargo, station markets | §5.4, §6.4 | A5 |
| Scan, discovery, basic events | §5.4, §5.5 | A9 |
| NPC and player encounters, simplified combat | §6.3, §10.2 | A6, A10 |
| Aggregate population in every system, individuals where observed (*GDD §2.7*) | §6.5, §10 | A13, A14 |
| Offline resolution | §5.4 (D-4), §6.3 | A6 |
| Teams, three factions, team chat, local communication (*GDD §7.3*) | §5.4, §8.3 | A1 |
| Local/Planet/System/Universe events, unified feed | §3.5, §5.5, §9.3 | A9 |
| Cycle steps 1–5, 11, 12 | §6 | A4, A10, A12, A13 |
| Half of unspent AP carries over to a ceiling (*GDD §3.2*) | §3.4, §6.7 | A15 |
| Design constraints C1–C10 (*GDD §10.4*) | C1 §5.2/§8.1 · C2 §6.1 · C3 §3.5 · C4 §5.5 · C5 §9.1 · C6 §6.3/§6.9 · C7 §3.4 · C8, C9 not applicable (D-10) · C10 not applicable | A3, A9, A10 |

---

# 19. Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.14 | 2026-08-28 | `GET /v1/systems/{id}` built for client slice C2: bodies in sight or charted, contacts graded by the shared sensor ladder (D-51), and a uniform `404` for any system the player is not in (D-52). |
| 0.13 | 2026-08-27 | Watch mode delivered (*UX §9*, client slice C1): `/v1/watch/*`, the public tile projection, and a browser client. Closed two real gaps found by building it — tick stages never emitted events (D-47) and world generation never seeded home territory (D-48). |
| 0.12 | 2026-08-27 | P6 delivered: the `cont` schema, capability-bounded `api_role` and `cont_role`, the Continuity's tick stage loaded by name and running under its own role, budgets that scale with world extent, and the anti-leak suite as a merge blocker. Recorded D-44 to D-46. |
| 0.11 | 2026-08-27 | NPC crews now draw and spend the same Action Point budget as players (D-43), replacing `actions_per_cycle`; migration `0014`. The Harrowing (*GDD §8.12*) is named in §1.3 as out of MVP scope. |
| 0.10 | 2026-08-27 | Design answers S1–S6 applied: salvage tax as a share of credits, hull-bound jump range, NPC persistence replacing dissolution, and independence confirmed for unteamed players. §17 is now empty. Recorded D-39 to D-42. |
| 0.9 | 2026-08-27 | P5 delivered: the `psycho` schema with aggregate-only views and a reader role that cannot see individuals, the pure historical model (variables, inertia, deviation, confidence, forecasts), tick stage 7 behind a feature flag, Knowledge earned by discovery, and `GET /v1/forecasts` disclosed per viewer. Recorded D-35 to D-38. |
| 0.8 | 2026-08-27 | Fixed a layering violation that had broken the `Layers` import contract since P3: the map-tile read model moved from `projections/` to `adapters/db/` (D-34). Pinned the CI interpreter to match `.python-version`. |
| 0.7 | 2026-08-27 | P4 delivered: event promotion and the permanent Chronicle with retention, mission generation from world pressure with accept/complete commands, reputation with clamped scores, and team defection as a Universe-scope event. Recorded D-29 to D-33. The tick now runs ten stages. |
| 0.6 | 2026-08-27 | P3 delivered: cargo, dock/launch, markets and buy/sell, jump and journeys, scan and discovery, the encounter resolver with live NPC combat and queued player encounters, standing orders, teams, territory, the two-tier NPC population with archetype behaviour, map tiles with ETags, and the nightly soak. Recorded D-25 to D-28. |
| 0.5 | 2026-08-27 | P2 delivered: the payload catalogue and validation, the partitioned `evt.events` log with deliveries and a transactional outbox, `resolve_audience`/`render_for`, the Redis relay, the WebSocket gateway, `send_message`, `GET /v1/feed`, and the digest stage. Recorded D-21 to D-24; D-19 is discharged. |
| 0.4 | 2026-08-27 | P1 delivered: the location tree on `ltree`, the world generator, SQLAlchemy repositories and unit of work, the tick runner with stages 1 and 11, and `GET /v1/me`. Recorded D-16 to D-20. Corrected the §7 sizing arithmetic (radius 8 is 217 hexes, not 169). |
| 0.3 | 2026-08-27 | P0 delivered. Recorded the decisions it forced: in-memory repositories for P0 (D-13), `ap_ledger` moved into migration `0001` (D-14), and `EventDraft` stamping with a new `IdPort` (D-15, §5.1). Noted the Alembic schema bootstrap in §4.4. |
| 0.2 | 2026-08-27 | Tracks *GDD* v2.3 and *ARCH* v0.2. The NPC population became a first-class MVP system: tick stage 4 (§6.5), the archetype catalogue (§10), `system_activity` and `npc_agents`, migration `0008`, and criteria A13–A14. Applied the answered design questions — the Planet/Sector ladder and two-letter `ltree` prefixes (§3.1), one ship per player (§4.2 of *GDD*), and half-carry of unspent AP with a signed `daily_reset` ledger entry (§3.4, §6.7, A15). Renamed `PLAYER_ENTERED` to `SHIP_ENTERED`. Restored decision-log ordering. |
| 0.1 | 2026-08-27 | First detailed design for phases P0–P3. |

---

*End of document.*
