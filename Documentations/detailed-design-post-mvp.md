# Software Detailed Design — Post-MVP

## *Frontier: The Seldon Era*, delivery phases P5 to P7+

| Field | Value |
| --- | --- |
| Status | Draft for review |
| Version | 0.8 |
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
| **P5 — History** | **Built** | Stage 7 with crisis detection; `psycho.history_variables`, `forecasts`, `crises`, `eras`, four region views; era naming in stage 10; `GET /v1/forecasts` and `/v1/history/{eras,crises}`; the Institute as a station type with a restricted `knowledge` market; the `psycho_reader` role |
| **P6 — The Continuity** | **Built and running behind its flag** | `frontier/continuity/stage.py` (`role = "cont_role"`, `order = 8`), loaded by name from `settings.extra_stages`; `cont.agents`, `cont.cells`, `cont.budget`, `cont.interventions`; fifteen anti-leak probes |
| **P7 — Clearance and recruitment** | **Built, but for permanent loss** | `core.players.clearance` and `generation`; the `directorate` channel; `GET /v1/survey`; addressed recruitment offers; twenty-four anti-leak probes |
| **P7+ — The Harrowing** | **Built** | `simulation/stages/harrowing.py` at order 85; the `incursion` archetype closing on a system from empty space; permanent loss for an agent who dies in one |

Two consequences follow, and they shape everything below.

**The Continuity now acts, behind its flag.** Its schema, role boundary and import contract were already enforced —
`lint-imports` forbids anything importing `frontier.continuity`, and `cont_role` has no grant to write `players`,
`ships` or `cargo` — and it needed only to be put in its proper place in the cycle (§3.1). With
`FEATURES_CONTINUITY` off it is inert and every `cont` table stays empty, which `B5` asserts.

**Psychohistory now has a subject.** Crises, eras and the Institute shipped in v0.2–0.3 of this document, so the
model no longer only measures: it names what is going wrong, history records what it was called, and the Institute
gives prediction a price. The expiry of an unresolved crisis is the signal the Harrowing waits on (§5).

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

- `economy.toml` gains `knowledge` to `[commodities]` and an `institute` entry to `[station_type]`.
- Buying a forecast is `buy` against that market. Selling a discovery is `sell`.
- Knowledge is **restricted**: a `[restricted]` table names, per commodity, the station type that may stock it.

This is the whole of `D-71`: the Institute reuses the market machinery rather than adding a parallel one.

The non-transferable default (*ARCH §18*) is enforced by **absence**, not by a check. `seed_markets` gives a station
a row only for commodities its type may stock, so an ordinary market has no `knowledge` line at all — and the trade
command's existing `COMMODITY_UNAVAILABLE` is the refusal, with no new rule anywhere. The loader rejects a
`[restricted]` entry naming a commodity or a station type that does not exist, so a typo fails at load rather than
quietly making something untradeable.

## 2.4 Endpoints

| Method | Path | Answers |
| --- | --- | --- |
| `GET` | `/v1/forecasts` | *(built)* Region forecasts the player may see |
| `GET` | `/v1/history/eras` | The named eras, newest first |
| `GET` | `/v1/history/crises` | Open crises in regions the player has charted |

A crisis is public — a visible condition of a region, not intelligence. It is **not** scoped to charted regions:
registration already grants every galaxy, region and system (`D-67`), so such a filter would restrict nothing and
would be a lie in the code. What is inside a system stays private, and no crisis says anything about that.

---

# 3. P6 — The Continuity, as an AI

**Goal.** The hidden faction acts on the world before any player can join it, so that the evidence players later
find is real history rather than something retrofitted (*ARCH §17*, ADR-13).

## 3.1 Turning it on

The work turned out to be smaller still, and one step of it was wrong as first written.

The stage is **not** registered in `TICK_STAGES`. It is named in configuration
(`settings.extra_stages`) and resolved by dotted path at runtime, so `tick.py` never mentions
it and neither does a stack trace pasted into a public bug report — which is most of what keeps
*GDD §9.4* true. An earlier draft of this section said to register it in the tuple; that would
have put the Continuity in the import graph of the thing that runs it and undone the point.

What remained:

