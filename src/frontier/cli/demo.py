"""`make demo` — build a world with a history worth looking at.

Watch mode shows public, system-or-wider events (*UX §9*), and a freshly generated galaxy has
none: nobody has discovered anything, fought anyone or taken a system. This seeds pilots, lets
them explore, and runs enough cycles for the world to have done something.
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text

from frontier.adapters.clock import SeededRng, SystemClock, UuidFactory
from frontier.adapters.db import models
from frontier.adapters.db.engine import make_engine, make_sessionmaker
from frontier.adapters.db.uow import SqlUnitOfWork
from frontier.adapters.registrar import SqlRegistrar
from frontier.adapters.rules_loader import load_ruleset
from frontier.application.commands.combat import AttackCommand
from frontier.application.commands.move import MoveCommand
from frontier.application.commands.navigation import JumpCommand, ScanCommand
from frontier.application.commands.teams import CreateTeamCommand
from frontier.application.executor import Executor
from frontier.cli.world import build_world
from frontier.config.settings import Settings
from frontier.domain.hex.geometry import distance, line, neighbours
from frontier.simulation.extensions import load
from frontier.simulation.stages.base import Features
from frontier.simulation.tick import TickRunner

PILOTS = 8
CYCLES = 10
NAMES = ("Vale", "Okonkwo", "Reyes", "Halloran", "Sato", "Marchetti", "Idris", "Blackwood")


# Dependency order: children before the rows they reference.
WIPE = (
    "evt.event_deliveries",
    "evt.events_outbox",
    "evt.events",
    "evt.digests",
    "cont.interventions",
    "cont.agents",
    "cont.cells",
    "cont.budget",
    "psycho.forecasts",
    "psycho.history_variables",
    "hist.chronicle",
    "hist.tick_stages",
    "hist.tick_runs",
    "core.mission_assignments",
    "core.missions",
    "core.reputation",
    "core.ap_ledger",
    "core.commands",
    "core.cargo",
    "core.encounter_queue",
    "core.npc_agents",
    "core.player_discoveries",
    "core.standing_orders",
    "core.journeys",
    "core.ships",
    "core.players",
    "core.teams",
    "core.accounts",
)


async def _wipe(settings: Settings) -> None:
    """A demo is meant to be re-run; leaving the last run's pilots behind would block it."""
    engine = make_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.execute(text("UPDATE core.locations SET discovered_by = NULL"))
        for table in WIPE:
            await connection.execute(text(f"DELETE FROM {table}"))
    await engine.dispose()


async def seed(settings: Settings) -> None:
    await _wipe(settings)
    await build_world(settings, force=True)

    engine = make_engine(settings.database_url)
    sessions = make_sessionmaker(engine)
    rules = load_ruleset(settings.ruleset_root, settings.ruleset_version)
    clock = SystemClock()
    executor = Executor(
        uow_factory=partial(SqlUnitOfWork, sessions),
        clock=clock,
        rng=SeededRng(settings.world_seed),
        ids=UuidFactory(clock),
        rules=rules,
    )
    registrar = SqlRegistrar(sessions, rules.ap.daily_grant, rules.world.jump_range_default_ly)
    tick = TickRunner(
        sessions=sessions,
        rules=rules,
        clock=clock,
        rng_for=SeededRng(settings.world_seed).for_,
        features=Features(psychohistory=True, continuity=settings.features_continuity),
        extra_stages=load(settings.extra_stages),
    )

    pilots = []
    for index, name in enumerate(NAMES[:PILOTS]):
        pilot = await registrar.register(
            f"{name.lower()}@frontier.demo", "correct horse battery", f"Cmdr {name}"
        )
        # Spread them across the three factions: a pilot without one contributes no presence,
        # so territory would never be contested and the map would never change hands.
        await executor.execute(
            CreateTeamCommand(
                id=uuid4(),
                idempotency_key=uuid4(),
                name=f"{name} Company",
                faction_id=(index % 3) + 1,
            ),
            pilot,
        )
        pilots.append(pilot)
    print(f"  seeded {len(pilots)} pilots across three factions")

    await _scatter(executor, sessions, pilots)
    await tick.run()  # journeys settle, and everyone is somewhere different

    for _ in range(CYCLES):
        for pilot in pilots:
            await _explore(executor, sessions, pilot)
            await _skirmish(executor, sessions, pilot)
        report = await tick.run()
        print(
            f"  day {report.world_day}: "
            + ", ".join(
                f"{name}={sum(v for k, v in metrics.items() if k != 'skipped')}"
                for name, metrics in report.stages.items()
                if metrics and name in ("npc_population", "missions", "economy")
            )
        )

    async with sessions() as session:
        public = (
            await session.execute(
                select(func.count())
                .select_from(models.Event)
                .where(models.Event.visibility == "public", models.Event.scope >= 2)
            )
        ).scalar_one()
    print(f"  {public} events a spectator can see")
    await engine.dispose()


