"""Runtime settings and environment configuration for the Kanban platform."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    public_base_url: str = Field(
        default="https://kanban.example",
        validation_alias=AliasChoices(
            "KANBAN_PUBLIC_BASE_URL", "KB_PUBLIC_BASE_URL", "public_base_url"
        ),
    )

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

    @model_validator(mode="after")
    def _validate_public_base_url(self) -> Self:
        url = self.public_base_url.strip().rstrip("/")
        parsed = urlparse(url)
        if self.deployment_mode == "standalone":
            is_allowed = (parsed.scheme == "https") or (
                parsed.scheme == "http" and parsed.hostname in self.standalone_cleartext_hosts
            )
            if not is_allowed:
                msg = (
                    "public_base_url must use https:// or http:// with "
                    "localhost/127.0.0.1 in standalone mode"
                )
                raise ValueError(msg)
        elif parsed.scheme != "https":
            msg = "public_base_url must use https:// in production mode"
            raise ValueError(msg)
        self.public_base_url = url
        return self
