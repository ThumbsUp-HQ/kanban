"""Pydantic v2 schemas for saved views CRUD and 2D query engine (S6.4, S3.4)."""

from __future__ import annotations

import json
import uuid  # noqa: TC003  # Required at runtime by Pydantic field resolution
from datetime import date  # noqa: TC003  # Required at runtime by Pydantic field resolution
from enum import StrEnum
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.issues import IssueResponse  # noqa: TC001  # Required at runtime by Pydantic
from kanban.security.access_manifest import AccessManifest  # noqa: TC001  # Required at runtime by Pydantic

MAX_FILTER_DEPTH: Final[int] = 3
MAX_FILTER_LEAVES: Final[int] = 25
MAX_ARRAY_ITEMS: Final[int] = 50
MAX_PAYLOAD_BYTES: Final[int] = 32768
MAX_WIP_LIMIT: Final[int] = 10000
MIN_WIP_LIMIT: Final[int] = 1


class ViewLayout(StrEnum):
    """Supported view layout formats."""

    BOARD = "board"
    LIST = "list"
    TABLE = "table"
    CALENDAR = "calendar"
    TIMELINE = "timeline"

    @classmethod
    def _missing_(cls, value: object) -> ViewLayout | None:
        if isinstance(value, str):
            normalized = value.strip().lower()
            aliases = {
                "kanban": cls.BOARD,
                "spreadsheet": cls.TABLE,
                "gantt": cls.TIMELINE,
            }
            if normalized in aliases:
                return aliases[normalized]
        return None


class GroupAxis(StrEnum):
    """Allowed grouping axes for 2D board and query engine."""

    NONE = "none"
    STATE = "state"
    PRIORITY = "priority"
    ASSIGNEE = "assignee"
    CYCLE = "cycle"
    MODULE = "module"
    LABEL = "label"


class SortField(StrEnum):
    """Allowed sort fields for query engine."""

    BOARD_RANK = "board_rank"
    SEQUENCE_ID = "sequence_id"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    DUE_DATE = "due_date"
    PRIORITY = "priority"


class SortDir(StrEnum):
    """Sort direction."""

    ASC = "asc"
    DESC = "desc"


class LabelMatch(StrEnum):
    """Label matching strategy."""

    ANY = "any"
    ALL = "all"


class GateStatus(StrEnum):
    """Workflow gate status filter."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def _check_complexity(data: object, depth: int = 1) -> tuple[int, int]:
    """Recursively calculate max depth and total leaf count in a filter payload."""
    if depth > MAX_FILTER_DEPTH:
        raise ProblemException(
            code="FILTER_TOO_COMPLEX",
            status=422,
            title="Filter Too Complex",
            detail=f"Filter nesting depth exceeded limit of {MAX_FILTER_DEPTH}",
        )
    if isinstance(data, dict):
        max_d = depth
        leaves = 0
        for val in data.values():
            d, leaf = _check_complexity(val, depth + 1)
            max_d = max(max_d, d)
            leaves += leaf
        if leaves > MAX_FILTER_LEAVES:
            raise ProblemException(
                code="FILTER_TOO_COMPLEX",
                status=422,
                title="Filter Too Complex",
                detail=f"Filter leaf count exceeded limit of {MAX_FILTER_LEAVES}",
            )
        return max_d, leaves
    if isinstance(data, list):
        if len(data) > MAX_ARRAY_ITEMS:
            raise ProblemException(
                code="FILTER_TOO_COMPLEX",
                status=422,
                title="Filter Too Complex",
                detail=f"Filter list operand exceeded limit of {MAX_ARRAY_ITEMS} items",
            )
        max_d = depth
        leaves = 0
        for item in data:
            d, leaf = _check_complexity(item, depth + 1)
            max_d = max(max_d, d)
            leaves += leaf
        return max_d, leaves
    return depth, 1


class FilterSpec(BaseModel):
    """Typed filter DSL for saved views and issue queries."""

    model_config = ConfigDict(extra="forbid")

    state_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_ARRAY_ITEMS)
    state_groups: list[str] = Field(default_factory=list, max_length=MAX_ARRAY_ITEMS)
    priority_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_ARRAY_ITEMS)
    assignee_ids: list[str] = Field(default_factory=list, max_length=MAX_ARRAY_ITEMS)
    has_free_text_assignee: bool | None = None
    label_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_ARRAY_ITEMS)
    label_match: LabelMatch = LabelMatch.ANY
    cycle_ids: list[str] = Field(default_factory=list, max_length=MAX_ARRAY_ITEMS)
    module_ids: list[str] = Field(default_factory=list, max_length=MAX_ARRAY_ITEMS)
    parent_issue_id: str | None = None
    start_date_from: date | None = None
    start_date_to: date | None = None
    due_date_from: date | None = None
    due_date_to: date | None = None
    overdue_only: bool = False
    blocked: bool | None = None
    gate_status: GateStatus | None = None
    include_archived: bool = False
    search_query: str | None = Field(default=None, max_length=200)

    @field_validator(
        "state_ids",
        "state_groups",
        "priority_ids",
        "assignee_ids",
        "label_ids",
        "cycle_ids",
        "module_ids",
        mode="before",
    )
    @classmethod
    def validate_array_length(cls, val: object) -> object:
        """Validate max array operand length."""
        if isinstance(val, list) and len(val) > MAX_ARRAY_ITEMS:
            raise ProblemException(
                code="FILTER_TOO_COMPLEX",
                status=422,
                title="Filter Too Complex",
                detail=f"Filter list operand exceeded limit of {MAX_ARRAY_ITEMS} items",
            )
        return val

    @model_validator(mode="before")
    @classmethod
    def validate_payload_limits(cls, data: object) -> object:
        """Enforce payload size and AST complexity limits."""
        if isinstance(data, dict):
            if "text" in data and "search_query" not in data:
                data["search_query"] = data.pop("text")
            try:
                dumped = json.dumps(data)
                if len(dumped.encode("utf-8")) > MAX_PAYLOAD_BYTES:
                    raise ProblemException(
                        code="FILTER_TOO_COMPLEX",
                        status=422,
                        title="Filter Too Complex",
                        detail=f"Filter JSON payload exceeds {MAX_PAYLOAD_BYTES} bytes",
                    )
            except (TypeError, ValueError):
                pass
            _check_complexity(data)
        return data


class WipLimit(BaseModel):
    """Soft and hard WIP limits for a group bucket."""

    model_config = ConfigDict(extra="forbid")

    soft: int | None = Field(default=None, ge=MIN_WIP_LIMIT, le=MAX_WIP_LIMIT)
    hard: int | None = Field(default=None, ge=MIN_WIP_LIMIT, le=MAX_WIP_LIMIT)

    @model_validator(mode="after")
    def validate_limits(self) -> WipLimit:
        """Ensure hard limit is at least soft limit."""
        if self.soft is not None and self.hard is not None and self.hard < self.soft:
            raise ProblemException(
                code="INVALID_WIP_LIMITS",
                status=422,
                title="Invalid WIP Limits",
                detail="Hard WIP limit must be greater than or equal to soft WIP limit",
            )
        return self


class ViewOwnerSummary(BaseModel):
    """Owner summary for view serialization."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    display_name: str
    handle: str | None = None


