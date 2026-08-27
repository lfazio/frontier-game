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

**P5 — History.** A psychohistorical model watches the world through aggregate views it cannot
see individuals through — the reader role holds no privilege on player tables at all — and
publishes probabilistic forecasts. Anyone may read one; Knowledge buys resolution, never access.
It ships dark behind `FEATURES_PSYCHOHISTORY` until the world is old enough to tune it. Next is
P6, the Continuity.

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
uv run uvicorn frontier.adapters.api.app:app --reload
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
