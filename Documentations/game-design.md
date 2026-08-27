# Game Design Document

## *Frontier: The Seldon Era*

> **A persistent, browser-based multiplayer space strategy game inspired by the gameplay philosophy of
> *Frontier: Elite II* and by Foundation-style concepts of historical prediction, civilizational change and
> emergent history.**

| Field | Value |
| --- | --- |
| Status | Draft for review |
| Version | 2.5 |
| Date | 2026-08-27 |
| Companion | `Documentations/architecture.md` v0.2 (cited as *ARCH §n*) |
| Companion | `Documentations/detailed-design-mvp.md` v0.2 — MVP implementation detail |
| Audience | Designers, engineers, writers, reviewers |

---

# 0. About this document

## 0.1 What this document is

This document is **normative for behaviour**: what exists in the world, what players may do, and what the world does
in response. It is the source of truth for design intent.

It is **not** a technical specification. Data models, processes, storage, protocols and deployment belong to the
companion architecture document. Where the two disagree, this document wins on *what the game does* and the
architecture document wins on *how it is built*; either way, one of them is wrong and must be amended.

Version 1.0 of this document contained five sections of technical architecture (old §47–§51). They have been removed
in favour of the architecture document, so that implementation guidance has exactly one home. §10.4 retains the
design-level constraints that the architecture must satisfy.

## 0.2 Conventions

| Marker | Meaning |
| --- | --- |
| **MUST** / **MUST NOT** | An invariant. Changing it changes what the game *is*, and requires a decision recorded in §11.2. |
| **SHOULD** | A strong default. Deviating needs a stated reason. |
| **MAY** | Permitted and optional. |
| `[BALANCE]` | A tunable value. Every number so marked is indicative; the authoritative values live in versioned rule data (*ARCH §11.2*), not in this document. |
| `[ILLUSTRATIVE]` | An example, mock-up or scenario shown to convey feel. Not a specification. |

Cross-references use `§n.m` for this document and *ARCH §n* for the architecture document.

## 0.3 Glossary

| Term | Meaning |
| --- | --- |
| **Cycle** | The 24-hour period that is the game's fundamental unit of time. One cycle = one world tick. |
| **World day** | The integer counter of elapsed cycles since world creation. Used in every timestamped record. |
| **AP** | Action Points. The per-cycle budget that limits what a player can do (§3.2). |
| **Level** | One rung of the spatial hierarchy: Galaxy, Region, System, Planet, Sector, Local (§2.2). |
| **Planet** | The level below System, and any substantial object on it: planet, moon, station, asteroid. The level is named for its archetypal member, as *System* is; an object's `kind` distinguishes the rest. |
| **Sector** | A named area of a Planet's surface or structure. |
| **Hex** | The atomic cell of the map at any level. |
| **Address** | An object's position, expressed as one hex coordinate per level (§2.3). |
| **Scope** | How far an event or message carries: Local, Planet, System, Region, Universe (§7.7). |
| **Event** | The single record type behind chat, combat, discovery, economy and history (§7.6). |
| **Faction** | One of the three public political blocs: Empire, Republic, Pirates (§6.1). |
| **Team** | A player-created group; the primary multiplayer unit. Belongs to one faction (§6.5). |
| **Standing orders** | A player's configured behaviour while offline (§4.4). |
| **The Model** | The psychohistorical simulation of large-scale civilizational variables (§8.2). |
| **Deviation** | How far the observed world has drifted from the Model's expected trajectory (§8.3). |
| **The Continuity** | The hidden fourth faction, whose goal is to hold deviation inside an envelope (§9). |
| **Chronicle** | The permanent, public historical record of the world (§8.10). |

---

# 1. Vision

## 1.1 High concept

*Frontier: The Seldon Era* is a persistent multiplayer space game played in a web browser.

Players inhabit a large, continuously evolving galaxy represented by hierarchical hexagonal maps. They belong to
player-created teams, and every team declares one of three public factions: **Empire**, **Republic** or **Pirates**.

The game is deliberately **asynchronous**. One major cycle elapses every 24 hours. Players receive Action Points,
connect when convenient, make strategic decisions, interact with other players, and leave.

The game **MUST** reward planning, knowledge, diplomacy and optimisation. It **MUST NOT** reward reflexes, or reward
time spent online beyond the point where that time improves decision quality.

## 1.2 Design pillars

### Pillar 1 — A persistent universe

The galaxy continues to evolve while players are offline. It contains NPC populations, factions, an economy, trade,
piracy, exploration, infrastructure, political conflict, player teams, territorial influence and historical events.
Player actions contribute to that evolution; they are not the only thing driving it.

### Pillar 2 — One cycle per day

The fundamental rhythm is 24 hours. A player receives an AP budget and spends it across the day. AP **MUST**
represent meaningful activities, never individual clicks (§3.2).

### Pillar 3 — Short sessions

A casual player **MUST** be able to complete a satisfying daily turn in about fifteen minutes. Additional time
**SHOULD** buy better decisions, not more actions.

| Player type | Target session |
| --- | --- |
| Casual | ≤ 15 min |
| Regular | 15–30 min |
| Hardcore optimiser | up to ~60 min |

## 1.3 The core design triangle

Everything in the game resolves into three interacting dimensions.

```text
                         SPACE
                    Where are you?
                         │
                         ▼
              ┌──────────────────────────────────────────────────┐
│ LOCAL PLANET SYSTEM REGION TEAM FACTION UNIVERSE │
├──────────────────────────────────────────────────┤
│ 🚀 Cmdr. Smith                                   │
│ Anyone heading toward Alpha-3?                   │
│                                                  │
│ ⚠ Pirate activity detected                       │
│ 3 hexes north                                    │
│                                                  │
│ 🚀 Cmdr. Jones                                   │
│ Yes. ETA 2 cycles.                               │
│                                                  │
│ ⚔ Combat detected                                │
│ Sector 184,72                                    │
├──────────────────────────────────────────────────┤
│ Type message...                           [Send] │
└──────────────────────────────────────────────────┘
                    ▲           ▲
                    │           │
                  TIME      ALLEGIANCE
               What can      Who are you
               you do now?    with?
```

| Dimension | Realised as | Detailed in |
| --- | --- | --- |
| **Space** | A hierarchical hex world: Galaxy → Region → System → Planet → Sector → Local | §2 |
| **Time** | A 24-hour cycle with a limited AP budget | §3 |
| **Allegiance** | Three public factions, player teams, and one hidden fourth faction | §6, §9 |

## 1.4 Player fantasy

The player should feel like **one individual living inside a vast, persistent frontier civilization**.

They decide where to go, what to trade, what to explore, whom to fight, whom to trust, what information to share,
which faction to serve, which team to join, and which historical events to influence. The galaxy evolves around them,
and their actions reach the economy, the factions, territory and history.

> **Explore the frontier. Build your fortune. Choose your allegiance. Exchange information. Shape your team's
> destiny. Influence history. And discover whether the future predicted for civilization can actually be changed.**

## 1.5 Endgame philosophy

The game **SHOULD NOT** end in a permanent "one faction wins the galaxy". Instead, eras produce different historical
outcomes, and the next era begins from the consequences of the last (§8.11).

```text
ERA 3 — THE FALL OF THE FRONTIER          [ILLUSTRATIVE]

Empire:        Fragmented
Republic:      Expanded
Pirates:       Dominant in outer systems

Team Orion:    Prevented the collapse of Earth
Red Corsairs:  Controlled 17 major trade routes
Blackstar:     Discovered the lost archive
```

Players collectively write the history of the universe. That record is permanent (§8.10).

## 1.6 Non-goals

Stated explicitly, because each one has been a tempting direction at some point in the design:

1. **Not a real-time game.** No mechanic may reward being online at a particular moment, beyond ordinary social
   coordination.
2. **Not a tactical combat game.** Combat resolves in a few decisions and **MUST NOT** grow into a separate game
   (§5.4).
3. **Not pay-to-win.** Nothing that affects AP, combat outcomes, market access or information quality may be sold.
4. **Not a permanent victory ladder.** See §1.5.
5. **Not a legal agreement.** The Continuity's confidentiality protocol is fiction and **MUST NOT** be implemented as
   an enforceable real-world contract (§9.3).
6. **Not derivative.** See §1.7.

## 1.7 Inspirations and originality

The game takes broad inspiration from *Frontier: Elite II* — space travel, trading, mining, exploration, missions,
ship equipment and progression, piracy, bounty hunting, factions, reputation, political conflict, a persistent economy
— and from *Foundation* — psychohistory, statistical prediction, historical inertia, civilizational decline,
historical crises, knowledge preservation, unpredictable individuals and self-fulfilling predictions.

The universe, characters, ships, artwork, place names and narrative **MUST** be original. No copyrighted content from
either source may be reproduced.

---

# 2. The world

## 2.1 One unified hexagonal world

Galaxy view, system view, planet view and local view are **not separate maps**. They are different spatial resolutions
of one hierarchical hexagonal world.

> **Zooming changes spatial resolution, not the underlying world.**

This is an invariant. The same objects exist at every level; a ship remains the same ship regardless of the level at
which it is being observed.

## 2.2 The scale ladder

The world has six addressable levels. The number of levels is configuration and **MAY** change; the principle in §2.1
**MUST NOT**.

| # | Level | Contains | A hex represents | Example |
| --- | --- | --- | --- | --- |
| 0 | **Galaxy** | Regions | Strategic distance between stellar neighbourhoods | The galaxy map |
| 1 | **Region** | Systems | Several light years | The Sirius Reach |
| 2 | **System** | Planets | Interplanetary distance | Sol |
| 3 | **Planet** | Sectors | Orbital / surface approach | Earth, Luna, Anchor Station |
| 4 | **Sector** | Local areas | Regional surface distance | The Industrial Belt |
| 5 | **Local** | — | Tactical / exploration distance | Hex 42,19 |