class ViewCreate(BaseModel):
    """Payload for creating a new saved view."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120, description="Saved view display name")
    description_markdown: str = Field(
        default="", max_length=16384, description="Detailed Markdown description of the view"
    )
    layout: ViewLayout = Field(
        default=ViewLayout.BOARD,
        description="View layout mode: board, list, table, calendar, or timeline",
    )
    group_by: GroupAxis | None = Field(
        default=None,
        description="Group axis: none, state, priority, assignee, cycle, module, or label",
    )
    sub_group_by: GroupAxis | None = Field(
        default=None, description="Secondary sub-grouping axis for 2D matrix rendering"
    )
    filters: FilterSpec = Field(
        default_factory=FilterSpec, description="Hierarchical issue filtering criteria"
    )
    wip_limits_override: dict[str, WipLimit | dict[str, Any]] = Field(
        default_factory=dict,
        description="Custom work-in-progress (WIP) soft/hard limits per bucket",
    )
    is_shared: bool = Field(
        default=False, description="Whether view is shared across workspace or private to creator"
    )
    visibility: str | None = Field(
        default=None, description="Explicit visibility classification token"
    )

    @field_validator("name")
    @classmethod
    def strip_name(cls, val: str) -> str:
        """Strip and validate name."""
        trimmed = val.strip()
        if not trimmed:
            raise ProblemException(
                code="INVALID_NAME",
                status=422,
                title="Invalid Name",
                detail="View name cannot be empty or whitespace only",
            )
        return trimmed


class ViewPatch(BaseModel):
    """Payload for updating an existing saved view."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None, min_length=1, max_length=120, description="Updated view display name"
    )
    description_markdown: str | None = Field(
        default=None, max_length=16384, description="Updated Markdown description"
    )
    layout: ViewLayout | None = Field(
        default=None, description="Updated layout mode: board, list, table, calendar, or timeline"
    )
    group_by: GroupAxis | None = Field(default=None, description="Updated primary grouping axis")
    sub_group_by: GroupAxis | None = Field(
        default=None, description="Updated secondary grouping axis"
    )
    filters: FilterSpec | None = Field(default=None, description="Updated issue filtering criteria")
    wip_limits_override: dict[str, WipLimit | dict[str, Any]] | None = Field(
        default=None, description="Updated custom WIP limits dictionary"
    )
    is_shared: bool | None = Field(default=None, description="Updated view sharing toggle")
    visibility: str | None = Field(
        default=None, description="Updated visibility classification token"
    )

    @field_validator("name")
    @classmethod
    def strip_name(cls, val: str | None) -> str | None:
        """Strip and validate name."""
        if val is None:
            return None
        trimmed = val.strip()
        if not trimmed:
            raise ProblemException(
                code="INVALID_NAME",
                status=422,
                title="Invalid Name",
                detail="View name cannot be empty or whitespace only",
            )
        return trimmed


