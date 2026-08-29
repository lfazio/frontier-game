# UI/UX Design — MVP Client

## *Frontier: The Seldon Era*, browser client

| Field | Value |
| --- | --- |
| Status | Draft for review |
| Version | 0.10 |
| Date | 2026-08-28 |
| Scope | The MVP client (*GDD §10.1*) and a spectator mode for demonstrating a running world |
| Depends on | `game-design.md` v2.9, `architecture.md` v0.8, `detailed-design-mvp.md` v0.15 |
| Audience | Client engineers, designers, anyone building or reviewing the front end |

### How to read this document

The design document is normative for **what the game does**; this document is normative for **what the player sees
and touches**. It specifies screens, states, wording rules and interaction contracts. It does **not** choose a
component library, a CSS framework or a state manager — those are implementation decisions, and *ARCH §4* fixes only
React and TypeScript.

Cited as `UX §n`. Where this document and the design document disagree, the design document wins.

---

# 1. What the client is for

A player has fifteen minutes (*GDD §1.2*, Pillar 3). In that time they must be able to find out what happened while
they were away, decide what to do, do it, and leave. Everything in this document serves that.

There are two audiences, and the MVP serves both from one codebase:

| Mode | Who | What they can do |
| --- | --- | --- |
| **Play** | An authenticated player | Read the world, spend Action Points, talk |
| **Watch** (§9) | Anyone, no account | Observe a running world: the map, the feed, the tick advancing. No commands |

Watch mode exists because a persistent asynchronous game is hard to show. A recording is not convincing and a live
account requires an invitation; a spectator view of a real server running real cycles is the honest demonstration.

## 1.1 Principles

These follow from the game's own invariants, and each one rules out a specific temptation.

1. **The server is the only source of truth.** The client submits intents and renders responses (*GDD §10.4 C1*). It
   **MUST NOT** predict an outcome, decrement AP locally before the server confirms, or animate a result it has not
   been told. Optimistic UI is forbidden for anything the server owns: AP, credits, position, damage, cargo, combat.
   *Why:* a client that guesses will eventually guess differently from the server, and the player will believe the
   client.
2. **Absence is absence.** The client renders exactly the payload it received. If a location is not in a map tile,
   there is nothing there to draw — no fog marker, no "unknown contact" placeholder, no greyed-out silhouette
   (*GDD §10.4 C4*). *Why:* a placeholder tells the player that something exists, which is the leak the server
   worked to prevent.
3. **AP is always on screen.** It is the scarce resource of the whole game (*GDD §3.2*). Every action shows its cost
   before it is taken, and the remaining balance after.
4. **Zoom changes resolution, not mode.** Galaxy, region and system are one map at three magnifications
   (*GDD §2.1*). No loading screen, no separate "system view" application, no modal transition.
5. **One feed.** Chat and world events are the same stream (*GDD §7.9*), filtered, never split into separate
   inboxes.
6. **The first screen is a report.** The world moved without the player. They arrive to read, not to act.
7. **Nothing is urgent.** No timers, no streaks, no countdown pressure. The cycle is 24 hours; the interface must
   never imply that acting sooner is better.

## 1.2 Non-goals

- No real-time tactical display. Combat is a few decisions and a result (*GDD §5.4*).
- No client-side simulation of any kind, including "preview" of a tick.
- No mobile-first layout in the MVP; the target is a desktop browser, and the layout is responsive enough not to
  break below it.
- No monetisation surfaces of any kind (*GDD §1.6*).

---

# 2. Information architecture