The ladder and its names were settled in v2.2 (§11.1 M1). *Planet* names the level after its archetypal member;
moons, stations and asteroids occupy the same level and are distinguished by `kind`. *Sector* replaces v1.0's
"Planetary Region", which collided with the Region level.

The Universe is the container of the Galaxy, not an addressable level. A world deployment holds one Galaxy.

## 2.3 Addresses

An object's position is an **address**: one hex coordinate per level, from Galaxy downward.

```text
Galaxy:  (124, 87)
Region:  (3, 1)
System:  (31, 14)
Planet:  (208, 73)
Sector:  (11, 4)
Local:   (42, 19)
```

Two rules follow, and both matter for gameplay:

- **Distance is only meaningful between siblings.** Two hexes may be compared only if they sit at the same level
  under the same parent. There is no cross-level distance, because a hex means a different physical distance at each
  level (§2.6).
- **Containment is prefix matching.** Everything inside Sol shares Sol's address prefix. This is what makes "all
  events in this system", "everyone within radio range" and "stream only this part of the map" the same question
  asked at different depths.

Addresses give the world seamless zoom, spatial event propagation, localised communication, efficient map streaming
and persistent object locations.

## 2.4 Zoom

The player zooms without changing game modes.

```text
Galaxy ──▶ Region ──▶ System ──▶ Planet ──▶ Sector ──▶ Local
  Sol         Sirius     Earth    Industrial    Hex 42,17
                                    Belt
```

Zooming **MUST NOT** be a loading screen, a separate interface or a different rule set. It is a change of resolution
on one continuous map.

## 2.5 What each level shows

| Level | Shows |
| --- | --- |
| **Galaxy / Region** | Star systems, faction territories, major trade routes, strategic infrastructure, major events, long-distance travel |
| **System** | Star, planets, orbits, stations, in-system traffic, local infrastructure, system-scale events |
| **Planet** | Sectors, ports and landing sites, surface or orbital features, resources, settlements |
| **Sector / Local** | Individual hexes, ships, structures, terrain, encounters, exploration targets |

## 2.6 Scale versus simulation

Spatial scale and game mechanics remain conceptually separate. A hex at Galaxy level and a hex at Local level differ
by many orders of magnitude in physical size, but they are the same kind of object to the rules. The player
experiences one world, not four engines.

## 2.7 The inhabited world

The galaxy is populated whether or not any player is looking at it. NPC haulers move cargo, patrols hold faction
space, raiders prey on trade routes, and civilian traffic fills the lanes. This is not decoration: it is what makes
Pillar 1 (§1.2) literally true rather than a slogan.

NPCs carry four jobs, and every NPC design should be judged against them:

| Job | Why the game needs it |
| --- | --- |
| **Presence** | A system a player has never visited must already have a history when they arrive. |
| **Circulation** | Goods must move between stations without players, so shortages propagate and prices mean something (§5.3). |
| **Territory** | Faction control must be held by *someone*; a border with no patrols is a line on a map (§6.6). |
| **Opposition** | Combat must be available on the player's schedule, not only when another player happens to be nearby (§5.4). |

### Simulation fidelity varies with observation

The world is simulated everywhere, but not at the same resolution everywhere. This mirrors §2.6: just as spatial
scale is separate from the rules, **simulation fidelity is separate from the world's existence**.

```text
        Never yet visited                    Once seen, ever after
        ─────────────────                    ─────────────────────
        Population simulated as              Individual ships, with
        aggregate flows:                     position, cargo, hull:
          trade flow                           haulers on real routes
          patrol strength      materialise     patrols on real orders
          raider pressure      ──────────▶     raiders hunting real cargo
                                                        │
                                               the server keeps playing
                                               them whether or not
                                               anyone is watching
```

Three rules make this honest rather than a trick:

- **The aggregate never stops.** Trade flow, patrol strength and raider pressure evolve every cycle in every system,
  visited or not. A player arriving somewhere new finds it genuinely changed, not frozen.
- **Materialisation is one-way.** A crew that has once been seen **MUST NOT** be deleted when the last player
  leaves: the server goes on playing it. The frontier therefore accumulates real inhabitants wherever people have
  been, and a trader you met last month is still running their route when you come back.
- **An observer MUST NOT be able to tell** where the boundary lies. Individuals are drawn from the aggregate and
  their outcomes feed back into it: a hauler that completes a run moves real stock; a raider that dies lowers raider
  pressure. What a player sees is a sample of the population, never a separate reality.

### Why this shape, and not simply "simulate everything"

Beyond cost, the aggregate layer is the same quantity the historical model will later measure. Trade flow, patrol
strength and raider pressure *are* population-scale variables of the kind §8.2 tracks, and §8.5's claim — that large
NPC populations are statistically predictable while players are not — is only true if NPC populations are actually
represented statistically. Building the aggregate now is what makes psychohistory measurable later, rather than a
number invented on top of an unrelated simulation.

### Constraints

- NPCs **MUST** obey the same rules as players, without exception: fuel, cargo capacity, hex distance, weapon
  range, combat resolution — **and the same daily Action Point budget** (§3.2). An NPC is a ship with a pilot who
  happens to be a program, so nothing it does may be cheaper for it than for a human.

  This is what makes the population fair rather than merely plausible. A player can look at any crew in the galaxy
  and know it cannot out-act them today; a faction cannot be given an army that never tires; and no future system
  can quietly buy itself unlimited influence by spawning more ships. Where a shipped AI plays a ship, it spends the
  same budget through the same commands, so an absent player resolved from standing orders (§3.5) and an NPC
  running its route are the same machinery with different policies.
- NPC behaviour **MUST** be legible. A player who watches a hauler for three cycles should be able to predict the
  fourth. Unpredictability is the players' role (§8.5), not the population's.
- NPCs **MUST NOT** be a difficulty dial disguised as a world. Raider pressure rises because trade is rich and
  patrols are thin — never because a player is doing well.

---

# 3. Time and the turn

## 3.1 The cycle

One cycle is 24 hours. At the cycle boundary the world advances: the economy moves, NPCs and factions act, territory
is recomputed, missions are generated and expired, offline interactions resolve, the historical model updates, and
every player receives a new AP grant.

The cycle boundary is a fixed hour, announced to players. The world **MUST** advance whether or not any player is
online (§1.2 Pillar 1). What the world does at the boundary is listed in §3.3; how it is executed is *ARCH §9*.

## 3.2 Action Points

AP is the game's scarcity. Each player receives a per-cycle grant and spends it on meaningful actions.

```text
Daily AP: 10                                     [BALANCE]

Move                1 AP
Scan                1 AP
Trade               1 AP
Mine              2–3 AP
Combat              2 AP
Repair              2 AP
Mission stage     1–3 AP
Hyperspace jump   4–6 AP
```

Rules:

- Every AP cost is a `[BALANCE]` value. No cost is fixed by this document; §5.6 holds the canonical catalogue.
- AP **MUST NOT** be purchasable.
- **Half of unspent AP carries over, up to an administrator-defined ceiling.**

  ```text
  carry       = min(floor(unspent ÷ 2), carry_ceiling)     [BALANCE]
  new balance = daily grant + carry
  ```

  Missing a day therefore costs something real without wiping the day out, and the ceiling stops anyone banking a
  week to dump it in one session. Both the halving and the ceiling are `[BALANCE]`; the halving is the design
  commitment, the number is not.
- An action that costs AP **MUST** be a decision. Navigating menus, reading, planning, talking and looking at maps
  are free.
- The server owns the AP balance; the client may never assert it (§10.4).

## 3.3 What the world does each cycle

| Order | The world… | Detailed in |
| --- | --- | --- |
| 1 | Completes journeys in progress | §5.1 |
| 2 | Resolves encounters queued since the last cycle, including those involving offline players | §3.5, §5.4 |
| 3 | Moves the economy: production, consumption, prices, shortages | §5.3 |
| 4 | Acts as NPCs and factions | §6, §8.2 |
| 5 | Recomputes territory and influence | §6.6 |
| 6 | Generates and expires missions | §5.5 |
| 7 | Updates the historical model and publishes forecasts | §8.2, §8.3 |
| 8 | Lets the Continuity spend its intervention budget | §9.5 |
| 9 | Promotes significant events to wider scopes | §7.7 |
| 10 | Writes permanent records to the Chronicle and expires transient events | §7.8, §8.10 |
| 11 | Grants Action Points | §3.2 |
| 12 | Prepares each player's daily overview and digest | §3.4 |

The order is deliberate: destroyed cargo must affect prices in the same cycle, and the Continuity must act *after*
seeing the day's forecast, because reacting to deviation is its entire purpose (§9.1).

## 3.4 The player session loop

```text
                    CYCLE BOUNDARY
                         │
                         ▼
                  WORLD ADVANCES  (§3.3)
                         │
                         ▼
                    PLAYER LOGIN
                         │
                         ▼
                  DAILY OVERVIEW
                         │
                  ┌──────┴──────┐
                  ▼             ▼
               Team chat     World events
                  └──────┬──────┘
                         ▼
                    PLAN ACTIONS
                         │
                         ▼
                     SPEND AP
                         │
       ┌────────┬────────┼────────┬────────┐
       ▼        ▼        ▼        ▼        ▼
    Travel    Trade   Mission  Explore  Combat
       └────────┴────────┼────────┴────────┘
                         ▼
                 PLAYER INTERACTION
                         │
                         ▼
                  EVENTS GENERATED
                         │
                         ▼
                      LOG OUT
```

