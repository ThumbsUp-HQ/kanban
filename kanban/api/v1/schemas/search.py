# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Pydantic schemas for full-text and trigram lexical search (S11.2, S11.3, S12.2, KB-P3-17)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by Pydantic field resolution
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from kanban.api.v1.schemas.views import FilterSpec  # noqa: TC001  # Required at runtime by Pydantic

SearchKind = Literal["issue", "doc", "page", "sticky"]
SearchMode = Literal["lexical", "hybrid"]


class SearchItem(BaseModel):
    """Unified search result item representing an issue, doc, page, or sticky."""

    model_config = ConfigDict(extra="forbid")

    kind: SearchKind
    id: uuid.UUID
    key: str | None = None
    title: str
    project_identifier: str | None = None
    anchor: str | None = None
    snippet: str
    match_spans: list[tuple[int, int]] = Field(default_factory=list)
    score: float
    summary: str | None = None


class SearchResponse(BaseModel):
    """Response payload for multi-entity search endpoint."""

    model_config = ConfigDict(extra="forbid")

    total: int
    executed_mode: Literal["lexical"] = "lexical"
    items: list[SearchItem]
    next_cursor: str | None = None


class IssueSearchItem(BaseModel):
    """Single issue match returned by issues search endpoint."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["issue"] = "issue"
    id: uuid.UUID
    key: str
    title: str
    summary: str
    project_identifier: str
    workspace: str | None = None
    anchor: str | None = None
    snippet: str
    match_spans: list[tuple[int, int]] = Field(default_factory=list)
    score: float
    state: str | None = None
    priority: str | None = None
    assignees: list[str] = Field(default_factory=list)
    description_markdown: str | None = None


class IssueSearchRequest(BaseModel):
    """Request payload for structured issue search with FilterSpec."""

    model_config = ConfigDict(extra="forbid")

    query: str = ""
    project: str | None = None
    workspace: str | None = None
    filters: FilterSpec | None = None
    mode: SearchMode = "lexical"
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = None


class IssueSearchResponse(BaseModel):
    """Response payload for structured issue search."""

    model_config = ConfigDict(extra="forbid")

    total: int
    executed_mode: Literal["lexical"] = "lexical"
    items: list[IssueSearchItem]
    next_cursor: str | None = None


class KnowledgeSearchItem(BaseModel):
    """Single doc, page, or sticky match returned by knowledge search endpoint."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["doc", "page", "sticky"]
    id: uuid.UUID
    key: str | None = None
    title: str
    project_identifier: str | None = None
    anchor: str | None = None
    snippet: str
    match_spans: list[tuple[int, int]] = Field(default_factory=list)
    score: float


def _default_knowledge_kinds() -> list[Literal["doc", "page", "sticky"]]:
    return ["doc", "page", "sticky"]


class KnowledgeSearchRequest(BaseModel):
    """Request payload for knowledge search across docs, pages, and stickies."""

    model_config = ConfigDict(extra="forbid")

    query: str
    kinds: list[Literal["doc", "page", "sticky"]] = Field(default_factory=_default_knowledge_kinds)
    project: str | None = None
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = None


class KnowledgeSearchResponse(BaseModel):
    """Response payload for knowledge search."""

    model_config = ConfigDict(extra="forbid")

    total: int
    executed_mode: Literal["lexical"] = "lexical"
    items: list[KnowledgeSearchItem]
    next_cursor: str | None = None