One shell, one persistent frame, five destinations. The frame never unmounts, so the feed and the AP counter are
continuous across navigation.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  FRONTIER          Cmdr Vale · Republic · Orion      AP ●●●●●●●○○○ 7/10  ⏱ D182│
├────────────┬─────────────────────────────────────────────┬───────────────────┤
│            │                                             │                   │
│  Overview  │                                             │      FEED         │
│  Map       │              MAIN PANEL                     │                   │
│  Ship      │                                             │   (always shown,  │
│  Station   │                                             │    filterable)    │
│  Missions  │                                             │                   │
│  Team      │                                             │                   │
│            │                                             │                   │
├────────────┴─────────────────────────────────────────────┴───────────────────┤
│  ga0_0/re0_n1/sy2_4/pln5_4 · Anchor Station · docked        [ Standing orders ]│
└──────────────────────────────────────────────────────────────────────────────┘
```

| Region of the frame | Always shows | Rule |
| --- | --- | --- |
| Header | Callsign, faction, team, **AP**, world day | AP is never hidden, never behind a hover |
| Left rail | The five destinations | Order is fixed; no badges that pulse or nag |
| Main panel | The current destination | One thing at a time |
| Right rail | The feed | Collapsible, never removable |
| Footer | Current address, place name, docking state | The address is selectable text — players trade coordinates |

**Station** appears in the rail only while the ship is docked; it is otherwise absent, not disabled. A destination
the player cannot use should not occupy the same visual weight as one they can.

---

# 3. The daily overview

The landing screen, and the one that has to do the most work. It answers the five questions of *GDD §3.4* without
further navigation: what happened to me, what changed near me, what my team said, what I can afford, what expires.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  DAY 182                                            Last seen: day 181       │
├──────────────────────────────────────────────────────────────────────────────┤
│  WHILE YOU WERE AWAY                                                         │
│                                                                              │
│   ⚔  Your convoy was attacked near Anchor Station        hull 100 → 64       │
│   💰 Grain rose 12% at Kestrel Yard                                          │
│   🚀 Two ships entered your hex                                              │
│   🏛 Republic influence in Sirius Reach fell below 50%                        │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  YOU                                    │  NEAR YOU                          │
│   AP        7 / 10   (+3 carried)       │   Kestrel Yard      2 hexes  trade  │
│   Credits   4 965                       │   Unidentified      4 hexes  ?      │
│   Hull      64 / 100      ⚠ damaged     │   Patrol            5 hexes  Empire │
│   Fuel      50 / 60                     │                                    │
│   Cargo     5 / 20                      │                                    │
│                                         │                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│  EXPIRES TODAY                                                               │
│   Mission "Patrol the approaches"  ends day 183       [ Open ]               │
└──────────────────────────────────────────────────────────────────────────────┘
```

Rules:

- **"While you were away" is built from the digest** (*SDD §6.8*), not assembled by the client from the feed. The
  client renders what the server summarised.
- **It is never empty.** A quiet cycle says so in words — *"The frontier was quiet."* — rather than showing an empty
  box, which reads as a failure.
- **Damage, low fuel and a full hold are stated, never merely coloured.** Colour is reinforcement, never the only
  channel (§8.3).
- The "last seen" line is the only place the interface refers to the player's own absence. It **MUST NOT** be
  phrased as a reproach.
- **Only the current cycle's overview is kept.** The client holds no history of past days and `GET /v1/me` takes no
  `world_day`: what happened before is in the feed and, if it mattered, in the Chronicle. Revisit only if fetching
  the latest turns out to cost more than caching a little of it would.

---

# 4. The map

One map, three magnifications, driven entirely by `GET /v1/map/tiles?path=…` (*SDD §9.1*).

