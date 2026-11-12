"""Pydantic schemas for Multi-Card Auth Studio cards (KB-P2-03)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuthCardPublic(BaseModel):
    """Public card summary displayed on login screen.

    Exposes no secret ciphertext, configuration internals, or administrative fields.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str
    display_name: str
    button_subtext: str | None = None
    icon_preset: str = "key"
    provider_kind: str


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
