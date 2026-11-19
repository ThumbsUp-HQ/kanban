# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for workflow hook management, reordering, and dry-run (KB-P5-17b)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.services.projects import get_project_or_404
from kanban.workflows.builtins import (
    WasmModuleSummaryResponse,
    ensure_approved_wasm_modules,
)
from kanban.workflows.dry_run import DryRunPayload, DryRunResponse, run_dry_run
from kanban.workflows.hooks_service import (
    TransitionRule,
    WorkflowHookCreateRequest,
    WorkflowHookReorderRequest,
    WorkflowHookResponse,
    WorkflowHookService,
    WorkflowHookUpdateRequest,
)

router = APIRouter(tags=["workflow-hooks"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.get(
    "/projects/{project}/workflow-hooks",
    response_model=list[TransitionRule],
    summary="List workflow hooks for a project grouped by transition",
)
async def list_workflow_hooks(
    project: str,
    caller: Caller,
    session: Session,
) -> list[TransitionRule]:
    """List workflow hooks grouped by (from_state, to_state). S3.4: returns 404 for non-admins."""
    async with timing_floor(floor_ms=25.0):
        return await WorkflowHookService.list_hooks(session, caller, project)


@router.post(
    "/projects/{project}/workflow-hooks",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkflowHookResponse,
    summary="Attach a new workflow hook to a transition",
)
async def create_workflow_hook(
    project: str,
    body: WorkflowHookCreateRequest,
    caller: Caller,
    session: Session,
) -> WorkflowHookResponse:
    """Create and attach a workflow hook. Requires PROJECT_ADMIN and AAL2."""
    async with timing_floor(floor_ms=25.0):
        return await WorkflowHookService.create_hook(session, caller, project, body)


@router.patch(
    "/workflow-hooks/{hook_id}",
    response_model=WorkflowHookResponse,
    summary="Update an existing workflow hook",
)
async def update_workflow_hook(
    hook_id: str,
    body: WorkflowHookUpdateRequest,
    caller: Caller,
    session: Session,
) -> WorkflowHookResponse:
    """Update hook parameters and recompute manifest_sha256. Requires PROJECT_ADMIN and AAL2."""
    async with timing_floor(floor_ms=25.0):
        return await WorkflowHookService.update_hook(session, caller, hook_id, body)


@router.post(
    "/workflow-hooks/{hook_id}/enable",
    response_model=WorkflowHookResponse,
    summary="Enable a workflow hook",
)
async def enable_workflow_hook(
    hook_id: str,
    caller: Caller,
    session: Session,
) -> WorkflowHookResponse:
    """Enable an existing workflow hook to resume intercepting state transitions.

    Requires project admin and AAL2.
    """
    async with timing_floor(floor_ms=25.0):
        return await WorkflowHookService.set_enabled(session, caller, hook_id, is_enabled=True)


@router.post(
    "/workflow-hooks/{hook_id}/disable",
    response_model=WorkflowHookResponse,
    summary="Disable a workflow hook",
)
async def disable_workflow_hook(
    hook_id: str,
    caller: Caller,
    session: Session,
) -> WorkflowHookResponse:
    """Disable an active workflow hook to bypass execution during state transitions.

    Does not detach the hook. Requires project admin and AAL2.
    """
    async with timing_floor(floor_ms=25.0):
        return await WorkflowHookService.set_enabled(session, caller, hook_id, is_enabled=False)


@router.delete(
    "/workflow-hooks/{hook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete/detach a workflow hook",
)
async def delete_workflow_hook(
    hook_id: str,
    caller: Caller,
    session: Session,
) -> Response:
    """Permanently delete and detach a workflow hook from a transition rule.

    Requires project admin and AAL2.
    """
    async with timing_floor(floor_ms=25.0):
        await WorkflowHookService.delete_hook(session, caller, hook_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project}/workflow-hooks/reorder",
    response_model=list[WorkflowHookResponse],
    summary="Atomically reorder workflow hooks for a transition",
)
async def reorder_workflow_hooks(
    project: str,
    body: WorkflowHookReorderRequest,
    caller: Caller,
    session: Session,
) -> list[WorkflowHookResponse]:
    """Atomically rewrite sort_rank for hooks in transition. Requires PROJECT_ADMIN and AAL2."""
    async with timing_floor(floor_ms=25.0):
        return await WorkflowHookService.reorder_hooks(session, caller, project, body)


@router.post(
    "/projects/{project}/workflow-hooks/dry-run",
    response_model=DryRunResponse,
    summary="Dry-run workflow hook pipeline against a sample or existing ticket",
)
async def dry_run_workflow_hooks(
    project: str,
    body: DryRunPayload,
    caller: Caller,
    session: Session,
) -> DryRunResponse:
    """Execute dry-run simulation inside a guaranteed non-persisted SAVEPOINT."""
    async with timing_floor(floor_ms=25.0):
        return await run_dry_run(session, caller, project, body)


@router.get(
    "/projects/{project}/approved-wasm-modules",
    response_model=list[WasmModuleSummaryResponse],
    summary="List approved WebAssembly modules for project/workspace",
)
async def list_approved_wasm_modules(
    project: str,
    caller: Caller,
    session: Session,
) -> list[WasmModuleSummaryResponse]:
    """List approved Wasm modules, seeding verified built-in formulas if needed."""
    async with timing_floor(floor_ms=25.0):
        project_obj = await get_project_or_404(session, caller, project)
        await WorkflowHookService.require_admin(session, caller, project_obj.id)
        return await ensure_approved_wasm_modules(
            session, caller.workspace_id, caller.principal_id, project_id=project_obj.id
        )