| Zoom | Path level | Hexes are | The player sees |
| --- | --- | --- | --- |
| Galaxy | `ga…` | Regions | Region names, faction control shading |
| Region | `ga…/re…` | Systems | Every system (the star chart is public), control, own position |
| System | `ga…/re…/sy…` | Planets, stations, void | A top-down board centred on the ship, live only as far as it can see (§4.1) |

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  SIRIUS REACH · region                        [ galaxy ‹ region › system ]    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│              ⬡       ⬡       ⬡                    ◆ you                       │
│          ⬡      (E)      ⬡       ⬡                ⬢ station                   │
│              ⬡       ◆       ⬡                    ⬡ system                    │
│          ⬡       ⬡      (P)      ⬡                                            │
│              ⬡       ⬡       ⬡                    (E) Empire                  │
│                                                    (R) Republic               │
│                                                    (P) Pirates                │
│                                                    ·   contested              │
├──────────────────────────────────────────────────────────────────────────────┤
│  Kestrel Reach · system · Republic 61%                                       │
│  4.2 ly · jump 4 AP · 8 fuel                          [ Plot jump ]           │
└──────────────────────────────────────────────────────────────────────────────┘
```

Rules:

- **Selecting a hex never spends anything.** Selection shows cost; a second, explicit action commits it.
- **An undiscovered system's interior is empty, and the interface says why**: *"Not surveyed. Scan from within the
  system to chart it."* This is the one place the client explains an absence, because the absence is a game
  mechanic rather than a gap.
- **Faction control uses shading plus a letter**, never hue alone (§8.3).
- **The player's own position is always marked and always findable** — a "centre on me" control that never scrolls
  off.
- Tiles carry an `ETag`; the client sends `If-None-Match` and treats `304` as "unchanged", not as an error.

## 4.1 The board, and how far you can see

At system zoom the map is a **top-down view of the hex board, centred on the ship and bounded by how far that ship
can see**. Sight is the ship's sensor range (*GDD §4.2*): a property of the hull the player chose, not a camera
setting.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  KESTREL REACH · system                       [ galaxy ‹ region › system ]    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│         ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·        · charted, not in sight    │
│         ·  ·  ⬢  ·  ·  ·  ·  ·  ·  ·  ·  ·        ⬢ station (charted)        │
│         ·  ·  ┌───────────────┐  ·  ·  ·  ·                                   │
│         ·  ·  │ ⬡  ⬡  ⬡  ⬡  ⬡ │  ·  ·  ·  ·        ── sight, radius 3 ──      │
│         ·  ·  │ ⬡  ◇  ⬡  ⬡  ⬡ │  ·  ·  ·  ·        ◇ unidentified            │
│         ·  ·  │ ⬡  ⬡  ◆  ⬢  ⬡ │  ·  ·  ·  ·        ◆ you                     │
│         ·  ·  │ ⬡  ⬡  ⬡  ⬡  ⬡ │  ·  ·  ·  ·        ⬡ empty, seen now         │
│         ·  ·  │ ⬡  ⬡  ⬡  ⬡  ⬡ │  ·  ·  ·  ·                                   │
│         ·  ·  └───────────────┘  ·  ·  ·  ·                                   │
│         ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·                                    │
├──────────────────────────────────────────────────────────────────────────────┤
│  Sight 3 hexes · 1 contact · Anchor Station charted day 176                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

Three layers, and the interface must keep them visibly distinct:

| Layer | What it holds | How it behaves |
| --- | --- | --- |
| **In sight** | Everything within sensor range right now: ships, stations, planets, empty hexes | Live. Updates from the feed as events arrive |
| **Charted** | Places this player has previously discovered (*GDD §5.2*) | Static and permanent. Drawn dimmer, with the day it was charted |
| **Unknown** | Everything else | **Nothing is drawn.** Not fogged, not greyed, not outlined |

Rules:

- **Terrain is remembered; ships are not.** A station stays on the board once charted, because a station does not
  move. A contact **MUST** disappear from the board the moment it leaves sight — the client keeps no ghost at the
  last known position, because a ghost is a claim the server never made.
- **The sight boundary is drawn.** The player must be able to see where their own knowledge stops; a map that fades
  ambiguously invites them to guess. A ship with a better sensor suite sees a visibly larger board, which is how
  the hull upgrade is felt rather than read.
- **The board does not scroll beyond what is charted.** Panning is bounded by the union of sight and chart, so
  empty space cannot be mistaken for explored space.
- **Sight is stated numerically** in the status line, because it is a stat the player can change.
- The same rule holds at region zoom for *contacts*: systems are public (§4), the ships inside them are not.

## 4.2 Contacts

Contacts come from the feed and from system tiles, already redacted by the server (*SDD §5.5*). The client renders
the two qualities it is given and invents nothing between them:

| Quality | Rendered as |
| --- | --- |
| `full` | Callsign, ship class, exact hex |
| `partial` | *"Unidentified contact"*, approximate position, no class, no name |

A `partial` contact **MUST NOT** be drawn with a placeholder identity, a guessed faction colour, or a tooltip that
speculates.

---

# 5. Acting

Every action follows one interaction contract, because every action follows one server contract (*SDD §5.2*).

```text
        select ──▶ cost shown ──▶ confirm ──▶ pending ──▶ result
                        │                         │          │
                        └── cancel                │          ├─ accepted: events rendered
                                                  │          └─ refused: reason, nothing changed
                                                  └─ 503: "the galaxy is turning"
