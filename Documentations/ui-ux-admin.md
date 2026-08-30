# UI/UX Design — Operator Console

## *Frontier: The Seldon Era*, the view for whoever runs a world

| Field | Value |
| --- | --- |
| Status | **Slices A0 to A2 built. The remaining screens (A3–A6) are design.** |
| Version | 0.5 |
| Date | 2026-08-30 |
| Scope | The operator's console: watching a world, diagnosing it, and turning its dials |
| Depends on | `game-design.md` v3.0, `architecture.md` v0.8, `detailed-design-mvp.md` v0.20, `detailed-design-post-mvp.md` v0.6 |
| Audience | Whoever runs a deployment, and whoever builds the console for them |

### How to read this document

`ui-ux-mvp.md` is normative for what a **player** sees. This document is normative for what an **operator** sees, and
the two surfaces share nothing but a design language: different audience, different entitlement, different risks.

Cited as `ADMIN §n`. **A0 to A2 are built** — the separate application, the fourth role, operator sign-in, the
grant model of §2, and the screens of §3.1 to §3.3. The rest of §3 is still design; §7 tracks it.

---

# 1. What it is for

An operator has three jobs, and the console exists to make each of them possible without a database client.

| Job | The question it answers |
| --- | --- |
| **Watch** | Is the world turning? Did last night's tick finish, and how long did each stage take? |
| **Diagnose** | A player says something is wrong. What actually happened to them, and when? |
| **Tune** | This world is too empty, too poor, too quiet. Which dial, and what does turning it do? |

## 1.1 Non-goals

- **It is not a god mode.** An operator does not fly a ship, move cargo, award credits or resolve a fight. Every
  one of those is a command with an Action Point cost, and a console that bypassed them would make the world's
  rules optional.
- **It is not a live rules editor.** Balance is versioned data (*GDD §10.4 C4*). See §5.
- **It is not a player-facing surface**, and it is not reachable from the player API at all (§2).

---

# 2. Who may use it, and how it stays separate

The console is a **separate deployment surface**, not a privileged corner of the player API.

```text
        players ──▶  api_role  ──▶  /v1/…            (the game)
      operators ──▶ admin_role ──▶  /admin/…         (this console, a different process)
```

**One console, many worlds** (QA-3). A deployment runs several worlds; the console is one application with a world
picker in its header, and every screen below is scoped to the selected world. Operator permissions are held per
world, so being trusted with the demonstration world grants nothing on the live one.

**Permission comes from another operator** (QA-1). There is no self-service admin and no shared secret. A world is
seeded with one original operator — *the Great Ancients*, the account that generated it — and every other operator
is granted by someone who already holds the permission. Two consequences worth stating: a grant is an event with a
name attached, so the console can always answer "who let them in?"; and the original operator cannot be removed,
because a world with no operator is a world nobody can rescue.

Three further rules, and the first is the one that matters:

- **An operator account is not a player account.** They are different tables and different tokens. A person may
  hold both; holding one grants nothing in the other, and no response on either surface mentions the other.
- **The console runs as `admin_role`**, a fourth database role beside `api_role`, `cont_role` and `psycho_reader`.
  It reads widely and writes almost nothing — see §6 for the exact grants.
- **The console is bound separately.** It is a distinct ASGI app on its own port, so exposing the game does not
  expose the console, and a misconfigured router cannot mount `/admin` inside `/v1`.

> **The console may read `cont`.** Whoever runs the world already can; pretending otherwise would be theatre. What
> the console **MUST NOT** do is give an operator's *player* account any advantage, or let anything read from
> `cont` reach a `/v1` response. `ADMIN §6` states the boundary and the anti-leak suite gains a probe for it.

---

# 3. The screens

## 3.1 Overview — is the world turning?

The first screen, and the only one most days.

```text
┌───────────────────────────────────────────────────────────────────────────────┐
│  FRONTIER · world "kestrel"                        day 181 · open             │
├───────────────────────────────────────────────────────────────────────────────┤
│  LAST TICK    day 181     finished 04:02:11 UTC      3.4 s      ✓ all stages  │
│  NEXT TICK    day 182     04:00 UTC                  in 19h 58m               │
│                                                                               │
│  47 systems   1 204 pilots   17 crews   3 268 hexes of empty space            │
│  2 crises open      1 incursion under way      era: The Second Age            │
└───────────────────────────────────────────────────────────────────────────────┘
```