1. **Position.** Extra stages were appended, so the faction ran last, after the digests. Every
   stage now declares its ARCH §9.2 number as `order`, and the runner sorts by it — so a stage
   loaded by name takes its designed place without the runner naming it. The Continuity declares
   `order = 8` and now runs between psychohistory (7) and promotion (9), as designed.
2. **The role.** Already handled: the runner applies `SET LOCAL ROLE` for any stage declaring one.
3. **The probes.** Six added (§3.4), taking the suite from nine to fifteen.

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

| Probe | Asserts | Built |
| --- | --- | --- |
| `B5` | With the flag off, stage 8 does not run and all four `cont` tables stay empty | ✅ |
| `B6` | A tick opens a budget of `interventions_for(systems)` and spends no more; no intervention exceeds `max_magnitude` | ✅ |
| `B7` | Every system's public projection has one shape, whether or not its region was leaned on, and none of them carries a population flow | ✅ |
| `B8` | `api_role` holds no privilege on `cont` — verified from the catalogue, not by inspection | ✅ *(shipped with P6's schema)* |
| `B9` | No request path moves the Continuity: the intervention count is unchanged across every player-facing endpoint | ✅ |
| `B10` | Nothing in the AP ledger, the digests, the chronicle or an event payload contains any of the six secret words | ✅ |

`B9` deserves a note. A timing difference is a side channel, so an agent's extra work **MUST** happen in the tick,
never in the request path — which is why interventions are a stage and not a command. The probe asserts the
structural fact (a request cannot move the faction) rather than sampling latency, because a timing assertion that
passes on a quiet machine and fails on a loaded one is not a merge gate.

Two facts about the faction's behaviour are worth recording, because both surprised the tests:

- **It cannot act on a world that has not surprised the Model.** Interventions are driven by deviation, and on a
  first tick the projection equals the observation exactly, so the deviation is zero and the budget goes unspent.
  The faction waits for drift by construction.
- **It leans on regions, not systems**, so a small world can find every region touched at once. A probe that needs
  an untouched region to compare against is therefore unreliable; `B7` compares *shape* across all systems instead.

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

- A declined offer **MUST NOT** write a row, an event, or a digest line. "Nothing remembered" is literal — and it
  is achieved by there being **no decline command at all**. An offer that is not taken expires with every other
  unclaimed one, so refusing costs nothing and records nothing.
- Eligibility is evaluated from the player's own record only (*GDD Q10*): re-recruitment after a loss is possible,
  but never automatic, and it evaluates the new pilot's record on its own terms.

**Built as an addressed offer** (Q-F). A mission may carry `offered_to`, and the board shows an addressed offer to
that pilot and to nobody else. Every ordinary mission has it null, so every other board is the board it always was
— which is what makes an approach unobservable rather than merely unlabelled.

The capability granted is `INSERT` on `core.missions` and nothing else: the faction may put work in front of
someone, and may not edit it, withdraw it, or touch the pilot. That is narrower than either option the question
posed, which is why neither boundary had to give.

What makes it a recruitment is a term in `terms`, which the board never serialises — so the offer reads as ordinary
courier work until it is taken. Eligibility is read from the pilot's own record (knowledge learned, no clearance
yet), never from any history of approaches, because no such history is kept.

## 4.2 Permanent loss and the new pilot

An agent who dies in the Harrowing returns as a fresh pilot (*GDD §9.14*, Q9). The seam is stated in `ARCH §18` and
is worth repeating because it is the sharpest constraint in the project:

> **No column may link a new pilot to a former agent.** Re-recruitment evaluates the new pilot's own record, so the
> link is not merely forbidden but unnecessary.

`players` gains a `generation`; a reset writes a new pilot row rather than mutating the old. The Chronicle already
records a death and **MUST NOT** distinguish this one.

**The column is built; the reset path is not, and it belongs with the Harrowing.** Ordinary death is not permanent:
a destroyed pilot is recovered for a salvage tax (*GDD* S1), so the only permanent loss in the design is an agent
dying in an incursion (*§9.14*) — and incursions are §5. Building the reset now would mean building a path nothing
can reach.

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

**Built as a fourth channel of `send_message`**, needing no new command. Three things about it were not obvious
until it was written:

