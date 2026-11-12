"""Runtime settings and environment configuration for the Kanban platform."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Platform configuration loaded from environment variables with KB_ prefix."""

    model_config = SettingsConfigDict(
        env_prefix="KB_",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    deployment_mode: Literal["standalone", "production"] = "production"
    web_dist: Path = Path("kanban/web/dist")
    standalone_cleartext_hosts: frozenset[str] = frozenset({"localhost", "127.0.0.1", "[::1]"})
    hsts_max_age: int = 63072000
    public_base_url: str = Field(
        default="http://localhost:8080",
        validation_alias=AliasChoices("KB_PUBLIC_BASE_URL", "KANBAN_PUBLIC_BASE_URL"),
    )

    @field_validator("public_base_url", mode="before")
    @classmethod
    def _clean_public_base_url(cls, v: object) -> str:
        if isinstance(v, str):
            return v.strip().rstrip("/")
        return "http://localhost:8080"

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
