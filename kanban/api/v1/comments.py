# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST endpoints for threaded comments, reactions, and access-checked mentions (KB-P3-05)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for FastAPI path parameter parsing
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002  # Runtime dependency for FastAPI

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.issues import _derive_provenance_tier
from kanban.api.v1.schemas.comments import (
    CommentCreate,
    CommentList,
    CommentPatch,
    CommentResponse,
    ReactionResponse,
)
from kanban.security.ratelimit import ISSUE_COMMENTS_RATE_LIMIT, rate_limited
from kanban.services import comments as svc
from kanban.services.issue_keys import resolve_issue_ref

__all__ = [
    "comments_router",
    "router",
]

router: Final[APIRouter] = APIRouter(tags=["comments"])
comments_router: Final[APIRouter] = router


async def _principal_rate_key(request: Request) -> list[str]:
    """Extract authenticated principal ID for rate limiting."""
    caller = await get_principal(request)
    return [str(caller.principal_id)]


@router.get(
    "/issues/{issue_ref}/comments",
    response_model=CommentList,
    summary="List comments on an issue with nested replies",
)
async def list_issue_comments(
    issue_ref: str,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    cursor: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> CommentList:
    """Return top-level comments ordered created_at ASC with up to 200 inlined replies."""
    async with timing_floor(floor_ms=25.0):
        await resolve_issue_ref(session, caller, issue_ref)
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
    dependencies=[Depends(rate_limited(ISSUE_COMMENTS_RATE_LIMIT, key_func=_principal_rate_key))],
)
async def create_issue_comment(  # noqa: PLR0913, PLR0917
    issue_ref: str,
    body: CommentCreate,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    response: Response,
    request: Request,
) -> CommentResponse:
    """Create comment after normalization, check mention access, and emit activity."""
    async with timing_floor(floor_ms=25.0):
        await resolve_issue_ref(session, caller, issue_ref)
        derived_tier = _derive_provenance_tier(request, caller)
        result, etag = await svc.create_comment(
            session=session,
            caller=caller,
            issue_ref=issue_ref,
            body=body,
        )
        if derived_tier != "trusted_member":
            await session.execute(
                text("UPDATE issue_comments SET provenance_tier = :pt WHERE id = :id"),
                {"pt": derived_tier, "id": result.id},
            )
        response.headers["Location"] = result.permalink
        response.headers["ETag"] = etag
        await session.commit()
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
        await session.commit()
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
        await session.commit()


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
        res = await svc.add_reaction(
            session=session,
            caller=caller,
            comment_id=comment_id,
            emoji=emoji,
        )
        await session.commit()
        return res


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
        await session.commit()
