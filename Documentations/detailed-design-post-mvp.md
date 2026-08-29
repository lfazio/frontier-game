# Software Detailed Design — Post-MVP

## *Frontier: The Seldon Era*, delivery phases P5 to P7+

| Field | Value |
| --- | --- |
| Status | Draft for review |
| Version | 0.1 |
| Date | 2026-08-29 |
| Scope | Delivery phases **P5, P6, P7 and P7+** (*ARCH §17*), and the deferred systems of *GDD §10.2* |
| Depends on | `game-design.md` v2.9, `architecture.md` v0.8, `detailed-design-mvp.md` v0.20 |
| Audience | Server engineers, client engineers, anyone reviewing the systems that ship after the MVP |

### How to read this document

`detailed-design-mvp.md` is normative for everything already built. This document is normative for what comes next,
and it does not restate the MVP: the module layout, the command contract, the event spine, the tick harness, the
role boundaries and the anti-leak suite are all as that document describes them, and every design here is built out
of those four shapes and no others — **a command, a rule, a tick stage, or an event subscriber** (*ARCH §18*).

The decision log continues the project's single `D-n` series, resuming at **D-71**; a citation of `D-52` still means
the MVP document. Acceptance criteria use a fresh **`B-n`** series, because the MVP's `A1`–`A15` are still live.

MUST / SHOULD / MAY carry their normative meaning (*GDD §0.2*).

---

# 1. Where the project actually stands

Phases are not a plan for greenfield code. Two of them are already partly built and shipping dark, and being precise
about what exists is the difference between "finish it" and "write it".

| Phase | State | Evidence in the tree |
| --- | --- | --- |
| **P0–P4** | Built | `frontier/` server, tick stages 1–7 and 9–13, 132 integration tests |
| **C0–C6** | Built | `client/` — the whole MVP client, *UX §11* |
| **P5 — History** | **Partly built** | `simulation/stages/psychohistory.py` runs as stage 7; `psycho.history_variables`, `psycho.forecasts`, four region views; `GET /v1/forecasts`; the `psycho_reader` role |
| **P6 — The Continuity** | **Partly built, not running** | `frontier/continuity/` with `stage.py` declaring `role = "cont_role"`; `cont.agents`, `cont.cells`, `cont.budget`, `cont.interventions`; the anti-leak suite. **Stage 8 is absent from `TICK_STAGES`**, so the faction does not act |
| **P7 — Clearance and recruitment** | Not built | — |
| **P7+ — The Harrowing** | Not built | — |

Two consequences follow, and they shape everything below.

**The Continuity is inert, not missing.** Its schema, its role boundary and its import contract all exist and are
enforced today; `lint-imports` forbids anything importing `frontier.continuity`, and `cont_role` has no grant to
write `players`, `ships` or `cargo`. Turning the faction on is registering one stage behind one flag — which is
exactly the shape ADR-13 intended, and the reason the work is small.

**Psychohistory has a reader, not yet a subject.** The model records region variables and emits forecasts. What it
does not yet have is the in-world institution that sells them (*GDD §8.8*), the knowledge economy that values them
(*§8.9*), or the crises that make them matter (*§8.10*) — and the Harrowing depends on that last one.

---

# 2. P5 — History

**Goal.** The world remembers, the model predicts, and prediction becomes something players can buy, sell and act on.

## 2.1 What the model may say

One invariant governs this entire phase, and it is not a guideline:

> **Prediction is statistical, never individual.** The model may never name a player (*GDD §10.4 C7*).

It is enforced structurally, not by review. `psycho_reader` has **no grant** on `core` or `evt`; the psychohistory
stage reads the four aggregate views and nothing else. A forecast names a *region*, a *variable* and a *band* — never
an actor. `B4` and the existing anti-leak probes hold this.

## 2.2 Crises and eras

A **crisis** is a sustained deviation of a region variable beyond a threshold, detected in stage 7 rather than by a
new stage: the stage already computes the deviation it would need.

