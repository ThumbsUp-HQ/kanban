# Copyright 2026 Kanban Platform Contributors
"""Configuration settings for Kanban MCP server and internal API client."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "McpSettings",
]


class McpSettings(BaseSettings):
    """Runtime configuration for the Kanban Model Context Protocol server."""

    model_config = SettingsConfigDict(env_prefix="KB_MCP_", extra="ignore")

    mode: Literal["mtls", "standalone_inprocess"] = "mtls"
    kanban_api_base_url: str = "https://127.0.0.1:8443"
    internal_ca_path: Path | None = None
    client_cert_path: Path | None = None
    client_key_path: Path | None = None

    allowed_origins: list[str] = Field(default_factory=list)
    session_ttl_s: float = 3600.0
    max_sessions: int = 10000

    request_body_limit_bytes: int = 1048576  # 1 MiB
    response_body_limit_bytes: int = 8388608  # 8 MiB

    auth_enabled: bool = False
