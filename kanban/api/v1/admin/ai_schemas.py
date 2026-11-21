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

    id: uuid.UUID = Field(description="Unique AI provider configuration UUID")
    provider_kind: str = Field(
        description="Provider kind identifier (e.g. openai, gemini, ollama, custom)"
    )
    display_name: str = Field(description="Human-readable provider display label")
    base_url: str | None = Field(
        default=None, description="Optional custom HTTP base URL for provider endpoint"
    )
    model_allowlist: list[str] = Field(
        description="List of model names authorized for completions on this provider"
    )
    residency_tier: str = Field(
        description="Data residency classification tier (e.g. us-east, eu-central, local)"
    )
    priority: int = Field(description="Provider fallback priority order (lower evaluates first)")
    settings: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary provider-specific configuration key-value pairs",
    )
    api_key_set: bool = Field(
        description="Whether an API secret key has been configured (key itself is write-only)"
    )
    is_enabled: bool = Field(description="Whether the provider configuration is currently enabled")
    project_id: uuid.UUID | None = Field(
        default=None, description="Owning project UUID if scoped to a project, null for workspace"
    )


class ProviderConfigCreate(BaseModel):
    """Payload for creating a new AI provider configuration."""

    model_config = ConfigDict(extra="forbid")

    provider_kind: str = Field(
        description="Provider kind identifier (e.g. openai, gemini, ollama, custom)"
    )
    display_name: str = Field(
        min_length=1, max_length=80, description="Human-readable provider display label"
    )
    model_allowlist: list[str] = Field(
        default_factory=list, description="List of authorized model names"
    )
    residency_tier: str = Field(default="default", description="Data residency tier classification")
    base_url: str | None = Field(
        default=None, description="Optional custom HTTP base URL for provider"
    )
    priority: int = Field(
        default=100, description="Provider fallback priority order (lower evaluates first)"
    )
    settings: dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific configuration dictionary"
    )
    project_id: uuid.UUID | None = Field(
        default=None, description="Optional project UUID if scoping to a single project"
    )
    is_enabled: bool = Field(
        default=True, description="Whether to immediately enable this provider"
    )
    api_key: SecretStr | None = Field(
        default=None, description="Secret API key credential (stored using envelope encryption)"
    )

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

    display_name: str | None = Field(
        default=None, min_length=1, max_length=80, description="Updated display label"
    )
    model_allowlist: list[str] | None = Field(
        default=None, description="Updated list of authorized model names"
    )
    residency_tier: str | None = Field(
        default=None, description="Updated data residency tier classification"
    )
    base_url: str | None = Field(
        default=None, description="Updated custom HTTP base URL for provider"
    )
    priority: int | None = Field(default=None, description="Updated fallback priority order")
    settings: dict[str, Any] | None = Field(
        default=None, description="Updated provider-specific configuration dictionary"
    )
    is_enabled: bool | None = Field(
        default=None, description="Updated provider enablement status toggle"
    )
    api_key: SecretStr | None = Field(
        default=None, description="Updated secret API key (pass null to clear existing key)"
    )

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

    period_kind: Literal["daily", "monthly"] = Field(
        description="Accounting period tier: daily or monthly"
    )
    period_start: date = Field(description="Period start calendar date (YYYY-MM-DD)")
    token_cap: int = Field(
        ge=0, le=10_000_000_000, description="Configured maximum token budget cap"
    )
    tokens_used: int = Field(ge=0, description="Tokens committed and consumed in this period")
    tokens_reserved: int = Field(ge=0, description="Tokens currently held in active reservations")


class BudgetSetRequest(BaseModel):
    """Payload for setting or updating token caps."""

    model_config = ConfigDict(extra="forbid")

    provider_config_id: uuid.UUID = Field(description="Target AI provider configuration UUID")
    project_id: uuid.UUID | None = Field(
        default=None, description="Optional project UUID if setting a project-specific budget"
    )
    period_kind: Literal["daily", "monthly"] = Field(
        description="Budget period tier: daily or monthly"
    )
    token_cap: int = Field(ge=0, le=10_000_000_000, description="Target maximum token budget cap")


class ProviderReorderRequest(BaseModel):
    """Payload for atomically reordering AI providers."""

    model_config = ConfigDict(extra="forbid")

    ordered_ids: list[uuid.UUID] = Field(
        min_length=1, description="List of provider UUIDs in ascending priority order"
    )


class ProviderProbeRequest(BaseModel):
    """Payload for probing or testing connection to an unsaved AI provider."""

    model_config = ConfigDict(extra="forbid")

    provider_kind: str = Field(description="Provider kind identifier (e.g. openai, gemini, ollama)")
    base_url: str | None = Field(default=None, description="Optional custom HTTP base URL")
    api_key: SecretStr | None = Field(default=None, description="Optional secret API key")
    settings_json: dict[str, Any] | None = Field(default=None, description="Optional settings")

    @field_validator("api_key")
    @classmethod
    def _validate_api_key_len(cls, v: SecretStr | None) -> SecretStr | None:
        if v is not None and len(v.get_secret_value()) > _MAX_KEY_LENGTH:
            msg = f"api_key length exceeds {_MAX_KEY_LENGTH} characters"
            raise ValueError(msg)
        return v


class SavedProviderProbeRequest(BaseModel):
    """Optional payload when probing or testing an existing saved provider."""

    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr | None = Field(
        default=None, description="Optional override API key (uses saved key if omitted)"
    )
    settings_json: dict[str, Any] | None = Field(
        default=None, description="Optional override settings (uses saved settings if omitted)"
    )

    @field_validator("api_key")
    @classmethod
    def _validate_api_key_len(cls, v: SecretStr | None) -> SecretStr | None:
        if v is not None and len(v.get_secret_value()) > _MAX_KEY_LENGTH:
            msg = f"api_key length exceeds {_MAX_KEY_LENGTH} characters"
            raise ValueError(msg)
        return v


class ProviderProbeResult(BaseModel):
    """Structured diagnostic result of server-side model probing or connection test."""

    model_config = ConfigDict(extra="forbid")

    ok: bool = Field(description="Whether connection and probe succeeded")
    latency_ms: float = Field(ge=0.0, description="Round-trip latency in milliseconds")
    models: list[str] = Field(
        default_factory=list,
        description="List of discovered model identifiers",
    )
    model_count: int = Field(ge=0, description="Count of discovered models")
    error_code: str | None = Field(default=None, description="Diagnostic error code if failed")
    message: str | None = Field(default=None, description="Human-readable status or error message")
