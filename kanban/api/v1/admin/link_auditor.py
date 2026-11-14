# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Administrative endpoints for Universal Object Graph link auditor and purge (KB-P4-11, S12.3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.api.problems import ProblemException
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.link_auditor import (
    LinkAuditListResponse,
    LinkAuditScanResponse,
    LinkPurgeRequest,
    LinkPurgeResponse,
)
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.services import link_auditor_admin as svc

router = APIRouter(
    prefix="/admin",
    tags=["admin-link-auditor"],
    dependencies=[Depends(require_admin_aal2)],
)

Caller = Annotated[PrincipalContext, Depends(require_admin_aal2)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


async def require_workspace_or_server_admin(
    caller: Caller,
    session: Session,
) -> PrincipalContext:
    """Verify caller holds WORKSPACE_ADMIN or SERVER_ADMIN role."""
    stmt = text("SELECT app_principal_has_role(NULL, ARRAY['WORKSPACE_ADMIN', 'SERVER_ADMIN'])")
    has_role = bool((await session.execute(stmt)).scalar_one())
    if not has_role:
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=status.HTTP_403_FORBIDDEN,
            title="Insufficient Capability",
            detail="Operation requires WORKSPACE_ADMIN or SERVER_ADMIN role.",
        )
    return caller


@router.post(
    "/object-links:audit",
    response_model=LinkAuditScanResponse,
    summary="Run Universal Object Graph Link Auditor",
)
async def post_audit_object_links(
    caller: Annotated[PrincipalContext, Depends(require_workspace_or_server_admin)],
    session: Session,
) -> LinkAuditScanResponse:
    """Scan workspace object links and return aggregated invalidity counts across 6 classes."""
    async with timing_floor(floor_ms=25.0):
        return await svc.run_link_audit(session, caller, caller.workspace_id)


@router.get(
    "/object-links/audits",
    response_model=LinkAuditListResponse,
    summary="List flagged invalid object link audit records",
)
async def get_object_link_audits(  # noqa: PLR0913, PLR0917
    caller: Annotated[PrincipalContext, Depends(require_workspace_or_server_admin)],
    session: Session,
    reason_code: Annotated[
        str | None,
        Query(description="Filter by invalidity reason code"),
    ] = None,
    status_filter: Annotated[
        str,
        Query(
            alias="status",
            description="Filter by audit status ('unpurged', 'purged', 'resolved', 'all')",
        ),
    ] = "unpurged",
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Page limit (1..100)"),
    ] = 50,
    cursor: Annotated[
        str | None,
        Query(description="Keyset pagination cursor"),
    ] = None,
) -> LinkAuditListResponse:
    """Retrieve paginated snapshot audits of flagged invalid object links."""
    async with timing_floor(floor_ms=25.0):
        return await svc.list_link_audits(
            session,
            caller,
            caller.workspace_id,
            reason_code=reason_code,
            status=status_filter,
            limit=limit,
            cursor=cursor,
        )


@router.post(
    "/object-links:purge",
    response_model=LinkPurgeResponse,
    summary="Audited purge of flagged invalid object links",
)
async def post_purge_object_links(
    body: LinkPurgeRequest,
    caller: Annotated[PrincipalContext, Depends(require_workspace_or_server_admin)],
    session: Session,
) -> LinkPurgeResponse:
    """Execute audited purge of flagged invalid object links and emit activity ledger entries."""
    async with timing_floor(floor_ms=25.0):
        return await svc.purge_flagged_links(
            session,
            caller,
            caller.workspace_id,
            audit_ids=body.audit_ids,
            reason=body.reason,
        )