Rules:

- **Never a blank screen.** A world that has never ticked says so in words, not with empty fields.
- **The tick's state is the headline**, because a stalled tick is the one failure that stops everything and the one
  a player cannot report.

## 3.2 The tick — what took so long, and what broke

Read from `hist.tick_runs` and `hist.tick_stages`, which already record exactly this.

```text
┌───────────────────────────────────────────────────────────────────────────────┐
│  TICK · day 181                                    3.4 s      resumed: no     │
├───────────────────────────────────────────────────────────────────────────────┤
│   10  settle_travel        0.02 s   journeys_settled 4                        │
│   20  resolve_encounters   0.31 s   encounters 12 · ships_destroyed 2         │
│   30  economy              0.44 s   markets 734 · price_shifts 19             │
│   40  npc_population       1.90 s   goods_moved 465 · npcs_acted 61      ⚠    │
│   70  psychohistory        0.12 s   regions 4 · crises_opened 1               │
│   80  continuity           0.08 s   allowed 4 · used 4                        │
│   85  harrowing            0.05 s   incursions 1 · hulls 6                    │
│   90  event_promotion      0.06 s   promoted 3                                │
│  …                                                                            │
└───────────────────────────────────────────────────────────────────────────────┘
```

- Stages are listed **in their declared order** (`Stage.order`, *PSDD D-81*), with the number shown: the console is
  the place where that numbering becomes visible to a human.
- A stage over a configurable share of the tick is flagged (`⚠`). It is a hint, not an alarm.
- A run that did not finish names **the stage it stopped after** — the one recorded last — and offers
  **Ask for a retry**.

> **The console does not run a tick, and "Resume" was the wrong word for what it can do.** A failed tick already
> resumes by itself: the next run finds the open row and carries on from the stage that broke. What an operator
> needs is for that run to happen *sooner*, so the button leaves a request on `hist.tick_runs` — the one table the
> console may write — and the worker acts on it. A worker that never reads it changes nothing, which is the property
> that makes the button safe.

- **Stage times are derived, not stored.** `tick_stages` records when each finished, so a stage's time is the gap
  since the one before it and the first is measured from the run's start. The tick has no business carrying numbers
  it does not use.

## 3.3 History — crises, eras, incursions

```text
┌───────────────────────────────────────────────────────────────────────────────┐
│  ERA  The Second Age            began day 96                                  │
├───────────────────────────────────────────────────────────────────────────────┤
│  OPEN CRISES                                                                  │
│   R2  stability          severity 4   opened 174   expires 186   ⏳ 5 days     │
│   R4  economic_health    severity 2   opened 179   expires 191   ⏳ 10 days    │
│                                                                               │
│  INCURSIONS                                                                   │
│   R1  6 hulls   raised day 181 from a stability crisis   4 still flying       │
└───────────────────────────────────────────────────────────────────────────────┘
```

The countdown is the point: an operator should be able to see that a region is about to be invaded **before** it
is, because that is when a world is most interesting and most likely to need watching. It warms as it runs down —
grey beyond eleven days, amber inside it, red inside five — because a date means nothing without today's number.

A crisis that has been answered carries **the incursion it raised**, on the same row: what came, and what it came
from. Severity is drawn as five marks as well as written, so a five reads at a glance across a room.

## 3.4 Balance — the dials, and what turning one costs

```text
┌───────────────────────────────────────────────────────────────────────────────┐
│  RULESET 2026.1                                          in use since day 0   │
├───────────────────────────────────────────────────────────────────────────────┤
│  world.region_radius            16      a bigger region is more empty space   │
│  world.jump_range_default_ly    12      below 12, regions fragment internally │
│  events.crisis_threshold      0.18      lower opens more crises               │
│  events.era_threshold            3      severity that closes an age           │
│  npc.incursion_ships_per_sev     2      hulls per point of severity           │
│  continuity.watch_interval    21600 s   overridden here: 120 s                │
├───────────────────────────────────────────────────────────────────────────────┤
│  These are read-only. Editing balance means publishing a new ruleset version. │
│                                            [ Draft 2026.2 from these values ] │
└───────────────────────────────────────────────────────────────────────────────┘
```

This screen is **read-only by design**, and that is the most important decision in this document.

> Balance is `[BALANCE]` data in versioned files (*GDD §10.4 C4*). A live editor would make the ruleset version a
> lie: two worlds claiming `2026.1` would behave differently, and a replayed tick would not reproduce.