```text
history_variables ──▶ deviation ──▶ sustained beyond floor for N cycles ──▶ crisis opened
                                                                              │
                                       resolved by play ◀── crisis window ────┤
                                                                              │
                                    expired unresolved ──▶ the Harrowing (§5) ┘
```

New tables:

| Table | Holds |
| --- | --- |
| `psycho.crises` | `id`, `region_id`, `variable`, `opened_on`, `expires_on`, `resolved_on`, `severity`, `magnitude` |
| `psycho.eras` | `id`, `name`, `began_on`, `ended_on`, `summary` — a named stretch of world days, closed when a crisis of `severity >= era_threshold` resolves |

An era is a *reading* of history, so it is written by the chronicle stage (10), which already owns narrative
promotion, rather than by the model. The model measures; the chronicle names.

## 2.3 The Historical Institute

The Institute (*GDD §8.8*) is an in-world buyer and seller of knowledge. It is **not** a new subsystem: it is a
station kind with a market whose commodity is `knowledge`.

- `data/rulesets/*/economy.toml` gains `knowledge` to `[commodities]` and an `institute` entry to `[station_type]`.
- Buying a forecast is `buy` against that market. Selling a discovery is `sell`.
- Knowledge carries a **non-transferable-by-default** flag (*ARCH §18*): a unit bought at the Institute may be read
  by its buyer and resold only to the Institute, not to another player, until knowledge trading (§6) ships.

This is the whole of `D-71`: the Institute reuses the market machinery rather than adding a parallel one.

## 2.4 Endpoints

| Method | Path | Answers |
| --- | --- | --- |
| `GET` | `/v1/forecasts` | *(built)* Region forecasts the player may see |
| `GET` | `/v1/history/eras` | The named eras, newest first |
| `GET` | `/v1/history/crises` | Open crises in regions the player has charted |

A crisis is public — it is a visible condition of a region, not intelligence — but it is **scoped to charted
regions**, so the crisis list is not a way to learn the shape of the galaxy without flying it.

---

# 3. P6 — The Continuity, as an AI

**Goal.** The hidden faction acts on the world before any player can join it, so that the evidence players later
find is real history rather than something retrofitted (*ARCH §17*, ADR-13).

## 3.1 Turning it on

The work is deliberately small:

1. Register the stage as **stage 8**, between missions (6/7) and event promotion (9), guarded by
   `features.continuity` so it is inert unless enabled.
2. The runner already applies `SET LOCAL ROLE` for a stage that declares one, so the stage runs as `cont_role`
   with no further wiring.
3. Extend the anti-leak suite before enabling it anywhere (§3.4).

## 3.2 What an intervention may do

Six verbs, and the sixth is the one that matters most:

| Verb | Effect | Never |
| --- | --- | --- |
| `push` | Raise a region's activity toward a target | Set it |
| `nudge` | Bias a price, a flow or a spawn weight | Fix an outcome |
| `delay` | Postpone a scheduled effect by whole cycles | Cancel it |
| `accelerate` | Bring one forward | Skip it |
| `hide` | Suppress promotion of an event to a wider scope | Delete it |
| `reveal` | Promote one earlier than it would have gone | Fabricate it |

> **The Continuity may push, nudge, delay, accelerate, hide and reveal — never force** (*GDD §10.4 C7*).

Concretely: an intervention writes to `system_activity` and to promotion decisions. It **MUST NOT** write
`players`, `ships`, `cargo`, `credits` or combat outcomes, and `cont_role` holds no grant that would let it.
The database is the enforcement; the table above is the explanation.

## 3.3 Budget

Effort is bounded by the size of the world, never by the number of players (*GDD Q4*) — a bigger galaxy does not
slip the Continuity's grip, and a popular one does not tighten it. The values are rule data
(`continuity.toml`, already present):

