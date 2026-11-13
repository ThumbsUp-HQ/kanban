"""Saved views CRUD and 2D query engine REST endpoints (S6.4, S3.4)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by FastAPI query parameter parsing
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Response

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.views import (
    AdHocQueryRequest,
    ViewCreate,
    ViewList,
    ViewPatch,
    ViewQueryResponse,
    ViewResponse,
)
from kanban.services import views as svc

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["views"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated["AsyncSession", Depends(get_rls_session)]


@router.get(
    "/projects/{project_ref}/views",
    response_model=ViewList,
    summary="List project saved views",
)
async def list_project_views(
    project_ref: str,
    caller: Caller,
    session: Session,
) -> ViewList:
    """List all saved views in a project visible to the caller under RLS."""
    async with timing_floor(floor_ms=25.0):
        return await svc.list_project_views(session, caller, project_ref)


@router.post(
    "/projects/{project_ref}/views",
    status_code=201,
    response_model=ViewResponse,
    summary="Create saved view",
)
async def create_view(
    project_ref: str,
    body: ViewCreate,
    caller: Caller,
    session: Session,
) -> ViewResponse:
    """Create a new saved view in a project."""
    async with timing_floor(floor_ms=25.0):
        return await svc.create_view(session, caller, project_ref, body)


@router.get(
    "/views/{view_id}",
    response_model=ViewResponse,
    summary="Get saved view",
)
async def get_view(
    view_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> ViewResponse:
    """Retrieve a saved view by its ID."""
    async with timing_floor(floor_ms=25.0):
        view = await svc.get_view_or_404(session, caller, view_id)
        return await svc.serialize_view(session, caller, view)


@router.patch(
    "/views/{view_id}",
    response_model=ViewResponse,
    summary="Update saved view",
)
async def update_view(
    view_id: uuid.UUID,
    body: ViewPatch,
    caller: Caller,
    session: Session,
) -> ViewResponse:
    """Update an existing saved view."""
    async with timing_floor(floor_ms=25.0):
        return await svc.update_view(session, caller, view_id, body)


@router.delete(
    "/views/{view_id}",
    status_code=204,
    response_class=Response,
    summary="Delete saved view",
)
async def delete_view(
    view_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> Response:
    """Delete a saved view."""
    async with timing_floor(floor_ms=25.0):
        await svc.delete_view(session, caller, view_id)
        return Response(status_code=204)


@router.get(
    "/views/{view_id}/issues",
    response_model=ViewQueryResponse,
    summary="Query issues in a saved view",
)
async def query_view_issues_get(
    view_id: uuid.UUID,
    caller: Caller,
    session: Session,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ViewQueryResponse:
    """Execute query for a saved view using its configuration."""
    async with timing_floor(floor_ms=25.0):
        return await svc.query_view_issues(session, caller, view_id, cursor=cursor, limit=limit)


@router.post(
    "/views/{view_id}/query",
    response_model=ViewQueryResponse,
    summary="Query issues in a saved view (POST alias)",
)
@router.post(
    "/views/{view_id}/issues",
    response_model=ViewQueryResponse,
    summary="Query issues in a saved view (POST issues alias)",
)
async def query_view_issues_post(
    view_id: uuid.UUID,
    caller: Caller,
    session: Session,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ViewQueryResponse:
    """Execute query for a saved view via POST."""
    async with timing_floor(floor_ms=25.0):
        return await svc.query_view_issues(session, caller, view_id, cursor=cursor, limit=limit)


@router.post(
    "/projects/{project_ref}/issues:query",
    response_model=ViewQueryResponse,
    summary="Ad-hoc query issues in a project",
)
@router.post(
    "/projects/{project_ref}/issues/query",
    response_model=ViewQueryResponse,
    summary="Ad-hoc query issues in a project (slash alias)",
    include_in_schema=False,
)
async def query_project_issues_adhoc(
    project_ref: str,
    body: AdHocQueryRequest,
    caller: Caller,
    session: Session,
) -> ViewQueryResponse:
    """Execute an ad-hoc query against issues in a project."""
    async with timing_floor(floor_ms=25.0):
        return await svc.query_project_issues_adhoc(session, caller, project_ref, body)
