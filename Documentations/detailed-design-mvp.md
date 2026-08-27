# Software Detailed Design — MVP

## *Frontier: The Seldon Era*, Python implementation

| Field | Value |
| --- | --- |
| Status | Draft for review |
| Version | 0.1 |
| Date | 2026-08-27 |
| Scope | Delivery phases **P0–P3** (*ARCH §17*), realising the MVP of *GDD §10.1* |
| Depends on | `Documentations/game-design.md` v2.0, `Documentations/architecture.md` v0.1 |

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
| World | Galaxy → Region → System → Body, generated once; system hex maps | District and Local levels — no surface gameplay yet `[D-1]` |
| Player | Account, credits, AP, position, faction, team, standing orders | Reputation *scores* exist and move; no reputation *effects* |
| Ship | One active ship: hull, shields, engine, fuel, cargo, one weapon, sensors | Fitting, modules market, multiple ships (*GDD* Q3) |
| Movement | In-system hex movement, inter-system jumps spanning cycles, dock/launch | Probes, advanced navigation, fuel scooping |
| Economy | Station markets, buy/sell, cargo, per-cycle price relaxation | Mining, production chains, player stations, smuggling |
| Exploration | Scan, permanent attributed discovery, per-player map knowledge | Anomalies, archives, deep survey |
| Combat | NPC encounters resolved live; PvP resolved at the tick from standing orders | Boarding, fleet battles, bounties |
| Social | Three factions, teams, team chat, local/system chat, unified feed | Defection, faction chat ranks, relays, comms delay |
| Events | One event spine, four scopes, per-viewer redaction, live WebSocket feed | Promotion to history, Chronicle, retention jobs |
| Cycle | Tick stages 1, 2, 3, 5, 11, 12, 13 | Stages 4, 6, 7, 8, 9, 10 |
| Hidden layers | — | Psychohistory (*GDD §8*) and the Continuity (*GDD §9*) are not built, not stubbed, not referenced |

**Tick stage numbering.** *GDD §3.3* lists twelve player-visible steps; *ARCH §9.2* lists thirteen executable
stages, because the design's step 12 ("prepares each player's daily overview and digest") splits into
`RebuildProjections` and `DispatchDigests`. The MVP runs ARCH stages **1, 2, 3, 5, 11, 12, 13**.

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

## 1.3 Explicitly not in the MVP

Stated so that nobody builds them "while they are in there": missions, reputation effects, defection, relays,
communication delay, bounties, mining, player stations, the Chronicle, forecasts, the Continuity. *ARCH §18* holds
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
│   ├── world/{location,body}.py             §3.3
│   ├── fleet/{ship,cargo,standing_orders}.py
│   ├── economy/{market,pricing}.py          §6.4
│   ├── encounter/{resolution}.py            §6.3
│   └── polity/{faction,team,territory}.py   §6.5
├── application/
│   ├── ports.py                             §5.1
│   ├── unit_of_work.py                      §5.2
│   ├── visibility.py                        §5.5
│   └── commands/                            §5.4 — one module per intent
├── simulation/
│   ├── tick.py                              §6.1
│   └── stages/{settle_travel,resolve_encounters,economy,territory,grant_ap,projections,digests}.py
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
    BODY = 3
    DISTRICT = 4
    LOCAL = 5

MVP_LEVELS = frozenset({Level.GALAXY, Level.REGION, Level.SYSTEM, Level.BODY})

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
| Galaxy | `g` | `g124_87` | `gn3_1` |
| Region | `r` | `r124_87` | `rn3_1` |
| System | `s` | … | … |
| Body | `b` | … | … |

