"""Pydantic schemas for Issue Copy API (KB-P3-08, S7.2 8n)."""

from __future__ import annotations

import uuid  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from kanban.api.v1.schemas.issues import IssueResponse  # noqa: TC001


class IssueCopyRequest(BaseModel):
    """Payload for issue copy request with interactive checkboxes."""

    model_config = ConfigDict(extra="forbid")

    include_sub_issues: bool = False
    include_attachments: bool = False
    link_as_relates_to: bool = False


class CopiedSubIssueSummary(BaseModel):
    """Summary pair mapping a copied sub-issue source key to its new copy key."""

    model_config = ConfigDict(extra="forbid")

    source_key: str
    copy_key: str


class IssueCopySkipped(BaseModel):
    """Summary of skipped objects during copy operation without leaking keys or titles."""

    model_config = ConfigDict(extra="forbid")

    restricted_sub_issues: int = 0


class IssueCopyResponse(BaseModel):
    """Canonical response for copy issue endpoint."""

    model_config = ConfigDict(extra="forbid")

    issue: IssueResponse
    copied_sub_issues: list[CopiedSubIssueSummary] = Field(default_factory=list)
    skipped: IssueCopySkipped = Field(default_factory=IssueCopySkipped)
    copied_attachments: int = 0
    link_id: uuid.UUID | None = None
