# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comment request and response schemas (S7.2 8k, S5.1, S3.4)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for Pydantic v2 type evaluation
from datetime import datetime  # noqa: TC003  # Runtime import required for Pydantic v2 type evaluation

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AuthorSummary",
    "CommentCreate",
    "CommentList",
    "CommentPatch",
    "CommentResponse",
    "MentionSummary",
    "ReactionResponse",
    "ReactionSummary",
]


class ReactionSummary(BaseModel):
    """Aggregated reaction count and caller participation."""

    model_config = ConfigDict(extra="forbid")

    emoji: str = Field(description="NFC-normalized reaction emoji")
    count: int = Field(ge=0, description="Total count of reactions with this emoji")
    reacted_by_me: bool = Field(default=False, description="Whether caller reacted with this emoji")


ReactionResponse = ReactionSummary


class MentionSummary(BaseModel):
    """Mentioned user handle and capability status."""

    model_config = ConfigDict(extra="forbid")

    handle: str = Field(description="Normalized handle prefixed with or without @")
    principal_id: uuid.UUID = Field(description="User principal identifier")
    has_access: bool = Field(
        description="Whether the mentioned user holds VIEW capability on the issue"
    )


class AuthorSummary(BaseModel):
    """Comment author display metadata."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Author principal identifier")
    handle: str = Field(description="Author handle")
    display_name: str = Field(description="Author display name")


class CommentCreate(BaseModel):
    """Payload for POST /api/v1/issues/{issue_ref}/comments."""

    model_config = ConfigDict(extra="forbid")

    body_markdown: str = Field(description="Comment body markdown (normalized on ingestion)")
    parent_comment_id: uuid.UUID | None = Field(
        default=None, description="Optional parent comment ID for depth-1 replies"
    )
    acknowledge_mentions: list[uuid.UUID] = Field(
        default_factory=list,
        description="Explicit acknowledgement of unauthorized mentioned principals to bypass 409",
    )


class CommentPatch(BaseModel):
    """Payload for PATCH /api/v1/comments/{comment_id}."""

    model_config = ConfigDict(extra="forbid")

    body_markdown: str = Field(description="Updated comment body markdown")
    acknowledge_mentions: list[uuid.UUID] = Field(
        default_factory=list,
        description="Explicit acknowledgement of unauthorized mentioned principals to bypass 409",
    )


class CommentResponse(BaseModel):
    """Canonical representation of an issue comment or reply."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Comment identifier")
    issue_id: uuid.UUID = Field(description="Parent issue identifier")
    parent_comment_id: uuid.UUID | None = Field(
        default=None, description="Parent comment identifier if a reply"
    )
    author_id: uuid.UUID = Field(description="Comment author principal identifier")
    author: AuthorSummary = Field(description="Author display details")
    body_markdown: str | None = Field(
        default=None, description="Comment body markdown (None if deleted)"
    )
    body_sha256: str | None = Field(
        default=None, description="SHA-256 hex digest of normalized body (None if deleted)"
    )
    permalink: str = Field(description="Copyable deep-link URL fragment")
    created_at: datetime = Field(description="Creation timestamp")
    edited_at: datetime | None = Field(default=None, description="Last edited timestamp")
    deleted: bool = Field(default=False, description="Whether the comment has been soft-deleted")
    reactions: list[ReactionSummary] = Field(
        default_factory=list, description="Aggregated emoji reactions"
    )
    replies: list[CommentResponse] = Field(
        default_factory=list, description="Nested depth-1 replies (max 200 inlined)"
    )
    replies_next_cursor: str | None = Field(
        default=None, description="Cursor for additional replies if exceeding 200"
    )
    mentions: list[MentionSummary] = Field(
        default_factory=list, description="Resolved in-boundary mentions with access"
    )
    unnotified_mentions: list[MentionSummary] = Field(
        default_factory=list, description="Acknowledged mentions without access"
    )


CommentResponse.model_rebuild()


class CommentList(BaseModel):
    """Keyset-paginated list of top-level comments."""

    model_config = ConfigDict(extra="forbid")

    items: list[CommentResponse] = Field(description="Top-level comments with inlined replies")
    next_cursor: str | None = Field(
        default=None, description="Opaque cursor for next page of comments"
    )
