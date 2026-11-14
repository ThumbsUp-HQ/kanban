# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Pydantic request and response schemas for Stickies API (S8.1, S8.2, KB-P3-15)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for Pydantic type validation
from datetime import datetime  # noqa: TC003  # Runtime import required for Pydantic type validation
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "PromotedDocSummary",
    "StickyColorToken",
    "StickyCreate",
    "StickyList",
    "StickyPromoteRequest",
    "StickyResponse",
    "StickyUpdate",
]


class StickyColorToken(StrEnum):
    """6-color palette tokens permitted for stickies on project and workspace surfaces."""

    AMBER = "amber"
    MINT = "mint"
    SKY = "sky"
    LAVENDER = "lavender"
    CORAL = "coral"
    SLATE = "slate"


class StickyCreate(BaseModel):
    """Payload for creating a project sticky note."""

    model_config = ConfigDict(extra="forbid")

    body_markdown: str = Field(default="", description="Canonical Markdown body")
    color_token: StickyColorToken = Field(
        default=StickyColorToken.AMBER, description="6-color palette token"
    )
    sort_rank: str | None = Field(default=None, description="Optional custom sort rank")


class StickyUpdate(BaseModel):
    """Payload for updating a sticky note."""

    model_config = ConfigDict(extra="forbid")

    body_markdown: str | None = Field(default=None, description="Updated Markdown body")
    color_token: StickyColorToken | None = Field(
        default=None, description="Updated 6-color palette token"
    )
    sort_rank: str | None = Field(default=None, description="Updated sort rank")


class StickyPromoteRequest(BaseModel):
    """Payload for promoting a sticky note into a permanent document or page."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(
        default=None,
        description="Optional title for the promoted doc/page. If omitted, derived from content.",
    )
    parent_doc_id: uuid.UUID | None = Field(
        default=None,
        description="Optional parent document to promote into as a page. Must match project scope.",
    )
    parent_page_id: uuid.UUID | None = Field(
        default=None,
        description="Optional parent page under parent_doc_id.",
    )
    structured_body_markdown: str | None = Field(
        default=None,
        description="Optional structured or edited Markdown body confirming preview.",
    )
    expected_sticky_sha256: str | None = Field(
        default=None,
        description="Optional expected sticky body SHA-256 for TOCTOU conflict prevention.",
    )


class StickyPromotePreviewResponse(BaseModel):
    """Response payload for Sticky -> Doc promotion preview."""

    model_config = ConfigDict(extra="forbid")

    proposal: dict[str, Any] = Field(
        description="Structured proposal adhering to kb-sticky-doc-proposal/v1",
    )
    rendered_markdown: str = Field(
        description="Canonical GFM rendered representation of the proposal",
    )
    original_sha256: str = Field(
        description="SHA-256 digest of current sticky body at preview time",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="List of integrity or structural warnings (e.g. FENCED_BLOCK_MODIFIED)",
    )
    acl_preview: dict[str, Any] = Field(
        description="Access manifest and direct ACL entries count preview",
    )


class PromotedDocSummary(BaseModel):
    """Summary of the target doc for a promoted sticky note stub."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID | None = Field(default=None, description="Target document UUID")
    canonical_key: str | None = Field(default=None, description="Target document canonical key")
    title: str | None = Field(default=None, description="Target document title")
    restricted: bool = Field(
        default=False, description="True if target doc is hidden from the caller by RLS/ACLs"
    )


class StickyResponse(BaseModel):
    """Full representation of a sticky note or promoted stub."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Unique sticky identifier")
    workspace_id: uuid.UUID = Field(description="Owning workspace UUID")
    project_id: uuid.UUID | None = Field(default=None, description="Owning project UUID, if any")
    body_markdown: str = Field(description="Canonical UTF-8 Markdown content")
    body_sha256: str = Field(description="Hex SHA-256 digest of body_markdown")
    color_token: str = Field(description="Color palette token")
    sort_rank: str = Field(description="C-collation sort rank")
    promotion_recommended: bool = Field(
        description="Whether complexity heuristic recommends promotion to Doc"
    )
    promotion_snoozed_at_length: int | None = Field(
        default=None, description="Body length when promotion was snoozed, if snoozed"
    )
    promoted_to_doc_id: uuid.UUID | None = Field(
        default=None, description="Target doc UUID if promoted"
    )
    is_promoted_stub: bool = Field(
        description="True if promoted to doc (renders compact [Open Doc] [Unarchive Copy] stub)"
    )
    promoted_to_doc: PromotedDocSummary | None = Field(
        default=None, description="Target document metadata or restricted summary"
    )
    triggers: list[str] = Field(
        default_factory=list, description="Active complexity heuristic trigger names"
    )
    etag: str = Field(description="Quoted ETag header value matching body_sha256")
    access_manifest: dict[str, Any] = Field(
        description="Anti-enumeration access manifest metadata (S3.4)"
    )
    capabilities: list[str] = Field(description="Active capabilities caller holds on this sticky")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class StickyList(BaseModel):
    """Keyset-paginated list of stickies."""

    model_config = ConfigDict(extra="forbid")

    items: list[StickyResponse] = Field(description="List of sticky responses")
    next_cursor: str | None = Field(
        default=None, description="Opaque keyset cursor for fetching next page"
    )
