"""Project request/response schemas (S7.2 8c, 8f, 8p; S12.2 ``projects`` DDL).

All request models forbid unknown keys. ``identifier`` is immutable after creation; it is
accepted by ``ProjectPatch`` only so the service can answer ``422 IDENTIFIER_IMMUTABLE``.
"""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by Pydantic field resolution
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from kanban.security.access_manifest import AccessManifest  # noqa: TC001  # Pydantic runtime type

IDENTIFIER_PATTERN = r"^[A-Z][A-Z0-9]{1,9}$"

ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
AutoArchiveDays = Annotated[int, Field(ge=1, le=365)]


class ProjectCreate(BaseModel):
    """Body of ``POST /api/v1/projects``."""

    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(
        pattern=IDENTIFIER_PATTERN,
        description="Unique uppercase project identifier slug (2 to 10 chars, e.g. KAN)",
    )
    name: ProjectName = Field(description="Human-readable project display name")
    description_markdown: str = Field(
        default="", description="Detailed project description in canonical Markdown"
    )
    modules_enabled: bool = Field(
        default=False, description="Whether sub-project modules feature is enabled"
    )
    auto_archive_days: AutoArchiveDays | None = Field(
        default=None, description="Number of days after completion before auto-archiving issues"
    )


class ProjectPatch(BaseModel):
    """Body of ``PATCH /api/v1/projects/{project_ref}`` (omitted keys are unchanged)."""

    model_config = ConfigDict(extra="forbid")

    identifier: str | None = Field(
        default=None,
        description="Immutable identifier (rejects with 422 if client attempts mutation)",
    )
    name: ProjectName | None = Field(
        default=None, description="Updated human-readable project display name"
    )
    description_markdown: str | None = Field(
        default=None, description="Updated project description in canonical Markdown"
    )
    modules_enabled: bool | None = Field(
        default=None, description="Updated modules feature enablement toggle"
    )
    auto_archive_days: AutoArchiveDays | None = Field(
        default=None, description="Updated auto-archive retention threshold in days"
    )


class ModuleDefaultsPut(BaseModel):
    """Body of ``PUT /api/v1/projects/{project_ref}/module-defaults``."""

    model_config = ConfigDict(extra="forbid")

    module_ids: list[uuid.UUID] = Field(
        max_length=20,
        description="List of module UUIDs automatically assigned to newly created issues",
    )

    @field_validator("module_ids")
    @classmethod
    def _unique(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        """Reject duplicate module identifiers."""
        if len(set(value)) != len(value):
            msg = "module_ids must be unique"
            raise ValueError(msg)
        return value


class ProjectResponse(BaseModel):
    """Canonical project representation returned by every project read and write."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(description="Unique project UUID identifier")
    identifier: str = Field(description="Project uppercase identifier slug (e.g. KAN)")
    name: str = Field(description="Project human-readable display name")
    description_markdown: str = Field(description="Project description in canonical Markdown")
    modules_enabled: bool = Field(description="Whether the modules feature is enabled")
    default_module_ids: list[uuid.UUID] = Field(
        description="Module UUIDs assigned by default to newly created issues"
    )
    auto_archive_days: int | None = Field(
        description="Configured auto-archive retention threshold in days, if enabled"
    )
    access_manifest: AccessManifest = Field(
        description="Anti-enumeration access manifest metadata (S3.4)"
    )
    capabilities: list[str] = Field(
        description="Effective capabilities held by the calling principal on this project"
    )


class ProjectList(BaseModel):
    """Keyset-paginated project listing."""

    model_config = ConfigDict(extra="forbid")

    items: list[ProjectResponse] = Field(description="List of project responses matching query")
    next_cursor: str | None = Field(
        default=None, description="Opaque keyset cursor for fetching the next page"
    )
