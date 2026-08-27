"""Environment configuration. Game balance never comes from here — ARCH §11.2."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    database_url: str = "postgresql+asyncpg://frontier:frontier@localhost:5432/frontier"
    redis_url: str = "redis://localhost:6379/0"
    ruleset_version: str = "2026.1"
    ruleset_root: Path = Path("data/rulesets")
    jwt_secret: str = Field(default="dev-only-secret-not-for-production-use", min_length=32)
    jwt_ttl_seconds: int = 900
    tick_hour_utc: int = Field(default=4, ge=0, le=23)
    world_seed: str = "p0-fixture"
    features_psychohistory: bool = False
    features_continuity: bool = False
    # The public surface connects as a role with no privilege on the hidden schema.
    api_role: str = "api_role"
    features_watch: bool = True
    # Optional tick stages, resolved by name so nothing imports them (ARCH ADR-13).
    extra_stages: tuple[str, ...] = ("frontier.continuity.stage:stage",)
