"""Tables owned by migration 0001 — SDD §4.2, §4.4."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
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
    defected_on: Mapped[int | None] = mapped_column(Integer)


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
    knowledge: Mapped[int] = mapped_column(Integer, default=0)
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
    jump_range_ly: Mapped[int] = mapped_column(Integer, default=8)
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


class Event(Base):
    __tablename__ = "events"
    __table_args__ = ({"schema": "evt"},)
    world_day: Mapped[int] = mapped_column(Integer, primary_key=True)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    type: Mapped[str] = mapped_column(String(32))
    origin_path: Mapped[HexAddr] = mapped_column(AddressPath)
    scope: Mapped[int] = mapped_column(SmallInteger)
    visibility: Mapped[str] = mapped_column(String(16))
    clearance: Mapped[int] = mapped_column(SmallInteger, default=0)
    severity: Mapped[int] = mapped_column(SmallInteger)
    participants: Mapped[list[UUID]] = mapped_column(ARRAY(PgUUID(as_uuid=True)))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    ruleset_version: Mapped[str] = mapped_column(String(16))
    causation_id: Mapped[UUID | None] = mapped_column()


class EventDelivery(Base):
    __tablename__ = "event_deliveries"
    __table_args__ = ({"schema": "evt"},)
    recipient_id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    world_day: Mapped[int] = mapped_column(Integer)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EventOutbox(Base):
    __tablename__ = "events_outbox"
    __table_args__ = ({"schema": "evt"},)
    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    world_day: Mapped[int] = mapped_column(Integer)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Digest(Base):
    __tablename__ = "digests"
    __table_args__ = ({"schema": "evt"},)
    player_id: Mapped[UUID] = mapped_column(primary_key=True)
    world_day: Mapped[int] = mapped_column(Integer, primary_key=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Cargo(Base):
    __tablename__ = "cargo"
    ship_id: Mapped[UUID] = mapped_column(ForeignKey("core.ships.id"), primary_key=True)
    commodity: Mapped[str] = mapped_column(String(24), primary_key=True)
    qty: Mapped[int] = mapped_column(Integer)
    avg_unit_cost: Mapped[int] = mapped_column(Integer, default=0)


class StandingOrders(Base):
    __tablename__ = "standing_orders"
    player_id: Mapped[UUID] = mapped_column(ForeignKey("core.players.id"), primary_key=True)
    posture: Mapped[str] = mapped_column(String(20), default="evade")
    engage_hostile: Mapped[bool] = mapped_column(Boolean, default=False)
    engage_above_cargo: Mapped[int | None] = mapped_column(Integer)
    retreat_at_hull_pct: Mapped[int] = mapped_column(Integer, default=50)
    auto_reply: Mapped[str | None] = mapped_column(String(200))


class Market(Base):
    __tablename__ = "markets"
    station_id: Mapped[UUID] = mapped_column(ForeignKey("core.locations.id"), primary_key=True)
    commodity: Mapped[str] = mapped_column(String(24), primary_key=True)
    stock: Mapped[int] = mapped_column(Integer)
    target_stock: Mapped[int] = mapped_column(Integer)
    base_price: Mapped[int] = mapped_column(Integer)


class EncounterQueue(Base):
    __tablename__ = "encounter_queue"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    world_day: Mapped[int] = mapped_column(Integer)
    attacker_id: Mapped[UUID] = mapped_column(ForeignKey("core.ships.id"))
    defender_id: Mapped[UUID] = mapped_column(ForeignKey("core.ships.id"))
    at_path: Mapped[HexAddr] = mapped_column(AddressPath)
    intent: Mapped[str] = mapped_column(String(16), default="attack")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class Territory(Base):
    __tablename__ = "territory"
    system_id: Mapped[UUID] = mapped_column(ForeignKey("core.locations.id"), primary_key=True)
    faction_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    influence: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)


class PlayerDiscovery(Base):
    __tablename__ = "player_discoveries"
    player_id: Mapped[UUID] = mapped_column(ForeignKey("core.players.id"), primary_key=True)
    location_id: Mapped[UUID] = mapped_column(ForeignKey("core.locations.id"), primary_key=True)
    seen_on: Mapped[int] = mapped_column(Integer)


class SystemActivity(Base):
    __tablename__ = "system_activity"
    system_id: Mapped[UUID] = mapped_column(ForeignKey("core.locations.id"), primary_key=True)
    trade_flow: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    patrol_strength: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    raider_pressure: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    civilian_traffic: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    patrol_losses: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    raider_losses: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    last_simulated_on: Mapped[int] = mapped_column(Integer, default=-1)


class NpcAgent(Base):
    __tablename__ = "npc_agents"
    ship_id: Mapped[UUID] = mapped_column(ForeignKey("core.ships.id"), primary_key=True)
    system_id: Mapped[UUID] = mapped_column(ForeignKey("core.locations.id"))
    archetype: Mapped[str] = mapped_column(String(16))
    slot: Mapped[int] = mapped_column(SmallInteger)
    faction_id: Mapped[int | None] = mapped_column(SmallInteger)
    route: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    materialised_on: Mapped[int] = mapped_column(Integer)
    last_seen_on: Mapped[int] = mapped_column(Integer)
    ap_balance: Mapped[int] = mapped_column(Integer, default=0)
    last_grant_day: Mapped[int] = mapped_column(Integer, default=-1)


class Chronicle(Base):
    __tablename__ = "chronicle"
    __table_args__ = ({"schema": "hist"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    world_day: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scope: Mapped[int] = mapped_column(SmallInteger)
    origin_path: Mapped[HexAddr] = mapped_column(AddressPath)
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    causation_id: Mapped[UUID | None] = mapped_column()


class Mission(Base):
    __tablename__ = "missions"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    faction_id: Mapped[int] = mapped_column(SmallInteger)
    kind: Mapped[str] = mapped_column(String(24))
    system_id: Mapped[UUID] = mapped_column(ForeignKey("core.locations.id"))
    target_id: Mapped[UUID | None] = mapped_column(ForeignKey("core.locations.id"))
    brief: Mapped[str] = mapped_column(String(300))
    terms: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    reward_credits: Mapped[int] = mapped_column(Integer)
    reward_reputation: Mapped[int] = mapped_column(Integer, default=1)
    offered_on: Mapped[int] = mapped_column(Integer)
    expires_on: Mapped[int] = mapped_column(Integer)


class MissionAssignment(Base):
    __tablename__ = "mission_assignments"
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("core.missions.id"), primary_key=True)
    player_id: Mapped[UUID] = mapped_column(ForeignKey("core.players.id"), primary_key=True)
    stage: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")
    accepted_on: Mapped[int] = mapped_column(Integer)
    closed_on: Mapped[int | None] = mapped_column(Integer)


class Reputation(Base):
    __tablename__ = "reputation"
    player_id: Mapped[UUID] = mapped_column(ForeignKey("core.players.id"), primary_key=True)
    faction_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    score: Mapped[int] = mapped_column(Integer, default=0)


class HistoryVariable(Base):
    __tablename__ = "history_variables"
    __table_args__ = ({"schema": "psycho"},)
    region_id: Mapped[UUID] = mapped_column(primary_key=True)
    world_day: Mapped[int] = mapped_column(Integer, primary_key=True)
    variable: Mapped[str] = mapped_column(String(32), primary_key=True)
    observed: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    expected: Mapped[Decimal] = mapped_column(Numeric(8, 4))


class ForecastRow(Base):
    __tablename__ = "forecasts"
    __table_args__ = ({"schema": "psycho"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    region_id: Mapped[UUID] = mapped_column()
    world_day: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    probability: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    deviation: Mapped[Decimal] = mapped_column(Numeric(6, 4))
