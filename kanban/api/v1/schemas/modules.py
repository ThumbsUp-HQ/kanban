# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Module request and response schemas (S7.2 8f, S11.4; KB-P3-10b)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for Pydantic field resolution
from datetime import date  # noqa: TC003  # Runtime import required for Pydantic field resolution
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kanban.api.problems import ProblemException
from kanban.content import normalize_to_markdown

MAX_MODULE_NAME_LENGTH: Final[int] = 120
MAX_DESCRIPTION_BYTES: Final[int] = 65536
MAX_MODULES_PER_ISSUE: Final[int] = 10

MODULE_STATUSES = Literal["backlog", "planned", "in_progress", "paused", "completed", "cancelled"]


class ModuleLeadSummary(BaseModel):
    """Lead principal summary for module representations."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    handle: str
    display_name: str
    type: str = "USER"


class ModuleCreate(BaseModel):
    """Request payload for creating a module within a project."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_MODULE_NAME_LENGTH)
    description_markdown: str = ""
    lead_principal_id: uuid.UUID | None = None
    status: MODULE_STATUSES = "planned"
    start_date: date | None = None
    target_date: date | None = None

    @field_validator("name", mode="after")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not (1 <= len(trimmed) <= MAX_MODULE_NAME_LENGTH):
            raise ProblemException(
                code="INVALID_MODULE_NAME",
                status=422,
                title="Invalid Module Name",
                detail=f"Module name must be between 1 and {MAX_MODULE_NAME_LENGTH} characters",
            )
        return trimmed

    @field_validator("description_markdown", mode="after")
    @classmethod
    def _validate_description(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
            raise ProblemException(
                code="DESCRIPTION_TOO_LARGE",
                status=422,
                title="Description Too Large",
                detail=f"Module description exceeds {MAX_DESCRIPTION_BYTES} bytes",
            )
        return normalize_to_markdown(value)

    @model_validator(mode="after")
    def _validate_dates(self) -> ModuleCreate:
        if self.start_date and self.target_date and self.target_date < self.start_date:
            raise ProblemException(
                code="INVALID_DATE_RANGE",
                status=422,
                title="Invalid Date Range",
                detail="Target date cannot be earlier than start date.",
            )
        return self


class ModulePatch(BaseModel):
    """Request payload for partially updating a module."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description_markdown: str | None = None
    lead_principal_id: uuid.UUID | None = None
    status: MODULE_STATUSES | None = None
    start_date: date | None = None
    target_date: date | None = None

    @field_validator("name", mode="after")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not (1 <= len(trimmed) <= MAX_MODULE_NAME_LENGTH):
            raise ProblemException(
                code="INVALID_MODULE_NAME",
                status=422,
                title="Invalid Module Name",
                detail=f"Module name must be between 1 and {MAX_MODULE_NAME_LENGTH} characters",
            )
        return trimmed

    @field_validator("description_markdown", mode="after")
    @classmethod
    def _validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
            raise ProblemException(
                code="DESCRIPTION_TOO_LARGE",
                status=422,
                title="Description Too Large",
                detail=f"Module description exceeds {MAX_DESCRIPTION_BYTES} bytes",
            )
        return normalize_to_markdown(value)


class ModuleResponse(BaseModel):
    """Canonical module representation returned by API."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    status: str
    lead: ModuleLeadSummary | None = None
    description_markdown: str = ""
    start_date: date | None = None
    target_date: date | None = None
    issue_count: int = 0
    completed_count: int = 0


class IssueModulesUpdate(BaseModel):
    """Request payload for setting issue module assignments."""

    model_config = ConfigDict(extra="forbid")

    module_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("module_ids", mode="after")
    @classmethod
    def _validate_modules(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        seen: set[uuid.UUID] = set()
        deduped: list[uuid.UUID] = []
        for mid in value:
            if mid not in seen:
                seen.add(mid)
                deduped.append(mid)
        if len(deduped) > MAX_MODULES_PER_ISSUE:
            raise ProblemException(
                code="MODULE_LIMIT",
                status=422,
                title="Module Limit Exceeded",
                detail=f"An issue cannot be assigned to more than {MAX_MODULES_PER_ISSUE} modules",
            )
        return deduped
