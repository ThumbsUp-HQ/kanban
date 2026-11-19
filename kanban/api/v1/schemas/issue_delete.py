"""Pydantic schemas for issue delete preview, trash, and restore endpoints (S7.2 8q, S12.3)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by Pydantic
from datetime import datetime  # noqa: TC003  # Required at runtime by Pydantic

from pydantic import BaseModel, ConfigDict, Field

from kanban.api.v1.schemas.issues import (
    PrioritySummary,  # noqa: TC001  # Required at runtime by Pydantic
    StateSummary,  # noqa: TC001  # Required at runtime by Pydantic
)

__all__ = [
    "BlastRadiusResponse",
    "IssueDeleteResponse",
    "TrashedIssueItem",
    "TrashedIssueList",
]


class BlastRadiusResponse(BaseModel):
    """Blast radius preview summary driving delete confirmation (S7.2 8q)."""

    model_config = ConfigDict(extra="forbid")

    issue_key: str
    sub_issues_unparented: int
    inbound_links_flagged: int
    outbound_links: int
    comments: int
    attachments: int
    summary_text: str
    blast_hash: str
    retention_days: int


class IssueDeleteResponse(BaseModel):
    """Response returned upon successful soft-delete into trash."""

    model_config = ConfigDict(extra="forbid")

    issue_key: str
    deleted_at: datetime
    purge_after: datetime


class TrashedIssueItem(BaseModel):
    """Item representation in the project trash bin."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    key: str
    summary: str
    deleted_at: datetime
    purge_after: datetime
    state: StateSummary | None = None
    priority: PrioritySummary | None = None
    capabilities: list[str] = Field(default_factory=list)


class TrashedIssueList(BaseModel):
    """Keyset-paginated listing of trashed issues."""

    model_config = ConfigDict(extra="forbid")

    items: list[TrashedIssueItem]
    next_cursor: str | None = None


class TrashedObjectItem(BaseModel):
    """Unified representation of any soft-deleted entity in project trash."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    key: str
    kind: str
    title: str
    deleted_at: datetime
    purge_after: datetime
    remaining_days: int
    capabilities: list[str] = Field(default_factory=list)


class TrashedObjectList(BaseModel):
    """Listing of all soft-deleted objects in project trash."""

    model_config = ConfigDict(extra="ignore")

    items: list[TrashedObjectItem]
    retention_days: int
