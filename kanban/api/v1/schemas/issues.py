"""Issue request/response schemas (S7.2 8a, 8e, 8g, 8h, 8i; S12.2).

All request models forbid unknown keys. Parent references serialize conditionally:
readable parents include key and summary; unreadable parents serialize as
RestrictedParentSummary (S7.2 8h) with zero identifier leakage.
"""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by Pydantic field resolution
from datetime import date, datetime  # noqa: TC003  # Required at runtime by Pydantic

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
)

from kanban.api.v1.schemas.assignees import AssigneeResponse  # noqa: TC001
from kanban.api.v1.schemas.issue_provenance import IssueProvenance  # noqa: TC001
from kanban.security.access_manifest import AccessManifest  # noqa: TC001  # Pydantic runtime type


class NormalParentSummary(BaseModel):
    """Public summary of a readable parent issue."""

    model_config = ConfigDict(extra="forbid")

    key: str
    summary: str


class RestrictedParentSummary(BaseModel):
    """Masked representation of an unreadable parent issue (S7.2 8h)."""

    model_config = ConfigDict(extra="forbid")

    restricted: bool = True
    label: str = "🔒 Restricted Parent Issue"


class StateSummary(BaseModel):
    """Workflow state metadata for issue response representation."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    group: str


class PrioritySummary(BaseModel):
    """Project priority metadata for issue response representation."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    label: str
    emoji: str | None = None


class LabelSummary(BaseModel):
    """Project label metadata for issue response representation."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    color_hex: str


class IssueCreate(BaseModel):
    """Body of POST /api/v1/projects/{project_ref}/issues."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    description_markdown: str = ""
    priority: str | uuid.UUID | None = None
    state_id: uuid.UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    cycle_id: uuid.UUID | None = None
    parent: str | uuid.UUID | None = None
    label_ids: list[uuid.UUID] | None = None
    module_ids: list[uuid.UUID] | None = None

    @field_validator("label_ids", mode="after")
    @classmethod
    def _dedupe_labels(cls, value: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        if value is None:
            return None
        seen: set[uuid.UUID] = set()
        deduped: list[uuid.UUID] = []
        for lid in value:
            if lid not in seen:
                seen.add(lid)
                deduped.append(lid)
        return deduped

    @field_validator("module_ids", mode="after")
    @classmethod
    def _dedupe_modules(cls, value: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        if value is None:
            return None
        seen: set[uuid.UUID] = set()
        deduped: list[uuid.UUID] = []
        for mid in value:
            if mid not in seen:
                seen.add(mid)
                deduped.append(mid)
        return deduped


class IssuePatch(BaseModel):
    """Body of PATCH /api/v1/issues/{issue_ref} (omitted keys are unchanged)."""

    model_config = ConfigDict(extra="forbid")

    summary: str | None = None
    description_markdown: str | None = None
    priority: str | uuid.UUID | None = None
    state_id: uuid.UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    cycle_id: uuid.UUID | None = None
    parent: str | uuid.UUID | None = None
    label_ids: list[uuid.UUID] | None = None
    module_ids: list[uuid.UUID] | None = None

    @field_validator("label_ids", mode="after")
    @classmethod
    def _dedupe_labels(cls, value: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        if value is None:
            return None
        seen: set[uuid.UUID] = set()
        deduped: list[uuid.UUID] = []
        for lid in value:
            if lid not in seen:
                seen.add(lid)
                deduped.append(lid)
        return deduped

    @field_validator("module_ids", mode="after")
    @classmethod
    def _dedupe_modules(cls, value: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        if value is None:
            return None
        seen: set[uuid.UUID] = set()
        deduped: list[uuid.UUID] = []
        for mid in value:
            if mid not in seen:
                seen.add(mid)
                deduped.append(mid)
        return deduped


class ArchiveEligibility(BaseModel):
    """Eligibility status and explanatory reason for archiving (S7.2 8p)."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason: str | None = None


class IssueResponse(BaseModel):
    """Canonical issue representation returned by all issue endpoints."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    key: str
    summary: str
    description_markdown: str
    description_sha256: str
    state: StateSummary
    priority: PrioritySummary
    start_date: date | None = None
    due_date: date | None = None
    cycle_id: uuid.UUID | None = None
    parent: NormalParentSummary | RestrictedParentSummary | None = None
    labels: list[LabelSummary] = Field(default_factory=list)
    module_ids: list[uuid.UUID] | None = Field(default=None)
    assignees: list[AssigneeResponse] = Field(default_factory=list)
    board_rank: str
    created_by_id: uuid.UUID
    provenance: IssueProvenance
    access_manifest: AccessManifest
    capabilities: list[str]
    archived_at: datetime | None = None
    archive_eligibility: ArchiveEligibility

    @model_serializer(mode="wrap")
    def _strip_module_ids_if_none(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        data: dict[str, object] = handler(self)
        if data.get("module_ids") is None:
            data.pop("module_ids", None)
        return data


class IssueList(BaseModel):
    """Keyset-paginated issue listing."""

    model_config = ConfigDict(extra="forbid")

    items: list[IssueResponse]
    next_cursor: str | None = None