async def _scatter(executor: Executor, sessions: Any, pilots: list[UUID]) -> None:
    """Send each pilot to a different system.

    Everyone registers at the same station, so without this the whole demo happens in one
    neighbourhood: one system's territory, one system's discoveries, and a map that never moves.
    """
    async with sessions() as session:
        systems = (
            (
                await session.execute(
                    select(models.Location)
                    .where(models.Location.kind == "system")
                    .order_by(models.Location.path)
                )
            )
            .scalars()
            .all()
        )

    sent = 0
    for index, pilot in enumerate(pilots):
        for offset in range(len(systems)):
            candidate = systems[(index * 3 + offset) % len(systems)]
            result = await executor.execute(
                JumpCommand(id=uuid4(), idempotency_key=uuid4(), to_system=candidate.path),
                pilot,
            )
            if result.status == "accepted":
                sent += 1
                break
    print(f"  {sent} of {len(pilots)} pilots are under way")


async def _explore(executor: Executor, sessions: object, pilot: object) -> None:
    """Scan, then step toward the nearest thing worth charting.

    Wandering in a straight line finds nothing: a system is mostly void, and discovery is what
    produces the system-wide events a spectator may see.
    """
    await executor.execute(ScanCommand(id=uuid4(), idempotency_key=uuid4()), pilot)  # type: ignore[arg-type]
    async with sessions() as session:  # type: ignore[operator]
        ship = (
            await session.execute(select(models.Ship).where(models.Ship.player_id == pilot))
        ).scalar_one_or_none()
        if ship is None:
            return
        somewhere = (
            await session.execute(
                select(models.Location)
                .where(
                    models.Location.parent_id == ship.system_id,
                    models.Location.kind.notin_(("void", "star")),
                    models.Location.discovered_on.is_(None),
                )
                .order_by(models.Location.path)
                .limit(1)
            )
        ).scalar_one_or_none()

    here = ship.position_path.tip
    if somewhere is None:
        step = neighbours(here)[0]
    else:
        route = line(here, somewhere.path.tip)
        step = route[1] if len(route) > 1 else neighbours(here)[0]
    target = ship.position_path.sibling(step)
    await executor.execute(
        MoveCommand(id=uuid4(), idempotency_key=uuid4(), to=target),
        pilot,  # type: ignore[arg-type]
    )


async def _skirmish(executor: Executor, sessions: object, pilot: object) -> None:
    """Pick a fight with whatever crew is standing next door, if any.

    A galaxy where nothing is ever at stake makes a dull thing to watch, and combat is what
    produces the system-wide events a spectator is allowed to see.
    """
    async with sessions() as session:  # type: ignore[operator]
        mine = (
            await session.execute(select(models.Ship).where(models.Ship.player_id == pilot))
        ).scalar_one_or_none()
        if mine is None:
            return
        crews = (
            (
                await session.execute(
                    select(models.Ship).where(
                        models.Ship.system_id == mine.system_id,
                        models.Ship.player_id.is_(None),
                        models.Ship.destroyed_on.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
    # Weapons reach one hex, so only a neighbour is a candidate.
    target = next((c for c in crews if distance(mine.position_path.tip, c.position_path.tip) <= 1), None)
    if target is None:
        return
    await executor.execute(
        AttackCommand(id=uuid4(), idempotency_key=uuid4(), target_ship_id=target.id),
        pilot,  # type: ignore[arg-type]
    )


def main() -> None:
    settings = Settings()
    print("building a world worth watching…")
    asyncio.run(seed(settings))
    print("\nrun the server and the client:")
    print("  uv run uvicorn frontier.adapters.api.app:app --port 8000")
    print("  cd client && npm run dev      →  http://localhost:5173")


if __name__ == "__main__":
    main()