- **Clearance is a column on `core.players`, not a record in `cont`.** Resolving who may receive the event is then
  ordinary SQL over ordinary tables, so the delivery code never mentions the hidden faction and its import graph
  and stack traces stay clean. The column is never serialised, and a probe asserts that.
- **The entitlement gate belongs in `observation_quality`, not in the delivery.** The WebSocket pump filters by
  *channel*, not by delivery, so a `UNIVERSE`-scope event reaches every open socket. Gating only the delivery row
  would have leaked every clearance message to every connected client. The check now sits in the one function both
  the socket and the HTTP feed pass through, and it cuts both ways: a holder receives wherever they are, and a
  non-holder receives at no distance.
- **The refusal must be indistinguishable from nonsense.** `channel` was a `Literal`, so naming the channel would
  have been refused with `422` while an unknown name got the same — but a *member* got `202`, which makes a
  successful guess an answer. The field now takes any short string and the command refuses an unusable channel and
  an unknown one with the same code and the same body.

## 4.4 The watch

The spectator projection built for *UX §9* becomes the Continuity's watch, gated by a **faction-wide** rate limit in
Redis rather than a per-player one (*GDD §9.6*, U1: one watch per X hours for the whole faction). It reads only, so
it emits no event and touches no write path — which is also why it cannot leak membership through a write.

**Built as `GET /v1/survey`.** The ration is claimed with a single atomic `SET NX EX`, so two members cannot both
win it, and one member spending it spends it for everyone: it is a shared instrument, not a personal advantage.
`watch_interval_seconds` is rule data.

Without clearance the route answers `404` with **exactly the body a route that does not exist answers** — word for
word. The `NOT_FOUND` detail the resource endpoints use would have marked this one as a real route being withheld,
which the probe caught before it shipped.

---

# 5. P7+ — The Harrowing

**Goal.** A historical crisis that expires unresolved brings an invasion of powerful alien starships, and players
must fight together to restore the balance (*GDD §8.12*).

## 5.1 It needs no new mechanism

An incursion ship is a ship. It has hulls, it holds a position, it spends Action Points, and it is resolved by the
encounter code that already exists. What is new is a fourth NPC archetype and the stage that spawns it.

