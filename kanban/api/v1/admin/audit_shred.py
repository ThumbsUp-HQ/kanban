# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API endpoints for two-stage audit ledger crypto-shredding under AAL2 (KB-SEC-SHRED-01)."""

from __future__ import annotations

import uuid  # noqa: TC003
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.services.crypto_shred import (
    execute_crypto_shred,
    request_crypto_shred,
)

__all__ = [
    "AuditShredExecuteIn",
    "AuditShredExecuteOut",
    "AuditShredRequestIn",
    "AuditShredRequestOut",
    "api_admin_audit_ledger_execute_shred",
    "api_admin_audit_ledger_request_shred",
    "router",
]

router = APIRouter(tags=["admin-audit-shred"], dependencies=[Depends(require_admin_aal2)])

Caller = Annotated[PrincipalContext, Depends(require_admin_aal2)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


class AuditShredRequestIn(BaseModel):
    """Payload for Stage 1 crypto-shred request."""

    model_config = ConfigDict(extra="forbid")

    activity_id: uuid.UUID | None = None
    object_id: uuid.UUID | None = None
    subject_principal_id: uuid.UUID | None = None
    reason: str = Field(min_length=5, max_length=500)


class AuditShredRequestOut(BaseModel):
    """Response returned by Stage 1 crypto-shred request."""

    model_config = ConfigDict(extra="ignore")

    stage: str
    target_type: str
    target_id: str
    records_matched: int
    records_to_shred: int
    blast_hash: str
    confirmation_token: str
    confirm_phrase: str
    expires_in_sec: int


class AuditShredExecuteIn(BaseModel):
    """Payload for Stage 2 crypto-shred execution."""

    model_config = ConfigDict(extra="forbid")

    confirmation_token: str = Field(min_length=1)
    confirm_phrase: str = Field(min_length=1)
    reason: str = Field(min_length=5, max_length=500)
    activity_id: uuid.UUID | None = None
    object_id: uuid.UUID | None = None
    subject_principal_id: uuid.UUID | None = None


class AuditShredExecuteOut(BaseModel):
    """Response returned by Stage 2 crypto-shred execution."""

    model_config = ConfigDict(extra="ignore")

    status: str
    target_type: str
    target_id: str
    records_shredded: int
    shredded_at: str
    shred_audit_id: str


@router.post(
    "/admin/audit-ledger/request-shred",
    response_model=AuditShredRequestOut,
    status_code=status.HTTP_200_OK,
    summary="Stage 1: Request audit ledger crypto-shred blast token under AAL2",
)
async def api_admin_audit_ledger_request_shred(
    body: AuditShredRequestIn,
    caller: Caller,
    session: Session,
) -> AuditShredRequestOut:
    """Compute blast radius and mint single-use confirmation token for crypto-shredding."""
    res = await request_crypto_shred(
        session=session,
        caller=caller,
        activity_id=body.activity_id,
        object_id=body.object_id,
        subject_principal_id=body.subject_principal_id,
        reason=body.reason,
    )
    return AuditShredRequestOut(
        stage=res.stage,
        target_type=res.target_type,
        target_id=res.target_id,
        records_matched=res.records_matched,
        records_to_shred=res.records_to_shred,
        blast_hash=res.blast_hash,
        confirmation_token=res.confirmation_token,
        confirm_phrase=res.confirm_phrase,
        expires_in_sec=res.expires_in_sec,
    )


@router.post(
    "/admin/audit-ledger/execute-shred",
    response_model=AuditShredExecuteOut,
    status_code=status.HTTP_200_OK,
    summary="Stage 2: Execute audit ledger crypto-shredding under AAL2",
)
async def api_admin_audit_ledger_execute_shred(
    body: AuditShredExecuteIn,
    caller: Caller,
    session: Session,
) -> AuditShredExecuteOut:
    """Consume single-use token and permanently overwrite wrapped DEKs with NULL."""
    res = await execute_crypto_shred(
        session=session,
        caller=caller,
        confirmation_token=body.confirmation_token,
        confirm_phrase=body.confirm_phrase,
        reason=body.reason,
    )
    return AuditShredExecuteOut(
        status=res.status,
        target_type=res.target_type,
        target_id=res.target_id,
        records_shredded=res.records_shredded,
        shredded_at=res.shredded_at.isoformat(),
        shred_audit_id=res.shred_audit_id,
    )
