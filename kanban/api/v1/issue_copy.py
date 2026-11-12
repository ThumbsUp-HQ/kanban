"""Issue copy API endpoint (KB-P3-08, S7.2 8n)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.issue_copy import IssueCopyRequest, IssueCopyResponse
from kanban.services.issue_copy import copy_issue

router = APIRouter(tags=["issues"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.post(
    "/issues/{issue_ref}/copy",
    response_model=IssueCopyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Make a copy of an issue",
)
async def copy_issue_endpoint(
    issue_ref: str,
    body: IssueCopyRequest,
    caller: Caller,
    session: Session,
    response: Response,
) -> IssueCopyResponse:
    """Clone an issue and optionally its descendant subtree and attachments."""
    async with timing_floor(floor_ms=25.0):
        result, canonical_key = await copy_issue(session, caller, issue_ref, body)
        response.headers["Location"] = f"/api/v1/issues/{canonical_key}"
        return result
