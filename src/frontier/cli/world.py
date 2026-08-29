"""`make world` — generate a galaxy and write it. Idempotent: it refuses a populated world."""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select

from frontier.adapters.clock import SeededRng
from frontier.adapters.db import models
from frontier.adapters.db.engine import make_engine, make_sessionmaker
from frontier.adapters.rules_loader import load_ruleset
from frontier.config.settings import Settings
from frontier.domain.rules.ruleset import RuleSet
from frontier.worldgen.generator import GeneratedLocation, Shape, generate, summarise


async def build_world(settings: Settings, force: bool = False) -> dict[str, int]:
    engine = make_engine(settings.database_url)
    sessions = make_sessionmaker(engine)
    try:
        async with sessions() as session, session.begin():
            existing = (await session.execute(select(func.count()).select_from(models.Location))).scalar_one()
            if existing and not force:
                raise SystemExit(f"world already has {existing} locations; use --force")
            if existing:
                # Dependency order: journeys reference ships, ships reference locations.
                await session.execute(delete(models.MissionAssignment))
                await session.execute(delete(models.Mission))
                await session.execute(delete(models.PlayerDiscovery))
                await session.execute(delete(models.Cargo))
                await session.execute(delete(models.EncounterQueue))
                await session.execute(delete(models.NpcAgent))
                await session.execute(delete(models.SystemActivity))
                await session.execute(delete(models.Market))
                await session.execute(delete(models.Territory))
                await session.execute(delete(models.Journey))
                await session.execute(delete(models.Ship))
                await session.execute(delete(models.Location))

            rules = load_ruleset(settings.ruleset_root, settings.ruleset_version)
            rows = generate(SeededRng(settings.world_seed).for_, Shape.of(rules.world))
            session.add_all(
                [
                    models.Location(
                        id=r.id,
                        parent_id=r.parent_id,
                        level=r.level,
                        q=r.q,
                        r=r.r,
                        path=r.path,
                        kind=r.kind,
                        name=r.name,
                        discovered_on=r.discovered_on,
                        attrs=r.attrs,
                    )
                    for r in rows
                ]
            )
            session.add_all(seed_markets(rows, rules, SeededRng(settings.world_seed).for_))
            session.add_all(seed_activity(rows))
            session.add_all(seed_territory(rows))
            state = (await session.execute(select(models.WorldState))).scalar_one_or_none()
            if state is None:
                session.add(
                    models.WorldState(id=True, world_day=0, world_seed=settings.world_seed, phase="open")
                )
        return summarise(rows)
    finally:
        await engine.dispose()


def main() -> None:
    summary = asyncio.run(build_world(Settings(), force="--force" in sys.argv))
    for key in sorted(summary):
        print(f"  {key:<10} {summary[key]}")


def seed_markets(rows: list[GeneratedLocation], rules: RuleSet, rng_for: Any) -> list[models.Market]:
    """Each station trades everything, but is long what it makes and short what it consumes."""
    economy = rules.economy
    out: list[models.Market] = []
    for row in rows:
        if row.kind != "station":
            continue
        profile = economy.station_type.get(str(row.attrs.get("station_type", "")), {})
        rng = rng_for("market", str(row.id))
        station_type = str(row.attrs.get("station_type", "")) or None
        for commodity, base_price in economy.commodities.items():
            if not economy.tradable_at(commodity, station_type):
                continue
            target = rng.randint(60, 140)
            if commodity == profile.get("produces"):
                target *= 3
            elif commodity == profile.get("consumes"):
                target = max(10, target // 3)
            out.append(
                models.Market(
                    station_id=row.id,
                    commodity=commodity,
                    stock=max(1, round(target * rng.uniform(0.7, 1.3))),
                    target_stock=target,
                    base_price=base_price,
                )
            )
    return out


FACTION_CODES = {"empire": 1, "republic": 2, "pirates": 3}


def seed_territory(rows: list[GeneratedLocation]) -> list[models.Territory]:
    """A faction holds its own home from the first cycle — SDD §7, step 6.

    Without this the galaxy starts uncontrolled everywhere and takes seven cycles to show a
    single border, which is neither true to the fiction nor much to look at.
    """
    out: list[models.Territory] = []
    for row in rows:
        faction = FACTION_CODES.get(str(row.attrs.get("home_for", "")))
        if faction is None:
            continue
        out.append(models.Territory(system_id=row.id, faction_id=faction, influence=Decimal("1")))
    return out


def seed_activity(rows: list[GeneratedLocation]) -> list[models.SystemActivity]:
    return [models.SystemActivity(system_id=r.id) for r in rows if r.kind == "system"]


if __name__ == "__main__":
    main()
