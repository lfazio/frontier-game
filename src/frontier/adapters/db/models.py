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
