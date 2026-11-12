"""Archive and unarchive endpoints for issues (S7.2 8p)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.issues import IssueResponse
from kanban.services import issue_archive as svc

router = APIRouter(tags=["issues"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.post(
    "/issues/{issue_ref}/archive",
    response_model=IssueResponse,
    summary="Archive an issue",
)
async def archive_issue(
    issue_ref: str,
    caller: Caller,
    session: Session,
) -> IssueResponse:
    """Archive an issue enforcing completed/cancelled state and no open sub-issues."""
    async with timing_floor(floor_ms=25.0):
        return await svc.archive_issue(session, caller, issue_ref)


@router.post(
    "/issues/{issue_ref}/unarchive",
    response_model=IssueResponse,
    summary="Unarchive an issue",
)
async def unarchive_issue(
    issue_ref: str,
    caller: Caller,
    session: Session,
) -> IssueResponse:
    """Unarchive an archived issue restoring active state."""
    async with timing_floor(floor_ms=25.0):
        return await svc.unarchive_issue(session, caller, issue_ref)
