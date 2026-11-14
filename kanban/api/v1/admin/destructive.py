# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for two-stage destructive lifecycle operations (KB-P4-12, S11.4)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.services.destructive_lifecycle import (
    execute_delete,
    request_delete,
    restore_object,
)

__all__ = [
    "DestructiveExecuteIn",
    "DestructiveExecuteOut",
    "DestructiveRequestIn",
    "DestructiveRequestOut",
    "DestructiveRestoreIn",
    "DestructiveRestoreOut",
    "router",
]

router = APIRouter(tags=["admin-destructive"], dependencies=[Depends(require_admin_aal2)])

Caller = Annotated[PrincipalContext, Depends(require_admin_aal2)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]

TargetKindLiteral = Literal["issue", "project", "doc", "page", "sticky", "cycle", "module", "view"]
ModeLiteral = Literal["trash", "permanent_purge"]


class DestructiveRequestIn(BaseModel):
    """Payload for Stage 1 delete request."""

    model_config = ConfigDict(extra="forbid")

    target_kind: TargetKindLiteral
    target: str = Field(min_length=1, max_length=200)
    mode: ModeLiteral = "trash"


class DestructiveRequestOut(BaseModel):
    """Response returned by Stage 1 delete request."""

    model_config = ConfigDict(extra="ignore")

    stage: str
    target: str
    target_kind: str
    target_id: str
    mode: str
    blast_summary: str
    blast_hash: str
    confirm_phrase: str
    confirmation_token: str
    expires_in_sec: int


class DestructiveExecuteIn(BaseModel):
    """Payload for Stage 2 delete execution."""

    model_config = ConfigDict(extra="forbid")

    target_kind: TargetKindLiteral
    target: str = Field(min_length=1, max_length=200)
    mode: ModeLiteral
    confirmation_token: str = Field(min_length=1)
    confirm_phrase: str = Field(min_length=1)
    reason: str = Field(min_length=10, max_length=500)


class DestructiveExecuteOut(BaseModel):
    """Response returned by Stage 2 delete execution."""

    model_config = ConfigDict(extra="ignore")

    status: str
    target: str
    target_kind: str
    target_id: str
    mode: str
    reason: str
    blast_hash: str


class DestructiveRestoreIn(BaseModel):
    """Payload for restore operation."""

    model_config = ConfigDict(extra="forbid")

    target_kind: TargetKindLiteral
    target: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=10, max_length=500)


class DestructiveRestoreOut(BaseModel):
    """Response returned by restore operation."""

    model_config = ConfigDict(extra="ignore")

    status: str
    target: str
    target_kind: str
    target_id: str
    reason: str


@router.post(
    "/admin/destructive:request",
    response_model=DestructiveRequestOut,
    status_code=status.HTTP_200_OK,
    summary="Stage 1: Request destructive delete and mint confirmation token",
)
async def api_destructive_request(
    payload: DestructiveRequestIn,
    caller: Caller,
    session: Session,
) -> DestructiveRequestOut:
    """Compute blast radius and issue a single-use 5m confirmation token."""
    res = await request_delete(
        session=session,
        caller=caller,
        target_kind=payload.target_kind,
        target_ref=payload.target,
        mode=payload.mode,
    )
    return DestructiveRequestOut(
        stage=res.stage,
        target=res.target,
        target_kind=res.target_kind,
        target_id=res.target_id,
        mode=res.mode,
        blast_summary=res.blast_summary,
        blast_hash=res.blast_hash,
        confirm_phrase=res.confirm_phrase,
        confirmation_token=res.confirmation_token,
        expires_in_sec=res.expires_in_sec,
    )


@router.post(
    "/admin/destructive:execute",
    response_model=DestructiveExecuteOut,
    status_code=status.HTTP_200_OK,
    summary="Stage 2: Execute destructive delete with confirmation token",
)
async def api_destructive_execute(
    payload: DestructiveExecuteIn,
    caller: Caller,
    session: Session,
) -> DestructiveExecuteOut:
    """Verify confirmation token and blast hash, then execute soft-trash or permanent purge."""
    res = await execute_delete(
        session=session,
        caller=caller,
        target_kind=payload.target_kind,
        target_ref=payload.target,
        mode=payload.mode,
        confirmation_token=payload.confirmation_token,
        confirm_phrase=payload.confirm_phrase,
        reason=payload.reason,
    )
    return DestructiveExecuteOut(
        status=res.status,
        target=res.target,
        target_kind=res.target_kind,
        target_id=res.target_id,
        mode=res.mode,
        reason=res.reason,
        blast_hash=res.blast_hash,
    )


@router.post(
    "/admin/destructive:restore",
    response_model=DestructiveRestoreOut,
    status_code=status.HTTP_200_OK,
    summary="Restore a soft-deleted object from trash",
)
async def api_destructive_restore(
    payload: DestructiveRestoreIn,
    caller: Caller,
    session: Session,
) -> DestructiveRestoreOut:
    """Restore a soft-deleted entity from trash back to active state."""
    res = await restore_object(
        session=session,
        caller=caller,
        target_kind=payload.target_kind,
        target_ref=payload.target,
        reason=payload.reason,
    )
    return DestructiveRestoreOut(
        status=res.status,
        target=res.target,
        target_kind=res.target_kind,
        target_id=res.target_id,
        reason=res.reason,
    )