The **daily overview** is the first screen after login and **MUST** answer, without further navigation: what happened
to me, what changed near me, what my team said, what I can afford to do, and what expires today.

## 3.5 Playing while offline

Players **MUST NOT** be required to be online simultaneously. Every interaction has an offline resolution path.

```text
Player B is OFFLINE
        │
        ▼
Player A encounters B
        │
        ▼
Server resolves the interaction
using B's standing orders (§4.4)
        │
        ▼
Result is recorded as events
        │
        ▼
B is notified at next login
```

The rules applied to an absent player **MUST** be the same rules applied to a present one. Being offline may change
the *decisions* made on a player's behalf; it may never change the *physics*.

---

# 4. The player

## 4.1 Identity and progression

A player is an individual inside a much larger civilization — never a head of state.

| Property | Notes |
| --- | --- |
| Credits | Personal, never shared automatically with the team |
| Reputation | Per faction, and separately with the player's own team |
| Faction | Inherited from the team (§6.5) |
| Team | One at a time |
| Knowledge | A strategic resource (§8.9) |
| Location | An address (§2.3) |
| Missions | Active and offered |
| Discoveries | Permanent, and creditable to the discoverer |

Progression is **horizontal**: better ships, better equipment, better information, better relationships. There are no
levels that gate content, and no build that makes a player immune to another.

## 4.2 Ships

A ship is composed of Hull, Shields, Engine, Fuel, Cargo, Weapons, Sensors and Equipment.

Sensors deserve emphasis: they determine not only what a player can shoot but what a player can *know* (§7.2), which
is what makes an unarmed scout a viable and valuable role.

A player commands **exactly one ship**. This is a design commitment, not a simplification: the game is about one
individual inside a civilization (§1.4), and a player flying a fleet is a different game with a different fantasy.
Fleet actions belong to teams (§6.5), which is where coordination is supposed to cost something.

Losing a ship therefore matters, and replacing one is a real setback rather than a switch to the next hull in the
hangar.

## 4.3 Specialisations

Trader, Explorer, Miner, Bounty hunter, Pirate, Scout, Combat pilot.

These **MUST** be soft specialisations expressed through ship fitting, reputation and habit — never rigid character
classes chosen at creation and never changed.

## 4.4 Standing orders

Because most interactions involve an absent player (§3.5), a player's offline behaviour is a first-class design
object, configured deliberately rather than defaulted silently.

```text
STANDING ORDERS                                  [ILLUSTRATIVE]

Posture:            DEFEND
Engage if:          Hostile faction AND cargo value > 5 000 cr
Retreat at hull:    40 %
Surrender cargo:    Never
Radio auto-reply:   "Trading run. No hostile intent."
```

Editing standing orders is free (§3.2) and **SHOULD** be prompted during onboarding. A player who has never
considered them is a player who will be surprised by their first offline loss, which is a design failure rather than a
gameplay outcome.

---

# 5. Actions

## 5.1 Movement

Ships move through hexagonal space. Movement consumes AP and fuel, and **MAY** consume other resources depending on
the method.

| Action | Meaning |
| --- | --- |
| Move | Traverse hexes at the current level |
| Travel to | A high-level order that resolves into a multi-hex journey, possibly spanning cycles |
| Jump | Long-range travel between systems; the expensive, strategic option. Reach is limited by **both** fuel and the hull's own jump range `[BALANCE]`, so a bigger tank does not make a distant system reachable |
| Dock / Launch | Enter or leave a station or port |
| Scan | Reveal information about the surrounding hexes (§7.2) |
| Deploy probe | Leave a persistent sensor behind |

High-level commands **MUST** exist so that a long journey is one decision, not thirty. Micromanagement is not a
difficulty setting; it is a failure to design the command.

Journeys that exceed the remaining cycle continue across the boundary and complete during step 1 of §3.3.

## 5.2 Exploration

Scanning and exploration reveal locations, resources, wrecks, anomalies and other ships. Discoveries are permanent
and attributed: the first player to identify a location **SHOULD** be recorded in the Chronicle (§8.10) and **MAY**
name it, subject to moderation.

Exploration is one of the three sources of Knowledge (§8.9), and the primary route by which an ordinary player first
encounters evidence of the Continuity (§9.8).

## 5.3 Trade and the economy

The galaxy runs an evolving economy: commodity markets, supply and demand, mining, industrial production, fuel,
equipment, regional shortages, trade routes and station markets.

The economy **MUST** generate gameplay without a scripted quest behind each activity:

```text
Mining disaster
      ↓
Resource shortage
      ↓
Prices increase
      ↓
Traders move toward the region
      ↓
Pirates target the trade routes
      ↓
Security missions increase
```

Every step in that chain is an ordinary consequence of ordinary rules. That is the standard the economy is held to.

Prices **MUST** be local: a shortage is only an opportunity if knowing about it is an advantage (§7.1).

## 5.4 Combat

Combat is deliberately simplified and **MUST NOT** become a separate long tactical game. A normal encounter resolves
in a few decisions and fits inside the daily AP budget.

Choices available in an encounter: **Attack**, **Defend**, **Escape**, **Board**, **Use equipment**.

Resolution depends on ship characteristics, weapons, shields, hull, equipment, sensors, relative position, the
decision taken, and controlled randomness.

```text
Laser power:        82          [ILLUSTRATIVE]
Enemy shields:      54
Hit probability:    76 %
Damage:             31

Enemy counterattack:
Damage:             18
```

### Losing a ship

A destroyed ship does not kill its pilot: the life capsule ejects and is recovered. What the pilot loses is the
hull, its cargo, and a **salvage tax** — a percentage of their credits `[BALANCE]`, charged for the rescue.

The tax is a share rather than a flat fee on purpose. A fixed sum is trivial to a veteran and ruinous to a newcomer,
and a pilot who cannot afford to fly again has been removed from the game rather than set back in it.

Two rules protect the format:

- **A player who is offline is resolved by their standing orders (§4.4), under identical rules.**
- **Every resolution MUST be reconstructible.** The inputs to each roll are recorded, so a disputed outcome is
  answered by replay rather than by argument (*ARCH §9.3*).

## 5.5 Missions

Missions are generated from the state of the world, not from a script. The same strategic situation **SHOULD**
produce different missions for different factions:

```text
Situation: the Republic is establishing a relay in Sirius-4.

Republic  →  Establish the communication relay in Sirius-4.
Empire    →  Prevent Republic expansion in Sirius-4.
Pirates   →  Raid the construction convoy.
```

This creates natural conflict around shared locations and resources without anyone authoring the conflict.

Missions have stages, each costing AP `[BALANCE]`, and expire. A mission **SHOULD** state its objective and leave the
method to the player.

## 5.6 Action catalogue

The canonical list of player actions and their costs. All values are `[BALANCE]`; the authoritative source is the
rule data (*ARCH §11.2*). This table exists so that there is exactly one place to look, and one place to change.

| Action | AP | Other cost | Notes |
| --- | --- | --- | --- |
| Move (per hex, current level) | 1 | Fuel | Batched inside a "Travel to" order |
| Travel to destination | 1 per hex | Fuel | May span cycles |
| Jump (inter-system) | 4–6 | Fuel, engine wear | Strategic scale |
| Dock / Launch | 0 | — | Free; not a decision |
| Scan | 1 | — | Range and quality from sensors |
| Deploy probe | 1 | Probe | Persistent sensor |
| Trade (per transaction) | 1 | Credits | Per market, not per unit |
| Mine | 2–3 | Fuel, equipment wear | |
| Repair | 2 | Credits or parts | |
| Combat round | 2 | Ammunition, damage | |
| Board | 2 | Risk | Only after shields drop |
| Mission stage | 1–3 | Varies | Stated on the mission |
| Send message | 0 | — | Free at every scope |
| Edit standing orders | 0 | — | Free |
| Read, plan, view maps | 0 | — | Always free (§3.2) |

---

# 6. Allegiance

## 6.1 The three public factions

```text
                 EMPIRE
                /       \
        REPUBLIC ------- PIRATES
```

The factions represent different philosophies, not a good/evil alignment. Each **MUST** be a legitimate strategic
choice with real strengths and real costs.

## 6.2 Empire — *Order through authority*

| Strengths | Weaknesses |
| --- | --- |
| Military power, infrastructure, security, technology, central organisation, reliable services | Bureaucracy, taxes, restrictions, political obligations |

## 6.3 Republic — *Freedom through law*

| Strengths | Weaknesses |
| --- | --- |
| Commerce, civilian infrastructure, trade, diplomacy, independent worlds, political flexibility | Weaker centralised military, political constraints, slow mobilisation |

## 6.4 Pirates — *Freedom from law*

| Strengths | Weaknesses |
| --- | --- |
| Raiding, smuggling, black markets, hidden bases, mobility, opportunistic missions | Poor infrastructure, bounties, few legitimate services, hostility from both other factions |

Pirates **MUST** be a legitimate strategic choice, not the "evil" faction.

## 6.5 Teams

Players organise into teams. A team declares one faction; a player's faction is their team's faction.

```text
Universe
├── Empire     ── Team Alpha, Team Blackstar, …
├── Republic   ── Team Orion, Team Frontier, …
└── Pirates    ── Red Corsairs, Freebooters, …
```

| Team-level | Player-level |
| --- | --- |
| Faction, team chat, shared objectives, team missions, team reputation, shared intelligence, **MAY** hold shared assets | Ships, credits, equipment, progression, personal reputation |

The team is the primary multiplayer organisation. It **MUST NOT** be able to spend an individual's AP or credits.

