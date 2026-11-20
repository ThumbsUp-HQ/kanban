"""Issue request/response schemas (S7.2 8a, 8e, 8g, 8h, 8i; S12.2).

All request models forbid unknown keys. Parent references serialize conditionally:
readable parents include key and summary; unreadable parents serialize as
RestrictedParentSummary (S7.2 8h) with zero identifier leakage.
"""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by Pydantic field resolution
from datetime import date, datetime  # noqa: TC003  # Required at runtime by Pydantic
from typing import TYPE_CHECKING, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
)

if TYPE_CHECKING:
    from pydantic.json_schema import JsonSchemaValue
    from pydantic_core import core_schema

from kanban.api.v1.schemas.assignees import AssigneeResponse  # noqa: TC001
from kanban.api.v1.schemas.issue_provenance import IssueProvenance  # noqa: TC001
from kanban.issues.serializers import (  # noqa: TC001
    LatestGateVerdictSummary,
    PendingGateSummary,
)
from kanban.security.access_manifest import AccessManifest  # noqa: TC001  # Pydantic runtime type


class NormalParentSummary(BaseModel):
    """Public summary of a readable parent issue."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Canonical project-qualified issue key (e.g. KAN-142)")
    summary: str = Field(description="Issue summary title")


class RestrictedParentSummary(BaseModel):
    """Masked representation of an unreadable parent issue (S7.2 8h)."""

    model_config = ConfigDict(extra="forbid")

    restricted: bool = Field(default=True, description="Always true for restricted parent issues")
    label: str = Field(
        default="🔒 Restricted Parent Issue",
        description="Masked placeholder label for parent issue outside caller visibility",
    )


class StateSummary(BaseModel):
    """Workflow state metadata for issue response representation."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Workflow state UUID")
    name: str = Field(description="Workflow state display name")
    group: str = Field(
        description="Workflow state group: backlog, unstarted, started, completed, or cancelled",
    )
    color_hex: str | None = Field(
        default=None,
        description="Workflow state display color hex (e.g. #7c3aed)",
    )


class PrioritySummary(BaseModel):
    """Project priority metadata for issue response representation."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(description="Priority slug identifier (e.g. urgent, high, medium, low, none)")
    label: str = Field(description="Human-readable priority display label")
    emoji: str | None = Field(default=None, description="Optional single semantic priority emoji")


class LabelSummary(BaseModel):
    """Project label metadata for issue response representation."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Label UUID")
    name: str = Field(description="Label text name")
    color_hex: str = Field(description="Hexadecimal color code (e.g. #FF5733)")


class CycleSummary(BaseModel):
    """Sprint cycle metadata for issue response representation."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Cycle UUID")
    name: str = Field(description="Cycle name")


class ModuleSummary(BaseModel):
    """Module metadata for issue response representation."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Module UUID")
    name: str = Field(description="Module name")


