"""Issue endpoints CRUD and outbound secret scrubbing.

Covers CRUD, keyset listing, description ETag concurrency, and secret redaction (S7.2, S3.4).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession  # Required by FastAPI at runtime

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.issues import IssueCreate, IssueList, IssuePatch, IssueResponse
from kanban.security.read_taint import (
    TaintGuard,
    TaintRecorder,
    get_taint_guard,
    get_taint_recorder,
)
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
        await session.commit()
        return result


@router.get(
    "/issues/{issue_key}",
    response_model=IssueResponse,
    summary="Get an issue by key or UUID",
)
async def get_issue(  # noqa: PLR0913, PLR0917
    issue_key: str,
    caller: Caller,
    session: Session,
    response: Response,
    request: Request,
    taint_recorder: Annotated[TaintRecorder, Depends(get_taint_recorder)],
    workspace: Annotated[str | None, Query(description="Optional workspace slug or UUID")] = None,
    if_none_match: Annotated[str | None, Header()] = None,
) -> IssueResponse | Response:
    """Return an issue, or 304 when If-None-Match matches current issue ETag."""
    workspace_ref = workspace or request.headers.get("x-kb-scope-workspace")
    async with timing_floor(floor_ms=25.0):
        issue = await svc.get_issue_or_404(session, caller, issue_key, workspace_ref=workspace_ref)
        await taint_recorder.record_project_ids([issue.project_id])
        serialized = await svc.serialize_issue(session, caller, issue)
        desc_sha = issue.description_sha256.hex() if issue.description_sha256 else ""
        etag = serialized.etag or (f'"{desc_sha}"' if desc_sha else '""')
        etag_hex = etag.strip('"')

        if if_none_match is not None:
            raw_header = if_none_match.strip()
            if raw_header.startswith("W/"):
                raw_header = raw_header[2:].strip()
            client_hex = raw_header.strip('"')
            if client_hex.lower() == etag_hex.lower() or raw_header == etag:
                return Response(status_code=304, headers={"ETag": etag})

        response.headers["ETag"] = etag
        return serialized


@router.patch(
    "/issues/{issue_key}",
    response_model=IssueResponse,
    summary="Update an issue",
)
async def patch_issue(  # noqa: PLR0913, PLR0917
    issue_key: str,
    body: IssuePatch,
    caller: Caller,
    session: Session,
    response: Response,
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
    if_match: Annotated[str | None, Header()] = None,
) -> IssueResponse:
    """Update issue fields under description ETag concurrency check."""
    async with timing_floor(floor_ms=25.0):
        issue = await svc.get_issue_or_404(session, caller, issue_key)
        await taint_guard.check_write(issue.project_id, tool_name="update_ticket")
        result, new_etag = await svc.update_issue(session, caller, issue_key, body, if_match)
        await session.commit()
        response.headers["ETag"] = new_etag
        return result


@router.get(
    "/projects/{project_ref}/issues",
    response_model=IssueList,
    summary="List issues in a project",
)
async def list_issues(  # noqa: PLR0913
    project_ref: str,
    caller: Caller,
    session: Session,
    taint_recorder: Annotated[TaintRecorder, Depends(get_taint_recorder)],
    *,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    include_archived: Annotated[bool, Query()] = False,
    only_archived: Annotated[bool, Query()] = False,
) -> IssueList:
    """List RLS-visible issues within a project using keyset pagination."""
    if not include_archived and only_archived:
        raise ProblemException(
            code="ARCHIVE_FILTER_CONFLICT",
            status=422,
            title="Archive Filter Conflict",
            detail="Cannot filter only_archived=true when include_archived=false",
        )
    async with timing_floor(floor_ms=25.0):
        res = await svc.list_issues(
            session,
            caller,
            project_ref,
            cursor=cursor,
            limit=limit,
            include_archived=include_archived,
            only_archived=only_archived,
        )
        await taint_recorder.record_project_ids([project_ref])
        return res