| Piece | Shape |
| --- | --- |
| Spawning | A tick stage watching **crisis expiry** (§2.2), not system activity. Every expired crisis brings one (Q-B); severity governs how bad it is, never whether it comes |
| The opponent | A fourth entry in `NPC_SHIP`, with its own hulls and weapons |
| Where it arrives | The empty space between systems — an address that exists precisely because a region is filled space (`D-68`) |
| Resolution | `encounter.resolve()` already takes participant *sets*; the MVP restricts cardinality to 1v1 **by rule, not by code**, so fleet battles are a rule change |
| Siding with them | An explicit command, a `players.allegiance` column, and a hit-chance term. Harrowers do not target an ally; the bonus applies against human ships while sided, and the penalty against Harrowers for anyone who **ever** sided (*GDD §8.12*, D-91) |

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
| **B1** | A sustained region deviation opens a crisis, it appears in `GET /v1/history/crises`, and it is named once however long it lasts |
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
| D-80 | A restricted commodity is kept out of a market by **not seeding a row**, rather than by a check in the trade command. | Absence needs no enforcement and cannot be bypassed: with no row there is nothing to buy, and the existing `COMMODITY_UNAVAILABLE` already says so in the player's language. A check would have needed the station's type plumbed into command state for a case that cannot arise. | No |
| D-81 | Every stage declares its ARCH §9.2 number as `order`, and the runner sorts by it. | Extra stages were appended, so a stage loaded by name ran last however the architecture numbered it. Sorting lets an optional stage take its designed position without the runner naming it — the numbering stops being a comment and becomes a fact the runner uses. | No |
| D-82 | Clearance is a column on `core.players`, not a record in `cont`. | Resolving a clearance audience becomes ordinary SQL over ordinary tables, so the delivery path never names the hidden faction. The alternative — reading `cont` from `event_sink` — would have put the word in a file every engineer reads, for no gain. The column is never serialised, and a probe asserts it over every player-facing response. | Yes |
| D-83 | The clearance gate lives in `observation_quality`, not in the delivery row. | The WebSocket pump filters by channel rather than by delivery, so a `UNIVERSE`-scope event reaches every open socket. Gating the delivery alone would have leaked every clearance message to every connected client. One gate, in the one function both the socket and the HTTP feed pass through. | No |
| D-84 | The survey's ration is claimed with one atomic `SET NX EX` on a key belonging to the faction, not the caller. | Two members cannot both win it, and one spending it spends it for everyone — which is the difference between a shared instrument and a per-member perk (U1). | No |
| D-85 | Knowledge is spent by a `read` command that consumes a unit and raises the pilot's knowledge; selling it is refused with `NOT_SELLABLE`. | Q-D: knowledge is not a commodity to flip. Reading costs no Action Points and needs no station — reading what you already carry is not an act in the world; what it costs is the unit. | Yes |
| D-86 | The watch ration is rule data, overridable per deployment by `WATCH_INTERVAL_SECONDS`. | Q-C: live pacing is balance, but a six-hour ration makes the feature invisible on a demonstration world. The override is a deployment concern, so it is a setting rather than a second ruleset. | No |
| D-87 | Recruitment is an offer addressed to one pilot via `missions.offered_to`, posted under an `INSERT`-only grant. | Q-F: narrower than either option the question posed. The faction may put work in front of someone; it may not edit it, withdraw it, or touch the pilot, and no other board changes at all. | Yes |
| D-88 | An incursion is raised into the region's empty space and closes on the nearest system over following cycles. | Arriving on top of a system would be an ambush; arriving in the dark and closing in is what gives a region its warning, and it uses the address D-68 created. `answered_on` on the crisis is what stops one expiry raising a fresh wave every cycle for ever. | Yes |
| D-89 | Permanent loss is decided from two ordinary facts — the pilot held a clearance, and something of the Harrowing was in the same place — and writes a **new** `players` row. | Nothing consults the hidden faction's own records, so the encounter code never mentions it. The old row stays exactly as it was, and no column links the two: re-recruitment reads the new pilot's own record (*ARCH §18*). Sign-in follows the highest generation. | No |
| D-90 | Stage `order` is the ARCH §9.2 number times ten. | The Harrowing had to run between the Continuity (8) and promotion (9), and integers left no room. Spacing lets a stage slot in without renumbering a normative document. | No |
| D-91 | Siding with an incursion is held in two columns: `allegiance`, which a pilot may clear, and `first_sided_on`, which nothing clears. The bonus reads the first; the penalty reads the second. | A cost that could be shed by renouncing at the right moment would make collaboration a tactic to pick up and put down. Attaching it to *having sided* is what makes it a choice about which side of a war a pilot is on. | Yes |
| D-72 | Crisis detection lives inside stage 7 rather than in a stage of its own. | The stage already computes the deviation a crisis is defined by. A separate stage would either recompute it or read the first stage's output, and both are worse than one pass. | Yes |
| D-73 | Eras are written by the chronicle stage, not by the model. | The model measures; naming a stretch of history is a narrative act, and the chronicle already owns promotion and retention. It also keeps the model's output free of prose. | Yes |
| D-74 | The Continuity ships as an unregistered stage first: the code, schema, role and import contract exist before the faction acts. | It makes enabling the faction a one-line change under a flag, and it means the anti-leak suite can be written and run against real code before anything is at stake. | No |
| D-75 | An intervention's effect is bounded by rule data (`max_magnitude`, `deviation_floor`) and its permissions by database grants. | Two independent bounds. A code error can exceed the first; nothing short of a migration can exceed the second. | No |
| D-76 | The Continuity acts only in the tick, never in a request path. | A request-path action is a timing side channel, and *C9* forbids membership being inferable from a timing difference. This is why interventions are a stage. | No |
| D-77 | A declined recruitment offer writes nothing at all — no row, no event, no digest line. | Any record of a decline is a record of an approach, and an approach identifies a candidate. "Nothing remembered" has to be literal to be safe. | No |
| D-78 | An incursion arrives in the empty space between systems. | Filling a region with addressable empty space (`D-68`) was what made this possible: an incursion needs somewhere to be that is not already someone's home system. | No |
| D-79 | Fleet battles are a rule change, not a code change. | `encounter.resolve()` takes participant sets already; the MVP's 1v1 restriction is a rule. The Harrowing needs many-on-one, so this is the cheapest of its prerequisites. | No |

