# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Runtime settings and environment configuration for the Kanban platform."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Platform configuration loaded from environment variables with KB_ or KANBAN_ prefix."""

    model_config = SettingsConfigDict(
        env_prefix="KB_",
        case_sensitive=False,
        extra="ignore",
    )

    deployment_mode: Literal["standalone", "production"] = Field(
        default="production",
        validation_alias=AliasChoices(
            "KB_DEPLOYMENT_MODE",
            "KANBAN_DEPLOYMENT_MODE",
            "deployment_mode",
        ),
    )
    web_dist: Path = Path("kanban/web/dist")
    standalone_cleartext_hosts: frozenset[str] = frozenset({"localhost", "127.0.0.1", "[::1]"})
    hsts_max_age: int = 63072000
    public_base_url: str = Field(
        default="https://kanban.example",
        validation_alias=AliasChoices(
            "KANBAN_PUBLIC_BASE_URL", "KB_PUBLIC_BASE_URL", "public_base_url"
        ),
    )

    public_origin: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "KB_PUBLIC_ORIGIN",
            "KANBAN_PUBLIC_ORIGIN",
            "PUBLIC_BASE_URL",
            "public_origin",
        ),
    )
    webauthn_rp_name: str = Field(
        default="👍kanban",
        validation_alias=AliasChoices(
            "KB_WEBAUTHN_RP_NAME",
            "KANBAN_WEBAUTHN_RP_NAME",
            "webauthn_rp_name",
        ),
    )
    webauthn_rp_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "KB_WEBAUTHN_RP_ID",
            "KANBAN_WEBAUTHN_RP_ID",
            "webauthn_rp_id",
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

    @model_validator(mode="after")
    def _validate_webauthn_and_origin(self) -> Self:
        origin = self.public_origin
        if not origin:
            if self.deployment_mode == "standalone":
                origin = "http://localhost:8080"
            else:
                origin = "https://kanban.hackedyour.info"

        parsed = urlparse(origin)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()

        if scheme == "http":
            if self.deployment_mode != "standalone":
                msg = f"Insecure HTTP origin '{origin}' is forbidden outside standalone mode"
                raise ValueError(msg)
            if host not in self.standalone_cleartext_hosts:
                msg = f"HTTP origin host '{host}' is not in standalone_cleartext_hosts"
                raise ValueError(msg)
        elif scheme != "https":
            msg = f"Invalid origin scheme '{scheme}': must be https or standalone http"
            raise ValueError(msg)

        rp_id = self.webauthn_rp_id
        if rp_id:
            rp_id = rp_id.strip().lower()
            if not (host == rp_id or host.endswith("." + rp_id)):
                msg = f"WebAuthn RP ID '{rp_id}' is not a valid suffix of origin host '{host}'"
                raise ValueError(msg)
        return self

    @property
    def effective_origin(self) -> str:
        """Effective canonical origin (e.g. 'https://kanban.hackedyour.info')."""
        if self.public_origin:
            return self.public_origin.rstrip("/")
        if self.deployment_mode == "standalone":
            return "http://localhost:8080"
        return "https://kanban.hackedyour.info"

    @property
    def effective_rp_id(self) -> str:
        """Effective WebAuthn RP ID (e.g. 'kanban.hackedyour.info')."""
        if self.webauthn_rp_id:
            return self.webauthn_rp_id.strip().lower()
        parsed = urlparse(self.effective_origin)
        return (parsed.hostname or "").lower()
