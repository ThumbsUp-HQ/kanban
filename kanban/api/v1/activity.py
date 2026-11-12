# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST endpoints for 4-tab activity feed with cursor pagination (S7.1, S7.2 8j, S3.4; KB-P3-13)."""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002  # Runtime dependency for FastAPI

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.activity import (
    ActivityFeedResponse,
    ActivityOrder,
    ActivityTab,
)
from kanban.services import activity_feed as svc

__all__ = [
    "activity_router",
    "router",
]

router: Final[APIRouter] = APIRouter(tags=["activity"])
activity_router: Final[APIRouter] = router


@router.get(
    "/issues/{issue_ref}/activity",
    response_model=ActivityFeedResponse,
    summary="List activity feed items for an issue across 4 tabs",
)
async def list_issue_activity(  # noqa: PLR0913, PLR0917
    issue_ref: str,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    tab: Annotated[
        ActivityTab, Query(description="Tab filter: all, comments, history, gates")
    ] = "all",
    order: Annotated[ActivityOrder, Query(description="Order by timestamp: desc or asc")] = "desc",
    limit: Annotated[int, Query(ge=1, le=100, description="Items per page (1..100)")] = 50,
    cursor: Annotated[
        str | None, Query(max_length=256, description="Opaque HMAC keyset cursor")
    ] = None,
    include_hashes: Annotated[  # noqa: FBT002
        bool, Query(description="Include cryptographic row/prev hashes")
    ] = False,
) -> ActivityFeedResponse:
    """Return paginated activity feed items with counts and hydrated comments for an issue."""
    async with timing_floor(floor_ms=25.0):
        return await svc.get_issue_activity(
            session=session,
            caller=caller,
            issue_ref=issue_ref,
            tab=tab,
            order=order,
            limit=limit,
            cursor=cursor,
            include_hashes=include_hashes,
        )


@router.get(
    "/projects/{project_ref}/activity",
    response_model=ActivityFeedResponse,
    summary="List activity feed items across a project with RLS filtering",
)
async def list_project_activity(  # noqa: PLR0913, PLR0917
    project_ref: str,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    tab: Annotated[
        ActivityTab, Query(description="Tab filter: all, comments, history, gates")
    ] = "all",
    order: Annotated[ActivityOrder, Query(description="Order by timestamp: desc or asc")] = "desc",
    limit: Annotated[int, Query(ge=1, le=100, description="Items per page (1..100)")] = 50,
    cursor: Annotated[
        str | None, Query(max_length=256, description="Opaque HMAC keyset cursor")
    ] = None,
    include_hashes: Annotated[  # noqa: FBT002
        bool, Query(description="Include cryptographic row/prev hashes")
    ] = False,
) -> ActivityFeedResponse:
    """Return paginated activity feed items across all readable objects in a project."""
    async with timing_floor(floor_ms=25.0):
        return await svc.get_project_activity(
            session=session,
            caller=caller,
            project_ref=project_ref,
            tab=tab,
            order=order,
            limit=limit,
            cursor=cursor,
            include_hashes=include_hashes,
        )