What the console offers instead is **Draft**: it writes the current values plus the operator's edits into a new
ruleset directory **on a branch** (QA-2), which is then reviewed and merged like any other change. The console
proposes; the repository decides. A draft that is never merged changes nothing, which is the property that makes
the button safe to press.

Each dial carries a one-line note on what turning it does — the note is written by whoever adds the dial, and is
part of adding it. `jump_range_default_ly` says what it says above because that was measured, not guessed.

## 3.5 Pilots — the support view

For "a player says something is wrong".

```text
┌───────────────────────────────────────────────────────────────────────────────┐
│  PILOT  Cmdr Vale                     generation 1 · joined day 12            │
├───────────────────────────────────────────────────────────────────────────────┤
│  15/15 AP   4 930 cr   hull 92/100   G0/R0:0/S5:-15/P4:-5   docked            │
│  crew: The Long Haul          standing: Empire +12, Republic −4               │
├───────────────────────────────────────────────────────────────────────────────┤
│  THEIR LAST DAY                                                               │
│   04:00  AP_GRANTED        15                                                 │
│   09:12  SHIP_ENTERED      …/P4:-5                                            │
│   09:14  TRADE_EXECUTED    grain ×10 @ 44                                     │
│   11:40  COMBAT_RESOLVED   escaped after 2 rounds                             │
└───────────────────────────────────────────────────────────────────────────────┘
```

- It shows **what the server did**, drawn from events and the ledger — the same record that would settle any
  dispute.
- It is **read-only**. There is no "give them their credits back": a correction is a world-level decision, and if
  one is ever needed it arrives as a command with a name, not as a text field on a support screen.
- **Clearance is not shown, ever** — not on this screen, not in a search filter, not in an export. An operator with
  a player account could otherwise learn who to follow. This is the one field the console redacts from itself.

## 3.6 The hidden faction — a separate screen, behind its own flag

Visible only when `FEATURES_CONTINUITY` is on **and** the operator holds the console's own continuity permission.

```text
┌───────────────────────────────────────────────────────────────────────────────┐
│  DIRECTORATE                                    budget day 181: 4 of 4 spent  │
├───────────────────────────────────────────────────────────────────────────────┤
│  CELLS      4        AGENTS  11 npc · 2 pilots                                │
│  LAST INTERVENTIONS                                                           │
│   R2  nudge        raider_pressure   −0.041                                   │
│   R4  delay        trade_flow        +0.038                                   │
│  OFFERS OUT  1 addressed, expires day 187                                     │
└───────────────────────────────────────────────────────────────────────────────┘
```

It exists because an operator tuning the faction cannot tune what they cannot see. It is a separate screen so that
**the ordinary screens stay ordinary**: nothing on §3.1–§3.5 changes shape when the faction is switched on, which is
the same property `B7` asserts for players.

---

# 4. What the console must never do

| Never | Why |
| --- | --- |
| Grant credits, AP, cargo, or move a ship | Every one is a command with a cost; a console that bypasses them makes the rules optional |
| Edit a live ruleset | Balance is versioned data; a live edit makes the version a lie (§3.4) |
| Show a pilot's clearance | An operator with a player account would learn who to follow (§3.5) |
| Expose anything read from `cont` on a `/v1` response | The console is a different surface; the boundary is a grant, not a habit (§6) |
| Delete a pilot, an event or a chronicle line | History is the product. A world that can be quietly edited has no history |

---

# 5. What the console calls

A separate app, a separate prefix, a separate role.

Every world-scoped route carries the world in its path, because one console reaches several (QA-3).

| Screen | Endpoints | Built |
| --- | --- | --- |
| Sign in | `POST /admin/auth/login`, `GET /admin/me` | ✅ |
| Overview | `GET /admin/worlds/{world}` | ✅ |
| The tick | `GET /admin/worlds/{world}/ticks`, `.../ticks/{day}`, `POST .../ticks/{day}:retry` | ✅ |
| Operators | `GET /admin/operators`, `POST /admin/operators:grant`, `:revoke` | ✅ *(A0)* |
| History | `GET /admin/worlds/{world}/history` | ✅ |
| Balance | `GET /admin/worlds/{world}/ruleset`, `POST .../ruleset:draft` | |
| Pilots | `GET /admin/worlds/{world}/pilots?q=…`, `.../pilots/{id}` | |
| Directorate | `GET /admin/worlds/{world}/directorate` | |

