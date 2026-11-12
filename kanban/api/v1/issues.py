"""Issue endpoints: CRUD, keyset listing, and description ETag concurrency (S7.2 8a, S3.4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession  # Required by FastAPI at runtime

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.issues import IssueCreate, IssueList, IssuePatch, IssueResponse
from kanban.services import issues as svc

router = APIRouter(tags=["issues"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.post(
    "/projects/{project_ref}/issues",
    status_code=201,
    response_model=IssueResponse,
    summary="Create an issue",
)
async def create_issue(
    project_ref: str,
    body: IssueCreate,
    caller: Caller,
    session: Session,
    response: Response,
) -> IssueResponse:
    """Create an issue in a project (caller requires EDIT capability on project)."""
    async with timing_floor(floor_ms=25.0):
        result, etag = await svc.create_issue(session, caller, project_ref, body)
        response.headers["Location"] = f"/api/v1/issues/{result.key}"
        response.headers["ETag"] = etag
        return result


@router.get(
    "/issues/{issue_ref}",
    response_model=IssueResponse,
    summary="Get an issue by key or UUID",
)
async def get_issue(
    issue_ref: str,
    caller: Caller,
    session: Session,
    response: Response,
    if_none_match: Annotated[str | None, Header()] = None,
) -> IssueResponse | Response:
    """Return an issue, or 304 when If-None-Match matches current description ETag."""
    async with timing_floor(floor_ms=25.0):
        issue = await svc.get_issue_or_404(session, caller, issue_ref)
        sha256_hex = issue.description_sha256.hex() if issue.description_sha256 else ""
        etag = f'"{sha256_hex}"'

        if if_none_match is not None:
            raw_header = if_none_match.strip()
            if raw_header.startswith("W/"):
                raw_header = raw_header[2:].strip()
            client_hex = raw_header.strip('"')
            if client_hex.lower() == sha256_hex.lower() or raw_header == etag:
                return Response(status_code=304, headers={"ETag": etag})

        response.headers["ETag"] = etag
        return await svc.serialize_issue(session, caller, issue)


@router.patch(
    "/issues/{issue_ref}",
    response_model=IssueResponse,
    summary="Update an issue",
)
async def patch_issue(  # noqa: PLR0913, PLR0917
    issue_ref: str,
    body: IssuePatch,
    caller: Caller,
    session: Session,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
) -> IssueResponse:
    """Update issue fields under description ETag concurrency check."""
    async with timing_floor(floor_ms=25.0):
        result, new_etag = await svc.update_issue(session, caller, issue_ref, body, if_match)
        response.headers["ETag"] = new_etag
        return result


@router.get(
    "/projects/{project_ref}/issues",
    response_model=IssueList,
    summary="List issues in a project",
)
async def list_issues(
    project_ref: str,
    caller: Caller,
    session: Session,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> IssueList:
    """List RLS-visible issues within a project using keyset pagination."""
    async with timing_floor(floor_ms=25.0):
        return await svc.list_issues(session, caller, project_ref, cursor=cursor, limit=limit)
