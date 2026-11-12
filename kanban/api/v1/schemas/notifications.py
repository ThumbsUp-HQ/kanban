# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Notification and subscription request and response schemas (S7.2 8l, KB-P3-06)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by Pydantic field resolution
from datetime import datetime  # noqa: TC003  # Required at runtime by Pydantic field resolution
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kanban.api.problems import ProblemException

MUTABLE_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "COMMENT_CREATED",
        "ISSUE_STATE_CHANGED",
        "ISSUE_FIELD_CHANGED",
        "ISSUE_DESCRIPTION_CHANGED",
        "ISSUE_LABELS_CHANGED",
        "ASSIGNEE_ADDED",
        "ASSIGNEE_REMOVED",
    }
)
MAX_MUTED_EVENT_TYPES: Final[int] = 7


class SubscriptionResponse(BaseModel):
    """Current user subscription state for an issue."""

    model_config = ConfigDict(extra="forbid")

    subscribed: bool = Field(description="Whether the user is currently subscribed")
    muted_event_types: list[str] = Field(
        default_factory=list, description="Event types muted by the user"
    )
    source: str | None = Field(
        default=None, description="Subscription source: manual, creator, assignee, mention, or null"
    )


class SubscriptionPut(BaseModel):
    """Payload for idempotent issue subscription."""

    model_config = ConfigDict(extra="forbid")

    muted_event_types: list[str] | None = Field(
        default=None, description="Optional initial list of muted event types"
    )

    @field_validator("muted_event_types")
    @classmethod
    def _validate_muted_types(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if len(v) > MAX_MUTED_EVENT_TYPES:
            raise ProblemException(
                code="TOO_MANY_MUTED_TYPES",
                status=422,
                title="Too Many Muted Event Types",
                detail=f"At most {MAX_MUTED_EVENT_TYPES} muted event types may be specified",
            )
        seen: set[str] = set()
        for t in v:
            if t not in MUTABLE_EVENT_TYPES:
                raise ProblemException(
                    code="EVENT_TYPE_NOT_MUTABLE",
                    status=422,
                    title="Event Type Not Mutable",
                    detail=f"Event type '{t}' cannot be muted",
                )
            if t in seen:
                raise ProblemException(
                    code="DUPLICATE_MUTED_TYPE",
                    status=422,
                    title="Duplicate Muted Event Type",
                    detail=f"Duplicate muted event type: '{t}'",
                )
            seen.add(t)
        return v


class SubscriptionPatch(BaseModel):
    """Payload for updating muted event types."""

    model_config = ConfigDict(extra="forbid")

    muted_event_types: list[str] = Field(
        description="Updated list of muted event types (max 7 entries, unique)"
    )

    @field_validator("muted_event_types")
    @classmethod
    def _validate_muted_types(cls, v: list[str]) -> list[str]:
        if len(v) > MAX_MUTED_EVENT_TYPES:
            raise ProblemException(
                code="TOO_MANY_MUTED_TYPES",
                status=422,
                title="Too Many Muted Event Types",
                detail=f"At most {MAX_MUTED_EVENT_TYPES} muted event types may be specified",
            )
        seen: set[str] = set()
        for t in v:
            if t not in MUTABLE_EVENT_TYPES:
                raise ProblemException(
                    code="EVENT_TYPE_NOT_MUTABLE",
                    status=422,
                    title="Event Type Not Mutable",
                    detail=f"Event type '{t}' cannot be muted",
                )
            if t in seen:
                raise ProblemException(
                    code="DUPLICATE_MUTED_TYPE",
                    status=422,
                    title="Duplicate Muted Event Type",
                    detail=f"Duplicate muted event type: '{t}'",
                )
            seen.add(t)
        return v


class NotificationIssueSummary(BaseModel):
    """Minimal issue metadata in a notification payload."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    key: str
    summary: str


class NotificationActorSummary(BaseModel):
    """Actor details or privacy-preserving redacted label."""

    model_config = ConfigDict(extra="forbid")

    handle: str | None = None
    display_name: str | None = None
    redacted: bool | None = None
    label: str | None = None


class NotificationItem(BaseModel):
    """Individual notification representation for the notifications tray."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    issue: NotificationIssueSummary
    event_type: str
    actor: NotificationActorSummary
    created_at: datetime
    read_at: datetime | None = None


class NotificationListResponse(BaseModel):
    """Keyset paginated notifications feed."""

    model_config = ConfigDict(extra="forbid")

    items: list[NotificationItem]
    next_cursor: str | None = None


class MarkAllReadResponse(BaseModel):
    """Response summary for bulk mark-all-read."""

    model_config = ConfigDict(extra="forbid")

    marked: int = Field(ge=0, description="Number of notifications marked as read")
