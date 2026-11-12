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

    identifier: str = Field(pattern=IDENTIFIER_PATTERN)
    name: ProjectName
    description_markdown: str = ""
    modules_enabled: bool = False
    auto_archive_days: AutoArchiveDays | None = None


class ProjectPatch(BaseModel):
    """Body of ``PATCH /api/v1/projects/{project_ref}`` (omitted keys are unchanged)."""

    model_config = ConfigDict(extra="forbid")

    identifier: str | None = None
    name: ProjectName | None = None
    description_markdown: str | None = None
    modules_enabled: bool | None = None
    auto_archive_days: AutoArchiveDays | None = None


class ModuleDefaultsPut(BaseModel):
    """Body of ``PUT /api/v1/projects/{project_ref}/module-defaults``."""

    model_config = ConfigDict(extra="forbid")

    module_ids: list[uuid.UUID] = Field(max_length=20)

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

    id: uuid.UUID
    identifier: str
    name: str
    description_markdown: str
    modules_enabled: bool
    default_module_ids: list[uuid.UUID]
    auto_archive_days: int | None
    access_manifest: AccessManifest
    capabilities: list[str]


class ProjectList(BaseModel):
    """Keyset-paginated project listing."""

    model_config = ConfigDict(extra="forbid")

    items: list[ProjectResponse]
    next_cursor: str | None = None
