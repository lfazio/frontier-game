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

**P2 — Event spine.** Every state change emits an event; one merged feed carries chat and world
events, redacted per viewer by a single `render_for`. A transactional outbox relays committed
events to Redis and out over a WebSocket. Next is P3, MVP gameplay.

## Running it

```sh
make install        # uv sync
make up             # postgres + redis
make migrate
make world       # generate a galaxy
make check          # lint, types, import boundaries, tests
make demo           # watch a player spend a day's AP
make tick           # advance the world one cycle
make relay          # publish committed events to Redis
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