```

| Stage | Rule |
| --- | --- |
| Cost shown | AP and fuel cost, and the balance that would remain. Shown *before* commitment, always |
| Confirm | One deliberate action. Free actions (dock, message, standing orders) skip confirmation |
| Pending | The control disables and says so. The client **MUST NOT** apply the change yet |
| Accepted | The server's events are rendered; AP and state come from the response, never from arithmetic |
| Refused | The reason is stated in the player's language, and the interface returns to exactly its prior state |

## 5.3 Routes

A journey of several hexes is **one decision, not one per hop**. The player plots a route, sees what the whole thing
costs, and confirms once.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  ROUTE · 5 hexes to Kestrel Yard                                             │
│                                                                              │
│    ◆──⬡──⬡──⬡──⬡──⬢                                                          │
│                                                                              │
│    5 AP · 5 fuel            leaves 2 AP · 45 fuel        [ Fly ]  [ Cancel ] │
└──────────────────────────────────────────────────────────────────────────────┘
```

It is submitted as one `POST /v1/commands:batch` (*SDD §8.2*). The server still evaluates and charges every hop
separately, which means a route can stop partway — and the interface **MUST** say so plainly rather than reporting
a failure:

> **Stopped after 3 of 5 hexes.** Not enough Action Points for the rest. You are at `…/pln4_3`.

Rules:

- **The cost shown is the whole route's**, with the balance remaining after it.
- **A partial route is a result, not an error.** The ship is somewhere real; the interface says where, why it
  stopped, and what would let it finish.
- **A route is never re-submitted automatically.** Resuming is the player's decision, with its own confirmation.
- **The route is drawn before it is flown**, and the drawn path is the path submitted — the client uses the
  server's own hex-line rule (§8.4) so the two cannot disagree.

## 5.4 Refusals are normal

A `409` is gameplay, not an error (*SDD §8.4*). It **MUST NOT** be presented as a failure: no red banner, no
"something went wrong", no error toast. It is an answer.

| Code | What the player is told |
| --- | --- |
| `INSUFFICIENT_AP` | "Not enough Action Points — 2 needed, 1 left. More at the next cycle." |
| `INSUFFICIENT_FUEL` | "Not enough fuel. Refuel at a station." |
| `NOT_ADJACENT` | "Too far for one move. Plot a route instead." |
| `BEYOND_JUMP_RANGE` | "Beyond this ship's jump range — 12 ly away, range 8 ly." |
| `MUST_LAUNCH_FIRST` | "You are docked. Launch first." |
| `CARGO_FULL` | "The hold is full — 20 of 20." |
| `TARGET_NOT_VISIBLE` | "Nothing there now. Your last sighting is three cycles old." |
| `WORLD_TICKING` (503) | "The galaxy is turning. A moment." — retried automatically, once |

Wording rules: state the fact, then the remedy. Never blame. Never use the word "error" for a refusal.

## 5.5 Idempotency

The client generates an `idempotency_key` (UUIDv4) **once per intent**, and reuses it on retry. A retry that returns
`Idempotent-Replay: true` is rendered as the original outcome, silently — the player asked once and it happened
once.

---

# 6. Station, market and cargo

