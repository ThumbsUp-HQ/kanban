# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Project configuration endpoints: workflow states, priorities & labels (KB-P3-01b)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for FastAPI path parameter parsing
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.project_config import (
    LabelCreate,
    LabelPatch,
    LabelResponse,
    PriorityCreate,
    PriorityPatch,
    PriorityResponse,
    StateCreate,
    StatePatch,
    StateResponse,
)
from kanban.services import project_config as svc

router = APIRouter(prefix="/projects/{project_ref}", tags=["project-config"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


# ---------------------------------------------------------------------------
# Workflow States Endpoints
# ---------------------------------------------------------------------------


@router.get("/states", response_model=list[StateResponse], summary="List workflow states")
async def list_states(
    project_ref: str,
    caller: Caller,
    session: Session,
) -> list[StateResponse]:
    """List workflow states ordered by sort_order."""
    async with timing_floor(floor_ms=25.0):
        return await svc.list_states(session, caller, project_ref)


@router.post(
    "/states", status_code=201, response_model=StateResponse, summary="Create a workflow state"
)
async def create_state(
    project_ref: str,
    body: StateCreate,
    caller: Caller,
    session: Session,
    response: Response,
) -> StateResponse:
    """Create a workflow state (project ADMIN only)."""
    async with timing_floor(floor_ms=25.0):
        result = await svc.create_state(session, caller, project_ref, body)
        response.headers["Location"] = f"/api/v1/projects/{project_ref}/states/{result.id}"
        return result


@router.patch("/states/{state_id}", response_model=StateResponse, summary="Update a workflow state")
async def patch_state(
    project_ref: str,
    state_id: uuid.UUID,
    body: StatePatch,
    caller: Caller,
    session: Session,
) -> StateResponse:
    """Update a workflow state (project ADMIN only)."""
    async with timing_floor(floor_ms=25.0):
        return await svc.update_state(session, caller, project_ref, state_id, body)


@router.delete("/states/{state_id}", status_code=204, summary="Delete a workflow state")
async def delete_state(
    project_ref: str,
    state_id: uuid.UUID,
    caller: Caller,
    session: Session,
    migrate_to: Annotated[uuid.UUID | None, Query()] = None,
) -> None:
    """Delete a workflow state, optionally migrating issues (project ADMIN only)."""
    async with timing_floor(floor_ms=25.0):
        await svc.delete_state(session, caller, project_ref, state_id, migrate_to=migrate_to)


# ---------------------------------------------------------------------------
# Project Priorities Endpoints
# ---------------------------------------------------------------------------


@router.get("/priorities", response_model=list[PriorityResponse], summary="List project priorities")
async def list_priorities(
    project_ref: str,
    caller: Caller,
    session: Session,
) -> list[PriorityResponse]:
    """List priorities for a project ordered by sort_order."""
    async with timing_floor(floor_ms=25.0):
        return await svc.list_priorities(session, caller, project_ref)


@router.post(
    "/priorities", status_code=201, response_model=PriorityResponse, summary="Create a priority"
)
async def create_priority(
    project_ref: str,
    body: PriorityCreate,
    caller: Caller,
    session: Session,
    response: Response,
) -> PriorityResponse:
    """Create a custom project priority (project ADMIN only)."""
    async with timing_floor(floor_ms=25.0):
        result = await svc.create_priority(session, caller, project_ref, body)
        response.headers["Location"] = f"/api/v1/projects/{project_ref}/priorities/{result.id}"
        return result


@router.patch(
    "/priorities/{priority_id}", response_model=PriorityResponse, summary="Update a priority"
)
async def patch_priority(
    project_ref: str,
    priority_id: uuid.UUID,
    body: PriorityPatch,
    caller: Caller,
    session: Session,
) -> PriorityResponse:
    """Update mutable priority fields (project ADMIN only)."""
    async with timing_floor(floor_ms=25.0):
        return await svc.update_priority(session, caller, project_ref, priority_id, body)


@router.delete("/priorities/{priority_id}", status_code=204, summary="Delete a priority")
async def delete_priority(
    project_ref: str,
    priority_id: uuid.UUID,
    caller: Caller,
    session: Session,
    migrate_to: Annotated[uuid.UUID | None, Query()] = None,
) -> None:
    """Delete a custom priority, optionally migrating issues (project ADMIN only)."""
    async with timing_floor(floor_ms=25.0):
        await svc.delete_priority(session, caller, project_ref, priority_id, migrate_to=migrate_to)


# ---------------------------------------------------------------------------
# Project Labels Endpoints
# ---------------------------------------------------------------------------


@router.get("/labels", response_model=list[LabelResponse], summary="List project labels")
async def list_labels(
    project_ref: str,
    caller: Caller,
    session: Session,
) -> list[LabelResponse]:
    """List labels for a project ordered by name."""
    async with timing_floor(floor_ms=25.0):
        return await svc.list_labels(session, caller, project_ref)


@router.post("/labels", status_code=201, response_model=LabelResponse, summary="Create a label")
async def create_label(
    project_ref: str,
    body: LabelCreate,
    caller: Caller,
    session: Session,
    response: Response,
) -> LabelResponse:
    """Create a project label (project EDIT or ADMIN allowed)."""
    async with timing_floor(floor_ms=25.0):
        result = await svc.create_label(session, caller, project_ref, body)
        response.headers["Location"] = f"/api/v1/projects/{project_ref}/labels/{result.id}"
        return result


@router.patch("/labels/{label_id}", response_model=LabelResponse, summary="Update a label")
async def patch_label(
    project_ref: str,
    label_id: uuid.UUID,
    body: LabelPatch,
    caller: Caller,
    session: Session,
) -> LabelResponse:
    """Update a project label (project ADMIN only)."""
    async with timing_floor(floor_ms=25.0):
        return await svc.update_label(session, caller, project_ref, label_id, body)


@router.delete("/labels/{label_id}", status_code=204, summary="Delete a label")
async def delete_label(
    project_ref: str,
    label_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> None:
    """Delete a project label and detach from issues (project ADMIN only)."""
    async with timing_floor(floor_ms=25.0):
        await svc.delete_label(session, caller, project_ref, label_id)