A player need not belong to one. Until they join or found a team they are **independent**: they have no faction, no
faction standing and no faction missions, and they answer to nobody. Independence is a legitimate way to play, not an
unfinished registration — and it is the state every player starts in.

## 6.6 Territory and influence

Faction influence exists at every map level and evolves through player actions, team actions, missions, military
activity, trade, infrastructure and political events.

```text
       E E E E
     E E E R R
   E E R R R P P
     R R R P P
       P P P

E = Empire   R = Republic   P = Pirates
```

Territory is **dynamic** and **MUST NOT** be permanently assigned. Control is a consequence of sustained presence and
activity, recomputed every cycle (§3.3 step 5).

## 6.7 Reputation and defection

Reputation is tracked per faction and changes through action, not declaration.

A team **MAY** change allegiance. Defection **MUST** be a major political event rather than a menu operation:

```text
Team Orion (Republic)  ──▶  Defection  ──▶  Empire
```

Consequences **SHOULD** include reputation changes, asset changes, new missions, territorial shifts, new enemies and
altered faction relations. The defection itself is a Universe-scope event (§7.7) — everyone learns of it.

Note the interaction with §9.4: a Continuity agent's public defection changes nothing about their secret role, and
that dissonance is intentional.

---

# 7. Information

## 7.1 Information as gameplay

What a player knows is a resource as real as fuel. What a player receives depends on their location, their sensors,
the communication infrastructure they can reach, and their faction's intelligence.

| Vantage point | Typically knows |
| --- | --- |
| Local player | Precisely what is happening in their hexes, right now |
| System-level observer | That something is happening, roughly where, with a delay |
| Faction intelligence | Aggregated, filtered, and possibly wrong |

Because knowledge is unevenly distributed, it can be traded, hoarded, sold and faked (§8.9). This is the foundation
that makes the Continuity's information warfare possible (§9.5) rather than a bolted-on mechanic.

## 7.2 Visibility and sensors

Visibility is graded, not binary. The same event **MUST** be able to reach two players in different detail.

| Observer situation | Sees |
| --- | --- |
| In range, good sensors | Full detail: who, what ship, exact hex |
| In range, weak sensors | "Unidentified contact", approximate position |
| Out of range, relay coverage | A delayed summary (§7.5) |
| No coverage | Nothing at all |

The server decides what each player sees and sends only that; the client **MUST NOT** receive information it is meant
not to display (§10.4).

## 7.3 Communication channels

| Channel | Scope | Reach |
| --- | --- | --- |
| **Local** | Local | Radio range from the sender's hex (§7.4) |
| **Planet** | Planet | Everyone at or around that planet |
| **System** | System | Everyone in the system, subject to infrastructure |
| **Region** | Region | Faction and commercial networks |
| **Team** | Organisational | Team members, wherever they are |
| **Faction** | Organisational | Faction members, subject to rank and infrastructure |
| **Universe** | Universe | Announcements and major historical events |
| **Continuity** | Clearance | Invisible to everyone else (§9.6) |

Sending a message costs no AP at any scope (§5.6). Communication is how a 15-minute session becomes a social game.

## 7.4 Radio range and infrastructure

Ships communicate over limited physical ranges.

```text
Effective range = Base range × Antenna × Equipment × Environment
```

Beyond direct range, messages travel through stations, relays, satellites, beacons and faction networks:

```text
Ship A ──radio──▶ Relay ──network──▶ Team
```

Communication infrastructure is therefore strategically valuable, contestable, and a legitimate military target.

## 7.5 Communication delay

Long-distance communication **MAY** be delayed. The physics stays abstract; the purpose is to make distance matter.

```text
Message sent: "Pirates spotted in Sirius."      [ILLUSTRATIVE]
Distance: 8.2 ly
Estimated delivery: 3 h 14 m
```

Delay is off in the MVP and enabled later (§10.2). The design **MUST** keep delay optional per channel, because a
delayed team chat is a worse game, while delayed intelligence is a better one.

## 7.6 The event model

Chat and world events share one underlying model. A player message is simply an event of type `MESSAGE`.

```text
Event
├── timestamp        when
├── type             what kind
├── origin           where (an address, §2.3)
├── scope            how far it carries (§7.7)
├── visibility       who may ever see it
├── severity         how much it matters
├── participants     who was involved
└── payload          the specifics
```

This is a design commitment, not an implementation detail: it is what allows one merged feed (§7.9), one set of
visibility rules (§7.2), and one path from a skirmish to a line in the Chronicle (§7.7).

Event types include `COMBAT_STARTED`, `SHIP_ENTERED`, `SHIP_DESTROYED`, `TRADE_EVENT`, `DISCOVERY`,
`PIRATE_ACTIVITY`, `FACTION_WAR`, `TERRITORY_CHANGE`, `MESSAGE`.

## 7.7 Scope and propagation

Events inherit the spatial hierarchy. Scopes are **Local, Planet, System, Region, Universe**.

An event **MAY** propagate upward when it becomes significant enough:

```text
Local combat
      ↓
Major local battle
      ↓
Planet-wide conflict
      ↓
System-wide conflict
      ↓
Major historical event  →  Chronicle (§8.10)
```

Not every local event becomes a universe notification. Promotion is threshold-driven `[BALANCE]` and happens once per
cycle (§3.3 step 9). The promoted event **SHOULD** retain a link to the events that caused it, so that a player
reading history can trace a war back to the skirmish that started it.

## 7.8 Categories and lifetimes

| Icon | Category |
| --- | --- |
| 🚀 | Player |
| ⚠ | System |
| ⚔ | Combat |
| 💰 | Economy |
| 🔭 | Discovery |
| ☠ | Piracy |
| 🏛 | Politics |

| Event scope | Lifetime `[BALANCE]` |
| --- | --- |
| Local | Short-lived |
| Planet | Several cycles |
| System | Days to weeks |
| Promoted historical | Permanent (§8.10) |

## 7.9 The unified feed

The interface merges messages and events into one chronological feed, filtered by channel.

```text
┌────────────────────────────────────────────────┐
│ LOCAL PLANET SYSTEM REGION TEAM FACTION UNIVERSE │
├────────────────────────────────────────────────┤
│ 🚀 Cmdr. Smith                                 │
│ Anyone heading toward Alpha-3?                 │
│                                                │
│ ⚠ Pirate activity detected                     │
│ 3 hexes north                                  │
│                                                │
│ 🚀 Cmdr. Jones                                 │
│ Yes. ETA 2 cycles.                             │
│                                                │
│ ⚔ Combat detected                              │
│ Sector 184,72                                  │
├────────────────────────────────────────────────┤
│ Type message...                         [Send] │
└────────────────────────────────────────────────┘
```

The feed is the game's primary narrative surface. A player who reads only the feed **SHOULD** still understand what
is happening to their part of the galaxy.

---

# 8. History

## 8.1 The Foundation-inspired layer

The game maintains a large-scale model of civilization and lets players see, use, argue with and break its
predictions. The concepts borrowed are psychohistory, statistical prediction, historical inertia, civilizational
decline, historical crises, knowledge preservation, unpredictable individuals and self-fulfilling prophecy (§1.7).

The whole layer resolves to one loop:

```text
       THE MODEL
           │
           ▼
    Predicted future
           │
           ▼
     PLAYER ACTIONS
           │
           ▼
     Actual future
           │
           ▼
   Model recalculates
           │
           └──────▶ New prediction ──▶ …
```

> **Can civilization escape its predicted future?**

The players determine the answer. The game **MUST NOT** contain one.

## 8.2 The Model

The Model tracks large-scale variables that evolve gradually.

```text
DAY 182                                          [ILLUSTRATIVE]

Empire        Military 87   Economy 62   Stability 71   Legitimacy 54
Republic      Military 52   Economy 81   Stability 78   Legitimacy 73
Pirates       Influence 41  Economic power 48
```

Tracked variables include faction stability, military strength, economic health, legitimacy, pirate influence,
population migration, technological development, infrastructure and trade connectivity.

The Model observes **populations**. It **MUST NOT** take individual players as input, and it **MUST NOT** produce
statements about them (§8.4).

## 8.3 Forecasts and deviation

Forecasts are probabilistic and carry a confidence value.

```text
HISTORICAL FORECAST                              [ILLUSTRATIVE]

Sirius Region

Probability of armed conflict:    81 %
Probability of economic collapse: 43 %
Probability of pirate takeover:   29 %

Confidence: 76 %
```

**Deviation** is the single metric expressing how far the observed world has drifted from the Model's expected
trajectory. It is the Continuity's central concern (§9.9) and the trigger for historical crises (§8.7).

```text
Expected trajectory:  0 %
Current deviation:   +2.7 %
Critical threshold:  +8 %                        [BALANCE]
```

Confidence falls as players produce outcomes the Model did not expect. A world where confidence has fallen from 98 %
to 31 % is a world that has escaped its own prediction — and that is a legitimate, even desirable, outcome.

### Forecasts are a public good of variable quality

Anyone may read a forecast. Nobody buys the right to one, and no faction owns it: the Historical Institute (§8.8)
publishes to the galaxy, because a prediction that only the powerful can see is a conspiracy, not a science, and the
self-fulfilling loop of §8.6 requires that ordinary people can act on it.

What varies is **quality**, not access:

| A reader with… | Sees |
| --- | --- |
| No Knowledge, no local data | The headline probability, wide confidence interval, region-level only |
| Accumulated Knowledge (§8.9) | Narrower intervals, more variables, finer spatial resolution |
| Local presence and good sensors | Recent data the published forecast has not yet absorbed |
| Archive or Institute access | The Model's reasoning, not only its output |