| Key | Meaning |
| --- | --- |
| `systems_per_intervention` | One intervention per N systems per cycle |
| `systems_per_agent` | One agent per N systems |
| `max_magnitude` | The largest deviation a single intervention may introduce |
| `deviation_floor` | Below this, the model is left alone: the faction acts on drift, not on noise |

## 3.4 The anti-leak obligation

This phase adds probes to `tests/antileak/`, and they are a merge gate exactly as the existing nine are.

> Membership **MUST NOT** be inferable from any response, error code, timing difference, statistic or ledger entry
> (*GDD §10.4 C9*).

| Probe | Asserts |
| --- | --- |
| `B7` | An intervened system's public projection is byte-identical in shape to an unintervened one |
| `B8` | `api_role` querying every player-facing endpoint never touches `cont` — verified by grants, not by inspection |
| `B9` | An agent's command latency distribution is indistinguishable from an ordinary pilot's |
| `B10` | No ledger entry, digest or chronicle line names an intervention |

`B9` deserves a note: a timing difference is a side channel, so an agent's extra work **MUST** happen in the tick,
never in the request path. That is why interventions are a stage and not a command.

## 3.5 The confidentiality protocol is fiction

The in-world secrecy of the Continuity is **narrative**, never a real-world legal agreement, and no text shipped in
the product may imply otherwise (*GDD §10.4 C9*). This applies to recruitment copy, refusal wording and any
in-fiction document.

---

# 4. P7 — Recruitment, clearance and the channel

## 4.1 Recruitment

An offer arrives as an ordinary mission. It is distinguishable from one only *after* acceptance, and declining
leaves no trace anywhere a player or an observer can read.

```text
mission board ──▶ an offer like any other ──▶ accepted ──▶ clearance granted
                              │
                              └─ declined ──▶ nothing written, nothing remembered
```

Rules:

- A declined offer **MUST NOT** write a row, an event, or a digest line. "Nothing remembered" is literal.
- Eligibility is evaluated from the player's own record only (*GDD Q10*): re-recruitment after a loss is possible,
  but never automatic, and it evaluates the new pilot's record on its own terms.

## 4.2 Permanent loss and the new pilot

An agent who dies in the Harrowing returns as a fresh pilot (*GDD §9.14*, Q9). The seam is stated in `ARCH §18` and
is worth repeating because it is the sharpest constraint in the project:

> **No column may link a new pilot to a former agent.** Re-recruitment evaluates the new pilot's own record, so the
> link is not merely forbidden but unnecessary.

`players` gains a `generation`; a reset writes a new pilot row rather than mutating the old. The Chronicle already
records a death and **MUST NOT** distinguish this one.

## 4.3 The channel

The Continuity's channel is instantaneous across the whole world (*GDD §9.6*). It needs no relay and no range
calculation, because it is expressed entirely in the existing event model:

| Field | Value |
| --- | --- |
| `visibility` | `CLEARANCE` |
| `scope` | `UNIVERSE` |
| `deliver_at` | `occurred_at` |

When communication delay ships (§6), `features.comms_delay` will apply to every channel *except* this one — it is
exempt by construction, not by a special case in the delay code.

## 4.4 The watch

The spectator projection built for *UX §9* becomes the Continuity's watch, gated by a **faction-wide** rate limit in
Redis rather than a per-player one (*GDD §9.6*, U1: one watch per X hours for the whole faction). It reads only, so
it emits no event and touches no write path — which is also why it cannot leak membership through a write.

---

# 5. P7+ — The Harrowing

**Goal.** A historical crisis that expires unresolved brings an invasion of powerful alien starships, and players
must fight together to restore the balance (*GDD §8.12*).

## 5.1 It needs no new mechanism

An incursion ship is a ship. It has hulls, it holds a position, it spends Action Points, and it is resolved by the
encounter code that already exists. What is new is a fourth NPC archetype and the stage that spawns it.

