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
from kanban.security.read_taint import (
    TaintGuard,
    TaintRecorder,
    get_taint_guard,
    get_taint_recorder,
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
    taint_recorder: Annotated[TaintRecorder, Depends(get_taint_recorder)],
    *,
    include_promoted: Annotated[bool, Query()] = True,
) -> list[StickyResponse]:
    """List stickies for a project ordered by sort rank.

    Orders rank using COLLATE 'C', with optional inclusion of promoted stubs.
    """
    res = await svc.list_project_stickies(
        session, caller, project_ref, include_promoted=include_promoted
    )
    await taint_recorder.record_project_ids([project_ref])
    return res


@router.post(
    "/projects/{project_ref}/stickies",
    status_code=201,
    response_model=StickyResponse,
    summary="Create a sticky note",
)
async def create_sticky(  # noqa: PLR0913
    project_ref: str,
    body: StickyCreate,
    *,
    caller: Caller,
    session: Session,
    response: Response,
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
) -> StickyResponse:
    """Create a new sticky note in the specified project.

    Supports auto-detected Markdown, color token, and sets ETag response header.
    """
    async with timing_floor(floor_ms=25.0):
        await taint_guard.check_write(project_ref, tool_name="create_sticky")
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
    taint_recorder: Annotated[TaintRecorder, Depends(get_taint_recorder)],
    *,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> StickyList:
    """Keyset-paginated listing of stickies across the workspace.

    Returns stickies visible to the caller under row-level security.
    """
    res = await svc.list_workspace_stickies(session, caller, cursor=cursor, limit=limit)
    pids = {s.project_id for s in res.items if s.project_id is not None}
    if pids:
        await taint_recorder.record_project_ids(pids)
    return res


@router.get(
    "/stickies/{sticky_id}",
    response_model=StickyResponse,
    summary="Get a sticky note",
    responses={304: {"description": "Not Modified"}},
)
async def get_sticky(  # noqa: PLR0913
    sticky_id: uuid.UUID,
    caller: Caller,
    session: Session,
    response: Response,
    taint_recorder: Annotated[TaintRecorder, Depends(get_taint_recorder)],
    *,
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response | StickyResponse:
    """Retrieve a sticky note by UUID with ETag caching.

    Returns 304 Not Modified when matching If-None-Match header.
    """
    result, etag = await svc.get_sticky(session, caller, sticky_id)
    if result.project_id is not None:
        await taint_recorder.record_project_ids([result.project_id])
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
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
    if_match: Annotated[str | None, Header()] = None,
) -> StickyResponse:
    """Update a sticky note with ETag optimistic concurrency enforcement.

    Enforces concurrency using the If-Match request header.
    """
    async with timing_floor(floor_ms=25.0):
        sticky, _ = await svc.get_sticky(session, caller, sticky_id)
        if sticky.project_id is not None:
            await taint_guard.check_write(sticky.project_id, tool_name="update_sticky")
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
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
) -> dict[str, Any]:
    """Soft-delete a sticky note into the project trash bin.

    Preserves activity audit ledger history.
    """
    async with timing_floor(floor_ms=25.0):
        sticky, _ = await svc.get_sticky(session, caller, sticky_id)
        if sticky.project_id is not None:
            await taint_guard.check_write(sticky.project_id, tool_name="delete_sticky")
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
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
) -> StickyResponse:
    """Snooze promotion recommendation until body grows by >= 1.5x."""
    async with timing_floor(floor_ms=25.0):
        sticky, _ = await svc.get_sticky(session, caller, sticky_id)
        if sticky.project_id is not None:
            await taint_guard.check_write(sticky.project_id, tool_name="snooze_sticky_promotion")
        result, etag = await svc.snooze_sticky_promotion(session, caller, sticky_id)
        response.headers["ETag"] = etag
        return result


@router.post(
    "/stickies/{sticky_id}/promote-to-doc",
    status_code=201,
    response_model=StickyResponse,
    summary="Promote sticky to doc",
)
async def promote_sticky_to_doc(  # noqa: PLR0913
    sticky_id: uuid.UUID,
    body: StickyPromoteRequest,
    *,
    caller: Caller,
    session: Session,
    response: Response,
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
) -> StickyResponse:
    """Atomically promote a sticky into a Doc + Page preserving direct ACLs verbatim."""
    async with timing_floor(floor_ms=25.0):
        sticky, _ = await svc.get_sticky(session, caller, sticky_id)
        if sticky.project_id is not None:
            await taint_guard.check_write(sticky.project_id, tool_name="promote_sticky_to_doc")
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
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
) -> StickyResponse:
    """Clone a promoted sticky's content, color, and ACLs into a fresh unpromoted sticky note."""
    async with timing_floor(floor_ms=25.0):
        sticky, _ = await svc.get_sticky(session, caller, sticky_id)
        if sticky.project_id is not None:
            await taint_guard.check_write(sticky.project_id, tool_name="unarchive_sticky_copy")
        result, etag = await svc.unarchive_sticky_copy(session, caller, sticky_id)
        response.headers["ETag"] = etag
        response.headers["Location"] = f"/api/v1/stickies/{result.id}"
        return result
