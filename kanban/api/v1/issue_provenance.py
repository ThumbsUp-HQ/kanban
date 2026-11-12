"""Administrative creator override and provenance endpoint (KB-P3-04, S7.2 8d, S11.4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.issue_provenance import (
    IssueOverrideCreatorRequest,  # noqa: TC001  # Required at runtime by FastAPI
)
from kanban.api.v1.schemas.issues import IssueResponse
from kanban.services import issue_provenance as svc

router = APIRouter(tags=["issues"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.patch(
    "/issues/{issue_ref}/created-by",
    response_model=IssueResponse,
    response_model_exclude_none=False,
)
async def patch_issue_created_by(
    issue_ref: str,
    body: IssueOverrideCreatorRequest,
    caller: Caller,
    session: Session,
    response: Response,
) -> IssueResponse:
    """Override created_by on an issue under administrative authorization (S7.2 8d)."""
    async with timing_floor(floor_ms=25.0):
        result, etag = await svc.override_issue_created_by(session, caller, issue_ref, body)
        response.headers["ETag"] = etag
        return result
