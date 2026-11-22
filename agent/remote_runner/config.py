# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Configuration model and key permission validation for remote runner (KB-P5-22b, S14.2)."""

from __future__ import annotations

import re
import tomllib
import uuid  # noqa: TC003
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "KeyPermissionsError",
    "RunnerConfig",
    "load_runner_config",
    "validate_key_permissions",
    "validate_runner_config",
]

_POOL_SLUG_REGEX: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


class KeyPermissionsError(ValueError):
    """Raised when client private key has overly permissive file permissions."""


def validate_key_permissions(key_path: Path) -> None:
    """Validate that private key file has strict permissions (0600, no group/other bits)."""
    if not key_path.exists():
        return
    st_mode = key_path.stat().st_mode
    if (st_mode & 0o077) != 0:
        mode_octal = oct(st_mode & 0o777)
        msg = (
            f"KEY_PERMISSIONS_TOO_OPEN: Private key {key_path} permissions {mode_octal} "
            f"are too open. Group and other permissions must be 000 (mode 0600 or 0400)."
        )
        raise KeyPermissionsError(msg)


class RunnerConfig(BaseModel):
    """Pydantic v2 configuration settings for kanban-agent-runner."""

    model_config = ConfigDict(extra="forbid")

    server_url: str
    pool_slug: str = "default"
    client_cert_path: Path | None = None
    client_key_path: Path | None = None
    ca_cert_path: Path | None = None

    cert_path: Path | None = None
    key_path: Path | None = None
    allowed_repos: list[str] = Field(default_factory=list)

    runner_id: uuid.UUID | None = None
    wss_url: str | None = None
    state_dir: Path | None = None
    max_concurrency: int = Field(default=1, ge=1, le=8)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    repo_mounts: dict[str, Path] = Field(default_factory=dict)
    https_proxy: str | None = None
    heartbeat_interval_s: float = Field(default=15.0, ge=1.0, le=60.0)
    nsjail_bin: Path = Path("/usr/bin/nsjail")

    @model_validator(mode="after")
    def _sync_paths(self) -> RunnerConfig:
        if self.client_cert_path is None and self.cert_path is not None:
            self.client_cert_path = self.cert_path
        elif self.cert_path is None and self.client_cert_path is not None:
            self.cert_path = self.client_cert_path

        if self.client_key_path is None and self.key_path is not None:
            self.client_key_path = self.key_path
        elif self.key_path is None and self.client_key_path is not None:
            self.key_path = self.client_key_path

        if (
            self.client_cert_path is None
            or self.client_key_path is None
            or self.ca_cert_path is None
        ):
            msg = "Missing required certificate or key paths"
            raise ValueError(msg)
        return self

    @field_validator("pool_slug")
    @classmethod
    def validate_pool_slug(cls, v: str) -> str:
        """Validate that pool_slug conforms to alphanumeric-hyphen slug format."""
        if not _POOL_SLUG_REGEX.match(v):
            msg = f"Invalid pool_slug '{v}': must match ^[a-z0-9][a-z0-9-]{{1,62}}$"
            raise ValueError(msg)
        return v

    def resolve_wss_url(self) -> str:
        """Resolve full outbound WebSocket URL from server_url or explicit wss_url."""
        if self.wss_url:
            return self.wss_url
        base = self.server_url.rstrip("/")
        if base.startswith("http://"):
            base = "ws://" + base[len("http://") :]
        elif base.startswith("https://"):
            base = "wss://" + base[len("https://") :]
        elif not base.startswith(("ws://", "wss://")):
            base = "wss://" + base
        return f"{base}/api/v1/agent-runners/ws"


def validate_runner_config(config: RunnerConfig) -> None:
    """Validate key permissions and configuration paths."""
    key_path = config.client_key_path or config.key_path
    if key_path is not None:
        validate_key_permissions(key_path)


def load_runner_config(config_path: Path) -> RunnerConfig:
    """Load, parse, and validate RunnerConfig from YAML or TOML file."""
    if not config_path.is_file():
        msg = f"Runner config file not found: {config_path}"
        raise FileNotFoundError(msg)
    raw_content = config_path.read_text(encoding="utf-8")
    if config_path.suffix.lower() == ".toml":
        data = tomllib.loads(raw_content)
    else:
        data = yaml.safe_load(raw_content) or {}
    config = RunnerConfig.model_validate(data)
    validate_runner_config(config)
    return config
