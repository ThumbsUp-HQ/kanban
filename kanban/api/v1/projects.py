"""Project endpoints: CRUD, list and module defaults (S7.2 8c/8f/8p, S3.4)."""

from __future__ import annotations

import uuid  # noqa: TC003  # FastAPI runtime type
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession  # Required by FastAPI at runtime

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.projects import (
    ModuleDefaultsPut,
    ProjectCreate,
    ProjectList,
    ProjectMemberAdd,
    ProjectMemberResponse,
    ProjectPatch,
    ProjectResponse,
)
from kanban.services import projects as svc

router = APIRouter(prefix="/projects", tags=["projects"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.post("", status_code=201, response_model=ProjectResponse, summary="Create a project")
async def create_project(
    body: ProjectCreate, caller: Caller, session: Session, response: Response
) -> ProjectResponse:
    """Create a new project with unique identifier slug and workflow defaults.

    Requires workspace admin or server admin role.
    """
    result = await svc.create_project(session, caller, body)
    response.headers["Location"] = f"/api/v1/projects/{result.identifier}"
    return result


@router.get("", response_model=ProjectList, summary="List readable projects")
async def list_projects(
    caller: Caller,
    session: Session,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ProjectList:
    """List all projects visible to the calling principal under row-level security.

    Uses keyset cursor pagination.
    """
    return await svc.list_projects(session, caller, cursor=cursor, limit=limit)


@router.get("/{project_ref}", response_model=ProjectResponse, summary="Get a project")
async def get_project(project_ref: str, caller: Caller, session: Session) -> ProjectResponse:
    """Return detailed project metadata.

    Returns jitter-equalized 404 response when absent or unreadable to prevent enumeration.
    """
    async with timing_floor(floor_ms=25.0):
        project = await svc.get_project_or_404(session, caller, project_ref)
        return await svc.serialize_project(session, caller, project)


@router.patch("/{project_ref}", response_model=ProjectResponse, summary="Update a project")
async def patch_project(
    project_ref: str, body: ProjectPatch, caller: Caller, session: Session
) -> ProjectResponse:
    """Update mutable project fields such as name and description markdown.

    Requires project ADMIN role.
    """
    async with timing_floor(floor_ms=25.0):
        return await svc.update_project(session, caller, project_ref, body)


@router.put(
    "/{project_ref}/module-defaults",
    response_model=ProjectResponse,
    summary="Replace default modules",
)
async def put_module_defaults(
    project_ref: str, body: ModuleDefaultsPut, caller: Caller, session: Session
) -> ProjectResponse:
    """Replace the project's default module assignment list for newly created issues.

    Requires project ADMIN role.
    """
    async with timing_floor(floor_ms=25.0):
        return await svc.replace_module_defaults(session, caller, project_ref, body.module_ids)


@router.get(
    "/{project_ref}/members",
    response_model=list[ProjectMemberResponse],
    summary="List project members",
)
async def list_project_members(
    project_ref: str, caller: Caller, session: Session
) -> list[ProjectMemberResponse]:
    """List role bindings for principals on this project."""
    async with timing_floor(floor_ms=25.0):
        return await svc.list_project_members(session, caller, project_ref)


@router.post(
    "/{project_ref}/members",
    response_model=ProjectMemberResponse,
    status_code=201,
    summary="Add project member",
)
async def add_project_member(
    project_ref: str, body: ProjectMemberAdd, caller: Caller, session: Session
) -> ProjectMemberResponse:
    """Bind a principal to a project role (PROJECT_ADMIN, MEMBER, VIEWER).

    Requires project ADMIN role.
    """
    async with timing_floor(floor_ms=25.0):
        return await svc.add_project_member(session, caller, project_ref, body)


@router.delete(
    "/{project_ref}/members/{principal_id}",
    status_code=204,
    summary="Remove project member",
)
async def delete_project_member(
    project_ref: str, principal_id: uuid.UUID, caller: Caller, session: Session
) -> Response:
    """Remove a principal role binding from this project.

    Requires project ADMIN role.
    """
    async with timing_floor(floor_ms=25.0):
        await svc.delete_project_member(session, caller, project_ref, principal_id)
        return Response(status_code=204)