The screens themselves are **rendered on the server** at `/console/{world}/…`, reading through the same functions
the JSON routes use. An operator console is an internal tool with a handful of screens: a page that arrives
finished is one less thing to be broken at 4am, and it spares the project a second front-end toolchain.

Two write endpoints in the whole console, and neither changes the world's state directly: one resumes a tick that
already exists, one writes a file for a human to review.

---

# 6. The boundary, as grants

`admin_role` is a fourth role, defined the way the other three are — by what the database will let it do, not by
what the code remembers (*ARCH ADR-13*).

| Schema | `admin_role` |
| --- | --- |
| `core`, `evt`, `hist`, `psycho` | `SELECT` |
| `cont` | `SELECT` |
| everything | **no `INSERT`, `UPDATE` or `DELETE`** except `hist.tick_runs` for a resume |

A console that cannot write cannot be the cause of a dispute about what happened. The one write it needs — marking
a tick resumable — is the narrowest grant that makes §3.2's Resume button work.

Three probes were added with A0, all reading the catalogue rather than the code:

- **`B17`** — `admin_role` can read every world schema, and its only write into the world is `hist.tick_runs`.
- `api_role` holds nothing at all on `admin`, asserted by a denied `SELECT` as well as by the grant table.
- `admin_role` is refused an `UPDATE` on `core.players`: the console diagnoses, it does not correct.

**Authentication** (QA-1's remaining half): an operator signs in with their own credentials, and the token carries
an audience of `frontier-console`. A player token has no audience and is refused here; an operator token has one and
is refused by the game — so the two surfaces stay separate **even if a deployment gives them the same secret**. A
login treats the address as a lookup key and does not validate it, so "that address could not exist" is never a
different answer from "no such operator".

---

# 7. Delivery

Each slice is independently useful, and the first two are most of the value.

| Slice | Delivers | Worth it because |
| --- | --- | --- |
| **A0** ✅ | The separate app, `admin_role`, operator auth, the grant model | Nothing else can exist until the surface is separate. **Built** |
| **A1** ✅ | Overview and the tick screen | Answers "is the world turning?", which is the only question that matters at 4am. **Built** |
| **A2** ✅ | History: crises, eras, incursions | The countdown to an incursion is the thing worth watching. **Built** |
| **A3** | Pilots: the support view | Turns "something went wrong" into a fact |
| **A4** | Balance: read-only dials and Draft | Makes tuning a reviewed change rather than a live one |
| **A5** | Operators: who holds permission, and who granted it | Follows A0's model; needed the moment a second person runs a world |
| **A6** | The Directorate screen | Last, and behind its own flag, for the same reason the faction shipped last |

---

# 8. Answered questions

| # | Question | Answer |
| --- | --- | --- |
| **QA-1** | How does an operator authenticate? | **Granted by another operator.** A world is seeded with one original operator — the Great Ancients — and permission spreads only by grant. No shared secret, no self-service. |
| **QA-2** | Does `Draft` open a branch or write to disk? | **A branch.** The draft is a change to review, so it arrives where changes are reviewed. |
| **QA-3** | One console per world, or one across many? | **One console, many worlds**, with permissions held per world. |

---

# 9. Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.5 | 2026-08-30 | Slice A2 built: eras, open crises with their countdown, and the incursion each answered crisis raised. The console now loads the world's ruleset, so a number on screen can say what it means. |
| 0.4 | 2026-08-30 | Slice A1 built: the overview and the tick, rendered on the server. Stage times are derived from the gaps between recorded finishes rather than stored. **Resume became "ask for a retry"** — the console cannot run a tick, and a failed one already resumes itself. |
| 0.3 | 2026-08-30 | Slice A0 built: the console as a separate application on its own port, `admin_role` and its read-mostly grants, operator sign-in on its own audience, and the grant model — including an origin that cannot be revoked. Three anti-leak probes. |
| 0.2 | 2026-08-30 | QA-1 to QA-3 answered: one console across many worlds, permission granted operator to operator from an original account, and `Draft` opening a branch. Adds the Operators screen (A5). |
| 0.1 | 2026-08-30 | First design of the operator console: a separate surface, a read-mostly boundary, and a balance screen that proposes a ruleset version rather than editing one. |

---

*End of document.*