Two consequences the design depends on. Because access is universal, a forecast **MUST NOT** be usable as a
gate on content or an advantage bought with money. Because quality is earned, Knowledge stays worth accumulating and
worth trading (§8.9) — what a well-informed player sells is not the forecast, which everyone has, but a *better
reading* of it.

## 8.4 Boundaries: prediction must never control players

The Model predicts populations and large-scale trends. It **MUST NOT** predict individuals.

| Permitted | Forbidden |
| --- | --- |
| "Probability of a pirate offensive: 78 %." | "Player Bob will attack Station Alpha tomorrow." |
| "This region is trending toward economic collapse." | "Team Orion will defect within three cycles." |

This is an invariant, not a guideline: a system that can predict a named player is a system that can be used to
target one, and player agency is the premise of the entire history layer. The architecture enforces it structurally
rather than by convention (*ARCH §12.1*).

## 8.5 Players as anomalies

Large NPC populations are statistically predictable. Players are not.

```text
Billions of NPCs   ──▶  statistically predictable
Player population  ──▶  increasing uncertainty
```

As players intervene, the Model loses accuracy — by design. Rare, sharp deviations surface as gameplay events:

```text
⚠ HISTORICAL ANOMALY                             [ILLUSTRATIVE]

Observed player activity has produced a
statistically improbable deviation.

Expected outcome: 84 %
Observed outcome: 17 %

Further analysis required.
```

Anomalies are the breadcrumbs of the long mystery (§9.8): they are what an attentive player notices first.

## 8.6 Self-fulfilling and self-defeating predictions

Publishing a forecast changes the world it forecasts. Both directions **MUST** be possible.

```text
Forecast: pirate invasion 70 %          Forecast: Empire collapse 80 %
        ↓                                       ↓
Empire buys weapons                     Players intervene
        ↓                                       ↓
Weapon prices rise                      Conditions change
        ↓                                       ↓
Pirates observe the activity            Collapse avoided
        ↓                                       ↓
Pirates decide to attack                Prediction fails
        ↓
Probability increases
```

A forecast is therefore never neutral information. Who receives it, when, and whether it is true are all playable
questions (§8.9, §9.5).

## 8.7 Historical crises

When deviation or instability crosses a threshold `[BALANCE]`, the Model identifies a **critical period**.

```text
╔══════════════════════════════════╗
║       HISTORICAL CRISIS          ║              [ILLUSTRATIVE]
║       THE SIRIUS CRISIS          ║
╠══════════════════════════════════╣
║ Empire control:      41 %        ║
║ Republic influence:  36 %        ║
║ Pirate influence:    23 %        ║
║ Critical period:     8 cycles    ║
╚══════════════════════════════════╝
```

A crisis is an announced window in which player action has outsized consequence. The game **MUST NOT** prescribe a
solution or a correct side. Crises are also the principal recruitment trigger for the Continuity (§9.3).

A crisis that runs its critical period without being resolved does not simply lapse. **Something answers it** —
see §8.12.

## 8.8 The Historical Institute

A fictional in-world organisation is the public face of historical analysis — working name **The Historical
Institute**. Its stated mission is to *preserve knowledge and civilization during periods of instability*.

It provides forecasts, archives, research, records and crisis warnings. It **SHOULD** remain somewhat mysterious in
early eras, and its relationship to the Continuity **SHOULD** remain ambiguous for a long time (§9.8).

## 8.9 Knowledge as a resource

**Knowledge** is a strategic resource, obtained through exploration, archives, research, sensors, missions,
discoveries, communication and ancient infrastructure. It improves forecast accuracy, strategic decisions, missions,
exploration and economic analysis.

Knowledge is tradable, and that is the point. A team holding *"a pirate fleet is preparing an attack"* may:

- keep it secret,
- sell it,
- give it to their faction,
- broadcast it,
- use it to move markets,
- use it to set an ambush,
- or publish a false version of it.

Information is thus a genuine multiplayer resource with the properties of a commodity and the risks of a rumour.

## 8.10 The Chronicle

Significant events become part of a permanent public record.

```text
DAY 183                                          [ILLUSTRATIVE]

BATTLE OF SIRIUS

Republic fleet destroyed.
Empire captured the station.
Pirate teams looted the wreckage.
```

The Chronicle records wars, discoveries, station destruction, territorial changes, team defections, economic crises,
major battles and civilizational transitions. It is written by promotion from the event stream (§7.7), never by hand.

The universe **MUST** have a collective memory. It is the reason a player's action can matter beyond their own
account, and it is the only data in the game whose loss would be unrecoverable in game terms.

## 8.11 Eras

The world moves through **eras** — long-lived civilizational states, each beginning from the consequences of the last.

```text
ERA I    Stability
ERA II   Historical Prediction
ERA III  Major Crises
ERA IV   Fragmentation
ERA V    Dark Age
ERA VI   Reconstruction
```

The sequence above is **illustrative, not scripted**: it is what the Model currently expects, and players may produce
a different one. Eras are distinct from the *narrative phases* of §9.12, which describe how much the player community
has discovered about the meta-game and happen only once.

### Era transitions are triggered by thresholds

An era changes when the Model's variables (§8.2) cross a configured boundary and stay across it for a sustained
period. Nothing else may trigger one:

- **No designer may fire an era transition by hand.** If a person can decide when the Dark Age begins, then players
  do not write the history of the universe (§1.5) — they attend it.
- **No single dramatic event is enough.** A transition requires the crossing to hold for a minimum number of cycles
  `[BALANCE]`. Hysteresis keeps a spike, a large battle or one bad cycle from flipping the world's state and
  flipping it back.
- Which variables, at what boundaries, is `[BALANCE]`. That the trigger is a threshold is not.

A transition is a Universe-scope event (§7.7) and a permanent Chronicle entry (§8.10): the galaxy is told that an age
has ended, and afterwards it can always be shown exactly when and why.

## 8.12 The Harrowing

> Numbered after §8.11 rather than beside §8.7 to leave the existing section numbers undisturbed. Read it as the
> consequence of a crisis nobody resolved.

When a historical crisis (§8.7) runs its critical period unresolved, the deviation does not merely persist. **Ships
arrive.**

They are not of the Empire, the Republic or the Pirates, and they are not of the Continuity. They are powerful,
unfamiliar and silent: no demands, no diplomacy, no terms, no visible motive. Working names: the event is **the
Harrowing**; the vessels are **Harrowers**. Both are placeholders until the fiction is written, and both **MUST**
remain original (§1.7).

The design intent is a single, sharp answer to a question the history layer otherwise leaves abstract: *what is
actually at stake if the trajectory is abandoned?* Until the Harrowing, deviation is a number on a forecast. After
it, deviation is the thing that brings ships.

### What an incursion does

| | |
| --- | --- |
| **Trigger** | A crisis whose critical period expires with deviation still past the threshold `[BALANCE]` |
| **Scale** | A region, not a system: several systems are contested at once |
| **Duration** | An episode with an end — an incursion **MUST** resolve, one way or another |
| **Announcement** | Universe scope (§7.7); the galaxy learns of it the cycle it begins |
| **Record** | Every loss is permanent and enters the Chronicle (§8.10) |
| **Aftermath** | The surviving state is where the next era starts (§8.11) |

### Rules

These constrain the system as firmly as §9.2 constrains the Continuity, and for the same reason: a threat that
cannot be reasoned about is not an opponent, it is weather.

- **Harrowers MUST obey the rules every other ship obeys** — fuel, cargo, hex distance, weapon range, combat
  resolution and the daily Action Point budget (§2.7). They are dangerous because of what they fly and how many of
  them there are, never because they are exempt. *A player who loses to one must be able to see why, and a player
  who studies one must be able to learn something usable.*
- **An incursion MUST be survivable by coordinated players and MUST NOT be survivable alone.** This is the one
  place the design deliberately requires cooperation across teams — and, if the players choose it, across factions.
- **The game MUST NOT prescribe the response.** The threat is common; what anyone does about it is not. The Empire
  may militarise, the Republic may evacuate, a pirate crew may loot the evacuation, and a trader may simply get
  rich selling hull plate. Refusing to fight is a legitimate choice with legitimate consequences.
- **Harrowers MUST NOT be farmable.** They are an emergency, not a resource: an incursion that becomes a reliable
  income has stopped being a crisis.
- **Losing MUST be possible.** If an incursion cannot be lost, it is a cutscene. What is lost — stations, systems,
  a faction's grip on a region — is what the next era inherits.

### What it does to the Model

An incursion is the largest deviation event the world can produce, and the Model is not exempt from it: confidence
falls sharply while one is under way (§8.3), because a galaxy under attack stops behaving like the population the
Model was fitted to. A region that survives one returns to a *different* expected trajectory, not the old one.

### The open thread

Whether the Continuity knows this is coming — whether the trajectory it defends is precisely the corridor in which
the Harrowing does not arrive — is deliberately unresolved in the fiction, and is recorded as an open design
question (§11.2 Q9). Players **MUST NOT** be able to settle it from any published number.

---

# 9. The Continuity

> **Restricted design material.** Sections 9.1–9.13 describe content that players are intended to discover through
> play. It is documented here in full because it cannot be built otherwise, and because its secrecy requirements are
> architectural (*ARCH §12.1*).

## 9.1 Premise

The universe publicly recognises three factions. A fourth organisation exists secretly:

> **The Continuity**

Its purpose is not to conquer territory or accumulate wealth. It is to **keep civilization sufficiently close to the
trajectory the Model predicts**.

That objective is not "make everything good", and not "make our faction win". It may require terrible things:

```text
Predicted trajectory                             [ILLUSTRATIVE]

Empire collapses → Republic rises → Pirates control the frontier
→ major war → civilizational collapse → reconstruction
```