Trading is the most numeric screen in the game and the easiest to make hostile. The rule is that the player should
never have to do arithmetic the interface could do.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  ANCHOR STATION · refinery · Republic                        [ Launch ]       │
├──────────────────────────────────────────────────────────────────────────────┤
│  COMMODITY      STOCK    BUY     SELL    HELD    AVG PAID   │  HOLD 5 / 20    │
│  Grain            412     43       36       5         41    │                 │
│  Ore              180     71       60       —          —    │  Credits 4 965  │
│  Alloys            44    198      167       —          —    │  AP      7 / 10 │
│  Medicine           8    612      516       —          —    │                 │
├──────────────────────────────────────────────────────────────────────────────┤
│  Buy Grain    [ − ]  5  [ + ]      215 cr      1 AP                           │
│                                    ↳ leaves 4 750 cr · hold 10/20   [ Buy ]   │
└──────────────────────────────────────────────────────────────────────────────┘
```

Rules:

- **Prices come from the server on every view.** The client never computes a price and never caches one across a
  cycle boundary (*SDD D-9*).
- **The spread is visible.** Buy and sell are both shown, always, so the cost of a round trip is legible rather than
  discovered.
- **"Avg paid" is shown wherever cargo is** — a trader must be able to see profit without a spreadsheet.
- Quantity is adjustable by a stepper *and* typed entry; the maximum affordable and the maximum that fits are one
  click away.

---

# 7. The feed

One stream, filtered by channel, newest first, cursor-paginated (*SDD §9.3*).

```text
┌────────────────────────────────────────────────┐
│ ALL · LOCAL · SYSTEM · TEAM                    │
├────────────────────────────────────────────────┤
│ 🚀 Cmdr Smith                            2h    │
│    Anyone heading toward Alpha-3?              │
│                                                │
│ ⚠  Unidentified contact                  3h    │
│    somewhere in this system                    │
│                                                │
│ ⚔  Combat resolved                       5h    │
│    Attacker won · 3 rounds                     │
│                                                │
│ 💰 Grain +12%                            9h    │
│    Kestrel Yard                                │
├────────────────────────────────────────────────┤
│ Say something…                        [ Send ] │
└────────────────────────────────────────────────┘
```

Rules:

- **Live events arrive over the WebSocket** and are de-duplicated on `event.id`; on reconnect the client fetches the
  gap over HTTP from its last cursor, then resumes.
- **A `partial`-quality event is rendered vaguely on purpose** — "somewhere in this system" — and the client
  **MUST NOT** enrich it from anything else it knows.
- Timestamps are relative within a cycle, absolute across one ("day 181").
- The composer posts to the channel currently filtered. It is disabled — with the reason — while in transit.

---

# 8. Craft

## 8.1 Reading the world at a glance

The palette carries three meanings and no more: **faction**, **danger**, **your own things**. Anything else is
neutral. A screen where everything is coloured tells the player nothing.

## 8.2 Motion

Motion is used only to show causation: a value that changed because of what the player just did may animate from old
to new. Nothing loops, nothing pulses, nothing draws attention to itself while idle. `prefers-reduced-motion` removes
all of it.

## 8.3 Accessibility

Non-negotiable for the MVP, because retrofitting is what never happens:

- **Never colour alone.** Faction is a letter plus shading; damage is a number plus a word; danger is an icon plus
  text. Verified against protanopia, deuteranopia and tritanopia simulation.
- **Keyboard-complete.** Every action reachable without a pointer, including map navigation and hex selection.
- **Screen-reader coherent.** The map exposes a textual list of what is in range, ordered by distance, as a peer of
  the graphical view — not a fallback.
- **Contrast** meets WCAG 2.2 AA at minimum; the feed and the market table meet AAA for body text.
- **No time-based interaction.** Nothing in the MVP requires a fast response, so nothing needs an extension.

## 8.4 Rendering the board

Hex maps are drawn on **canvas**, not SVG. A system is a radius-8 board — 217 hexes — and a region view can hold
several hundred marks; as DOM nodes that is an amount of layout work no browser should be asked to do sixty times a
second while panning.

The consequence is not optional. **Canvas has no accessibility tree**, so the textual view specified in §8.3 stops
being a courtesy and becomes the only way a screen reader can perceive the map at all. It is therefore built
alongside the canvas, from the same data, in the same slice — never afterwards. A canvas map shipped without it is
an inaccessible map, not an incomplete one.

Two further rules follow from the choice:

- **Keyboard focus is the client's job.** Canvas has no focusable children, so hex selection, panning and zoom are
  driven from an explicit focus model the client owns and draws — a visible focus ring on the selected hex, moved
  with the arrow keys.
- **Hit-testing is arithmetic, not the DOM.** Pointer position converts to axial coordinates directly, which is the
  same `Axial` maths the server uses; the client **MUST** use the identical rounding rule so that the hex a player
  clicks is the hex the server is asked about.

## 8.5 Language

- Second person, plain, unhurried. *"You are docked."* not *"Player is currently in a docked state."*
- The world's terms are used exactly as the design defines them: **cycle**, **world day**, **Planet**, **Sector**,
  **Action Points**. Never "turn", never "energy", never "stamina".
- Numbers are grouped (`4 965`), units are stated (`4.2 ly`, `7 AP`), and percentages are whole unless precision
  matters.

---

# 9. Watch mode

A read-only, top-down view of a live world: where fighting is happening, where control is shifting, where trade has
stopped. It has **two lives**, and the same rendering serves both.

| | Demonstration deployment | Live world |
| --- | --- | --- |
| Who | Anyone, no account | The Continuity, and nobody else (*GDD §9.6*) |
| How often | Freely | One watch every `X` hours `[BALANCE]`, rationed across the whole faction |
| Why it exists | The game is hard to show; a recording is not convincing and an account requires an invitation | It is the faction's sight, and its scarcest shared resource |

Building it once serves both, which is the main reason it is slice **C1** (§11). The rationed version is phase P7
work; the MVP builds only the demonstration deployment.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  FRONTIER · watching                                   DAY 182   ▸ live      │
├────────────────────────────────────────────────┬─────────────────────────────┤
│                                                │  UNIVERSE FEED              │
│            (galaxy map, control shading)       │   ⚔ Combat · Sirius Reach   │
│                                                │   🏛 Territory changed       │
│                                                │   🔭 Discovery · Kestrel     │
├────────────────────────────────────────────────┴─────────────────────────────┤
│  47 systems · 3 factions · 12 pilots · 84 crews        [ ▸ advance a cycle ]  │
└──────────────────────────────────────────────────────────────────────────────┘
```

