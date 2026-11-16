# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Activity feed request and response schemas (S7.1, S7.2 8j, S12.2, S3.4; KB-P3-13)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for Pydantic v2 type evaluation
from datetime import datetime  # noqa: TC003  # Runtime import required for Pydantic v2 type evaluation
from typing import TYPE_CHECKING, Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    SerializerFunctionWrapHandler,
    model_serializer,
)

if TYPE_CHECKING:
    from pydantic.json_schema import JsonSchemaValue
    from pydantic_core import core_schema

from kanban.api.v1.schemas.comments import ReactionSummary  # noqa: TC001
from kanban.services.activity import ActivityCategory  # noqa: TC001

__all__ = [
    "ActiveCommentSummary",
    "ActivityCounts",
    "ActivityFeedResponse",
    "ActivityItemResponse",
    "ActivityOrder",
    "ActivityTab",
    "NormalActorSummary",
    "RedactedActorSummary",
    "SoftDeletedCommentSummary",
]

type ActivityTab = Literal["all", "comments", "history", "gates"]
type ActivityOrder = Literal["desc", "asc"]


class ActivityCounts(BaseModel):
    """Aggregate counts across all 4 activity tabs for drawer badges."""

    model_config = ConfigDict(extra="forbid")

    all: int = Field(ge=0, description="Total matching activity items across all tabs")
    comments: int = Field(ge=0, description="Total comment-related activity items")
    history: int = Field(ge=0, description="Total history and lifecycle activity items")
    gates: int = Field(ge=0, description="Total agent and workflow gate items")


class NormalActorSummary(BaseModel):
    """Visible in-boundary principal metadata for activity actors."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Principal UUID")
    type: str = Field(description="Principal type: USER, AGENT, or SERVICE_PRINCIPAL")
    handle: str | None = Field(default=None, description="User handle with @ prefix")
    slug: str | None = Field(default=None, description="Agent slug identifier")
    display_name: str = Field(description="Full display name")


class RedactedActorSummary(BaseModel):
    """Anonymized placeholder for out-of-boundary principals."""

    model_config = ConfigDict(extra="forbid")

    redacted: Literal[True] = Field(default=True, description="Always true for redacted principals")
    label: str = Field(
        default="1 External Collaborator",
        description="Redacted principal summary label",
    )


class ActiveCommentSummary(BaseModel):
    """Hydrated metadata for an active comment."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Comment UUID")
    body_markdown: str = Field(description="Canonical comment markdown body")
    permalink: str = Field(description="Canonical URL permalink fragment to the comment")
    edited_at: datetime | None = Field(default=None, description="Timestamp of last edit")
    reactions: list[ReactionSummary] = Field(
        default_factory=list, description="Aggregated emoji reactions"
    )


class SoftDeletedCommentSummary(BaseModel):
    """Tombstone metadata for a soft-deleted comment preventing body leakage."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Comment UUID")
    deleted: Literal[True] = Field(default=True, description="Always true for deleted comments")


class ActivityItemResponse(BaseModel):
    """A single activity feed item with actor and comment hydration."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Activity record UUID")
    category: ActivityCategory = Field(description="Display category tab grouping")
    event_type: str = Field(description="Exact activity event type token")
    actor: NormalActorSummary | RedactedActorSummary | None = Field(
        default=None, description="Initiating principal or redacted collaborator"
    )
    created_at: datetime = Field(description="Timestamp when event was recorded")
    payload: dict[str, Any] = Field(default_factory=dict, description="Structured event payload")
    comment: ActiveCommentSummary | SoftDeletedCommentSummary | None = Field(
        default=None, description="Hydrated comment object for comment events"
    )
    prev_hash: str | None = Field(
        default=None, description="Hex-encoded 32-byte cryptographic predecessor hash"
    )
    row_hash: str | None = Field(
        default=None, description="Hex-encoded 32-byte cryptographic row hash"
    )

    @model_serializer(mode="wrap")
    def _strip_optional_omissions(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        """Omit null hash fields and comment field when not present."""
        data: dict[str, object] = handler(self)
        if data.get("prev_hash") is None:
            data.pop("prev_hash", None)
        if data.get("row_hash") is None:
            data.pop("row_hash", None)
        if data.get("comment") is None:
            data.pop("comment", None)
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


class ActivityFeedResponse(BaseModel):
    """Paginated activity feed response with counts and keyset cursor."""

    model_config = ConfigDict(extra="forbid")

    tab: str = Field(description="Active filter tab: all, comments, history, or gates")
    counts: ActivityCounts = Field(description="Badge counts for all 4 tabs")
    items: list[ActivityItemResponse] = Field(description="Ordered list of activity items")
    next_cursor: str | None = Field(
        default=None, description="Opaque HMAC-signed cursor for keyset pagination"
    )
