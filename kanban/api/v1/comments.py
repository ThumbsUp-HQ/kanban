# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST endpoints for threaded comments, reactions, and access-checked mentions (KB-P3-05)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for FastAPI path parameter parsing
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002  # Runtime dependency for FastAPI

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.comments import (
    CommentCreate,
    CommentList,
    CommentPatch,
    CommentResponse,
    ReactionResponse,
)
from kanban.security.read_taint import (
    TaintGuard,
    TaintRecorder,
    get_taint_guard,
    get_taint_recorder,
)
from kanban.services import comments as svc
from kanban.services.issue_keys import resolve_issue_ref

__all__ = [
    "comments_router",
    "router",
]

router: Final[APIRouter] = APIRouter(tags=["comments"])
comments_router: Final[APIRouter] = router


@router.get(
    "/issues/{issue_ref}/comments",
    response_model=CommentList,
    summary="List comments on an issue with nested replies",
)
async def list_issue_comments(  # noqa: PLR0913, PLR0917
    issue_ref: str,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    taint_recorder: Annotated[TaintRecorder, Depends(get_taint_recorder)],
    cursor: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> CommentList:
    """Return top-level comments ordered created_at ASC with up to 200 inlined replies."""
    async with timing_floor(floor_ms=25.0):
        issue = await resolve_issue_ref(session, caller, issue_ref)
        await taint_recorder.record_project_ids([issue.project_id])
        return await svc.list_comments(
            session=session,
            caller=caller,
            issue_ref=issue_ref,
            cursor=cursor,
            limit=limit,
        )


@router.post(
    "/issues/{issue_ref}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a top-level comment or depth-1 reply on an issue",
)
async def create_issue_comment(  # noqa: PLR0913, PLR0917
    issue_ref: str,
    body: CommentCreate,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    response: Response,
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
) -> CommentResponse:
    """Create comment after normalization, check mention access, and emit activity."""
    async with timing_floor(floor_ms=25.0):
        issue = await resolve_issue_ref(session, caller, issue_ref)
        await taint_guard.check_write(issue.project_id, tool_name="add_comment")
        result, etag = await svc.create_comment(
            session=session,
            caller=caller,
            issue_ref=issue_ref,
            body=body,
        )
        response.headers["Location"] = result.permalink
        response.headers["ETag"] = etag
        return result


@router.patch(
    "/comments/{comment_id}",
    response_model=CommentResponse,
    summary="Update comment body under ETag concurrency control",
)
async def update_comment(  # noqa: PLR0913, PLR0917
    comment_id: uuid.UUID,
    body: CommentPatch,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
) -> CommentResponse:
    """Author-only edit verifying If-Match ETag and mention access warning gate."""
    async with timing_floor(floor_ms=25.0):
        result, new_etag = await svc.update_comment(
            session=session,
            caller=caller,
            comment_id=comment_id,
            body=body,
            if_match=if_match,
        )
        response.headers["ETag"] = new_etag
        return result


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a comment (author or project admin)",
)
async def delete_comment(
    comment_id: uuid.UUID,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> None:
    """Soft-delete comment setting deleted_at and emitting activity."""
    async with timing_floor(floor_ms=25.0):
        await svc.delete_comment(
            session=session,
            caller=caller,
            comment_id=comment_id,
        )


@router.put(
    "/comments/{comment_id}/reactions/{emoji}",
    response_model=ReactionResponse,
    summary="Add an emoji reaction to a comment",
)
async def add_reaction(
    comment_id: uuid.UUID,
    emoji: str,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> ReactionResponse:
    """Idempotently add an allowlisted emoji reaction to a visible comment."""
    async with timing_floor(floor_ms=25.0):
        return await svc.add_reaction(
            session=session,
            caller=caller,
            comment_id=comment_id,
            emoji=emoji,
        )


@router.delete(
    "/comments/{comment_id}/reactions/{emoji}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an emoji reaction from a comment",
)
async def delete_reaction(
    comment_id: uuid.UUID,
    emoji: str,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> None:
    """Idempotently remove an emoji reaction from a visible comment."""
    async with timing_floor(floor_ms=25.0):
        await svc.delete_reaction(
            session=session,
            caller=caller,
            comment_id=comment_id,
            emoji=emoji,
        )