| Rule | Why |
| --- | --- |
| **Public-scope events only.** Watch mode subscribes to what a location-less viewer may see: `Scope ≥ SYSTEM`, `Visibility = PUBLIC` | It must be strictly weaker than any player's view, or it becomes an intelligence tool |
| **No player-identifying detail beyond callsigns already public** | *GDD §10.4 C4* applies to spectators too |
| **Nothing about the hidden faction, at any zoom, ever** | *GDD §9.4*; the anti-leak suite covers spectator responses as it covers player ones |
| **Watch mode has no sight of its own** and therefore sees no contacts at all — only public, system-or-wider events | A viewer with no ship has no sensors; §4.1 applied to a spectator yields an empty board |
| **"Advance a cycle" exists only on a demo deployment**, never production | It is a demonstration control, not a game action |
| **On a live world the view is unreachable without a watch**, and taking one leaves no trace | *GDD §9.6*: a watch is a read. No event, no notification, no timing difference |
| **Watch mode is unauthenticated and rate-limited** | It is a public surface |

Watch mode is the smallest client that is still honest: it renders the same tiles and the same feed through the same
redaction, and it can be built before any command surface exists.

---

## 9.1 A note on the hidden faction's channel

When the Continuity's secure channel ships (*GDD §9.6*, phase P7), it reaches the whole galaxy with no delay while
every other channel is bound by range and relays. Two client rules follow, and they are absolute:

- The channel's surface is **absent** for anyone without clearance — not disabled, not greyed, not hinted at in a
  filter list. An interface element that exists but is unavailable announces that something is there (*GDD §9.4*).
- Nothing in the ordinary feed may reveal that a message travelled instantly: no route metadata, no latency figure,
  no "delivered" marker that differs from any other channel's.

A third rule covers permanent loss (*GDD §9.14*). When a pilot is not recovered from an incursion, the interface
that greets the new pilot **MUST** be the ordinary first-run experience, identical for an ex-agent and for anyone
else who was not recovered. No different wording, no acknowledgement, no "you know what this was". The player
remembers; the interface does not.

