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
    approval_status: str | None = None
    required_approver_tier: str | None = None
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CustomFieldApprovalRequestCreate(BaseModel):
    """Payload to request escalation approval for a custom field."""

    model_config = ConfigDict(extra="forbid")

    manifest_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    justification: str = Field(min_length=10, max_length=2000)


class CustomFieldApprovalApproveRequest(BaseModel):
    """Payload to approve a pending custom field escalation."""

    model_config = ConfigDict(extra="forbid")

    manifest_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    sp_warning_acknowledged: bool = False


class CustomFieldApprovalResponse(BaseModel):
    """Public projection of a custom field escalation approval record."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    field_id: uuid.UUID
    manifest_sha256: str
    target_scope: str
    credential_mode: str
    required_tier: str
    status: str
    requested_by_id: uuid.UUID
    justification: str
    primary_approver_id: uuid.UUID | None = None
    primary_approver_aal: int | None = None
    primary_approved_at: datetime | None = None
    secondary_approver_id: uuid.UUID | None = None
    secondary_approver_aal: int | None = None
    secondary_approved_at: datetime | None = None
    sp_warning_acknowledged: bool
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    created_at: datetime


class WasmModuleUploadRequest(BaseModel):
    """Payload to upload and validate a WebAssembly module."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    wasm_base64: str = Field(description="Base64-encoded WebAssembly binary")


class WasmModuleResponse(BaseModel):
    """Projection of an approved WebAssembly module."""

    sha256: str
    name: str
    size_bytes: int


class CustomFieldValueItem(BaseModel):
    """Single custom field evaluation result or cached value."""

    field_id: str
    slug: str
    name: str
    output_format: str
    output_format_metadata: dict[str, Any] = Field(default_factory=dict)
    value: Any = None
    computed_at: str | None = None
    last_latency_ms: int = 0
    tier: str = "wasm"
    token_scope: str = "PROJECT"  # noqa: S105
    credential_mode: str = "INVOKING_USER"
    status: str = "computed"
