"""Archive and unarchive endpoints for issues (S7.2 8p)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.issues import IssueResponse
from kanban.services import issue_archive as svc

router = APIRouter(tags=["issues"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


class IssueUnarchiveRequest(BaseModel):
    """Optional request payload for unarchiving an issue."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(
        default=None,
        description="Optional administrative unarchive justification",
    )
    admin_override: bool = Field(
        default=False,
        description="Whether unarchive was invoked as an administrative override",
    )


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
    body: IssueUnarchiveRequest | None = None,
) -> IssueResponse:
    """Unarchive an archived issue restoring active board state and workflow participation."""
    async with timing_floor(floor_ms=25.0):
        reason = body.reason if body else None
        admin_override = body.admin_override if body else False
        return await svc.unarchive_issue(
            session,
            caller,
            issue_ref,
            reason=reason,
            admin_override=admin_override,
        )
