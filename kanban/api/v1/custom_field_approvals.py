# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for Custom Field escalation approvals (KB-P5-12, S13.2, S4.2)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by FastAPI path parameter resolution
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.custom_fields import (
    CustomFieldApprovalApproveRequest,
    CustomFieldApprovalRequestCreate,
    CustomFieldApprovalResponse,
)
from kanban.custom_fields.approvals import CustomFieldApprovalService

router = APIRouter(tags=["custom-field-approvals"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.post(
    "/custom-fields/{field_id}/approval-requests",
    response_model=CustomFieldApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an escalation approval request for a custom field",
)
async def create_approval_request(
    field_id: str,
    body: CustomFieldApprovalRequestCreate,
    caller: Caller,
    session: Session,
) -> CustomFieldApprovalResponse:
    """Create a pending escalation approval request (requires PROJECT_ADMIN and AAL2)."""
    async with timing_floor(floor_ms=25.0):
        return await CustomFieldApprovalService.request_approval(session, caller, field_id, body)


@router.post(
    "/custom-field-approvals/{approval_id}/approve",
    response_model=CustomFieldApprovalResponse,
    summary="Approve a custom field escalation request",
)
async def approve_escalation(
    approval_id: uuid.UUID,
    body: CustomFieldApprovalApproveRequest,
    caller: Caller,
    session: Session,
) -> CustomFieldApprovalResponse:
    """Approve an escalation request (requires AAL2 <=900s, tier admin, and dual control)."""
    async with timing_floor(floor_ms=25.0):
        return await CustomFieldApprovalService.approve(session, caller, approval_id, body)


@router.get(
    "/custom-fields/{field_id}/approvals",
    response_model=list[CustomFieldApprovalResponse],
    summary="List escalation approval history for a custom field",
)
async def list_approvals(
    field_id: str,
    caller: Caller,
    session: Session,
) -> list[CustomFieldApprovalResponse]:
    """List escalation approvals for a custom field visible to project administrators."""
    async with timing_floor(floor_ms=25.0):
        return await CustomFieldApprovalService.list_approvals(session, caller, field_id)
