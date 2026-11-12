# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Hybrid assignee request/response schemas (S7.2 8b, S3.4; KB-P3-03)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by Pydantic field resolution
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kanban.api.problems import ProblemException

FREE_TEXT_HINT: Final[str] = (
    "External free-text label - grants zero access and sends zero notifications"
)


class AssigneeCreate(BaseModel):
    """Request payload for assigning a principal or free-text assignee."""

    model_config = ConfigDict(extra="forbid")

    principal: str | uuid.UUID | None = None
    free_text: str | None = None

    @model_validator(mode="after")
    def _validate_exclusive(self) -> AssigneeCreate:
        has_principal = self.principal is not None
        has_free_text = self.free_text is not None
        if (has_principal and has_free_text) or (not has_principal and not has_free_text):
            raise ProblemException(
                code="INVALID_PAYLOAD",
                status=422,
                title="Invalid Assignee Payload",
                detail="Must provide exactly one of 'principal' or 'free_text'",
            )
        return self


class PrincipalSummary(BaseModel):
    """Minimal non-leaking principal metadata for assignee responses."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    handle: str
    display_name: str
    type: str


class PrincipalAssigneeResponse(BaseModel):
    """Principal assignee response model."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    kind: Literal["principal"] = "principal"
    principal: PrincipalSummary


class FreeTextAssigneeResponse(BaseModel):
    """Free-text external label assignee response model."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    kind: Literal["free_text"] = "free_text"
    free_text: str
    notify: bool = False
    hint: str = FREE_TEXT_HINT


AssigneeResponse = Annotated[
    PrincipalAssigneeResponse | FreeTextAssigneeResponse,
    Field(discriminator="kind"),
]


class AssigneeSuggestionItem(BaseModel):
    """Autocomplete suggestion item for eligible project viewers."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    handle: str
    display_name: str
    type: str


class AssigneeSuggestionsResponse(BaseModel):
    """Autocomplete suggestions response listing eligible assignees."""

    model_config = ConfigDict(extra="forbid")

    items: list[AssigneeSuggestionItem]