class IssueCreate(BaseModel):
    """Body of POST /api/v1/projects/{project_ref}/issues."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(description="Issue summary title")
    description_markdown: str = Field(
        default="", description="Issue description body in canonical Markdown"
    )
    priority: str | uuid.UUID | None = Field(
        default=None, description="Priority slug or UUID identifier"
    )
    state: str | uuid.UUID | None = Field(
        default=None, description="Workflow state name or UUID identifier"
    )
    state_id: uuid.UUID | None = Field(default=None, description="Workflow state UUID identifier")
    start_date: date | None = Field(default=None, description="Scheduled start date (YYYY-MM-DD)")
    due_date: date | None = Field(
        default=None, description="Target completion due date (YYYY-MM-DD)"
    )
    cycle_id: uuid.UUID | None = Field(default=None, description="Optional sprint cycle UUID")
    parent: str | uuid.UUID | None = Field(default=None, description="Parent issue key or UUID")
    label_ids: list[uuid.UUID] | None = Field(
        default=None, description="List of label UUIDs to attach"
    )
    module_ids: list[uuid.UUID] | None = Field(
        default=None, description="List of module UUIDs to assign"
    )

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

    summary: str | None = Field(default=None, description="Updated issue summary title")
    description_markdown: str | None = Field(
        default=None, description="Updated issue description body in canonical Markdown"
    )
    priority: str | uuid.UUID | None = Field(
        default=None, description="Updated priority slug or UUID identifier"
    )
    state: str | uuid.UUID | None = Field(
        default=None, description="Updated workflow state name or UUID identifier"
    )
    state_id: uuid.UUID | None = Field(
        default=None, description="Updated workflow state UUID identifier"
    )
    start_date: date | None = Field(default=None, description="Updated scheduled start date")
    due_date: date | None = Field(default=None, description="Updated target completion due date")
    cycle_id: uuid.UUID | None = Field(default=None, description="Updated sprint cycle UUID")
    parent: str | uuid.UUID | None = Field(
        default=None, description="Updated parent issue key or UUID"
    )
    label_ids: list[uuid.UUID] | None = Field(
        default=None, description="Updated list of attached label UUIDs"
    )
    module_ids: list[uuid.UUID] | None = Field(
        default=None, description="Updated list of assigned module UUIDs"
    )

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

    allowed: bool = Field(description="Whether the issue is currently eligible for archiving")
    reason: str | None = Field(
        default=None, description="Explanatory reason if archiving is prohibited"
    )


class IssueResponse(BaseModel):
    """Canonical issue representation returned by all issue endpoints."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Unique issue UUID identifier")
    object_id: uuid.UUID = Field(
        description="Spine object record UUID identifier matching issue.id",
    )
    key: str = Field(description="Canonical issue key (e.g. KAN-101)")
    summary: str = Field(description="Issue summary title")
    description_markdown: str = Field(description="Canonical UTF-8 Markdown description body")
    description_sha256: str = Field(
        description="Hex-encoded SHA-256 digest of description_markdown for ETag concurrency"
    )
    etag: str | None = Field(
        default=None,
        description=(
            "Quoted strong ETag digest covering description and serialized attributes (KANBA-212)"
        ),
    )
    state: StateSummary = Field(description="Workflow state metadata")
    priority: PrioritySummary = Field(description="Priority metadata")
    start_date: date | None = Field(default=None, description="Scheduled start date (YYYY-MM-DD)")
    due_date: date | None = Field(
        default=None, description="Target completion due date (YYYY-MM-DD)"
    )
    cycle_id: uuid.UUID | None = Field(default=None, description="Sprint cycle UUID if assigned")
    cycle: CycleSummary | None = Field(
        default=None, description="Sprint cycle metadata if assigned"
    )
    parent: NormalParentSummary | RestrictedParentSummary | None = Field(
        default=None, description="Parent issue summary or masked restricted placeholder"
    )
    labels: list[LabelSummary] = Field(
        default_factory=list, description="List of attached project labels"
    )
    module_ids: list[uuid.UUID] | None = Field(
        default=None, description="List of assigned module UUIDs"
    )
    modules: list[ModuleSummary] = Field(
        default_factory=list, description="List of assigned module metadata"
    )
    assignees: list[AssigneeResponse] = Field(
        default_factory=list, description="List of principal or free-text assignees"
    )
    board_rank: str = Field(description="Fractional indexing board order rank")
    created_by_id: uuid.UUID = Field(description="UUID of the principal who created this issue")
    provenance: IssueProvenance = Field(
        description="Creator provenance and administrative override tracking"
    )
    access_manifest: AccessManifest = Field(
        description="Anti-enumeration access manifest metadata (S3.4)"
    )
    capabilities: list[str] = Field(
        description="Effective capabilities held by the calling principal on this issue"
    )
    created_at: datetime = Field(description="Issue creation timestamp")
    updated_at: datetime = Field(description="Issue last updated timestamp")
    archived_at: datetime | None = Field(
        default=None, description="Timestamp when the issue was archived, if archived"
    )
    archive_eligibility: ArchiveEligibility = Field(
        description="Archiving eligibility status and reason"
    )
    note: str | None = Field(
        default=None, description="Optional contextual note or transition reason"
    )
    pending_gate: PendingGateSummary | None = Field(
        default=None, description="Active asynchronous agent gate hold metadata, if pending"
    )
    latest_gate_verdict: LatestGateVerdictSummary | None = Field(
        default=None, description="Latest completed agent transition gate verdict, if any"
    )

    @model_serializer(mode="wrap")
    def _strip_module_ids_if_none(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        data: dict[str, object] = handler(self)
        if data.get("module_ids") is None:
            data.pop("module_ids", None)
            data.pop("modules", None)
        return data

    @classmethod
    def __get_pydantic_json_schema__(
        cls, cs: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        """Preserve full field schema in OpenAPI serialization mode despite wrap serializer."""
        if cs.get("serialization"):
            stripped_cs = dict(cs)
            stripped_cs.pop("serialization", None)
            cs = cast("core_schema.CoreSchema", stripped_cs)
        schema = handler(cs)
        if cls.__doc__ and "description" not in schema:
            schema["description"] = cls.__doc__.strip()
        return schema


class IssueList(BaseModel):
    """Keyset-paginated issue listing."""

    model_config = ConfigDict(extra="forbid")

    items: list[IssueResponse] = Field(description="List of issue responses matching query")
    next_cursor: str | None = Field(
        default=None, description="Opaque keyset cursor for fetching next page"
    )
