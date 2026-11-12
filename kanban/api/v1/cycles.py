# Copyright 2026 Kanban Platform Contributors
# Licensed under Apache-2.0
"""Cycle management, lifecycle transitions, and burndown endpoints (S7.2 8g, S11.4)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by FastAPI path parameter parsing
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.cycles import (
    BurndownResponse,
    CycleComplete,
    CycleCompleteResponse,
    CycleCreate,
    CyclePatch,
    CycleResponse,
)
from kanban.services import burndown as burndown_svc
from kanban.services import cycles as svc

router = APIRouter(tags=["cycles"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.get(
    "/projects/{project_ref}/cycles",
    response_model=list[CycleResponse],
    summary="List cycles for a project",
)
async def list_cycles(
    project_ref: str,
    caller: Caller,
    session: Session,
    status: Annotated[
        str | None,
        Query(description="Filter by cycle status: upcoming, active, completed"),
    ] = None,
) -> list[CycleResponse]:
    """List cycles belonging to a project, ordered by start date."""
    async with timing_floor(floor_ms=25.0):
        return await svc.list_cycles(session, caller, project_ref, status=status)


@router.post(
    "/projects/{project_ref}/cycles",
    status_code=201,
    response_model=CycleResponse,
    summary="Create a new cycle",
)
async def create_cycle(
    project_ref: str,
    body: CycleCreate,
    caller: Caller,
    session: Session,
    response: Response,
) -> CycleResponse:
    """Create a new cycle in upcoming status (requires project ADMIN)."""
    async with timing_floor(floor_ms=25.0):
        result = await svc.create_cycle(session, caller, project_ref, body)
        response.headers["Location"] = f"/api/v1/cycles/{result.id}"
        return result


@router.get(
    "/cycles/{cycle_id}",
    response_model=CycleResponse,
    summary="Get cycle by UUID",
)
async def get_cycle(
    cycle_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> CycleResponse:
    """Retrieve cycle details and real-time issue counts."""
    async with timing_floor(floor_ms=25.0):
        return await svc.get_cycle(session, caller, cycle_id)


@router.patch(
    "/cycles/{cycle_id}",
    response_model=CycleResponse,
    summary="Update cycle fields",
)
async def patch_cycle(
    cycle_id: uuid.UUID,
    body: CyclePatch,
    caller: Caller,
    session: Session,
) -> CycleResponse:
    """Update name, start_date, or end_date for upcoming or active cycles."""
    async with timing_floor(floor_ms=25.0):
        return await svc.patch_cycle(session, caller, cycle_id, body)


@router.post(
    "/cycles/{cycle_id}/start",
    response_model=CycleResponse,
    summary="Start an upcoming cycle",
)
async def start_cycle(
    cycle_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> CycleResponse:
    """Activate an upcoming cycle, enforcing at most one active cycle per project."""
    async with timing_floor(floor_ms=25.0):
        return await svc.start_cycle(session, caller, cycle_id)


@router.post(
    "/cycles/{cycle_id}/activate",
    response_model=CycleResponse,
    summary="Activate an upcoming cycle (alias)",
)
async def activate_cycle(
    cycle_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> CycleResponse:
    """Activate an upcoming cycle (semantic alias to /start)."""
    async with timing_floor(floor_ms=25.0):
        return await svc.start_cycle(session, caller, cycle_id)


@router.post(
    "/cycles/{cycle_id}/complete",
    response_model=CycleCompleteResponse,
    summary="Complete an active cycle",
)
async def complete_cycle(
    cycle_id: uuid.UUID,
    body: CycleComplete,
    caller: Caller,
    session: Session,
) -> CycleCompleteResponse:
    """Complete an active cycle and optionally roll over unfinished issues."""
    async with timing_floor(floor_ms=25.0):
        return await svc.complete_cycle(session, caller, cycle_id, body)


@router.delete(
    "/cycles/{cycle_id}",
    status_code=204,
    summary="Delete a cycle",
)
async def delete_cycle(
    cycle_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> Response:
    """Delete a non-completed cycle, setting issues.cycle_id to NULL."""
    async with timing_floor(floor_ms=25.0):
        await svc.delete_cycle(session, caller, cycle_id)
        return Response(status_code=204)


@router.put(
    "/cycles/{cycle_id}/issues/{issue_ref}",
    summary="Add an issue to a cycle",
)
async def add_issue_to_cycle(
    cycle_id: uuid.UUID,
    issue_ref: str,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Assign an issue to a cycle, enforcing at-most-one active/upcoming cycle constraint."""
    async with timing_floor(floor_ms=25.0):
        await svc.add_issue_to_cycle(session, caller, cycle_id, issue_ref)
        return {"status": "ok", "cycle_id": str(cycle_id), "issue_ref": issue_ref}


@router.delete(
    "/cycles/{cycle_id}/issues/{issue_ref}",
    status_code=204,
    summary="Remove an issue from a cycle",
)
async def remove_issue_from_cycle(
    cycle_id: uuid.UUID,
    issue_ref: str,
    caller: Caller,
    session: Session,
) -> Response:
    """Remove an issue from a cycle, clearing cycle_id."""
    async with timing_floor(floor_ms=25.0):
        await svc.remove_issue_from_cycle(session, caller, cycle_id, issue_ref)
        return Response(status_code=204)


@router.get(
    "/cycles/{cycle_id}/burndown",
    response_model=BurndownResponse,
    summary="Get cycle burndown metrics",
)
async def get_burndown(
    cycle_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> BurndownResponse:
    """Retrieve daily burndown scope and remaining points replaying historical activity."""
    async with timing_floor(floor_ms=25.0):
        return await burndown_svc.compute_burndown(session, caller, cycle_id)
