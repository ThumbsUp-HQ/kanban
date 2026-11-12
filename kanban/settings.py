"""Runtime settings and environment configuration for the Kanban platform."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["MAX_TRASH_RETENTION_DAYS", "Settings", "get_settings"]

MAX_TRASH_RETENTION_DAYS: Final[int] = 365


class Settings(BaseSettings):
    """Platform configuration loaded from environment variables with KB_ prefix."""

    model_config = SettingsConfigDict(
        env_prefix="KB_",
        case_sensitive=False,
        extra="ignore",
    )

    deployment_mode: Literal["standalone", "production"] = "production"
    web_dist: Path = Path("kanban/web/dist")
    standalone_cleartext_hosts: frozenset[str] = frozenset({"localhost", "127.0.0.1", "[::1]"})
    hsts_max_age: int = 63072000
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "KANBAN_DATABASE_URL",
            "KB_DATABASE_URL",
            "DATABASE_URL",
        ),
    )
    trash_retention_days: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "KANBAN_TRASH_RETENTION_DAYS",
            "KB_TRASH_RETENTION_DAYS",
            "TRASH_RETENTION_DAYS",
        ),
    )

    @field_validator("trash_retention_days")
    @classmethod
    def _validate_trash_retention_days(cls, v: int) -> int:
        if not (1 <= v <= MAX_TRASH_RETENTION_DAYS):
            msg = f"trash_retention_days must be between 1 and {MAX_TRASH_RETENTION_DAYS}, got {v}"
            raise ValueError(msg)
        return v

    @field_validator("standalone_cleartext_hosts", mode="before")
    @classmethod
    def _parse_standalone_cleartext_hosts(cls, v: object) -> frozenset[str]:
        defaults = {"localhost", "127.0.0.1", "[::1]"}
        if v is None:
            return frozenset(defaults)
        if isinstance(v, str):
            entries = {s.strip().lower() for s in v.replace(",", " ").split() if s.strip()}
            return frozenset(defaults | entries)
        if isinstance(v, (set, frozenset, list, tuple)):
            entries = {str(s).strip().lower() for s in v if str(s).strip()}
            return frozenset(defaults | entries)
        return frozenset(defaults)


@lru_cache
def get_settings() -> Settings:
    """Return cached platform Settings instance."""
    return Settings()
