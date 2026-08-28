# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

This repository currently contains **no source code** — only two documents in `Documentations/`. There is no build,
lint, test, or run command yet. Do not invent one; if a task needs tooling, scaffold it per the architecture document
and say so.

| Document | Authority |
| --- | --- |
| `Documentations/game-design.md` (v2.9) | **What the game does.** Normative for behaviour. Cited as `§n.m`. |
| `Documentations/architecture.md` (v0.8) | **How it is built.** Normative for structure. Cited as `ARCH §n`. |
| `Documentations/detailed-design-mvp.md` (v0.15) | **How the MVP is built.** Module, schema, API and algorithm
detail. Cited as `SDD §n`. |
| `Documentations/ui-ux-mvp.md` (v0.5) | **What the player sees and touches.** Screens, states, wording and
interaction contracts. Cited as `UX §n`. |

Where they disagree, the design document wins on behaviour and the architecture document wins on implementation —
and one of them needs amending. Neither is aspirational notes: read the relevant sections before implementing.

## Stack

Python 3.12+ server (FastAPI, SQLAlchemy 2.0 async, PostgreSQL 16, Redis, arq), React/TypeScript browser client.
Rationale and rejected alternatives are in `ARCH §4`; the enforced package layout is `ARCH §16`.

## Where to look

| Topic | Design | Architecture |
| --- | --- | --- |
| Cycle/AP model, session targets | §1.2, §3.1–§3.2, §5.6 | §7.3, §9 |
| Hierarchical hex world, addresses | §2 | §7.1, §10.2 |
| Player, ships, actions, combat, economy | §4, §5 | §6 |
| Factions, teams, territory | §6 | §6 |
| NPC population and simulation fidelity | §2.7 | §6 (Population), §9.2 stage 4 · SDD §6.5, §10 |
| Communication, visibility, event model | §7 | §7.2, §7.4, §10.5 |
| Psychohistory and history | §8 | §12.1, ADR-12 |
| The Continuity (hidden faction) | §9 | §12.1, §13.3, ADR-13 |
| MVP scope / deferred systems | §10.1, §10.2 | §17, §18 |
| MVP tables, endpoints, commands, tick stages | — | SDD §4, §5, §6, §8 |
| MVP task breakdown and acceptance criteria | — | SDD §1.2, §15 |
| Design constraints on implementation | §10.4 (C1–C10) | throughout |
| Open design questions | §11.2 (Q1–Q8) | §20 |

Section numbers changed in design v2.0; `§11.3` maps the old flat numbering (v1.0 §1–§75) to the new one.

## Invariants

These cut across many sections and constrain nearly every feature. The design document states them as C1–C10 (§10.4);
the short form:

- **One world, many zoom levels.** Galaxy → Region → System → Planet → Sector → Local is one hierarchical hex world,
  not separate maps or game modes. An object holds a coordinate at every level; containment is prefix matching;
  distance is only meaningful between siblings under the same parent.
- **The server is authoritative; the browser is untrusted.** The client submits intents, never outcomes. The server
  owns AP, credits, position, damage, cargo, combat results and ship state.
- **Everything is an event.** Chat, combat, discovery and economy changes share one model and one spine that feeds
  chat, missions, economy, factions, history and statistics. Add gameplay by emitting events, not by wiring
  subsystems to each other.
- **Time is a 24-hour cycle with an AP budget.** Costs are balance data, never literals in code. Any action must fit
  the format; combat resolves in a few decisions.
- **Every interaction has an offline path.** Absent players are resolved from their standing orders under identical
  rules.
- **Information is scoped and redacted server-side.** Never send a client a field it is meant not to show.
- **Prediction is statistical, never individual.** The model may never name a player. The hidden faction may push,
  nudge, delay, accelerate, hide and reveal — never force.
- **The Continuity's confidentiality protocol is fiction**, never a real-world legal agreement, and membership must
  not be inferable from any response, error code, timing difference, statistic or ledger entry.
- **Original IP only.** *Frontier: Elite II* and *Foundation* are inspirations; reproduce nothing from either.

## Working conventions

- Design text marked `[BALANCE]` is a tunable value: it belongs in versioned rule data (`data/rulesets/`), not in
  code. `[ILLUSTRATIVE]` blocks are examples, not specifications.
- MUST/SHOULD/MAY in the design document carry their normative meaning (§0.2). Changing a MUST is a design decision,
  recorded in §11.1.
- `ARCH §18` lists the seam for each deferred system. New gameplay should arrive as a command, a rule, a tick stage
  or an event subscriber; if a feature fits none of those, revisit the architecture rather than special-casing it.
- Comments explain only what the code cannot: a non-obvious invariant, a rationale, the shape of a value, a
  design reference. Explicit code gets no comment — never restate a name in prose.
- Terminology: **cycle** (24 h period), **world day** (counter), **Planet** (the level, and any
  planet/moon/station/asteroid on it), **Sector** (area of a planet). Do not reintroduce "turn", "body" or
  "planetary region".

## Scope discipline

§10.1 defines the MVP and §10.2 lists deliberately deferred systems. When a task touches a §10.2 system, confirm it
is wanted now rather than pulling post-MVP scope forward. Psychohistory (§8) and the Continuity (§9) ship last by
design decision, not by accident (§10.3).