| Piece | Shape |
| --- | --- |
| Spawning | A tick stage watching **crisis expiry** (§2.2), not system activity |
| The opponent | A fourth entry in `NPC_SHIP`, with its own hulls and weapons |
| Where it arrives | The empty space between systems — an address that exists precisely because a region is filled space (`D-68`) |
| Resolution | `encounter.resolve()` already takes participant *sets*; the MVP restricts cardinality to 1v1 **by rule, not by code**, so fleet battles are a rule change |

## 5.2 Why it comes last

It requires an opponent that scales past a single player, so it follows fleet battles; and it is the payoff of the
history layer, so it follows P5. Both dependencies are real, and neither is negotiable by reordering.

The Continuity goes first into the fighting and has the most to lose: a death there returns an agent to a fresh
pilot (*GDD* Q9). This is a design decision about stakes, not a mechanical exception — the loss uses the same path
as §4.2.

---

# 6. Deferred systems (*GDD §10.2*)

Each has a seam in `ARCH §18`. None requires reopening the foundations, and the table is here so that "is this in
scope?" has an answer that does not require reading three documents.

| System | Shape it arrives in | Notes |
| --- | --- | --- |
| Advanced ship fitting | Rule data + ship columns | |
| Mining, smuggling | New `Command` classes + `RuleSet` entries | No new infrastructure |
| Bounty system | Event subscriber on `SHIP_DESTROYED` + a `polity` ledger | |
| Player-owned stations, colonisation | New `locations.kind` values with owner attribution | The tree already supports them |
| Communication relays and delay | `comms` already computes `deliver_at`; the MVP sets delay to zero | The Continuity channel is exempt (§4.3) |
| Advanced economy, dynamic faction wars | Stage 4's second half, plus a replacement stage-3 behind the `Stage` protocol | |
| Named, persistent NPCs | A `persistent` flag on `npc_agents` | Nothing else |
| Player-created missions | A second `MissionProvider` | |
| Fleet battles | A rule change; resolution already takes sets | Prerequisite for §5 |
| Advanced exploration | New commands + rule data | |
| Knowledge trading | Clearing the non-transferable flag of §2.3 | |
| Procedural historical events | A generator subscribing to the promotion stage | |

---

# 7. Cross-cutting obligations

These apply to every phase above, and a change that breaks one is a design decision, not a bug fix.

- **Feature flags.** `FEATURES_PSYCHOHISTORY`, `FEATURES_CONTINUITY` and `FEATURES_WATCH` let this code ship dark.
  A flag guards *behaviour*, never the schema: tables and roles exist from P1 so that enabling a flag is not a
  migration.
- **Role boundaries.** `api_role`, `cont_role` and `psycho_reader` are the enforcement of §2.1 and §3.2. A new
  capability is a **grant**, and the anti-leak suite asserts the grants rather than trusting the code.
- **Every interaction keeps an offline path.** An absent player is resolved from their standing orders under
  identical rules — including in an incursion.
- **Information stays scoped and redacted server-side.** A client is never sent a field it is meant not to show;
  the sensor ladder (`D-51`) and the channel stamp (`D-62`) are the two shared definitions that keep this true.
- **Original IP only.** *Frontier: Elite II* and *Foundation* are inspirations; reproduce nothing from either.

---

# 8. Acceptance criteria