`HexAddr.parse` is the inverse and is round-trip tested (§14.2). The human-readable form used in the API and in
logs is `g124_87/r3_1/s31_14`, i.e. the ltree with `.` replaced by `/`.

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
carry_over_max = 0            # GDD Q6 open; MVP does not carry over

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
| `PLAYER_ENTERED` | move, jump arrival | LOCAL | PUBLIC | `ship_id, from, to` |
| `JOURNEY_COMPLETED` | stage 1 | LOCAL | PARTICIPANTS | `journey_id, arrived_at` |
| `SCAN_PERFORMED` | scan | LOCAL | PARTICIPANTS | `range, contacts_found` |
| `DISCOVERY` | scan | SYSTEM | PUBLIC | `location_id, kind, first_by` |
| `TRADE_EXECUTED` | buy, sell | LOCAL | PARTICIPANTS | `station_id, commodity, qty, unit_price` |
| `MARKET_SHIFT` | stage 3 | BODY | PUBLIC | `station_id, commodity, old, new` |
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
    player_id     uuid NOT NULL UNIQUE REFERENCES core.players(id),   -- one active ship, GDD Q3
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
CREATE INDEX ships_position_gist ON core.ships USING gist (position_path);
CREATE INDEX ships_system ON core.ships (system_id) WHERE destroyed_on IS NULL;

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
| `0001_core_identity` | P0 | accounts, players, teams, factions, world_state, commands |
| `0002_world_tree` | P1 | locations, ltree extension, indexes |
| `0003_ap_and_time` | P1 | ap_ledger, tick_runs, tick_stages |
| `0004_event_spine` | P2 | events (partitioned), deliveries, outbox, first partitions |
| `0005_fleet` | P3 | ships, cargo, standing_orders, journeys |
| `0006_economy` | P3 | markets |
| `0007_conflict` | P3 | encounter_queue, territory, player_discoveries |

A partition-creation job runs monthly ahead of need; the MVP pre-creates twelve partitions so a forgotten job cannot
stop the tick.

---

# 5. Application layer

## 5.1 Ports

