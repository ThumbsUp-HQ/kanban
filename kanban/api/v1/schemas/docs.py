# Copyright 2026 Kanban Platform Contributors
"""Pydantic schemas for Docs and Pages API endpoints (S8.1, S12.2)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Evaluated at runtime by Pydantic
from datetime import datetime  # noqa: TC003  # Evaluated at runtime by Pydantic
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "BreadcrumbItem",
    "DocCreate",
    "DocResponse",
    "DocSummaryResponse",
    "DocUpdate",
    "OutlineItem",
    "PageCreate",
    "PageMove",
    "PageResponse",
    "PageTreeNode",
    "PageUpdate",
    "PageVersionResponse",
]


class BreadcrumbItem(BaseModel):
    """Breadcrumb trail element representing an ancestor doc or page."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    title: str | None = None
    slug: str | None = None
    canonical_key: str | None = None
    restricted: bool = False
    label: str | None = None


class OutlineItem(BaseModel):
    """Heading outline entry extracted from Markdown body."""

    model_config = ConfigDict(extra="forbid")

    level: int
    text: str
    anchor: str
    start_line: int


class DocCreate(BaseModel):
    """Payload for creating a new top-level documentation entity."""

    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID | None = None
    title: str = Field(min_length=1)
    body_markdown: str = ""


class DocUpdate(BaseModel):
    """Payload for updating doc metadata and markdown content."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    body_markdown: str | None = None


class DocSummaryResponse(BaseModel):
    """Compact summary of a document for list views."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    canonical_key: str
    project_id: uuid.UUID | None
    title: str
    version_seq: int
    body_sha256: str


class DocResponse(BaseModel):
    """Full detail of a document including breadcrumbs, outline, and access metadata."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    canonical_key: str
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    body_markdown: str
    body_sha256: str
    hierarchy_path: str
    version_seq: int
    breadcrumbs: list[BreadcrumbItem]
    outline: list[OutlineItem]
    access_manifest: dict[str, Any]
    capabilities: list[str]


class PageCreate(BaseModel):
    """Payload for creating a hierarchical page within a document."""

    model_config = ConfigDict(extra="forbid")

    parent_page_id: uuid.UUID | None = None
    title: str = Field(min_length=1)
    body_markdown: str = ""
    after_page_id: uuid.UUID | None = None
    before_page_id: uuid.UUID | None = None


class PageUpdate(BaseModel):
    """Payload for updating an existing page."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    body_markdown: str | None = None


class PageMove(BaseModel):
    """Payload for moving a page within the hierarchy or re-ranking siblings."""

    model_config = ConfigDict(extra="forbid")

    parent_page_id: uuid.UUID | None = None
    after_page_id: uuid.UUID | None = None
    before_page_id: uuid.UUID | None = None


class PageTreeNode(BaseModel):
    """Hierarchical node in a document page tree with restricted ancestor masking."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    title: str | None = None
    slug: str | None = None
    sort_rank: str | None = None
    restricted: bool = False
    label: str | None = None
    children: list[PageTreeNode] = Field(default_factory=list)


class PageResponse(BaseModel):
    """Full detail of a hierarchical page."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    canonical_key: str
    doc_id: uuid.UUID
    parent_page_id: uuid.UUID | None
    workspace_id: uuid.UUID
    title: str
    body_markdown: str
    body_sha256: str
    hierarchy_path: str
    version_seq: int
    sort_rank: str
    breadcrumbs: list[BreadcrumbItem]
    outline: list[OutlineItem]
    access_manifest: dict[str, Any]
    capabilities: list[str]


class PageVersionResponse(BaseModel):
    """Historical immutable snapshot of a page version."""

    model_config = ConfigDict(extra="forbid")

    page_id: uuid.UUID
    version_seq: int
    title: str
    body_markdown: str
    body_sha256: str
    created_by_id: uuid.UUID | None
    created_at: datetime
