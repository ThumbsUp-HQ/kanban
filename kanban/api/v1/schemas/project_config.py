# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Project configuration request and response schemas (KB-P3-01b).

Covers workflow states, custom priorities, and labels with exclusive groups.
All models forbid unknown keys.
"""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for Pydantic v2 type evaluation
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"
PRIORITY_SLUG_PATTERN = r"^[a-z][a-z0-9_-]{0,31}$"
EXCLUSIVE_GROUP_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,31}$"
MAX_EMOJI_LENGTH = 8

StateGroupName = Literal["backlog", "unstarted", "started", "completed", "cancelled"]

StateName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
PriorityLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]
LabelName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
HexColor = Annotated[str, Field(pattern=HEX_COLOR_PATTERN)]
PrioritySlug = Annotated[str, Field(pattern=PRIORITY_SLUG_PATTERN)]
ExclusiveGroup = Annotated[str, Field(pattern=EXCLUSIVE_GROUP_PATTERN)]


class StateCreate(BaseModel):
    """Payload for POST /api/v1/projects/{project_ref}/states."""

    model_config = ConfigDict(extra="forbid")

    name: StateName
    group: StateGroupName
    color_hex: HexColor
    sort_order: int = 0
    is_default: bool = False
    wip_soft_limit: int | None = Field(default=None, ge=1, le=999)
    wip_hard_limit: int | None = Field(default=None, ge=1, le=999)

    @model_validator(mode="after")
    def validate_wip_limits(self) -> StateCreate:
        """Enforce wip_soft_limit <= wip_hard_limit when both are present."""
        if (
            self.wip_soft_limit is not None
            and self.wip_hard_limit is not None
            and self.wip_soft_limit > self.wip_hard_limit
        ):
            msg = "wip_soft_limit must be less than or equal to wip_hard_limit"
            raise ValueError(msg)
        return self


class StatePatch(BaseModel):
    """Payload for PATCH /api/v1/projects/{project_ref}/states/{state_id}."""

    model_config = ConfigDict(extra="forbid")

    name: StateName | None = None
    group: StateGroupName | None = None
    color_hex: HexColor | None = None
    sort_order: int | None = None
    is_default: bool | None = None
    wip_soft_limit: int | None = Field(default=None, ge=1, le=999)
    wip_hard_limit: int | None = Field(default=None, ge=1, le=999)

    @model_validator(mode="after")
    def validate_wip_limits(self) -> StatePatch:
        """Enforce wip_soft_limit <= wip_hard_limit when both are present."""
        if (
            self.wip_soft_limit is not None
            and self.wip_hard_limit is not None
            and self.wip_soft_limit > self.wip_hard_limit
        ):
            msg = "wip_soft_limit must be less than or equal to wip_hard_limit"
            raise ValueError(msg)
        return self


class StateResponse(BaseModel):
    """Response model for a workflow state."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    group: StateGroupName
    color_hex: str
    sort_order: int
    is_default: bool
    wip_soft_limit: int | None = None
    wip_hard_limit: int | None = None
    issue_count: int = 0


class PriorityCreate(BaseModel):
    """Payload for POST /api/v1/projects/{project_ref}/priorities."""

    model_config = ConfigDict(extra="forbid")

    slug: PrioritySlug
    label: PriorityLabel
    emoji: str | None = None
    color_hex: HexColor
    sort_order: int = 0
    is_default: bool = False

    @model_validator(mode="after")
    def validate_emoji(self) -> PriorityCreate:
        """Enforce emoji length 1..8 code points if provided."""
        if self.emoji is not None and not (1 <= len(self.emoji) <= MAX_EMOJI_LENGTH):
            msg = "emoji must be between 1 and 8 code points"
            raise ValueError(msg)
        return self


class PriorityPatch(BaseModel):
    """Payload for PATCH /api/v1/projects/{project_ref}/priorities/{priority_id}."""

    model_config = ConfigDict(extra="forbid")

    slug: PrioritySlug | None = None
    label: PriorityLabel | None = None
    emoji: str | None = None
    color_hex: HexColor | None = None
    sort_order: int | None = None
    is_default: bool | None = None

    @model_validator(mode="after")
    def validate_emoji(self) -> PriorityPatch:
        """Enforce emoji length 1..8 code points if provided."""
        if self.emoji is not None and not (1 <= len(self.emoji) <= MAX_EMOJI_LENGTH):
            msg = "emoji must be between 1 and 8 code points"
            raise ValueError(msg)
        return self


class PriorityResponse(BaseModel):
    """Response model for a project priority."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    project_id: uuid.UUID
    slug: str
    label: str
    emoji: str | None = None
    color_hex: str
    sort_order: int
    is_default: bool


class LabelCreate(BaseModel):
    """Payload for POST /api/v1/projects/{project_ref}/labels."""

    model_config = ConfigDict(extra="forbid")

    name: LabelName
    color_hex: HexColor
    exclusive_group: ExclusiveGroup | None = None


class LabelPatch(BaseModel):
    """Payload for PATCH /api/v1/projects/{project_ref}/labels/{label_id}."""

    model_config = ConfigDict(extra="forbid")

    name: LabelName | None = None
    color_hex: HexColor | None = None
    exclusive_group: ExclusiveGroup | None = None


class LabelResponse(BaseModel):
    """Response model for a project label."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    color_hex: str
    exclusive_group: str | None = None


class WorkflowHookSummary(BaseModel):
    """Summary of a workflow transition hook referencing a state."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    hook_kind: str
    is_enabled: bool
    from_state_id: uuid.UUID | None = None
    to_state_id: uuid.UUID


class SavedViewSummary(BaseModel):
    """Summary of a saved view referencing a state or label."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str


class StateAuditImpactResponse(BaseModel):
    """Reverse-audit impact response for deleting a workflow state."""

    model_config = ConfigDict(extra="forbid")

    state_id: uuid.UUID
    project_id: uuid.UUID
    issues_count: int
    sample_issue_keys: list[str] = Field(default_factory=list)
    workflow_hooks: list[WorkflowHookSummary] = Field(default_factory=list)
    pending_executions_count: int = 0
    historical_executions_count: int = 0
    saved_views: list[SavedViewSummary] = Field(default_factory=list)
    is_default: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    valid_replacement_states: list[StateResponse] = Field(default_factory=list)


class LabelAuditImpactResponse(BaseModel):
    """Reverse-audit impact response for deleting a project label."""

    model_config = ConfigDict(extra="forbid")

    label_id: uuid.UUID
    project_id: uuid.UUID
    issues_count: int
    sample_issue_keys: list[str] = Field(default_factory=list)
    saved_views: list[SavedViewSummary] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    valid_replacement_labels: list[LabelResponse] = Field(default_factory=list)