```python
class ClockPort(Protocol):
    def now(self) -> datetime: ...
    def world_day(self) -> int: ...

class RngPort(Protocol):
    def for_(self, *parts: str | int) -> random.Random: ...

class EventBusPort(Protocol):
    def emit(self, event: Event) -> None: ...

class PlayerRepo(Protocol):
    async def get_for_update(self, player_id: UUID) -> PlayerAggregate: ...
    async def save(self, aggregate: PlayerAggregate) -> None: ...
```

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
{"action": "move", "to": "g0_0/r1_0/s4_2/b12_7", "idempotency_key": "..."}
```

| Order | Precondition | Rejection |
| --- | --- | --- |
| 1 | ship not in transit | `IN_TRANSIT` |
| 2 | ship not docked | `MUST_LAUNCH_FIRST` |
| 3 | `to` is in the same system as the ship | `SCALE_MISMATCH` |
| 4 | `distance(from, to) == 1` | `NOT_ADJACENT` |
| 5 | `ap_balance >= ap_cost` | `INSUFFICIENT_AP` |
| 6 | `fuel >= fuel_cost` | `INSUFFICIENT_FUEL` |

Effects: position updated, fuel debited, AP debited. Events: `PLAYER_ENTERED` (LOCAL, PUBLIC).

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
Events: none at departure beyond the participants' `COMMAND_ACCEPTED`; `JOURNEY_COMPLETED` and `PLAYER_ENTERED` fire
at stage 1 (criterion A4).

### `scan`

Preconditions: not in transit; AP ≥ cost. Effects: computes contacts (§5.5), inserts `player_discoveries` rows for
newly seen locations, sets `locations.discovered_on/by` where still null. Events: `SCAN_PERFORMED` (PARTICIPANTS),
plus one `DISCOVERY` (SYSTEM, PUBLIC) per location first identified by this player.

### `dock` / `launch`

Free (0 AP). `dock` requires a station at the ship's exact hex and the ship not in transit. `launch` requires
`docked_at IS NOT NULL`. Docking is a state, not a sub-map: the MVP has no Body-level hex movement `[D-1]`.

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
`LOCAL`, `BODY` and `SYSTEM` events are queried on read by path prefix. `UNIVERSE` exists but nothing in the MVP
emits it.

---

# 6. The daily tick

## 6.1 Runner

```python
MVP_STAGES: Final = (
    SettleTravel(),          # ARCH stage 1
    ResolveEncounters(),     # ARCH stage 2
    EconomyStep(),           # ARCH stage 3
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
    emit PLAYER_ENTERED    (local, public)
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
resulting price moves more than a threshold `[BALANCE]`, a `MARKET_SHIFT` event is emitted at BODY scope so that
traders in the system learn about it without a scripted news system (*GDD §5.3*).

## 6.5 Stage 5 — Territory

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

## 6.6 Stage 11 — Grant Action Points

```text
for player in active players where last_grant_day < world_day:
    carry  = min(ap_balance, carry_over_max)            # MVP: carry_over_max = 0
    grant  = daily_grant + carry - ap_balance
    insert ap_ledger(delta=grant, reason='daily_grant')
    ap_balance    := daily_grant + carry
    last_grant_day := world_day
    emit AP_GRANTED (participants)
```

The `last_grant_day` guard makes the stage idempotent. It runs after encounters and the economy so that a player
logging in immediately after the tick acts against a fully simulated world (*GDD §3.3*).

## 6.7 Stages 12–13 — Projections and digests

Stage 12 rebuilds map tiles for every path prefix touched by the day's events and bumps their cache version. Stage 13
composes each player's daily overview from their `event_deliveries` plus scoped events and stores it as the
`player_dashboard` read model; email delivery is a P4 concern, but the dashboard content is MVP (*GDD §3.4*).

## 6.8 Determinism

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
| System hex map radius | 8 (169 hexes) |
| Bodies per system | 3–8 |
| Stations per system | 1–3 |
| Commodities | 8 |
| Faction home systems | 1 per faction |

```text
1. Create the galaxy root and 4 region hexes.
2. For each region, place systems on distinct galaxy-child hexes via Poisson-disc sampling.
3. For each system, place a star at (0,0) and bodies on rings 2..8 with decreasing density.
4. Designate stations: faction homes first, then one station per 2 bodies, biased toward the inner rings.
5. Assign each station a type; seed its market from the type's production and consumption profile.
6. Seed territory: home systems at influence 1.0 for their faction, all others at 0.
7. Mark faction home systems and their immediate neighbours discovered; everything else undiscovered.
```

Every step draws from `Rng.for_("worldgen", step, index)`, so a seed reproduces a world exactly — which is what makes
the simulation soak test (§14.5) meaningful.

Sizing check: 48 systems × 169 hexes = 8 112 addressable system hexes and roughly 250 bodies. Small enough to
generate in seconds and to inspect by hand, large enough that map streaming (§9.1) is genuinely exercised rather
than accidentally satisfied.

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
| `GET` | `/v1/systems/{id}` | System detail: bodies, stations, visible contacts |
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
| System tile | Bodies, stations, contacts within sensor range, the viewer's ship |

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

# 10. NPCs in the MVP

The world must not feel empty on day one, and combat needs a live opponent. The MVP ships the smallest NPC set that
achieves both `[D-6]`.

| NPC | Behaviour | Purpose |
| --- | --- | --- |
| **Hauler** | Flies a fixed loop between two stations, carrying cargo | Makes systems look inhabited; a legitimate pirate target |
| **Patrol** | Sits in a faction-controlled system, engages pirates on sight | Makes faction territory mean something |
| **Raider** | Sits in a low-control system, engages ships carrying cargo | Gives traders a reason to fit a weapon |

NPC ships live in `core.ships` with a null `player_id` — the same table, the same combat resolver, the same events.
NPC movement is not a tick stage in the MVP (stage 4 is deferred); haulers advance one hop per cycle inside stage 1,
which is a deliberate stopgap noted here so it is removed rather than forgotten when stage 4 arrives.

---

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

## 14.5 Simulation soak

A seeded world runs 90 cycles headless with scripted cohorts (30 traders, 10 pirates, 10 explorers). Assertions:

- No faction exceeds 80 % territory before cycle 60.
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
| 3.8 | Territory, stage 5 (§6.5) | Control changes after sustained presence, not instantly |
| 3.9 | NPCs: hauler, patrol, raider (§10) | A generated world has visible traffic on day 1 |
| 3.10 | Map tiles, dashboard, ETags (§9) | A11 |
| 3.11 | Simulation soak in CI nightly (§14.5) | A12 |

**Critical path:** 0.6 → 1.1 → 1.3 → 1.6 → 2.3 → 3.2 → 3.6. Everything else can proceed in parallel once its
dependency lands. The riskiest item is 2.3: visibility touches every later feature, and retrofitting it is the one
mistake in this plan that would cost a rewrite.

---

# 16. Decisions taken in this document

| ID | Decision | Rationale | Reversible? |
| --- | --- | --- | --- |
| D-1 | The MVP addresses four levels (Galaxy, Region, System, Body); District and Local are generated by nothing and used by nothing. Docking is a state, not a sub-map. | Surface gameplay has no MVP content; generating empty levels invites accidental dependencies. | Yes — `Level` already carries all six |
| D-2 | No pathfinding. Route cost is `distance × ap_per_hex`. | In-system space is uniform in the MVP; A* arrives with hazards. | Yes |
| D-3 | Contact search narrows by system in SQL and filters by hex distance in Python. | GiST cannot express hex range; a system holds hundreds of ships, not millions. | Yes |
| D-4 | Player-versus-player encounters always resolve at tick stage 2, never live — even when both players are online. | One code path for offline and online defence, so they can never diverge (*GDD §3.5*). | Yes, but only by accepting two paths |
| D-5 | Public API responses are explicit allowlists from the first commit, not ORM dumps. | The MVP has no secrets to leak, but the discipline is what prevents leaking later (*ARCH §12.1*). | No — this is a standing rule |
| D-6 | Three NPC archetypes, sharing `core.ships` and the player combat resolver. | The world must not be empty and combat needs an opponent, without building faction AI. | Yes |
| D-7 | Haulers advance inside stage 1 until tick stage 4 exists. | A stopgap, recorded so it is removed rather than inherited. | Yes — delete on stage 4 |
| D-8 | One `POST /v1/commands` endpoint with a discriminated union, plus a batch variant. | Locking, idempotency and ledger writes exist once. | Yes |
| D-9 | Prices are computed inside the transaction from current stock; a client-sent price is ignored, not validated. | Validating a client price implies the client has one (*GDD* C1). | No |
| D-10 | The `psycho` and `cont` schemas are not created in the MVP. | An empty schema for an unbuilt feature attracts content. | Yes |

---

# 17. Open questions

Blocking, with the MVP's working assumption. The first three are *GDD §11.2* questions reaching implementation.

| # | Question | MVP assumption | Blocks |
| --- | --- | --- | --- |
| Q1 | Is the six-level ladder final, and are Body/District the accepted names? | Yes; four levels used (D-1) | Task 1.4, address encoding |
| Q3 | May a player operate more than one ship? | No — `ships.player_id` is unique | Task 3.1; relaxing it later is a migration, not a redesign |
| Q6 | Is unspent AP carried over? | No — `carry_over_max = 0` | Stage 11 |
| S1 | What does a destroyed player lose? | Respawn at faction home, base hull, empty cargo, credit penalty `[BALANCE]` | Task 3.5 |
| S2 | Can a player exist without a team? | No — registration requires creating or joining one | Task 3.7, faction denormalisation |
| S3 | Is jump range limited by fuel alone, or also by a maximum per jump? | Fuel alone in the MVP | Task 3.2 |
| S4 | Starting endowment: ship class, credits, fuel? | One light freighter, 5 000 cr, full tank `[BALANCE]` | Task 3.1 |

S1–S4 are design questions that surfaced during detailed design; they belong in *GDD §11.2* once answered.

---

# 18. Traceability

| MVP requirement (*GDD §10.1*) | Designed in | Verified by |
| --- | --- | --- |
| Hierarchical hex map, galaxy, systems, zoom | §3.1, §3.2, §4.2, §7, §9.1 | A11, property tests |
| Basic faction territories | §6.5 | Tick tests, soak |
| Account, credits, AP, location, reputation | §3.3, §4.2, §6.6 | A1, A2, A3 |
| Standing orders | §3.3, §5.4 | A6 |
| Ship: hull, shields, fuel, cargo, weapon, equipment | §3.3, §4.2 | A1, A5 |
| Hex movement, AP and fuel consumption | §5.4, §3.4 | A2 |
| Journeys across cycle boundaries | §5.4, §6.2 | A4 |
| Buy, sell, cargo, station markets | §5.4, §6.4 | A5 |
| Scan, discovery, basic events | §5.4, §5.5 | A9 |
| NPC and player encounters, simplified combat | §6.3, §10 | A6, A10 |
| Offline resolution | §5.4 (D-4), §6.3 | A6 |
| Teams, three factions, team chat, local communication (*GDD §7.3*) | §5.4, §8.3 | A1 |
| Local/Body/System/Universe events, unified feed | §3.5, §5.5, §9.3 | A9 |
| Cycle steps 1–3, 5, 11, 12 | §6 | A4, A10, A12 |
| Design constraints C1–C10 (*GDD §10.4*) | C1 §5.2/§8.1 · C2 §6.1 · C3 §3.5 · C4 §5.5 · C5 §9.1 · C6 §6.3/§6.8 · C7 §3.4 · C8, C9 not applicable (D-10) · C10 not applicable | A3, A9, A10 |

---

*End of document.*
