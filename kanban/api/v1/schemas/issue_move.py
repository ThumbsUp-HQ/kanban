"""Pydantic schemas for issue move endpoint and WIP limit feedback (KB-P3-12, S6.4)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by Pydantic

from pydantic import BaseModel, ConfigDict, Field


class IssueMoveRequest(BaseModel):
    """Request payload for moving or reordering an issue on the board."""

    model_config = ConfigDict(extra="forbid")

    target_state_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Target workflow state UUID. If omitted or equal to current state, "
            "performs intra-column reordering."
        ),
    )
    after_issue: str | None = Field(
        default=None,
        description="Issue key or UUID preceding target position in column.",
    )
    before_issue: str | None = Field(
        default=None,
        description="Issue key or UUID following target position in column.",
    )
    wip_override_reason: str | None = Field(
        default=None,
        description="Mandatory justification when overriding column hard WIP limit.",
    )
    override_wip: bool = Field(
        default=False,
        description="Flag indicating administrative intent to override hard WIP limit.",
    )


class WipWarning(BaseModel):
    """Soft WIP limit exceeded advisory warning."""

    model_config = ConfigDict(extra="forbid")

    soft_limit: int = Field(..., description="Configured soft WIP limit on target state")
    resulting_count: int = Field(..., description="Resulting active issue count in column")


class IssueMoveResponse(BaseModel):
    """Response payload for issue move endpoint."""

    model_config = ConfigDict(extra="forbid")

    issue_key: str = Field(..., description="Human-readable issue key (e.g. KAN-142)")
    state_id: uuid.UUID = Field(..., description="Resulting workflow state UUID")
    board_rank: str = Field(..., description="Assigned Base-62 board rank")
    rebalance_scheduled: bool = Field(
        ...,
        description="Whether a background column rebalance was enqueued (> 32 chars)",
    )
    wip_warning: WipWarning | None = Field(
        default=None,
        description="Non-null if the move caused the column to exceed its soft WIP limit",
    )
    hard_limit: int | None = Field(
        default=None,
        description="Configured hard WIP limit on target state if overridden",
    )
    resulting_count: int | None = Field(
        default=None,
        description="Resulting active issue count in column if WIP limit was evaluated",
    )
    gate_status: str | None = Field(
        default=None,
        description="Gate status ('pending') if the move triggered an async workflow gate hold",
    )
    execution_id: uuid.UUID | None = Field(
        default=None,
        description="Active workflow gate execution UUID if gate is pending",
    )
    hook_name: str | None = Field(
        default=None,
        description="Triggered workflow gate hook name if gate is pending",
    )
    from_state_id: uuid.UUID | None = Field(
        default=None,
        description="Source state UUID if gate is pending",
    )
    to_state_id: uuid.UUID | None = Field(
        default=None,
        description="Target state UUID if gate is pending",
    )
