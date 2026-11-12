# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Pydantic schemas for Custom Field definitions REST API (KB-P5-11, S13.1)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by Pydantic
from datetime import datetime  # noqa: TC003  # Required at runtime by Pydantic
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from kanban.custom_fields.output_formats import OutputFormatType  # noqa: TC001  # Pydantic runtime


class CustomFieldCreateRequest(BaseModel):
    """Payload to create a new admin-defined custom field."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    name: str = Field(min_length=1, max_length=80)
    tier: Literal["wasm", "nsjail"] = "wasm"
    output_format: OutputFormatType
    output_format_metadata: dict[str, Any] = Field(default_factory=dict)
    script_source: str = Field(min_length=1, max_length=131072)
    wasm_module_sha256: str | None = None
    target_scope: Literal["PROJECT", "WORKSPACE", "SERVER"] = "PROJECT"
    credential_mode: Literal["INVOKING_USER", "PROJECT_ADMIN_SP", "SERVER_ADMIN_SP"] = (
        "INVOKING_USER"
    )
    egress_allowlist: list[str] = Field(default_factory=list, max_length=16)
    is_enabled: bool = True


class CustomFieldUpdateRequest(BaseModel):
    """Payload to update an existing admin-defined custom field."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    tier: Literal["wasm", "nsjail"] | None = None
    output_format: OutputFormatType | None = None
    output_format_metadata: dict[str, Any] | None = None
    script_source: str | None = Field(default=None, min_length=1, max_length=131072)
    wasm_module_sha256: str | None = None
    target_scope: Literal["PROJECT", "WORKSPACE", "SERVER"] | None = None
    credential_mode: Literal["INVOKING_USER", "PROJECT_ADMIN_SP", "SERVER_ADMIN_SP"] | None = None
    egress_allowlist: list[str] | None = Field(default=None, max_length=16)
    is_enabled: bool | None = None


class CustomFieldResponse(BaseModel):
    """Public projection of a custom field definition."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    slug: str
    name: str
    tier: str
    output_format: str
    output_format_metadata: dict[str, Any]
    script_source: str | None = None
    wasm_module_sha256: str | None = None
    script_version: int
    target_scope: str
    credential_mode: str
    egress_allowlist: list[str]
    manifest_sha256: str | None = None
    is_enabled: bool
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