If the Continuity considers this trajectory necessary, then players *preventing* the Empire's collapse is what
provokes intervention. This is the inversion that makes the faction interesting: it is not opposed to the players'
goals, it is opposed to their deviation.

Empire, Republic and Pirates are **political identities**. The Continuity is a **secret meta-game identity**. A
player has one of the first and may also have the second.

## 9.2 What the Continuity is not

These constraints are load-bearing. Without them, ordinary players correctly conclude that their actions do not
matter, and the game loses its premise.

| The Continuity **MAY** | The Continuity **MUST NOT** |
| --- | --- |
| push, nudge, delay, accelerate, hide, reveal | force |
| shift probabilities | determine outcomes |
| act through information, markets, NPCs, missions, technology and communication | write directly to player-owned ships, credits or cargo |
| know more than others | know everything |
| be almost everywhere | be everywhere at once |

Concretely, its power is bounded by `[BALANCE]` budgets: limited agents, limited interventions per cycle, limited
resources, limited knowledge, and imperfect predictions.

**The budgets scale with the size of the world, not with the number of players.** A galaxy twice as large gets
roughly twice the intervention budget, so the Continuity's reach *per system* stays constant:

```text
interventions per cycle ≈ systems ÷ systems_per_intervention        [BALANCE]
agent ceiling           ≈ systems ÷ systems_per_agent               [BALANCE]
```

Two things follow, and both are the point. A growing galaxy does not slip out of the Continuity's grip, so the
premise survives expansion. And a growing *population* does not strengthen it, so the odds facing any individual
player never worsen because the game got popular — which is what §9.2's whole table exists to protect.

It manipulates probabilities in the small:

```text
Expected:                    After intervention:              [ILLUSTRATIVE]
Empire victory     61 %      Empire victory     67 %
Republic victory   29 %      Republic victory   23 %
Pirate victory     10 %      Pirate victory     10 %
```

It does not press a button labelled *"Empire wins"*.

## 9.3 Membership

### The organisation exists before any player joins it

The Continuity is **NPC-operated from the moment it exists in the world**. It runs its own agents, spends its own
budget and shapes events long before the first player is invited. Player recruitment is a later addition to a working
organisation, never its creation.

This ordering does most of the narrative work by itself:

- **The evidence players eventually find is real.** By the time anyone notices a pattern (§9.8), the interventions
  that produced it actually happened, at recorded times, for reasons the Model can be shown to have had. Nothing is
  retrofitted, and nothing needs to be.
- **A recruit joins something.** They get a handler, a cell and a clearance tier that already existed (§9.6), rather
  than founding a conspiracy of one.
- **Declining costs the world nothing.** If no player ever accepts, the Continuity carries on. That is what makes
  declining genuinely free (see below) rather than a refusal to let the story proceed.

The delivery consequence is recorded in §10.3: the first shipped form of §9 is the AI, and player agents follow.

### Recruitment

The Continuity **MUST NOT** be selectable at character or team creation. Players are invited, rarely, after doing
something notable: an exceptional discovery, participation in a historical crisis (§8.7), noticing an anomaly
(§8.5), an unusual chain of decisions, exceptional reputation, or finding Continuity-related evidence.

```text
Major historical event
        │
        ▼
Player participates
        │
        ▼
Hidden evaluation
        │
        ├── No invitation  (silent, no record shown to the player)
        │
        └── Candidate ──▶ Secret invitation ──┬── Accept ──▶ Agent
                                              └── Decline
```

The invitation should feel like an achievement, and gives players a reason to show up for major historical events
even when there is no immediate reward.

```text
┌──────────────────────────────────────────┐    [ILLUSTRATIVE]
│             CLASSIFIED MESSAGE           │
├──────────────────────────────────────────┤
│ Commander,                               │
│                                          │
│ Your actions during the Sirius Crisis    │
│ have attracted our attention.            │
│                                          │
│ There are events occurring in the        │
│ galaxy that you do not yet understand.   │
│                                          │
│ We would like to offer you access to     │
│ information unavailable to the public.   │
│                                          │
│ This invitation is confidential.         │
│                                          │
│ [ ACCEPT ]              [ DECLINE ]      │
└──────────────────────────────────────────┘
```

### The protocol

Acceptance requires agreeing to a fictional in-universe confidentiality commitment, presented as a classified
document: not to disclose Continuity operations, personnel, forecasts, objectives, internal communications or
interventions to players outside the organisation.

> **This is a role-playing commitment and MUST NOT be implemented as a real-world legal agreement.** No enforceable
> contract may be required to play. No real identity information may be collected for it. See §1.6.

### Declining

Declining **MUST** be entirely legitimate and **MUST NOT** be punished in or out of game. The player **MAY** be told
the offer will not return, or it **MAY** return after a long interval `[BALANCE]`. The mystery itself is part of the
reward for having been noticed.

## 9.4 Two identities

An agent does **not** leave their faction. Their public identity is unchanged, and their secret role is visible only
in Continuity-specific interfaces.

```text
                 PLAYER
          ┌─────────┴─────────┐
          ▼                   ▼
   PUBLIC IDENTITY      SECRET IDENTITY
   Republic             Continuity
   Team Orion           Agent Node 37
   Trader               Operation JANUS
```

Two rules make this work:

- **Agents exist inside every faction.** No player may ever be able to say "all Continuity members are Empire". An
  agent may plausibly be an Imperial officer, a Republic politician or a pirate captain — and **MAY** sincerely
  believe they are serving that faction.
- **Agents MUST NOT be publicly identifiable.** There is no Continuity rank, badge, colour, icon, title or hint
  visible to anyone else, and none may be introduced. In the interface, a player's hidden affiliation reads only as:

```text
Faction:               Empire
Team:                  Blackstar
Reputation:            Imperial +72
Unknown affiliations:  ???
```

Only specific in-game evidence can reveal a hidden membership (§9.8). This is a hard requirement with architectural
consequences: secrecy must survive not just the interface but error codes, response timing, statistics and the
ledger (*ARCH §12.1*).

## 9.5 Operations

Agents receive missions invisible to everyone else. Two properties distinguish them from faction missions: they state
an **outcome** rather than a method, and they carry a concealment constraint.

```text
CLASSIFIED OPERATION: JANUS                      [ILLUSTRATIVE]

Public situation:
Republic forces are approaching Sirius-7.

Historical requirement:
Sirius-7 must remain under Republic control for the next 6 cycles.

Objective:
Ensure the Republic convoy reaches Sirius-7.

Constraints:
Do not reveal Continuity involvement.

Reward:
Historical stability +0.8 %
```

```text
CLASSIFIED OPERATION: MERIDIAN                   [ILLUSTRATIVE]

Historical requirement:
The Empire must lose control of Sirius-4.

Objective:
Delay Imperial reinforcement by 2 cycles.
Do not directly attack Imperial forces.

Recommended:
Manipulate trade availability.
```

The player decides how: trade, intelligence, persuading another player, escorting a convoy, moving a market, delaying
an enemy, spreading information, withholding it, or completing an apparently unrelated mission. Preserving that
choice is what keeps an agent a player rather than an instrument.

### Methods

The Continuity almost never appears directly. It works through **information** (leaks, rumours, fabricated
intelligence, selective disclosure), **economics** (market manipulation, hidden subsidies, artificial shortages,
funding), **NPCs** (politicians, officers, traders, scientists, criminal organisations), **missions** (creating and
modifying them), **technology** (introducing or suppressing developments) and **communication** (shaping what reaches
whom).

### Budgets

```text
Continuity resources:  3                         [BALANCE]
Interventions:         1
Classified intel:      2
```

Budgets regenerate slowly. An agent's advantage **MUST** remain *better information, secret objectives and the
ability to influence events* — never raw power (§9.2).

## 9.6 Cells, clearance and secret communication

The organisation is compartmentalised. An agent knows their own identity, their handler, their current operation and
their clearance level — and nothing else.

```text
              CONTINUITY
             Central Model
          ┌────────┼────────┐
        Cell A   Cell B   Cell C
          │        │        │
        Agent    Agent    Agent
```

| Clearance | Sees |
| --- | --- |
| 1 | A local operation, with no stated reason |
| 2 | Regional historical objectives |
| 3 | System-level trajectory |
| 4 | The civilizational model |
| 5 | The Plan |

A newly recruited player might know only *"something terrible will happen if Sirius-7 falls"*, and not why. Agents
**MUST NOT** be shown the membership list; two agents may sit on opposite sides of a war and cooperate without ever
learning each other's identity. Compartmentalisation makes the organisation resilient, makes exposure partial, and
makes paranoia a feature.

Agents share a secure channel that **MUST NOT** resemble faction chat and **MUST** be invisible to everyone else.

```text
CONTINUITY // SECURE                             [ILLUSTRATIVE]

NODE 17:  Historical deviation +2.1 %
NODE 04:  Republic intervention successful.
NODE 17:  Proceed with JANUS.
MODEL:    Trajectory confidence 81.4 %
```

Messages **MAY** be delayed, routed through special infrastructure, or restricted by clearance.

## 9.7 Betrayal and exposure

An agent can betray the organisation, and the game **SHOULD** support it as gameplay rather than prevent it.

```text
Agent leaks classified information
        ↓
Other players learn something true
        ↓
Historical trajectory changes
        ↓
Continuity responds
```

Consequences **MAY** include loss of privileges and access, being hunted, new missions, becoming a tracked anomaly,
or triggering a storyline. All consequences **MUST** be in-game. Breaking a fictional confidentiality commitment
**MUST NOT** carry any out-of-game penalty (§1.6, §9.3).