The MVP client implements none of this. It is written here so that whoever builds the channel does not discover
these constraints afterwards.

---

# 10. What the client calls

Each screen maps to a small, fixed set of endpoints. Nothing else is permitted; a screen that needs data no endpoint
provides is a server change, not a client workaround.

| Screen | Endpoints |
| --- | --- |
| Sign in / register | `POST /v1/auth/register`, `POST /v1/auth/login` |
| Daily overview | `GET /v1/me` |
| Map | `GET /v1/map/tiles?path=…`, `GET /v1/systems/{id}` |
| Ship, station, market | `GET /v1/me`, `GET /v1/stations/{id}/market` |
| Buy, sell, repair | `POST /v1/commands` |
| Feed | `GET /v1/feed`, `WS /v1/stream` |
| Missions | `GET /v1/missions` |
| Crew | `GET /v1/teams` |
| Standing orders | `GET /v1/orders` |
| Any action | `POST /v1/commands` |
| A route | `POST /v1/commands:batch` |
| Costs shown before commitment | `GET /v1/rules` |
| Watch mode | `GET /v1/map/tiles`, `GET /v1/feed`, `WS /v1/stream` |

The gaps this document opened, both since closed:

| Needed | For | Note |
| --- | --- | --- |
| ~~`GET /v1/systems/{id}`~~ | Contacts and bodies in the current system | **Built**: bodies in sight or charted, contacts graded by the shared sensor ladder |
| ~~Spectator scope~~ | Watch mode | **Built**: `/v1/watch/overview`, `/v1/watch/map`, `/v1/watch/feed`, unauthenticated and behind `FEATURES_WATCH` |
| ~~`POST /v1/commands:batch`~~ | A route as one decision (§5.3) | **Built**: stops at the first refusal and reports how far it got |
| ~~`GET /v1/rules`~~ | Showing a cost before commitment (§5) | **Built**: AP costs and fuel rates only — no combat, NPC or Continuity tuning |
| ~~System extent~~ | Clipping the board to the rim (§4.1) | **Built**: `system.radius`, so no hex is offered that is not a place |
| ~~`GET /v1/stations/{id}/market`~~ | The station screen (§6) | **Built**: both sides of the spread, stock, held and average paid, priced on every view |
| ~~Cargo off-station~~ | Reading the hold away from a berth | **Built**: `GET /v1/me` carries `cargo` and the ship's maxima |
| ~~`GET /v1/teams`~~ | Finding a crew to join (§10) | **Built**: `join_team` needs an id, so the register of crews is public; who is in one is not |
| ~~Event channel~~ | Filtering the feed (§7) | **Built**: every view is stamped with the channel the server delivered it on, so the client never guesses |
| ~~Message sender~~ | Chat with a speaker (§7) | **Built**: `payload.from`, dropped by the same redaction that hides the text |
| ~~Contact ship id~~ | Targeting (§4.2) | **Built**: `ship_id` on resolved contacts only — a vague sighting is not a handle on a ship |
| ~~`GET /v1/orders`~~ | Editing standing orders (GDD §4.4) | **Built**: the form opens with what is set, so saving cannot silently replace it |
| ~~Descending from the galaxy~~ | Zooming in (§4) | **Fixed**: a region can be opened like a system, and every zoom level stays reachable from every other |
| ~~A region drawn as scattered points~~ | The region chart (§4) | **Fixed**: the region is a filled board like the system one, a hex per system or per patch of empty space, with the hex size fitted to the region's radius |
| ~~No coordinates on the boards~~ | Reading a position off the map (§8.1) | **Built**: q and r rulers around every board, pinned outside it, plus the coordinate in text beside any selection |

---

# 11. Delivery

The client is built in the order that makes each slice independently demonstrable.

| Slice | Delivers | Demonstrable as |
| --- | --- | --- |
| **C0** ✅ | Shell, auth, `GET /v1/me` | "A player can log in and see their day". Built |
| **C1** ✅ | Watch mode: galaxy and region maps on canvas, universe feed, textual chart | "Here is a living world" — no account needed. Built |
| **C2** ✅ | Map at three zooms, contacts, selection | "Here is where I am and what is near me". Built |
| **C3** ✅ | Commands: move, jump, dock, launch, scan | "I can fly". Built |
| **C4** ✅ | Market, cargo, repair | "I can trade". Built |
| **C5** ✅ | Feed, chat, missions, team | "I can talk and take work". Built |
| **C6** ✅ | Combat, standing orders | "I can fight, and I can be fought while away". Built |

