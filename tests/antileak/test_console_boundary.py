"""The console's boundary is a set of grants, not a habit — ADMIN §6, probe B17.

A merge blocker like the rest of this directory. The console reads widely on purpose; what it
must not do is write the world, and what the game must not do is reach the registry.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

WORLD_SCHEMAS = ("core", "evt", "hist", "psycho", "cont")


async def privileges(sessions, role: str) -> set[tuple[str, str, str]]:
    async with sessions() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT table_schema, table_name, privilege_type "
                    "FROM information_schema.role_table_grants WHERE grantee = :role"
                ).bindparams(role=role)
            )
        ).all()
    return {(r.table_schema, r.table_name, r.privilege_type) for r in rows}


async def test_the_console_reads_the_world_and_writes_almost_none_of_it(sessions):
    """B17: one write into the world — the marker that lets a failed tick be resumed."""
    held = await privileges(sessions, "admin_role")

    reads = {(s, t) for s, t, p in held if p == "SELECT"}
    assert {s for s, _ in reads} >= set(WORLD_SCHEMAS), "the console cannot see the world"

    writes = {(s, t, p) for s, t, p in held if p in ("INSERT", "UPDATE", "DELETE")}
    into_the_world = {(s, t, p) for s, t, p in writes if s in WORLD_SCHEMAS}
    assert into_the_world == {("hist", "tick_runs", "UPDATE")}, into_the_world


async def test_the_game_cannot_reach_the_register_of_operators(sessions):
    """An operator account is not a player account, and `api_role` never learns it exists."""
    held = await privileges(sessions, "api_role")

    assert not [row for row in held if row[0] == "admin"]

    async with sessions() as session, session.begin():
        await session.execute(text("SET LOCAL ROLE api_role"))
        with pytest.raises(Exception, match="permission denied"):
            await session.execute(text("SELECT count(*) FROM admin.operators"))


async def test_the_console_cannot_touch_a_player(sessions):
    """It diagnoses; it does not correct. A correction is a command with a name."""
    async with sessions() as session, session.begin():
        await session.execute(text("SET LOCAL ROLE admin_role"))
        with pytest.raises(Exception, match="permission denied"):
            await session.execute(text("UPDATE core.players SET credits = credits + 1"))