Secrecy also produces the design's strongest social effect. When a Republic player asks *"why did you abandon the
convoy?"* and the answer is *"I had another objective"*, no one can tell whether that was strategy, betrayal,
selfishness or an intervention. The Continuity injects durable uncertainty into every player relationship — and it
does so even for the majority of players who never learn it exists.

## 9.8 Discovery

Discovery by ordinary players is a long-term arc, not a reveal.

```text
Something strange is happening.
        ↓
Some events are statistically improbable.
        ↓
Someone appears to be shaping events.
        ↓
The same individuals recur behind unrelated events.
        ↓
There is a fourth player in this game.
```

Discovery **MUST NOT** deliver the whole picture at once. A player who finds a classified document learns that
*Operation MERIDIAN* exists and aims to "maintain historical trajectory" — and not who issued it, how large the
organisation is, what the phrase means, whether the prediction is sound, or whether the organisation is benevolent.

The mystery is a permanent feature of the world, not a puzzle with a solution date.

## 9.9 Deviation as the Continuity's metric

The agent-facing expression of §8.3:

```text
HISTORICAL DEVIATION                             [ILLUSTRATIVE]

Expected trajectory:  0 %
Current deviation:   +2.7 %
Critical threshold:  +8 %

        -5%          0%          +5%
         └───────────┼───────────┘
              stable envelope
```

The agent's job is to keep the world inside the envelope. Exceeding the threshold triggers a historical crisis
(§8.7) — which is the same event ordinary players see, from the other side.

## 9.10 The paradox and the twist

The Continuity believes history must remain predictable. Its own interventions change history.

```text
Intervention → world changes → Model changes → new intervention required → …
```

Two revelations follow, and both **SHOULD** be reachable only late:

1. **The Continuity may be causing some of the events it exists to prevent.**
2. **The Continuity may not be the villain.** Its model may predict a catastrophe — fragmentation, massive population
   loss, a long dark age, eventual recovery — and conclude that interference produces something worse. Its mission
   becomes *allow the smaller catastrophe in order to prevent the greater one*.

At that point Continuity players and ordinary players can hold the same facts and still disagree, which is the
philosophical position the whole design has been building toward.

## 9.11 The three-level game

| Level | Content | Who plays it |
| --- | --- | --- |
| **1 — Individual** | Ship, credits, missions, exploration, combat | Everyone |
| **2 — Political** | Team, faction, territory, economy, diplomacy, war | Most players |
| **3 — Historical** | The Model, forecasts, crises, the Continuity, civilizational trajectory | Players who go looking |

Levels 1 and 2 **MUST** be complete and satisfying on their own. Level 3 is discovered, never required. A player who
never learns the Continuity exists **MUST** still be playing a good game.

## 9.12 Narrative phases

How much the *player community* has discovered. These happen once, at world scale, and are distinct from the
recurring eras of §8.11.

| Phase | Name | The community believes |
| --- | --- | --- |
| I | The Frontier | This is a normal three-faction space game |
| II | The Pattern | Strange correlations link unrelated events |
| III | The Forecast | Historical predictions exist and can be obtained |
| IV | The Hand | Someone is manipulating events |
| V | The Continuity | A small number of players know the fourth faction exists |
| VI | The Crisis | The Model predicts a civilization-scale catastrophe |
| VII | The Choice | Follow the plan, or break it |

The final question is deliberately left open:

> **Is the Continuity preserving civilization, or preventing civilization from evolving?**
>
> **Is the predicted future actually the best future?**

## 9.13 The most important design rule

> **The Continuity can manipulate probabilities, but it cannot determine outcomes.**

It can push, nudge, delay, accelerate, hide and reveal. It can never force.

The players remain the authors of history:

> **The future may be predictable, but it is not predetermined.**

If any proposed Continuity mechanic conflicts with this rule, the mechanic is wrong.

---

# 10. Scope

## 10.1 MVP

The first playable version stays small. Everything below is required; nothing below is optional.

| Area | In the MVP |
| --- | --- |
| **World** | Hierarchical hex map, galaxy, star systems, zoom, basic faction territories |
| **Player** | Account, credits, AP, location, reputation, standing orders |
| **Ship** | Hull, shields, fuel, cargo, one weapon, basic equipment; one active ship |
| **Movement** | Hex movement, AP and fuel consumption, journeys across cycle boundaries |
| **Economy** | Buy, sell, cargo, basic station markets |
| **Exploration** | Scan, discover locations, basic events |
| **Combat** | NPC encounters, player encounters, simplified resolution, offline resolution |
| **Population** | Aggregate NPC simulation in every system; haulers, patrols and raiders materialised where observed (§2.7) |
| **Multiplayer** | Teams, the three factions, team chat, local communication |
| **Events** | Local, Planet, System and Universe scopes with the unified feed |
| **Cycle** | The full daily advance of §3.3 steps 1–5, 11, 12 |

Deliberately **absent** from the MVP but designed for: communication delay, relays, missions beyond a basic form,
defection, psychohistory, the Chronicle and the Continuity.

## 10.2 Deferred systems

Designed, not yet built. Each has a defined attachment point in the architecture (*ARCH §18*), so none of them
requires reopening the foundations.

| System | Depends on | Notes |
| --- | --- | --- |
| Advanced ship fitting | MVP ships | |
| Mining, smuggling | Economy | New actions and rules only |
| Bounty system | Combat, reputation | Driven by `SHIP_DESTROYED` events |
| Player-owned stations, colonisation | World, economy | New location kinds with owners |
| Advanced faction intelligence | Information (§7) | |
| Communication relays and delay | Comms (§7.4, §7.5) | Off by default in the MVP |
| Advanced economy, dynamic faction wars | Economy, territory | Replaces cycle steps 3–5 |
| Player-created missions | Missions | A second mission source |
| Fleet battles | Combat | Resolution already takes participant sets |
| Advanced exploration | Exploration | |
| **The Harrowing** (§8.12) | Historical crises, fleet battles, advanced combat | The one system that requires cross-team cooperation; needs an opponent that scales beyond one player |
| Historical archives, prediction, crises, eras | The Model (§8) | Needs months of real event data to tune |
| Knowledge trading | Knowledge (§8.9) | |
| Procedural historical events | Event promotion (§7.7) | |
| **The Continuity** | Everything above | Deliberately last (§10.3) |

## 10.3 Delivery order

The build sequence, its rationale and its phase gates live in *ARCH §17*. Two ordering decisions are design
decisions rather than engineering ones, and are recorded here:

1. **The Model (§8) ships after months of live play.** Its variables cannot be tuned against a world that has no
   history. Until then, forecasts do not exist in the fiction either.
2. **The Continuity (§9) ships last.** It only means anything once players have a history to deviate from, and
   its secrecy requirements need a mature world to be tested against. Introducing it early would spend the reveal on
   an empty galaxy.
3. **The Continuity ships as an AI first, and recruits players second.** Its first release operates entirely through
   NPC agents (§9.3). Player recruitment is a separate, later release, so that by the time anyone is invited the
   organisation has a real history of interventions to have been invited into.

## 10.4 Design constraints on implementation

The design imposes the following on any implementation. The architecture document describes how each is satisfied;
this section states *why the design requires it*, so that a proposed shortcut can be evaluated against intent.

| # | Constraint | Because |
| --- | --- | --- |
| C1 | **The server is authoritative; the browser is untrusted.** The client submits intents; the server decides outcomes and owns AP, credits, position, damage, cargo, combat results and ship state. | A persistent shared world whose state can be asserted by a client is not persistent and not shared. |
| C2 | **The simulation runs independently of any client.** | The world evolves while everyone is offline (§1.2, §3.1). |
| C3 | **Chat and world events use one model.** | The unified feed (§7.9), uniform visibility (§7.2) and promotion to history (§7.7) all depend on it. |
| C4 | **Visibility is computed server-side, per viewer.** The client never receives what it must not show. | Information is a resource (§7.1); a client-side filter is a client-side leak. |
| C5 | **The client receives only the detail its current zoom requires.** | The world must be able to grow without the client growing with it (§2.4). |
| C6 | **Outcomes are reconstructible.** Inputs to random resolution are recorded. | Disputes are answered by replay (§5.4), and the Chronicle must be trustworthy (§8.10). |
| C7 | **Balance values are data, not code.** | Every number in this document is `[BALANCE]`; designers change them without a release. |
| C8 | **The Model cannot read individual players.** | §8.4, enforced structurally rather than by convention. |
| C9 | **Continuity membership must not be inferable** from any interface, response, error, timing, statistic or ledger entry. | §9.4; a leak is unrecoverable. |
| C10 | **The confidentiality protocol creates no real-world obligation.** | §1.6, §9.3. |

---

# 11. Design change control

## 11.1 Modifications introduced in v2.0

Version 2.0 restructures version 1.0 without discarding design content. The following changes go beyond editing and
should be reviewed as design decisions. Each can be reverted independently.