C1 before C2 is deliberate: watch mode is the cheapest slice that proves the whole spine — tiles, feed, WebSocket,
redaction — and it is the artefact to show anyone who asks what the game is.

---

# 12. Open questions

| # | Question | Blocks |
| --- | --- | --- |
**None outstanding.** The answers are recorded in the sections they settle.

| Answered | Question | Answer |
| --- | --- | --- |
| U1 | Is watch mode production or demo-only? | Both, differently. Freely available on a demonstration deployment; on a live world it is a rationed Continuity capability (§9, *GDD §9.6*) |
| U2 | Hex rendering: SVG or canvas? | **Canvas** (§8.5) |
| U3 | Does the client keep past overviews? | Only the latest, so `GET /v1/me` needs no `world_day` (§3) |
| U4 | One confirmation per route or per hop? | One for the route (§5.3) |

---

# 13. Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.10 | 2026-08-29 | The region chart is now a filled hex board like the system one — one hex per system or per hex of empty space — with the hex size fitted to the region radius, empty space drawn rather than omitted, and summarised rather than listed in the textual chart. Both boards carry q and r rulers. |
| 0.9 | 2026-08-28 | Fixed three faults in the map: the galaxy map was empty and so offered nothing to click; a selected region had no way in; and the zoom breadcrumbs disabled themselves once you reached the galaxy. A station now carries its own colour on the board and keeps it once charted, with a legend and a matching mark in the textual chart. |
| 0.8 | 2026-08-28 | Slice C6 built, completing the client: attacking a contact from the map, and the standing orders screen. Resolved contacts now carry the `ship_id` that `attack` targets; vague ones still carry nothing. `GET /v1/orders` lets the orders form open with what is already set. A player-versus-player attack is reported as queued, because that is what it is. |
| 0.7 | 2026-08-28 | Slice C5 built: the feed with channel filters and a composer, live over the WebSocket and de-duplicated on event id against the HTTP page; the mission board; and the crew register with founding, joining and leaving. The server now stamps each event with its channel and names the speaker of a message. |
| 0.6 | 2026-08-28 | Slice C4 built: the station screen, the market, cargo and repair. `GET /v1/stations/{id}/market` prices both sides of the spread on every view and is readable only from the berth; `GET /v1/me` carries the hold so cargo is legible away from a station. Quantity has a stepper, typed entry and a one-click maximum that respects credits, stock and free hold at once. |
| 0.5 | 2026-08-28 | Slice C3 built: move, route, jump, dock, launch and scan. The route is one decision submitted as `POST /v1/commands:batch`, drawn with the server's own hex-line rule and reported honestly when it stops partway. `GET /v1/rules` supplies costs so the client never holds a balance literal, and the board clips to the system's rim so it cannot offer a hex that is not a place. |
| 0.4 | 2026-08-28 | Slices C0 and C2 built: sign-in, the play shell with a permanent AP counter, the daily overview, and the map at three zooms — galaxy and region from tiles, the system as a sight-bounded board with contacts and hex selection. `GET /v1/systems/{id}` closed the last endpoint gap. |
| 0.3 | 2026-08-27 | Watch mode built (slice C1): a canvas star chart with its textual peer, the universe feed, and the `/v1/watch/*` spectator scope. |
| 0.2 | 2026-08-27 | Answered U1–U4: watch mode serves both a demonstration deployment and, on a live world, the Continuity's rationed watch (§9); hex maps are drawn on canvas, which makes the textual map view mandatory rather than courteous (§8.4); the client keeps only the latest overview (§3); a route is one confirmation and a partial route is a result, not an error (§5.3). |
| 0.1 | 2026-08-27 | First UI/UX design for the MVP client and watch mode. |

---

*End of document.*