class ViewResponse(BaseModel):
    """Canonical representation of a saved view."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Unique saved view UUID identifier")
    project_id: uuid.UUID | None = Field(
        description="Owning project UUID, or null for workspace-level views"
    )
    name: str = Field(description="Saved view display name")
    description_markdown: str = Field(description="Markdown description of the view")
    layout: ViewLayout = Field(description="View layout mode format")
    group_by: str = Field(description="Primary grouping axis slug")
    sub_group_by: str = Field(description="Secondary sub-grouping axis slug")
    filters: FilterSpec = Field(description="Configured issue filtering criteria")
    wip_limits_override: dict[str, Any] = Field(description="Active WIP limits overrides")
    is_shared: bool = Field(description="Whether the view is shared with workspace collaborators")
    visibility: str = Field(description="Visibility classification string")
    owner: ViewOwnerSummary = Field(description="View owner principal summary")
    access_manifest: AccessManifest = Field(
        description="Anti-enumeration access manifest metadata (S3.4)"
    )
    capabilities: list[str] = Field(
        description="Effective capabilities held by the calling principal on this view"
    )


class ViewList(BaseModel):
    """List of saved views for a project."""

    model_config = ConfigDict(extra="forbid")

    items: list[ViewResponse] = Field(description="List of saved view definitions")


class AdHocQueryRequest(BaseModel):
    """Payload for ad-hoc unsaved issue querying."""

    model_config = ConfigDict(extra="forbid")

    layout: ViewLayout = Field(
        default=ViewLayout.BOARD,
        description="Target layout mode: board, list, table, calendar, timeline",
    )
    group_by: GroupAxis = Field(default=GroupAxis.STATE, description="Primary grouping axis")
    sub_group_by: GroupAxis = Field(
        default=GroupAxis.NONE, description="Secondary sub-grouping axis"
    )
    filters: FilterSpec = Field(
        default_factory=FilterSpec, description="Ad-hoc issue filtering criteria"
    )
    sort_by: SortField = Field(default=SortField.BOARD_RANK, description="Sort order field")
    sort_dir: SortDir = Field(default=SortDir.ASC, description="Sort order direction: asc or desc")
    wip_limits_override: dict[str, Any] = Field(
        default_factory=dict, description="Ad-hoc WIP limits overrides"
    )
    limit: int = Field(default=50, ge=1, le=200, description="Maximum number of issues to return")
    cursor: str | None = Field(
        default=None, description="Opaque keyset cursor for fetching next page"
    )


class WipStatus(BaseModel):
    """WIP evaluation result for a group bucket."""

    model_config = ConfigDict(extra="forbid")

    soft: int | None = None
    hard: int | None = None
    exceeded: str | None = None


class SubGroupResult(BaseModel):
    """A sub-group cell along the secondary grouping axis."""

    model_config = ConfigDict(extra="forbid")

    sub_group_key: str
    key: str
    label: str
    count: int
    issue_ids: list[uuid.UUID]
    items: list[uuid.UUID]

    @model_validator(mode="before")
    @classmethod
    def sync_keys_and_items(cls, data: object) -> object:
        """Synchronize aliases."""
        if isinstance(data, dict):
            if "key" in data and "sub_group_key" not in data:
                data["sub_group_key"] = data["key"]
            elif "sub_group_key" in data and "key" not in data:
                data["key"] = data["sub_group_key"]
            if "issue_ids" in data and "items" not in data:
                data["items"] = data["issue_ids"]
            elif "items" in data and "issue_ids" not in data:
                data["issue_ids"] = data["items"]
        return data


class GroupResult(BaseModel):
    """A primary group bucket along the primary grouping axis."""

    model_config = ConfigDict(extra="forbid")

    group_key: str
    key: str
    label: str
    count: int
    wip: WipStatus | None = None
    sub_groups: list[SubGroupResult] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def sync_keys(cls, data: object) -> object:
        """Synchronize aliases."""
        if isinstance(data, dict):
            if "key" in data and "group_key" not in data:
                data["group_key"] = data["key"]
            elif "group_key" in data and "key" not in data:
                data["key"] = data["group_key"]
        return data


class TimelineLink(BaseModel):
    """An active dependency link between issues in a timeline layout."""

    model_config = ConfigDict(extra="forbid")

    source_key: str
    target_key: str
    link_type: str


class ViewQueryResponse(BaseModel):
    """Complete query response including items, 2D swimlanes, and timeline links."""

    model_config = ConfigDict(extra="forbid")

    items: list[IssueResponse]
    groups: list[GroupResult] = Field(default_factory=list)
    timeline_links: list[TimelineLink] = Field(default_factory=list)
    next_cursor: str | None = None
    total_matching: int