| # | Modification | Rationale |
| --- | --- | --- |
| **M1** | **Canonical six-level scale ladder** (§2.2): Galaxy → Region → System → Planet → Sector → Local. "Planetary Region" renamed **Sector**. | v1.0 used an eight-noun hierarchy in one section and a four-level one in three others, and "Planetary Region" collided with the Region level. v2.0 additionally proposed renaming *Planet* to *Body* because the level must also carry moons, stations and asteroids; that was **rejected in v2.2** — the level keeps the name of its archetypal member, and `kind` carries the distinction. |
| **M2** | **Technical architecture removed** (old §47–§51) and replaced by design constraints C1–C10 (§10.4) plus the companion document. | Two documents describing the same system drift. Behaviour and structure now have one home each. |
| **M3** | **Normative conventions introduced** (§0.2): MUST/SHOULD/MAY, `[BALANCE]`, `[ILLUSTRATIVE]`. | v1.0 stated invariants and tunables in the same voice ("Possible…", "can…"), so readers could not tell which numbers were decisions and which were examples. |
| **M4** | **The Continuity consolidated** into §9 from twenty-one scattered sections (old §56–§75). | The material restated the same six ideas three to four times, and its subsections sat at the same heading level as unrelated top-level sections. No design content was dropped. |
| **M5** | **The Continuity's limits expressed as a capability list** (§9.2) rather than a warning. | "Don't make them overpowered" is not checkable. "May shift probabilities, may not write to player-owned entities" is. |
| **M6** | **Standing orders promoted to a first-class concept** (§4.4). | v1.0 mentioned "configured defensive behaviour" once, inside the offline-play section, though it governs the outcome of most player-versus-player contact. |
| **M7** | **Single action/AP catalogue** (§5.6). | Costs appeared in one illustrative block and nowhere else; the catalogue gives designers one place to look and one place to change. |
| **M8** | **Explicit non-goals** (§1.6). | Several were implicit and repeatedly at risk: no real-time play, no pay-to-win, no tactical combat game, no legal agreement. |
| **M9** | **Deviation defined once** (§8.3) and referenced by crises (§8.7) and the Continuity (§9.9). | v1.0 defined the metric inside the Continuity material, leaving crises without a stated trigger. |
| **M10** | **Eras and narrative phases separated** (§8.11 vs §9.12). | v1.0 contained two overlapping six- and seven-step progressions. They describe different things: recurring world states, and one-time community discovery. |
| **M11** | **"Turn" replaced by "cycle"** throughout; "world day" reserved for the counter. | v1.0 used "turn" for the 24-hour period, for a mission duration and for a player's session. |
| **M12** | **Authorial voice removed.** | v1.0 contained first- and second-person commentary ("I would make…", "your game") and duplicated conversational fragments, which read as notes rather than specification. |
| **M15** | **The Harrowing added (§8.12)**: an unresolved historical crisis triggers an incursion of powerful alien vessels, which players fight to restore the balance. | Deviation was an abstraction — a number on a forecast with no visible stake. The Harrowing makes the cost of abandoning the trajectory concrete, gives the cooperative end of the game a reason to exist, and supplies §8.11's eras with something that actually ends one. Constrained hard (no exemptions, must be losable, must not be farmable, response never prescribed) so that it stays an opponent rather than weather. |
| **M14** | **Materialised NPCs persist and are played by the server** (§2.7), rather than dissolving back into the aggregate when the last observer leaves. Adds the salvage tax (§5.4), the hull's own jump range (§5.1), and states that an unteamed player is *independent* (§6.5). | Answers to the implementation questions S1–S6. Dissolution made a system's inhabitants a function of who was watching, which contradicts the persistence §2.7 is there to promise; the cost of keeping them is bounded by the systems players have actually visited. The flat destruction penalty was replaced by a share of credits because a fixed sum removes a poor pilot from the game rather than setting them back. |
| **M13** | **The NPC population promoted to a design section (§2.7)**, with simulation fidelity tied to observation, and moved into the MVP along with cycle step 4. | v1.0 and v2.0 mentioned NPCs in six places without ever saying what they are for or how many there are. A persistent universe (§1.2) in which nothing happens unless a player causes it is not persistent, and the aggregate layer §2.7 introduces is the same quantity §8.2 will later measure. |

## 11.2 Open questions

Decisions the design still owes. Each is blocking something concrete.

Identifiers are stable: an answered question is removed from this table rather than renumbered, and its answer
is recorded in §11.4 and in the section it settles. Gaps in the numbering mean *answered*, not *lost*.

| # | Question | Blocks |
| --- | --- | --- |
| **Q8** | May teams own shared assets (§6.5), and who controls them on disband? | Team model; station ownership later |
| **Q9** | Does the Continuity know that the trajectory it defends is the corridor in which the Harrowing (§8.12) does not arrive? | Whether §9 is a conspiracy of caretakers or of survivors; the late-game reveal in §9.10 |

## 11.3 Section mapping, v1.0 → v2.0

For notes, issues or commits that cite the old flat numbering.

| v1.0 | v2.0 | | v1.0 | v2.0 |
| --- | --- | --- | --- | --- |
| §1 High concept | §1.1 | | §38 Historical crises | §8.7 |
| §2 Design pillars | §1.2 | | §39 Historical Institute | §8.8 |
| §3 Core game loop | §3.4 | | §40 Knowledge resource | §8.9 |
| §4 World map | §2.1, §2.5 | | §41 Information trading | §8.9 |
| §5 Seamless zoom | §2.4 | | §42 Historical anomalies | §8.5 |
| §6 Hierarchical coordinates | §2.3 | | §43 Long-term story | §8.11 |
| §7 Scale vs simulation | §2.6 | | §44 Persistent history | §8.10 |
| §8 Player | §4.1 | | §45 Endgame philosophy | §1.5 |
| §9 Ships | §4.2, §4.3 | | §46 Central concept | §8.1 |
| §10 Movement | §5.1 | | §47–§51 Technical architecture | §10.4 + *ARCH* |
| §11 Combat | §5.4 | | §52 MVP | §10.1 |
| §12 Frontier-inspired | §1.7 | | §53 Future features | §10.2 |
| §13 Economy | §5.3 | | §54 Design triangle | §1.3 |
| §14–§17 Factions | §6.1–§6.4 | | §55 Final vision | §1.4 |
| §18 Teams | §6.5 | | §56 The Continuity | §9.1 |
| §19 Territory | §6.6 | | §56.1–§56.3 Recruitment, protocol | §9.3 |
| §20 Faction missions | §5.5 | | §56.4, §56.15, §60 Across factions | §9.4 |
| §21 Defection | §6.7 | | §56.5–§56.7, §59, §67 Operations | §9.5 |
| §22 Communication | §7.3 | | §56.8, §56.16, §61 Cells, clearance | §9.6 |
| §23 Local radio | §7.4 | | §56.9 Recruitment events | §9.3 |
| §24 Infrastructure | §7.4 | | §56.10 Declining | §9.3 |
| §25 Communication delay | §7.5 | | §56.11, §56.12 Betrayal, social game | §9.7 |
| §26 Chat interface | §7.9 | | §56.13, §66 Not identifiable | §9.4 |
| §27 Event system | §7.6 | | §56.14, §70 Secret channel | §9.6 |
| §28 Event scope | §7.7 | | §56.17 Historical deviation | §9.9 |
| §29 Event categories | §7.8 | | §56.18, §64, §71 Paradox, twist | §9.10 |
| §30 Offline multiplayer | §3.5 | | §56.19, §73 Ultimate question | §9.12 |
| §31 Information as gameplay | §7.1 | | §56.20 Integration | §9.1 |
| §32 Foundation concepts | §1.7, §8.1 | | §57 The core secret | §9.1 |
| §33 Psychohistorical model | §8.2 | | §58, §68 Constraints | §9.2 |
| §34 Historical prediction | §8.3 | | §62, §63 Discovery | §9.8 |
| §35 Predictions and players | §8.4 | | §65 Challenging the model | §8.3 |
| §36 Players as anomalies | §8.5 | | §69 AI + player faction | §9.3 |
| §37 Self-fulfilling predictions | §8.6 | | §72 Three-level game | §9.11 |
| | | | §74 Campaign structure | §9.12 |
| | | | §75 Most important rule | §9.13 |

## 11.4 Change log

| Version | Date | Change |
| --- | --- | --- |
| 2.5 | 2026-08-27 | Added §8.12, the Harrowing: an unresolved historical crisis draws an incursion of powerful alien vessels that players fight to restore the balance, bound by the same rules as every other ship. Amended §2.7 so NPC crews spend the same daily Action Point budget as pilots. New open question Q9. See §11.1 M14, M15. |
| 2.4 | 2026-08-27 | Implementation questions S1–S6 answered: a wrecked pilot's capsule is recovered for a salvage tax that is a share of credits, not a flat fee (§5.4); a player may remain independent of any team (§6.5); jump range depends on the hull as well as the tank (§5.1); materialised NPCs persist and the server keeps playing them (§2.7). See §11.1 M14. |
| 2.3 | 2026-08-27 | Q4–Q7 answered. Q4: the Continuity's budget scales with world extent, holding its reach per system constant (§9.2). Q5: the Continuity is NPC-operated from the moment it exists; player agents are recruited into a working organisation (§9.3, §10.3). Q6: half of unspent AP carries over, up to an administrator-defined ceiling (§3.2). Q7: era transitions fire on sustained threshold crossings, never by hand (§8.11). |
| 2.2 | 2026-08-27 | Q1, Q2 and Q3 answered. Q1: the ladder is final at Galaxy → Region → System → Planet → Sector → Local; *Body* is withdrawn in favour of *Planet* and the Planet-scope channel renamed to match (§11.1 M1). Q2: forecasts are a public good of variable quality, not a commodity or a privilege (§8.3). Q3: a player commands exactly one ship (§4.2). |
| 2.1 | 2026-08-27 | Added §2.7, promoting the NPC population from an implicit detail to a stated design pillar with an observation-dependent fidelity model; the MVP now includes it and cycle step 4. See §11.1 M13. |
| 2.0 | 2026-08-27 | Restructured into eleven parts with hierarchical numbering; terminology unified with the architecture document; technical architecture extracted; Continuity material consolidated; normative conventions, non-goals, action catalogue, open questions and this change control section added. See §11.1. |
| 1.0 | — | Original design document, 75 flat sections. Preserved in version control. |

---

*End of document.*
