"""Tables owned by migration 0001 — SDD §4.2, §4.4."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from frontier.adapters.db.types import AddressPath
from frontier.domain.hex.coordinates import HexAddr


class Base(DeclarativeBase):
    metadata = MetaData(schema="core")


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Faction(Base):
    __tablename__ = "factions"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    faction_id: Mapped[int] = mapped_column(ForeignKey("core.factions.id"))
    founded_on: Mapped[int] = mapped_column(Integer)


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        CheckConstraint("credits >= 0", name="credits_non_negative"),
        CheckConstraint("ap_balance >= 0", name="ap_non_negative"),
        CheckConstraint(
            "(team_id IS NULL AND faction_id IS NULL) OR (team_id IS NOT NULL AND faction_id IS NOT NULL)",
            name="faction_matches_team",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("core.accounts.id"))
    callsign: Mapped[str] = mapped_column(String(32), unique=True)
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("core.teams.id"), nullable=True)
    faction_id: Mapped[int | None] = mapped_column(ForeignKey("core.factions.id"), nullable=True)
    credits: Mapped[int] = mapped_column(BigInteger, default=0)
    ap_balance: Mapped[int] = mapped_column(Integer, default=0)
    last_grant_day: Mapped[int] = mapped_column(Integer, default=-1)


class ApLedger(Base):
    __tablename__ = "ap_ledger"
    __table_args__ = (
        Index(
            "ap_ledger_command_uniq",
            "command_id",
            unique=True,
            postgresql_where=text("command_id IS NOT NULL"),
        ),
        Index("ap_ledger_player_day", "player_id", "world_day"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[UUID] = mapped_column(ForeignKey("core.players.id"))
    world_day: Mapped[int] = mapped_column(Integer)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(32))
    command_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Command(Base):
    __tablename__ = "commands"
    __table_args__ = (UniqueConstraint("player_id", "idempotency_key", name="commands_idempotency"),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    player_id: Mapped[UUID] = mapped_column(ForeignKey("core.players.id"))
    idempotency_key: Mapped[UUID] = mapped_column()
    action: Mapped[str] = mapped_column(String(32))
    request: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    ruleset_version: Mapped[str] = mapped_column(String(16))
    world_day: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorldState(Base):
    __tablename__ = "world_state"
    id: Mapped[bool] = mapped_column(Boolean, primary_key=True, default=True)
    world_day: Mapped[int] = mapped_column(Integer, default=0)
    world_seed: Mapped[str] = mapped_column(String(64))
    phase: Mapped[str] = mapped_column(String(16), default="open")


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        Index("locations_path_gist", "path", postgresql_using="gist"),
        UniqueConstraint("parent_id", "q", "r", name="locations_parent_hex"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("core.locations.id"))
    level: Mapped[int] = mapped_column(SmallInteger)
    q: Mapped[int] = mapped_column(Integer)
    r: Mapped[int] = mapped_column(Integer)
    path: Mapped[HexAddr] = mapped_column(AddressPath)
    kind: Mapped[str] = mapped_column(String(24))
    name: Mapped[str | None] = mapped_column(String(64))
    discovered_on: Mapped[int | None] = mapped_column(Integer)
    discovered_by: Mapped[UUID | None] = mapped_column(ForeignKey("core.players.id"))
    attrs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Ship(Base):
    __tablename__ = "ships"
    __table_args__ = (
        CheckConstraint("hull >= 0", name="hull_non_negative"),
        CheckConstraint("fuel >= 0", name="fuel_non_negative"),
        Index(
            "ships_one_per_player",
            "player_id",
            unique=True,
            postgresql_where=text("player_id IS NOT NULL AND destroyed_on IS NULL"),
        ),
        Index("ships_position_gist", "position_path", postgresql_using="gist"),
        Index("ships_system", "system_id", postgresql_where=text("destroyed_on IS NULL")),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    player_id: Mapped[UUID | None] = mapped_column(ForeignKey("core.players.id"))
    hull: Mapped[int] = mapped_column(Integer)
    hull_max: Mapped[int] = mapped_column(Integer)
    shields: Mapped[int] = mapped_column(Integer, default=0)
    shields_max: Mapped[int] = mapped_column(Integer, default=0)
    fuel: Mapped[int] = mapped_column(Integer)
    fuel_max: Mapped[int] = mapped_column(Integer)
    cargo_max: Mapped[int] = mapped_column(Integer)
    sensor_range: Mapped[int] = mapped_column(Integer)
    system_id: Mapped[UUID] = mapped_column(ForeignKey("core.locations.id"))
    position_path: Mapped[HexAddr] = mapped_column(AddressPath)
    docked_at: Mapped[UUID | None] = mapped_column(ForeignKey("core.locations.id"))
    destroyed_on: Mapped[int | None] = mapped_column(Integer)


class Journey(Base):
    __tablename__ = "journeys"
    __table_args__ = (Index("journeys_pending", "arrives_on", postgresql_where=text("NOT settled")),)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    ship_id: Mapped[UUID] = mapped_column(ForeignKey("core.ships.id"))
    from_path: Mapped[HexAddr] = mapped_column(AddressPath)
    to_path: Mapped[HexAddr] = mapped_column(AddressPath)
    to_system_id: Mapped[UUID] = mapped_column(ForeignKey("core.locations.id"))
    departed_on: Mapped[int] = mapped_column(Integer)
    arrives_on: Mapped[int] = mapped_column(Integer)
    settled: Mapped[bool] = mapped_column(Boolean, default=False)


class TickRun(Base):
    __tablename__ = "tick_runs"
    __table_args__ = ({"schema": "hist"},)
    world_day: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TickStage(Base):
    __tablename__ = "tick_stages"
    __table_args__ = ({"schema": "hist"},)
    world_day: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage: Mapped[str] = mapped_column(String(48), primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
