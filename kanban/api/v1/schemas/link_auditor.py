# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Pydantic schemas for admin link auditor and purge operations (KB-P4-11, S12.3)."""

from __future__ import annotations

import datetime as dt  # noqa: TC003  # Required at runtime by Pydantic
import uuid  # noqa: TC003  # Required at runtime by Pydantic
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InvalidLinkReason(StrEnum):
    """Universal Object Graph link invalidity classifications (S12.3)."""

    DANGLING_SOURCE = "DANGLING_SOURCE"
    DANGLING_TARGET = "DANGLING_TARGET"
    SOFT_DELETED_ENDPOINT = "SOFT_DELETED_ENDPOINT"
    ARCHIVED_POLICY_VIOLATION = "ARCHIVED_POLICY_VIOLATION"
    TYPE_MATRIX_VIOLATION = "TYPE_MATRIX_VIOLATION"
    CROSS_WORKSPACE_LEAK = "CROSS_WORKSPACE_LEAK"
    PERMISSION_SEVERED = "PERMISSION_SEVERED"


class LinkAuditScanResponse(BaseModel):
    """Summary scan report of flagged invalid object links grouped by reason."""

    model_config = ConfigDict(extra="forbid")

    flagged_total: int = Field(..., description="Total count of flagged invalid links")
    by_reason: dict[str, int] = Field(
        ...,
        description="Counts of flagged invalid links grouped by invalidity reason",
    )


class LinkAuditRecordResponse(BaseModel):
    """Detailed audit snapshot of a flagged invalid object link."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(..., description="Audit record UUID")
    workspace_id: uuid.UUID = Field(..., description="Workspace UUID")
    link_id: uuid.UUID = Field(..., description="Flagged object link UUID")
    reason: str = Field(..., description="Invalidity reason code")
    detected_at: dt.datetime = Field(..., description="Detection timestamp")
    purged_at: dt.datetime | None = Field(
        default=None,
        description="Purge timestamp if purged",
    )
    resolved_at: dt.datetime | None = Field(
        default=None,
        description="Resolution timestamp if resolved",
    )
    link_snapshot: dict[str, Any] = Field(
        ...,
        description="Frozen snapshot of object_links row at audit time",
    )
    source_snapshot: dict[str, Any] | None = Field(
        default=None,
        description="Snapshot of source object at audit time",
    )
    target_snapshot: dict[str, Any] | None = Field(
        default=None,
        description="Snapshot of target object at audit time",
    )


class LinkAuditListResponse(BaseModel):
    """Paginated list of invalid object link audit records."""

    model_config = ConfigDict(extra="forbid")

    items: list[LinkAuditRecordResponse] = Field(
        ...,
        description="List of link audit records matching filters",
    )
    next_cursor: str | None = Field(
        default=None,
        description="Keyset pagination cursor for subsequent page",
    )
    has_more: bool = Field(
        default=False,
        description="Whether more records exist beyond the current page",
    )
    total: int | None = Field(
        default=None,
        description="Total unpurged count if requested",
    )


class LinkPurgeRequest(BaseModel):
    """Request payload for executing audited purge of flagged invalid object links."""

    model_config = ConfigDict(extra="forbid")

    audit_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=200,
        description="List of 1 to 200 audit record UUIDs to purge",
    )
    reason: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Mandatory administrative justification (10 to 500 characters)",
    )


class LinkPurgeResponse(BaseModel):
    """Result of executing audited purge of flagged invalid object links."""

    model_config = ConfigDict(extra="forbid")

    purged_count: int = Field(..., description="Number of invalid links purged")
    activity_ids: list[str] = Field(
        ...,
        description="List of activity ledger UUIDs emitted for the purge",
    )
