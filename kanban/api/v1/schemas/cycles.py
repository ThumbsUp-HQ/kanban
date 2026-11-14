# Copyright 2026 Kanban Platform Contributors
# Licensed under Apache-2.0
"""Pydantic v2 schemas for cycle management and burndown (S7.2 8g, S11.4)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by Pydantic field resolution
from datetime import date  # noqa: TC003  # Required at runtime by Pydantic
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_CYCLE_NAME_LEN: Final[int] = 120
CycleStatus = Literal["upcoming", "active", "completed"]


class CycleCreate(BaseModel):
    """Payload to create a new cycle in upcoming status."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=MAX_CYCLE_NAME_LEN)
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Strip whitespace and enforce length constraints."""
        clean = v.strip()
        if not (1 <= len(clean) <= MAX_CYCLE_NAME_LEN):
            msg = f"Cycle name must be between 1 and {MAX_CYCLE_NAME_LEN} characters"
            raise ValueError(msg)
        return clean


class CyclePatch(BaseModel):
    """Payload to update an existing upcoming or active cycle."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=MAX_CYCLE_NAME_LEN)
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        """Strip whitespace and enforce length constraints if present."""
        if v is None:
            return None
        clean = v.strip()
        if not (1 <= len(clean) <= MAX_CYCLE_NAME_LEN):
            msg = f"Cycle name must be between 1 and {MAX_CYCLE_NAME_LEN} characters"
            raise ValueError(msg)
        return clean


class CycleComplete(BaseModel):
    """Payload to complete an active cycle with optional issue rollover."""

    model_config = ConfigDict(extra="forbid")

    rollover_to_cycle_id: uuid.UUID | None = None


class CycleRolloverRequest(BaseModel):
    """Payload to rollover unfinished issues to a target cycle without completing."""

    model_config = ConfigDict(extra="forbid")

    target_cycle_id: uuid.UUID


class CycleRolloverResponse(BaseModel):
    """Response returned upon successful issue rollover."""

    model_config = ConfigDict(extra="forbid")

    status: str = "rolled_over"
    from_cycle: str
    to_cycle: str
    moved: int


class CycleResponse(BaseModel):
    """Public representation of a cycle with real-time aggregate issue counts."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    status: CycleStatus
    start_date: date | None = None
    end_date: date | None = None
    issue_count: int = 0
    completed_count: int = 0


class CycleCompleteResponse(BaseModel):
    """Response returned upon successful cycle completion and issue rollover."""

    model_config = ConfigDict(extra="forbid")

    cycle: CycleResponse
    rolled_over: int
    rollover_to_cycle_id: uuid.UUID | None = None


class BurndownPoint(BaseModel):
    """Daily scope and remaining count for cycle burndown metrics."""

    model_config = ConfigDict(extra="forbid")

    date: str
    scope: int
    remaining: int


class BurndownIdealPoint(BaseModel):
    """Linear target progression for cycle completion."""

    model_config = ConfigDict(extra="forbid")

    date: str
    remaining: float | int


class BurndownResponse(BaseModel):
    """Burndown metrics series and ideal line for a cycle."""

    model_config = ConfigDict(extra="forbid")

    cycle_id: uuid.UUID
    series: list[BurndownPoint]
    ideal: list[BurndownIdealPoint]
