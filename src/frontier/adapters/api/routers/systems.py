"""What is in the system around you — UX §4.1.

Three layers, and the server decides all three: what is in sight now, what this player has
charted before, and — by omission — what they know nothing about. Contacts are graded by the
same sensor ladder the event feed uses, so a ship is never more visible than the events it
makes.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from frontier.adapters.api.deps import ContainerDep, CurrentPlayer
from frontier.adapters.db import models
from frontier.application.visibility import Quality, sensor_quality
from frontier.domain.hex.coordinates import HexAddr, ScaleMismatch
from frontier.domain.hex.geometry import addr_distance

router = APIRouter(prefix="/v1", tags=["map"])


@router.get("/systems/{system_id}")
async def system(system_id: UUID, player_id: CurrentPlayer, c: ContainerDep) -> dict[str, Any]:
    async with c.sessions() as session:
        ship = (
            await session.execute(
                select(models.Ship).where(
                    models.Ship.player_id == player_id, models.Ship.destroyed_on.is_(None)
                )
            )
        ).scalar_one_or_none()
        if ship is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")

        here = (
            await session.execute(select(models.Location).where(models.Location.id == system_id))
        ).scalar_one_or_none()
        # A system the player is not in is not theirs to look inside; 404 rather than 403, so
        # the answer is the same whether it exists or not.
        if here is None or ship.system_id != system_id:
            raise HTTPException(status_code=404, detail="NOT_FOUND")

        charted = {
            row.location_id: row.seen_on
            for row in (
                await session.execute(
                    select(models.PlayerDiscovery).where(models.PlayerDiscovery.player_id == player_id)
                )
            ).scalars()
        }
        places = (
            (
                await session.execute(
                    select(models.Location)
                    .where(models.Location.parent_id == system_id, models.Location.kind != "void")
                    .order_by(models.Location.path)
                )
            )
            .scalars()
            .all()
        )
        others = (
            (
                await session.execute(
                    select(models.Ship).where(
                        models.Ship.system_id == system_id,
                        models.Ship.destroyed_on.is_(None),
                        models.Ship.id != ship.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        crews = {
            row.ship_id: row.archetype for row in (await session.execute(select(models.NpcAgent))).scalars()
        }
        callsigns = {row.id: row.callsign for row in (await session.execute(select(models.Player))).scalars()}
        controller = await _controller(session, system_id)
        radius = await _radius(session, system_id)

    reach = ship.sensor_range
    bodies = [
        {
            "id": str(place.id),
            "path": str(place.path),
            "kind": place.kind,
            "name": place.name,
            "q": place.q,
            "r": place.r,
            "in_sight": _steps(ship.position_path, place.path) <= reach,
            "charted_on": charted.get(place.id),
        }
        for place in places
        if place.id in charted or _steps(ship.position_path, place.path) <= reach
    ]

    contacts = []
    for other in others:
        quality = sensor_quality(_steps(ship.position_path, other.position_path), reach)
        if quality is Quality.NONE:
            continue
        if quality is Quality.FULL:
            contacts.append(
                {
                    "quality": "full",
                    # The id is what `attack` targets, so it is given only where the contact is
                    # resolved: a partial sighting must not hand out a durable handle on a ship.
                    "ship_id": str(other.id),
                    "position": str(other.position_path),
                    "name": callsigns.get(other.player_id) if other.player_id else None,
                    "kind": crews.get(other.id, "ship"),
                    "docked": other.docked_at is not None,
                }
            )
        else:
            # Partial: something is out there. Not who, not what, and not exactly where.
            parent = other.position_path.parent() or other.position_path
            contacts.append(
                {
                    "quality": "partial",
                    "ship_id": None,
                    "position": str(parent),
                    "name": None,
                    "kind": None,
                    "docked": None,
                }
            )

    return {
        "system": {
            "id": str(here.id),
            "path": str(here.path),
            "name": here.name,
            "controller": controller,
            "radius": radius,
        },
        "you": {
            "position": str(ship.position_path),
            "sensor_range": reach,
            "docked_at": str(ship.docked_at) if ship.docked_at else None,
        },
        "bodies": bodies,
        "contacts": contacts,
    }


def _steps(here: HexAddr, there: HexAddr) -> int:
    try:
        return addr_distance(here, there)
    except ScaleMismatch:
        return 10**6


async def _radius(session: Any, system_id: UUID) -> int:
    """How far the system extends, so the client never offers a hex that is not a place.

    Read from the world rather than assumed: a route plotted beyond the rim would be refused
    hop by hop, which is a refusal the player should never have been allowed to earn.
    """
    extent = func.max(
        func.greatest(
            func.abs(models.Location.q),
            func.abs(models.Location.r),
            func.abs(models.Location.q + models.Location.r),
        )
    )
    value = (
        await session.execute(select(extent).where(models.Location.parent_id == system_id))
    ).scalar_one_or_none()
    return int(value or 0)


async def _controller(session: Any, system_id: UUID) -> int | None:
    rows = (
        (await session.execute(select(models.Territory).where(models.Territory.system_id == system_id)))
        .scalars()
        .all()
    )
    best = max(rows, key=lambda row: float(row.influence), default=None)
    return best.faction_id if best and float(best.influence) >= 0.5 else None
