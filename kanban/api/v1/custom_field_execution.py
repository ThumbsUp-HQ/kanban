# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for custom field execution and Wasm module registration (KB-P5-13, S13.3)."""

from __future__ import annotations

import base64
import hashlib
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.wasm_module import ApprovedWasmModule
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.custom_fields import (
    CustomFieldValueItem,
    WasmModuleResponse,
    WasmModuleUploadRequest,
)
from kanban.custom_fields.executor import CustomFieldExecutor
from kanban.custom_fields.service import CustomFieldDefinitionService
from kanban.sandbox.wasm_runner import TierAWasmRunner, WasmRunError
from kanban.security.ratelimit.base import RateLimitPolicy
from kanban.security.ratelimit.pg import PgRateLimiter
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.issue_keys import resolve_issue_ref
from kanban.services.projects import get_project_or_404

router = APIRouter(tags=["custom-field-execution"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.get(
    "/issues/{issue_key}/custom-fields",
    response_model=list[CustomFieldValueItem],
    summary="List computed and cached custom field values for an issue",
)
async def list_custom_fields_for_issue(
    issue_key: str,
    request: Request,
    caller: Caller,
    session: Session,
) -> list[CustomFieldValueItem]:
    """Retrieve all custom field values for an issue.

    When X-Kanban-Script-Depth >= 1 (or request.state.script_depth >= 1),
    serves cached rows only and avoids recursive execution.
    """
    script_depth = getattr(request.state, "script_depth", 0)
    if script_depth == 0:
        header_depth = request.headers.get("x-kanban-script-depth", "0")
        if header_depth.isdigit():
            script_depth = int(header_depth)

    cached_only = script_depth >= 1
    async with timing_floor(floor_ms=25.0):
        executor = CustomFieldExecutor(session)
        results = await executor.list_values_for_issue(
            session, caller, issue_key, cached_only=cached_only
        )
        return [CustomFieldValueItem.model_validate(r) for r in results]


@router.post(
    "/issues/{issue_key}/custom-fields/{field_id}/execute",
    response_model=CustomFieldValueItem,
    summary="Force fresh execution of a custom field for an issue",
)
async def execute_custom_field_for_issue(
    issue_key: str,
    field_id: str,
    caller: Caller,
    session: Session,
    *,
    force_refresh: bool = True,
) -> CustomFieldValueItem:
    """Force fresh execution of a custom field.

    Bypasses cache and records server audit if escalated.
    Rate limited to 6 requests/minute per (principal, issue, field).
    """
    async with timing_floor(floor_ms=25.0):
        # Resolve issue under caller's RLS session
        issue = await resolve_issue_ref(session, caller, issue_key)

        if force_refresh:
            rate_limiter = PgRateLimiter(session=session)
            policy = RateLimitPolicy(name="custom_field_execute", limit=6, window_seconds=60)
            key = hashlib.sha256(f"{caller.principal_id}:{issue.id}:{field_id}".encode()).digest()
            decision = await rate_limiter.hit(policy, key)
            if not decision.allowed:
                raise ProblemException(
                    status=429,
                    code="RATE_LIMITED",
                    title="Rate Limited",
                    detail=(
                        f"Execution rate limit exceeded. "
                        f"Retry after {decision.retry_after_seconds}s."
                    ),
                )

        executor = CustomFieldExecutor(session)
        result = await executor.execute_for_issue(
            session,
            caller,
            issue_key,
            field_id,
            force_refresh=force_refresh,
        )
        return CustomFieldValueItem.model_validate(result)


@router.post(
    "/projects/{project}/wasm-modules",
    status_code=status.HTTP_201_CREATED,
    response_model=WasmModuleResponse,
    summary="Upload and validate a WebAssembly module artifact",
)
async def upload_wasm_module(
    project: str,
    body: WasmModuleUploadRequest,
    caller: Caller,
    session: Session,
) -> WasmModuleResponse:
    """Upload, validate, and register a compiled WebAssembly module.

    Admin role and AAL2 required.
    """
    async with timing_floor(floor_ms=25.0):
        proj = await get_project_or_404(session, caller, project)
        await CustomFieldDefinitionService.require_admin_and_aal2(session, caller, proj)

        try:
            wasm_bytes = base64.b64decode(body.wasm_base64, validate=True)
        except Exception as ex:
            raise ProblemException(
                status=422,
                code="WASM_BINARY_INVALID",
                title="Invalid Base64 Encoding",
                detail="Invalid base64 payload",
            ) from ex

        runner = TierAWasmRunner.get_instance()
        try:
            sha256_digest = runner.validate_module(wasm_bytes)
        except WasmRunError as ex:
            raise ProblemException(
                status=422,
                code=ex.code,
                title=ex.code.replace("_", " ").title(),
                detail=ex.message,
            ) from ex

        # Persist into approved_wasm_modules if not already existing
        stmt = select(ApprovedWasmModule).where(
            ApprovedWasmModule.workspace_id == caller.workspace_id,
            ApprovedWasmModule.sha256 == sha256_digest,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing is None:
            mod = ApprovedWasmModule(
                id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
                workspace_id=caller.workspace_id,
                project_id=proj.id,
                sha256=sha256_digest,
                name=body.name,
                wasm_bytes=wasm_bytes,
                approved_by_id=caller.principal_id,
            )
            session.add(mod)
            await session.flush()

            await record_activity(
                session=session,
                workspace_id=caller.workspace_id,
                object_id=proj.id,
                actor_principal_id=caller.principal_id,
                event_type=ActivityEventType.WASM_MODULE_UPLOADED,
                payload={
                    "sha256": sha256_digest.hex(),
                    "name": body.name,
                    "size_bytes": len(wasm_bytes),
                },
            )

        return WasmModuleResponse(
            sha256=sha256_digest.hex(),
            name=body.name,
            size_bytes=len(wasm_bytes),
        )
