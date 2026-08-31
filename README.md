# Frontier: The Seldon Era

A persistent, browser-based multiplayer space strategy game. One world cycle every 24 hours; players
spend a limited Action Point budget and log out.

## Documents

| Document | Authority |
| --- | --- |
| [`Documentations/game-design.md`](Documentations/game-design.md) | What the game does. Normative for behaviour. |
| [`Documentations/architecture.md`](Documentations/architecture.md) | How the system is structured. |
| [`Documentations/detailed-design-mvp.md`](Documentations/detailed-design-mvp.md) | How the MVP is built (phases P0–P3). |

## Status

**P6 — The Continuity.** A hidden fourth faction, NPC-operated, that reads the world's deviation
and leans on population flows to correct it. Its secrecy is structural rather than careful: it
lives in its own schema, nothing imports it, the public API connects as a role with no grant on
that schema, and its own role cannot write to a player's ship or credits at all. `make antileak`
is a merge gate.

Both the historical model and the Continuity ship dark, behind `FEATURES_PSYCHOHISTORY` and
`FEATURES_CONTINUITY`.

## Playing

Sign in at the client and you get the shell: a permanent Action Point counter, the daily
overview built from the server's digest, and the map at three magnifications — galaxy and
region from tiles, and your own system as a top-down board bounded by what your sensors reach.

From there you can fly. Click a hex inside the sight boundary and the client plots a route with
the server's own hex-line rule, prices the whole journey from `GET /v1/rules`, and submits it as
one batch: a journey is one decision, even though the server still charges every hop. If the
Action Points run out partway the answer says so and names where the ship actually is — that is
a result, not an error. Jump between systems from the region chart, and scan, dock and launch
from the system view. Refusals are written as answers: what is true, then what would help.

Docking opens the station: a market with both sides of the spread on screen, what you hold and
what you paid for it, and a quantity you can step, type or fill to the largest amount your
credits, the hold and the station's stock all allow. Repair is quoted before it is bought.

The feed is one stream filtered by channel — local, system, crew — arriving live over a
WebSocket and merged with the fetched page on event id, so nothing appears twice. You can speak
on it, take work from the mission board, and found or join a crew.

A ship you can see clearly and reach can be fired on from the map; a fight between two players
is queued and resolved for both at the turn of the cycle, so neither is punished for being the
one who was asleep. Standing orders decide what your ship does while you are away, and the
screen opens with what is already set rather than a blank form.

## Watching a world

The quickest way to see the game is watch mode — a spectator view of a real server, no account
needed. It is deliberately weaker than any player's view: the star chart, who holds it, and
events that already carry across a whole system.

```sh
make up && make migrate
make demo      # a world with eight pilots and fifty cycles of history
make serve     # API on :8000
make client    # browser client on :5173
```

## Operating a world

The console is a **separate application on its own port**, not a privileged corner of the game.
An operator account is not a player account: different tables, different tokens, and a token
minted for one is refused by the other even if both are given the same secret.

```sh
make ancients     # the world's first operator — nobody grants this one
make console      # the console on :8001
```

Seven screens: whether the world is turning and what last night's tick did, the crises counting
down toward an incursion, any pilot's record, the balance dials, who may run the world, and —
behind its own permission — the hidden faction. Nothing on it can change the world: the balance
screen drafts a new ruleset version on a branch rather than editing the live one, and the
console's only write into a world is asking for a failed tick to be retried.

Permission spreads only by grant, from that first account outward, and the console can always
say who let someone in. The original operator cannot be revoked: a world with no operator is a
world nobody can rescue.

## Running it

```sh
make install        # uv sync
make up             # postgres + redis
make migrate
make world       # generate a galaxy
make check          # lint, types, import boundaries, tests
make tick           # advance the world one cycle
make relay          # publish committed events to Redis
make soak           # 60-cycle simulation, nightly rather than per-commit

# The historical model ships dark; enable it with FEATURES_PSYCHOHISTORY=true.
make serve
```

`make check` is the gate: `ruff`, `mypy --strict` over `domain` and `application`, `import-linter`
contracts, and the test suite. Integration tests (`make test-int`) need the database from `make up`.

## Layout

```text
src/frontier/
  domain/       pure rules — no I/O, no framework imports
  application/  use cases, ports, the command template
  adapters/     FastAPI, SQLAlchemy, in-memory, clock and RNG
  worldgen/     world description
  config/       settings and the composition root
data/rulesets/  balance values, versioned; never in code
```

The layering is enforced by `import-linter`, not by review: a domain module importing `sqlalchemy`
fails CI.
