# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Module endpoints: CRUD, issue assignment, and feature flag enforcement (KB-P3-10b)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for FastAPI path parameter parsing
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.modules import (
    IssueModulesUpdate,
    ModuleCreate,
    ModulePatch,
    ModuleResponse,
)
from kanban.services import modules as svc

router = APIRouter(tags=["modules"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.get(
    "/projects/{project_ref}/modules",
    response_model=list[ModuleResponse],
    summary="List modules in a project",
)
async def list_modules(
    project_ref: str,
    caller: Caller,
    session: Session,
) -> list[ModuleResponse]:
    """List modules for a project (VIEW capability required; 404 MODULES_DISABLED if disabled)."""
    async with timing_floor(floor_ms=25.0):
        return await svc.list_modules(session, caller, project_ref)


@router.post(
    "/projects/{project_ref}/modules",
    status_code=201,
    response_model=ModuleResponse,
    summary="Create a module in a project",
)
async def create_module(
    project_ref: str,
    body: ModuleCreate,
    caller: Caller,
    session: Session,
    response: Response,
) -> ModuleResponse:
    """Create a new module within a project (project ADMIN capability required)."""
    async with timing_floor(floor_ms=25.0):
        result = await svc.create_module(session, caller, project_ref, body)
        response.headers["Location"] = f"/api/v1/modules/{result.id}"
        return result


@router.get(
    "/modules/{module_id}",
    response_model=ModuleResponse,
    summary="Get a module by ID",
)
async def get_module(
    module_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> ModuleResponse:
    """Retrieve detailed module metadata and status by unique ID (project VIEW required)."""
    async with timing_floor(floor_ms=25.0):
        return await svc.get_module(session, caller, module_id)


@router.patch(
    "/modules/{module_id}",
    response_model=ModuleResponse,
    summary="Update a module",
)
async def patch_module(
    module_id: uuid.UUID,
    body: ModulePatch,
    caller: Caller,
    session: Session,
) -> ModuleResponse:
    """Update mutable module fields such as name, status, or lead (project ADMIN required)."""
    async with timing_floor(floor_ms=25.0):
        return await svc.patch_module(session, caller, module_id, body)


@router.delete(
    "/modules/{module_id}",
    status_code=204,
    summary="Delete a module",
)
async def delete_module(
    module_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> Response:
    """Delete a module and remove all issue links (project ADMIN required)."""
    async with timing_floor(floor_ms=25.0):
        await svc.delete_module(session, caller, module_id)
        return Response(status_code=204)


@router.put(
    "/issues/{issue_ref}/modules",
    response_model=IssueModulesUpdate,
    summary="Replace issue module assignments",
)
async def put_issue_modules(
    issue_ref: str,
    body: IssueModulesUpdate,
    caller: Caller,
    session: Session,
) -> IssueModulesUpdate:
    """Replace all module assignments on an issue in a single operation (issue EDIT required)."""
    async with timing_floor(floor_ms=25.0):
        updated = await svc.update_issue_modules(session, caller, issue_ref, body.module_ids)
        return IssueModulesUpdate(module_ids=updated)


@router.put(
    "/modules/{module_id}/issues/{issue_ref}",
    status_code=204,
    summary="Add an issue to a module",
)
async def add_issue_to_module(
    module_id: uuid.UUID,
    issue_ref: str,
    caller: Caller,
    session: Session,
) -> Response:
    """Add a single issue to a module assignment link (issue EDIT required)."""
    async with timing_floor(floor_ms=25.0):
        await svc.add_issue_to_module(session, caller, module_id, issue_ref)
        return Response(status_code=204)


@router.delete(
    "/modules/{module_id}/issues/{issue_ref}",
    status_code=204,
    summary="Remove an issue from a module",
)
async def remove_issue_from_module(
    module_id: uuid.UUID,
    issue_ref: str,
    caller: Caller,
    session: Session,
) -> Response:
    """Remove a single issue from a module assignment link (issue EDIT required)."""
    async with timing_floor(floor_ms=25.0):
        await svc.remove_issue_from_module(session, caller, module_id, issue_ref)
        return Response(status_code=204)
