# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Schemas for issue tree creation and responses (KB-P4-05)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by Pydantic
from datetime import date  # noqa: TC003  # Required at runtime by Pydantic

from pydantic import BaseModel, ConfigDict, Field


class IssueTreeNode(BaseModel):
    """Recursive issue node schema for hierarchical tree creation."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    description_markdown: str = ""
    state: str | uuid.UUID | None = None
    priority: str | uuid.UUID | None = None
    assignees: list[str] = Field(default_factory=list, max_length=20)
    labels: list[str | uuid.UUID] = Field(default_factory=list, max_length=20)
    cycle: str | uuid.UUID | None = None
    modules: list[str | uuid.UUID] | None = None
    parent: str | uuid.UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    children: list[IssueTreeNode] = Field(default_factory=list, max_length=49)


class IssueTreeRootSummary(BaseModel):
    """Summary projection of the root issue in a created tree."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    key: str
    summary: str
    state: str
    priority: str
    parent: str | None = None


class IssueTreeChildSummary(BaseModel):
    """Summary projection of a child issue in a created tree."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    key: str
    summary: str
    parent: str


class IssueTreeResponse(BaseModel):
    """Response payload returned by POST /api/v1/projects/{project_ref}/issue-trees."""

    model_config = ConfigDict(extra="forbid")

    created: int
    root: IssueTreeRootSummary
    children: list[IssueTreeChildSummary]
