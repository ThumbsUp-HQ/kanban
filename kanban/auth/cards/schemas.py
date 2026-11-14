# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Pydantic schemas for Multi-Card Auth Studio cards (KB-P2-03, KB-P2-10)."""

from __future__ import annotations

import re
import uuid  # noqa: TC003  # Runtime import required for Pydantic v2 type evaluation
from datetime import datetime  # noqa: TC003  # Runtime import required for Pydantic v2 type evaluation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLUG_REGEX = re.compile(r"^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$")


class AuthCardPublic(BaseModel):
    """Public card summary displayed on login screen.

    Exposes no secret ciphertext, configuration internals, or administrative fields.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    slug: str
    display_name: str
    button_subtext: str | None = None
    icon_preset: str = "key"
    provider_kind: str


class AuthCardPublicListResponse(BaseModel):
    """List of enabled cards for the public login screen."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cards: list[AuthCardPublic]


class AuthCardAdmin(BaseModel):
    """Administrative card presentation model.

    Includes non-secret metadata and boolean presence indicator for secrets.
    Never exposes encrypted_secret_blob or wrapped_dek.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    workspace_id: uuid.UUID | None = None
    provider_kind: str
    slug: str
    display_name: str
    button_subtext: str | None = None
    icon_preset: str = "key"
    is_enabled: bool = False
    sort_rank: str
    auto_provision_users: bool = False
    allowed_email_domains: list[str] = Field(default_factory=list)
    public_config: dict[str, Any] = Field(default_factory=dict)
    dek_kid: str = "kek-v1"
    last_health_status: str = "UNVERIFIED"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    has_secret: bool = False


class AuthCardAdminListResponse(BaseModel):
    """List of all authentication cards for administrative overview."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cards: list[AuthCardAdmin]


class AuthCardCreate(BaseModel):
    """Payload to create a new authentication card."""

    model_config = ConfigDict(extra="forbid")

    provider_kind: Literal["OIDC", "OAUTH2", "LDAP", "LOCAL_ADMIN"]
    slug: str = Field(min_length=3, max_length=48)
    display_name: str = Field(min_length=1, max_length=100)
    button_subtext: str | None = Field(default=None, max_length=200)
    icon_preset: str = Field(default="key", max_length=50)
    is_enabled: bool = False
    sort_rank: str | None = None
    auto_provision_users: bool = False
    allowed_email_domains: list[str] = Field(default_factory=list, max_length=50)
    public_config: dict[str, Any] = Field(default_factory=dict)
    secret: str | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate slug follows standard format."""
        if not SLUG_REGEX.match(v):
            msg = "Slug must match '^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$'"
            raise ValueError(msg)
        return v


class AuthCardUpdate(BaseModel):
    """Payload to update an existing authentication card."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    button_subtext: str | None = Field(default=None, max_length=200)
    icon_preset: str | None = Field(default=None, max_length=50)
    is_enabled: bool | None = None
    auto_provision_users: bool | None = None
    allowed_email_domains: list[str] | None = Field(default=None, max_length=50)
    public_config: dict[str, Any] | None = None
    secret: str | None = None


class AuthCardReorderRequest(BaseModel):
    """Payload to reposition an authentication card in the display sequence."""

    model_config = ConfigDict(extra="forbid")

    after: str | None = None


class AuthCardDeleteRequest(BaseModel):
    """Payload required to permanently delete an authentication card."""

    model_config = ConfigDict(extra="forbid")

    confirm_slug: str


class HandshakeProbeResult(BaseModel):
    """Diagnostic result of a live authentication provider handshake probe."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    status: str
    latency_ms: int
    error_code: str | None = None
