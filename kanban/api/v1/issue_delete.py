"""Issue delete preview, soft trash, trash listing, and restore endpoints (S7.2 8q)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.issue_delete import (
    BlastRadiusResponse,
    IssueDeleteResponse,
    TrashedIssueList,
)
from kanban.api.v1.schemas.issues import IssueResponse
from kanban.security.permissions import Capability, require_capability
from kanban.services import issue_delete as svc
from kanban.services.issue_keys import resolve_issue_ref

router = APIRouter(tags=["issues"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.get(
    "/issues/{issue_ref}/delete-preview",
    response_model=BlastRadiusResponse,
    summary="Get issue delete blast radius preview",
)
async def delete_preview(
    issue_ref: str,
    caller: Caller,
    session: Session,
) -> BlastRadiusResponse:
    """Return blast radius preview for deleting an issue (requires DELETE capability)."""
    async with timing_floor(floor_ms=25.0):
        issue = await resolve_issue_ref(session, caller, issue_ref)
        await require_capability(session, caller, issue.id, Capability.DELETE)
        blast = await svc.compute_blast_radius(session, issue.id)
        return BlastRadiusResponse(
            issue_key=blast.issue_key,
            sub_issues_unparented=blast.sub_issues_unparented,
            inbound_links_flagged=blast.inbound_links_flagged,
            outbound_links=blast.outbound_links,
            comments=blast.comments,
            attachments=blast.attachments,
            summary_text=blast.summary_text,
            blast_hash=blast.blast_hash,
            retention_days=blast.retention_days,
        )


@router.delete(
    "/issues/{issue_ref}",
    response_model=IssueDeleteResponse,
    summary="Soft-delete an issue into trash",
    responses={
        428: {
            "description": (
                "Precondition Required: Kb-Blast-Hash header is required. Directs callers to "
                "GET /api/v1/issues/{id}/delete-preview to obtain blast_hash (confirm_blast_hash)."
            )
        }
    },
)
async def delete_issue(
    issue_ref: str,
    caller: Caller,
    session: Session,
    kb_blast_hash: Annotated[str | None, Header(alias="Kb-Blast-Hash")] = None,
) -> IssueDeleteResponse:
    """Soft-delete an issue into trash guarded by blast-radius hash concurrency check."""
    async with timing_floor(floor_ms=25.0):
        return await svc.trash_issue(session, caller, issue_ref, kb_blast_hash)


@router.get(
    "/projects/{project_ref}/trash",
    response_model=TrashedIssueList,
    summary="List issues in project trash",
)
async def list_trash(
    project_ref: str,
    caller: Caller,
    session: Session,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TrashedIssueList:
    """List soft-deleted issues in project trash where caller has DELETE capability."""
    async with timing_floor(floor_ms=25.0):
        return await svc.list_trash(session, caller, project_ref, cursor=cursor, limit=limit)


@router.post(
    "/issues/{issue_ref}/restore",
    response_model=IssueResponse,
    summary="Restore an issue from trash",
)
async def restore_issue(
    issue_ref: str,
    caller: Caller,
    session: Session,
) -> IssueResponse:
    """Restore a soft-deleted issue from trash back into active state."""
    async with timing_floor(floor_ms=25.0):
        return await svc.restore_issue(session, caller, issue_ref)