| # | Criterion |
| --- | --- |
| **B1** | A sustained region deviation opens a crisis, and the crisis appears in `GET /v1/history/crises` for a player who has charted that region — and not for one who has not |
| **B2** | A crisis that is resolved by play closes; one that is not expires, and expiry is what the incursion stage watches |
| **B3** | An era is named by the chronicle stage, never by the model |
| **B4** | No forecast, crisis or era row contains a player id, callsign or ship id — asserted over the whole schema, not sampled |
| **B5** | With `FEATURES_CONTINUITY` off, stage 8 does not run and `cont` is untouched by a tick |
| **B6** | With it on, a tick performs at most `ceil(systems / systems_per_intervention)` interventions, none exceeding `max_magnitude` |
| **B7** | An intervened system's public projection is indistinguishable in shape from an unintervened one |
| **B8** | `api_role` holds no grant on `cont`; asserted from the catalogue, not from code inspection |
| **B9** | Command latency for an agent is statistically indistinguishable from an ordinary pilot's |
| **B10** | No ledger entry, digest, chronicle line or event payload names an intervention |
| **B11** | A declined recruitment offer writes no row and emits no event |
| **B12** | A reset agent's new pilot has no stored reference to the former one; a search of the schema for such a link finds nothing |
| **B13** | A Continuity channel message is delivered with `deliver_at == occurred_at` at `UNIVERSE` scope, and is invisible to every player without clearance |
| **B14** | The watch is rate-limited per faction, not per player |
| **B15** | An expired crisis spawns an incursion in the empty space of the affected region, and the incursion ships spend Action Points under the same rules as any crew |
| **B16** | An absent player in an incursion is resolved from their standing orders |

---

# 9. Decisions

| # | Decision | Why | Schema? |
| --- | --- | --- | --- |
| D-71 | The Historical Institute is a station kind with a market whose commodity is `knowledge`, not a new subsystem. | Buying a forecast and buying grain are the same transaction with different goods; a parallel mechanism would duplicate pricing, cargo and refusal handling for no gain. | Yes |
| D-72 | Crisis detection lives inside stage 7 rather than in a stage of its own. | The stage already computes the deviation a crisis is defined by. A separate stage would either recompute it or read the first stage's output, and both are worse than one pass. | Yes |
| D-73 | Eras are written by the chronicle stage, not by the model. | The model measures; naming a stretch of history is a narrative act, and the chronicle already owns promotion and retention. It also keeps the model's output free of prose. | Yes |
| D-74 | The Continuity ships as an unregistered stage first: the code, schema, role and import contract exist before the faction acts. | It makes enabling the faction a one-line change under a flag, and it means the anti-leak suite can be written and run against real code before anything is at stake. | No |
| D-75 | An intervention's effect is bounded by rule data (`max_magnitude`, `deviation_floor`) and its permissions by database grants. | Two independent bounds. A code error can exceed the first; nothing short of a migration can exceed the second. | No |
| D-76 | The Continuity acts only in the tick, never in a request path. | A request-path action is a timing side channel, and *C9* forbids membership being inferable from a timing difference. This is why interventions are a stage. | No |
| D-77 | A declined recruitment offer writes nothing at all — no row, no event, no digest line. | Any record of a decline is a record of an approach, and an approach identifies a candidate. "Nothing remembered" has to be literal to be safe. | No |
| D-78 | An incursion arrives in the empty space between systems. | Filling a region with addressable empty space (`D-68`) was what made this possible: an incursion needs somewhere to be that is not already someone's home system. | No |
| D-79 | Fleet battles are a rule change, not a code change. | `encounter.resolve()` takes participant sets already; the MVP's 1v1 restriction is a rule. The Harrowing needs many-on-one, so this is the cheapest of its prerequisites. | No |

---

# 10. Open questions

| # | Question | Blocks |
| --- | --- | --- |
| **Q-A** | What is the era threshold — which crisis severity closes an era and opens the next? | §2.2 |
| **Q-B** | Does an unresolved crisis always produce an incursion, or only above a severity? | §5.1 |
| **Q-C** | How long is the watch interval, and is it the same on a demonstration world as on a live one? | §4.4 |
| **Q-D** | May knowledge be resold to the Institute at a loss, or is it consumed on reading? | §2.3 |
| **Q-E** | *GDD* Q8 — team shared assets — is still open, and player-owned stations depend on the answer. | §6 |

---

# 11. Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | 2026-08-29 | First post-MVP detailed design: P5 History, P6 the Continuity as an AI, P7 recruitment, clearance and the channel, P7+ the Harrowing, and the deferred systems. Decisions D-71 to D-79, acceptance criteria B1–B16. |

---

*End of document.*
