# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Stickies endpoints: project sticky notes, complexity signals & promote-to-doc (KB-P3-15)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by FastAPI query/path parameter parsing
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.stickies import (
    StickyCreate,
    StickyList,
    StickyPromoteRequest,
    StickyResponse,
    StickyUpdate,
)
from kanban.services import stickies as svc

router = APIRouter(tags=["stickies"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.get(
    "/projects/{project_ref}/stickies",
    response_model=list[StickyResponse],
    summary="List project stickies",
)
async def list_project_stickies(
    project_ref: str,
    caller: Caller,
    session: Session,
    *,
    include_promoted: Annotated[bool, Query()] = True,
) -> list[StickyResponse]:
    """List stickies for a project ordered by sort rank.

    Orders rank using COLLATE 'C', with optional inclusion of promoted stubs.
    """
    return await svc.list_project_stickies(
        session, caller, project_ref, include_promoted=include_promoted
    )


@router.post(
    "/projects/{project_ref}/stickies",
    status_code=201,
    response_model=StickyResponse,
    summary="Create a sticky note",
)
async def create_sticky(
    project_ref: str,
    body: StickyCreate,
    *,
    caller: Caller,
    session: Session,
    response: Response,
) -> StickyResponse:
    """Create a new sticky note in the specified project.

    Supports auto-detected Markdown, color token, and sets ETag response header.
    """
    async with timing_floor(floor_ms=25.0):
        result, etag = await svc.create_sticky(session, caller, project_ref, body)
        response.headers["ETag"] = etag
        response.headers["Location"] = f"/api/v1/stickies/{result.id}"
        return result


@router.get(
    "/stickies",
    response_model=StickyList,
    summary="List workspace stickies",
)
async def list_workspace_stickies(
    caller: Caller,
    session: Session,
    *,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> StickyList:
    """Keyset-paginated listing of stickies across the workspace.

    Returns stickies visible to the caller under row-level security.
    """
    return await svc.list_workspace_stickies(session, caller, cursor=cursor, limit=limit)


@router.get(
    "/stickies/{sticky_id}",
    response_model=StickyResponse,
    summary="Get a sticky note",
    responses={304: {"description": "Not Modified"}},
)
async def get_sticky(
    sticky_id: uuid.UUID,
    caller: Caller,
    session: Session,
    response: Response,
    *,
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response | StickyResponse:
    """Retrieve a sticky note by UUID with ETag caching.

    Returns 304 Not Modified when matching If-None-Match header.
    """
    result, etag = await svc.get_sticky(session, caller, sticky_id)
    if if_none_match and (if_none_match.strip() in (etag, etag.strip('"'), "*")):
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return result


@router.patch(
    "/stickies/{sticky_id}",
    response_model=StickyResponse,
    summary="Update a sticky note",
)
async def update_sticky(  # noqa: PLR0913
    sticky_id: uuid.UUID,
    body: StickyUpdate,
    *,
    caller: Caller,
    session: Session,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
) -> StickyResponse:
    """Update a sticky note with ETag optimistic concurrency enforcement.

    Enforces concurrency using the If-Match request header.
    """
    async with timing_floor(floor_ms=25.0):
        result, etag = await svc.update_sticky(session, caller, sticky_id, body, if_match)
        response.headers["ETag"] = etag
        return result


@router.delete(
    "/stickies/{sticky_id}",
    status_code=200,
    summary="Delete a sticky note",
)
async def delete_sticky(
    sticky_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> dict[str, Any]:
    """Soft-delete a sticky note into the project trash bin.

    Preserves activity audit ledger history.
    """
    async with timing_floor(floor_ms=25.0):
        return await svc.delete_sticky(session, caller, sticky_id)


@router.post(
    "/stickies/{sticky_id}/snooze-promotion",
    status_code=200,
    response_model=StickyResponse,
    summary="Snooze promotion recommendation",
)
async def snooze_sticky_promotion(
    sticky_id: uuid.UUID,
    caller: Caller,
    session: Session,
    response: Response,
) -> StickyResponse:
    """Snooze promotion recommendation until body grows by >= 1.5x."""
    async with timing_floor(floor_ms=25.0):
        result, etag = await svc.snooze_sticky_promotion(session, caller, sticky_id)
        response.headers["ETag"] = etag
        return result


@router.post(
    "/stickies/{sticky_id}/promote-to-doc",
    status_code=201,
    response_model=StickyResponse,
    summary="Promote sticky to doc",
)
async def promote_sticky_to_doc(
    sticky_id: uuid.UUID,
    body: StickyPromoteRequest,
    *,
    caller: Caller,
    session: Session,
    response: Response,
) -> StickyResponse:
    """Atomically promote a sticky into a Doc + Page preserving direct ACLs verbatim."""
    async with timing_floor(floor_ms=25.0):
        result, etag = await svc.promote_sticky_to_doc(session, caller, sticky_id, body)
        response.headers["ETag"] = etag
        response.headers["Location"] = f"/api/v1/stickies/{result.id}"
        return result


@router.post(
    "/stickies/{sticky_id}/unarchive-copy",
    status_code=201,
    response_model=StickyResponse,
    summary="Unarchive copy of promoted sticky",
)
async def unarchive_sticky_copy(
    sticky_id: uuid.UUID,
    *,
    caller: Caller,
    session: Session,
    response: Response,
) -> StickyResponse:
    """Clone a promoted sticky's content, color, and ACLs into a fresh unpromoted sticky note."""
    async with timing_floor(floor_ms=25.0):
        result, etag = await svc.unarchive_sticky_copy(session, caller, sticky_id)
        response.headers["ETag"] = etag
        response.headers["Location"] = f"/api/v1/stickies/{result.id}"
        return result