---

# 10. Answered questions

All six were answered on 2026-08-30. Each is recorded here and in the section it settles; the identifiers stay
stable so a citation of `Q-B` keeps meaning what it meant.

| # | Question | Answer |
| --- | --- | --- |
| **Q-A** | What is the era threshold? | **Configurable.** It already is: `era_threshold` in `events.toml`, like every other tunable. The operator-facing view for turning such dials is now designed in `ui-ux-admin.md` (*ADMIN §3.4*), where it is deliberately read-only: the console drafts a new ruleset version rather than editing a live one. |
| **Q-B** | Does an unresolved crisis always produce an incursion, or only above a severity? | **Always.** Every crisis that expires unresolved brings an incursion. Severity governs how bad the incursion is, not whether it comes — so the world's promise is simple: leave a crisis alone long enough and something arrives. |
| **Q-C** | How long is the watch interval, and does a demonstration world differ? | **Shorter on a demonstration world.** The live pacing is rule data; a deployment may shorten it, and the demo does, because a six-hour ration makes the feature invisible to anyone being shown the game. |
| **Q-D** | May knowledge be resold to the Institute, or is it consumed on reading? | **Consumed when read.** Knowledge is not a commodity to flip: reading it spends it. Selling it back is therefore refused — the only thing to do with knowledge is learn it. |
| **Q-E** | Who may own a station? | **A faction, never a player or a team** (*GDD §11.1 M20*, answering *GDD* Q8). Teams hold no shared assets at all, so disbanding one raises no question of inheritance. |
| **Q-F** | Recruitment must place an offer on a mission board, but `cont_role` cannot write `core.missions` and stage 6 must not read `cont`. Which boundary gives? | **Neither.** A third option: a *targeted* offer. The Continuity posts a recruitment offer to one named pilot's board. It is not a general power to write missions — it writes an offer addressed to a pilot, which is a narrower capability than either option on the table. |

---

# 11. Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.8 | 2026-08-30 | A pilot may side with an incursion (*GDD* M21, D-91): explicit, announced at Universe scope, and paid for twice — a bonus that ends with the emergency and a penalty that does not. |
| 0.7 | 2026-08-30 | P7+ built: the Harrowing. A crisis that expires unanswered raises an incursion in the empty space of its region, which closes on a system and fights (D-88); an agent who dies there returns as a new pilot with no column linking the two (D-89). Stage orders are spaced by ten so a stage can slot between two without renumbering the architecture (D-90). |
| 0.6 | 2026-08-30 | All six open questions answered (§10) and acted on: knowledge is consumed by reading (D-85), the ration may be shortened per deployment (D-86), and recruitment ships as an addressed offer with a narrow `INSERT` grant (D-87). P7 is complete but for permanent loss, which waits on the Harrowing. |
| 0.5 | 2026-08-29 | P7 part one: the zero-delay clearance channel (D-82, D-83) and the faction-wide rationed survey (D-84). Recruitment and permanent loss remain — §4.1 and §4.2 record why each is blocked. |
| 0.4 | 2026-08-29 | P6 built: the Continuity acts at stage 8 behind `FEATURES_CONTINUITY`, ARCH's stage numbers became executable as `Stage.order` (D-81), and the anti-leak suite went from nine probes to fifteen. §3.1 corrected — the stage is loaded by name, never registered in `TICK_STAGES`. |
| 0.3 | 2026-08-29 | P5 complete: the Historical Institute ships as a station type with a restricted `knowledge` market (D-80). Fourteen Institutes in the generated world, and no other station stocks it. |
| 0.2 | 2026-08-29 | P5 part one built: crises and eras. `psycho.crises` and `psycho.eras`, detection folded into stage 7, era naming in stage 10, and `GET /v1/history/{eras,crises}`. B1 corrected — a crisis is public because the star chart already is, so the charted-region filter it described would have restricted nothing. |
| 0.1 | 2026-08-29 | First post-MVP detailed design: P5 History, P6 the Continuity as an AI, P7 recruitment, clearance and the channel, P7+ the Harrowing, and the deferred systems. Decisions D-71 to D-79, acceptance criteria B1–B16. |

---

*End of document.*
