# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Pydantic schemas for Report Templates and Multi-Format Export Engine (KB-JINJA-REPORTS)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReportTemplateResponse(BaseModel):
    """Schema representing a stored or built-in report template."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None = None
    slug: str
    name: str
    description: str | None = None
    is_builtin: bool
    template_markdown: str
    parameters_schema_json: list[dict[str, Any]] | dict[str, Any] = Field(default_factory=list)
    csv_columns_json: list[dict[str, Any]] = Field(default_factory=list)
    allowed_formats: list[str] = Field(
        default_factory=lambda: ["PDF", "XLSX", "CSV", "DOCX", "ODT", "HTML", "MD"]
    )
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class ReportTemplateListResponse(BaseModel):
    """Schema representing a list of report templates."""

    model_config = ConfigDict(extra="forbid")

    items: list[ReportTemplateResponse]
    total: int


class ReportTemplateCreateRequest(BaseModel):
    """Schema for creating a custom report template."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9-_]+$")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    project_id: uuid.UUID | None = None
    template_markdown: str = Field(min_length=1, max_length=131072)
    parameters_schema_json: list[dict[str, Any]] | dict[str, Any] | None = None
    csv_columns_json: list[dict[str, Any]] | None = None
    allowed_formats: list[str] | None = None


class ReportTemplateUpdateRequest(BaseModel):
    """Schema for updating a custom report template."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    template_markdown: str | None = Field(default=None, min_length=1, max_length=131072)
    parameters_schema_json: list[dict[str, Any]] | dict[str, Any] | None = None
    csv_columns_json: list[dict[str, Any]] | None = None
    allowed_formats: list[str] | None = None


class ReportPreviewRequest(BaseModel):
    """Schema for rendering a fast live preview of a report template."""

    model_config = ConfigDict(extra="forbid")

    template_ref: str | None = None
    template_markdown: str | None = Field(default=None, max_length=131072)
    project_ref: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    issue_ids: list[uuid.UUID] | None = None
    format: Literal["HTML", "MD"] = "HTML"


class ReportPreviewResponse(BaseModel):
    """Schema for report preview output."""

    model_config = ConfigDict(extra="forbid")

    rendered_content: str
    format: str
    issue_count: int


class ReportGenerateRequest(BaseModel):
    """Schema for generating a full multi-format report export."""

    model_config = ConfigDict(extra="forbid")

    template_ref: str = Field(description="Slug or UUID of template")
    format: Literal["PDF", "XLSX", "CSV", "DOCX", "ODT", "HTML", "MD"] = "PDF"
    parameters: dict[str, Any] = Field(default_factory=dict)
    issue_ids: list[uuid.UUID] | None = None
    filter_query: str | None = None
    zip_password: str | None = Field(default=None, min_length=4, max_length=128)
