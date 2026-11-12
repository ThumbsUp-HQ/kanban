"""Pydantic schemas for issue provenance and creator override endpoint (KB-P3-04)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class CreatorPrincipalSummary(BaseModel):
    """Summary of a visible user principal in provenance."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="UUID of the user principal")
    handle: str = Field(..., description="Display handle or username without leading @")


class RedactedCreatorSummary(BaseModel):
    """Redacted placeholder for principals outside the caller's visibility boundary."""

    model_config = ConfigDict(extra="forbid")

    redacted: Literal[True] = Field(
        default=True,
        description="Always true for redacted placeholders",
    )
    label: str = Field(
        default="1 External Collaborator",
        description="Redacted label per Section 3.4",
    )


type CreatorSummary = Annotated[
    CreatorPrincipalSummary | RedactedCreatorSummary,
    Field(discriminator=None),
]


class IssueProvenance(BaseModel):
    """Provenance tracking for issue creator and administrative overrides."""

    model_config = ConfigDict(extra="forbid")

    created_by: CreatorSummary = Field(..., description="Current effective creator summary")
    original_created_by: CreatorSummary = Field(
        ..., description="Original creator at issue creation time"
    )
    overridden: bool = Field(..., description="Whether created_by has been overridden by an admin")
    creator_modified_by: CreatorSummary | None = Field(
        default=None, description="Admin user who performed the override"
    )
    creator_modified_at: str | None = Field(
        default=None, description="ISO-8601 timestamp when override occurred"
    )
    reason: str | None = Field(
        default=None, description="Mandatory admin reason provided for the override"
    )


class IssueOverrideCreatorRequest(BaseModel):
    """Request payload for administrative creator override endpoint."""

    model_config = ConfigDict(extra="forbid")

    created_by: str = Field(..., description="UUID or @handle of the new creator")
    reason: str = Field(..., description="Mandatory administrative justification for override")
