# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Pydantic schemas for AI provider configuration and budget administration (KB-P5-05b)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import date  # noqa: TC003
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

_MAX_KEY_LENGTH = 512


class ProviderConfigPublic(BaseModel):
    """Public representation of an AI provider configuration with write-only key custody."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    provider_kind: str
    display_name: str
    base_url: str | None = None
    model_allowlist: list[str]
    residency_tier: str
    priority: int
    settings: dict[str, Any] = Field(default_factory=dict)
    api_key_set: bool
    is_enabled: bool
    project_id: uuid.UUID | None = None


class ProviderConfigCreate(BaseModel):
    """Payload for creating a new AI provider configuration."""

    model_config = ConfigDict(extra="forbid")

    provider_kind: str
    display_name: str = Field(min_length=1, max_length=80)
    model_allowlist: list[str] = Field(default_factory=list)
    residency_tier: str = "default"
    base_url: str | None = None
    priority: int = 100
    settings: dict[str, Any] = Field(default_factory=dict)
    project_id: uuid.UUID | None = None
    is_enabled: bool = True
    api_key: SecretStr | None = None

    @field_validator("api_key")
    @classmethod
    def _validate_api_key_len(cls, v: SecretStr | None) -> SecretStr | None:
        if v is not None and len(v.get_secret_value()) > _MAX_KEY_LENGTH:
            msg = f"api_key length exceeds {_MAX_KEY_LENGTH} characters"
            raise ValueError(msg)
        return v


class ProviderConfigUpdate(BaseModel):
    """Payload for updating an existing AI provider configuration."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    model_allowlist: list[str] | None = None
    residency_tier: str | None = None
    base_url: str | None = None
    priority: int | None = None
    settings: dict[str, Any] | None = None
    is_enabled: bool | None = None
    api_key: SecretStr | None = None

    @field_validator("api_key")
    @classmethod
    def _validate_api_key_len(cls, v: SecretStr | None) -> SecretStr | None:
        if v is not None and len(v.get_secret_value()) > _MAX_KEY_LENGTH:
            msg = f"api_key length exceeds {_MAX_KEY_LENGTH} characters"
            raise ValueError(msg)
        return v


class BudgetRecord(BaseModel):
    """Active or historical token budget ledger row."""

    model_config = ConfigDict(extra="forbid")

    period_kind: Literal["daily", "monthly"]
    period_start: date
    token_cap: int = Field(ge=0, le=10_000_000_000)
    tokens_used: int = Field(ge=0)
    tokens_reserved: int = Field(ge=0)


class BudgetSetRequest(BaseModel):
    """Payload for setting or updating token caps."""

    model_config = ConfigDict(extra="forbid")

    provider_config_id: uuid.UUID
    project_id: uuid.UUID | None = None
    period_kind: Literal["daily", "monthly"]
    token_cap: int = Field(ge=0, le=10_000_000_000)
