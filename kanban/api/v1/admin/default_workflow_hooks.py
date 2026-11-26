# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: C901, PLR0912, TC003, FBT002
"""REST API router for default workflow hook templates administration and workspace management."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.agent_definition import AgentDefinition
from database.models.spine import Workspace
from database.models.wasm_module import ApprovedWasmModule
from database.models.workflow import DefaultWorkflowHook
from kanban.agents.cli_policy import CliPolicyError, assert_runtime_argv
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException, not_found
from kanban.api.timing import timing_floor
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.workflows.builtins import BUILTIN_WASM_FORMULAS, seed_builtin_wasm
from kanban.workflows.hooks_service import _parse_sha256_hex, _validate_mutable_fields

logger = logging.getLogger(__name__)

ScopeKind = Literal["system", "workspace"]
FailurePolicy = Literal["fail_closed", "fail_open_warn"]


class DefaultWorkflowHookCreateRequest(BaseModel):
    """Payload for creating a default workflow hook template."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120, description="Unique template name")
    scope_kind: ScopeKind = Field(description="Scope kind: system or workspace")
    workspace_id: uuid.UUID | None = Field(
        default=None, description="Workspace ID (required for workspace scope, null for system)"
    )
    from_state_name: str | None = Field(
        default=None,
        max_length=80,
        description="Source state name, or null/'*' for Any State wildcard",
    )
    to_state_name: str = Field(
        min_length=1, max_length=80, description="Target state name (e.g. Done)"
    )
    hook_kind: str = Field(
        default="agent_async",
        description="Hook kind: agent_async, wasm_sync, builtin (or agent_interceptor)",
    )
    sort_rank: int = Field(default=100, ge=0, description="Sort rank ordering (>= 0)")
    is_enabled: bool = Field(default=True, description="Whether template is enabled")
    wasm_module_sha256: str | None = Field(
        default=None, description="Hex SHA-256 of approved WASM module"
    )
    agent: str | None = Field(
        default=None, description="Agent definition UUID or slug (e.g. @reality-checker)"
    )
    agent_definition_id: uuid.UUID | None = Field(default=None, description="Agent definition UUID")
    agent_slug: str | None = Field(default=None, max_length=80, description="Agent slug")
    allowed_mutable_fields: list[str] = Field(
        default_factory=list, description="Fields this hook is permitted to modify"
    )
    failure_policy: FailurePolicy = Field(
        default="fail_closed", description="Failure policy: fail_closed or fail_open_warn"
    )
    timeout_ms: int | None = Field(
        default=None, ge=1000, le=600000, description="Optional timeout in ms (1000..600000)"
    )
    max_rework_attempts: int = Field(
        default=3, ge=1, le=20, description="Maximum rework attempts (1..20)"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate template name is not empty or whitespace only."""
        clean = v.strip()
        if not clean:
            msg = "Template name cannot be empty or whitespace only"
            raise ValueError(msg)
        return clean

    @field_validator("to_state_name")
    @classmethod
    def validate_to_state(cls, v: str) -> str:
        """Validate target state name is not empty or whitespace only."""
        clean = v.strip()
        if not clean:
            msg = "Target state name cannot be empty or whitespace only"
            raise ValueError(msg)
        return clean

    @field_validator("from_state_name")
    @classmethod
    def validate_from_state(cls, v: str | None) -> str | None:
        """Normalize from_state_name wildcard or whitespace to None."""
        if v is None:
            return None
        clean = v.strip()
        if not clean or clean == "*":
            return None
        return clean


class DefaultWorkflowHookUpdateRequest(BaseModel):
    """Payload for updating an existing default workflow hook template."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    from_state_name: str | None = Field(default=None, max_length=80)
    to_state_name: str | None = Field(default=None, min_length=1, max_length=80)
    hook_kind: str | None = Field(default=None)
    sort_rank: int | None = Field(default=None, ge=0)
    is_enabled: bool | None = Field(default=None)
    wasm_module_sha256: str | None = Field(default=None)
    agent: str | None = Field(default=None)
    agent_definition_id: uuid.UUID | None = Field(default=None)
    agent_slug: str | None = Field(default=None, max_length=80)
    allowed_mutable_fields: list[str] | None = Field(default=None)
    failure_policy: FailurePolicy | None = Field(default=None)
    timeout_ms: int | None = Field(default=None, ge=1000, le=600000)
    max_rework_attempts: int | None = Field(default=None, ge=1, le=20)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        """Validate template name is not empty or whitespace only."""
        if v is None:
            return None
        clean = v.strip()
        if not clean:
            msg = "Template name cannot be empty or whitespace only"
            raise ValueError(msg)
        return clean

    @field_validator("to_state_name")
    @classmethod
    def validate_to_state(cls, v: str | None) -> str | None:
        """Validate target state name is not empty or whitespace only."""
        if v is None:
            return None
        clean = v.strip()
        if not clean:
            msg = "Target state name cannot be empty or whitespace only"
            raise ValueError(msg)
        return clean

    @field_validator("from_state_name")
    @classmethod
    def validate_from_state(cls, v: str | None) -> str | None:
        """Normalize from_state_name wildcard or whitespace to None."""
        if v is None:
            return None
        clean = v.strip()
        if not clean or clean == "*":
            return None
        return clean


class DefaultWorkflowHookResponse(BaseModel):
    """Serialized representation of a default workflow hook template."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    scope_kind: ScopeKind
    workspace_id: uuid.UUID | None = None
    name: str
    from_state_name: str | None = None
    to_state_name: str
    hook_kind: str
    sort_rank: int
    is_enabled: bool
    wasm_module_sha256: str | None = None
    agent_definition_id: uuid.UUID | None = None
    agent_slug: str | None = None
    allowed_mutable_fields: list[str]
    failure_policy: str
    timeout_ms: int | None = None
    max_rework_attempts: int
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


def _normalize_hook_kind(raw: str) -> str:
    cleaned = raw.strip().lower()
    if cleaned in ("agent_async", "agent_interceptor"):
        return "agent_async"
    if cleaned in ("wasm_sync", "wasm_validator", "sync_validator", "sync_mutator"):
        return "wasm_sync"
    if cleaned == "builtin":
        return "builtin"
    raise ProblemException(
        code="INVALID_HOOK_KIND",
        status=422,
        title="Invalid Hook Kind",
        detail=f"Unsupported hook_kind '{raw}'. Must be agent_async, wasm_sync, or builtin.",
    )


def _serialize_template(t: DefaultWorkflowHook) -> DefaultWorkflowHookResponse:
    wasm_hex = t.wasm_module_sha256.hex() if t.wasm_module_sha256 else None
    fields = list(t.allowed_mutable_fields)
    return DefaultWorkflowHookResponse(
        id=t.id,
        scope_kind="system" if t.scope_kind == "system" else "workspace",
        workspace_id=t.workspace_id,
        name=t.name,
        from_state_name=t.from_state_name,
        to_state_name=t.to_state_name,
        hook_kind=t.hook_kind,
        sort_rank=t.sort_rank,
        is_enabled=t.is_enabled,
        wasm_module_sha256=wasm_hex,
        agent_definition_id=t.agent_definition_id,
        agent_slug=t.agent_slug,
        allowed_mutable_fields=fields,
        failure_policy=t.failure_policy,
        timeout_ms=t.timeout_ms,
        max_rework_attempts=t.max_rework_attempts,
        created_by=t.created_by,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


async def _get_admin_roles(session: AsyncSession) -> tuple[bool, bool]:
    is_server_admin = bool(
        (
            await session.execute(
                text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
            )
        ).scalar_one()
    )
    is_ws_admin = bool(
        (
            await session.execute(
                text(
                    "SELECT app_principal_has_role(NULL, ARRAY['WORKSPACE_ADMIN', 'SERVER_ADMIN'])"
                )
            )
        ).scalar_one()
    )
    return is_server_admin, is_ws_admin


async def _assert_unique_name(
    session: AsyncSession,
    scope_kind: str,
    workspace_id: uuid.UUID | None,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> None:
    stmt = select(DefaultWorkflowHook.id).where(
        DefaultWorkflowHook.scope_kind == scope_kind,
        DefaultWorkflowHook.workspace_id == workspace_id,
        func.lower(DefaultWorkflowHook.name) == name.strip().lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(DefaultWorkflowHook.id != exclude_id)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise ProblemException(
            code="TEMPLATE_NAME_CONFLICT",
            status=409,
            title="Template Name Conflict",
            detail=(
                f"A default workflow hook template with name '{name.strip()}' "
                "already exists in this scope."
            ),
        )


async def _validate_wasm_sha(
    session: AsyncSession,
    wasm_hex: str | None,
    scope_kind: str,
    workspace_id: uuid.UUID | None,
    caller_principal_id: uuid.UUID,
) -> bytes | None:
    if not wasm_hex:
        return None
    raw_hex = wasm_hex.strip()
    if raw_hex.lower().startswith("0x"):
        raw_hex = raw_hex[2:]
    wasm_bytes = _parse_sha256_hex(raw_hex)

    if scope_kind == "workspace" and workspace_id is not None:
        stmt = select(ApprovedWasmModule).where(
            ApprovedWasmModule.workspace_id == workspace_id,
            ApprovedWasmModule.sha256 == wasm_bytes,
        )
        approved = (await session.execute(stmt)).scalar_one_or_none()
        if approved is None:
            approved = await seed_builtin_wasm(
                session, workspace_id, caller_principal_id, wasm_bytes
            )
        if approved is None:
            raise ProblemException(
                code="WASM_MODULE_NOT_APPROVED",
                status=422,
                title="WASM Module Not Approved",
                detail="WASM module SHA-256 is not approved in this workspace.",
            )
    elif scope_kind == "system":
        is_builtin = any(b.sha256_bytes == wasm_bytes for b in BUILTIN_WASM_FORMULAS)
        if not is_builtin:
            sys_stmt = select(ApprovedWasmModule.id).where(ApprovedWasmModule.sha256 == wasm_bytes)
            if (await session.execute(sys_stmt)).scalar_one_or_none() is None:
                raise ProblemException(
                    code="WASM_MODULE_NOT_APPROVED",
                    status=422,
                    title="WASM Module Not Approved",
                    detail="WASM module SHA-256 is not approved.",
                )
    return wasm_bytes


router = APIRouter(
    prefix="/admin/default-workflow-hooks",
    tags=["admin-default-workflow-hooks"],
    dependencies=[Depends(require_admin_aal2)],
)

workspace_router = APIRouter(
    prefix="/workspaces/{workspace}/default-workflow-hooks",
    tags=["workspace-default-workflow-hooks"],
    dependencies=[Depends(require_admin_aal2)],
)

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.get(
    "",
    response_model=list[DefaultWorkflowHookResponse],
    summary="List default workflow hook templates",
)
async def admin_list_default_hooks(
    caller: Caller,
    session: Session,
    scope_kind: Annotated[ScopeKind | None, Query()] = None,
    workspace_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[DefaultWorkflowHookResponse]:
    """List default workflow hook templates. Requires admin role and AAL2."""
    del caller
    async with timing_floor(floor_ms=25.0):
        is_server_admin, is_ws_admin = await _get_admin_roles(session)
        if not (is_server_admin or is_ws_admin):
            raise ProblemException(
                code="INSUFFICIENT_CAPABILITY",
                status=403,
                title="Insufficient Capability",
                detail="Administrative role required.",
            )

        stmt = select(DefaultWorkflowHook)
        if scope_kind is not None:
            stmt = stmt.where(DefaultWorkflowHook.scope_kind == scope_kind)
        if workspace_id is not None:
            stmt = stmt.where(DefaultWorkflowHook.workspace_id == workspace_id)

        stmt = stmt.order_by(
            DefaultWorkflowHook.sort_rank.asc(), DefaultWorkflowHook.created_at.asc()
        )
        rows = list((await session.execute(stmt)).scalars().all())
        return [_serialize_template(r) for r in rows]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DefaultWorkflowHookResponse,
    summary="Create a default workflow hook template",
)
async def admin_create_default_hook(  # noqa: PLR0915
    body: DefaultWorkflowHookCreateRequest,
    caller: Caller,
    session: Session,
) -> DefaultWorkflowHookResponse:
    """Create a new default workflow hook template.

    Requires SERVER_ADMIN for system, WORKSPACE_ADMIN for workspace.
    """
    async with timing_floor(floor_ms=25.0):
        is_server_admin, is_ws_admin = await _get_admin_roles(session)

        clean_name = body.name.strip()
        clean_to_state = body.to_state_name.strip()
        clean_from_state = (
            None
            if body.from_state_name is None or body.from_state_name.strip() in ("", "*")
            else body.from_state_name.strip()
        )
        hook_kind = _normalize_hook_kind(body.hook_kind)
        clean_fields = _validate_mutable_fields(body.allowed_mutable_fields)

        agent_def_id: uuid.UUID | None = None
        agent_slug: str | None = None

        if body.scope_kind == "system":
            if not is_server_admin:
                raise ProblemException(
                    code="INSUFFICIENT_CAPABILITY",
                    status=403,
                    title="Insufficient Capability",
                    detail="Operation requires SERVER_ADMIN role.",
                )
            if body.workspace_id is not None:
                raise ProblemException(
                    code="INVALID_TEMPLATE_SCOPE",
                    status=422,
                    title="Invalid Template Scope",
                    detail="System templates must have workspace_id set to null.",
                )
            if body.agent_definition_id is not None:
                raise ProblemException(
                    code="SYSTEM_TEMPLATE_REQUIRES_AGENT_SLUG",
                    status=422,
                    title="System Template Requires Agent Slug",
                    detail=(
                        "System templates must not specify an agent_definition_id; "
                        "use agent_slug instead to prevent cross-tenant leakage."
                    ),
                )
            if body.agent is not None:
                raw_agent = body.agent.strip()
                try:
                    uuid.UUID(raw_agent)
                    raise ProblemException(
                        code="SYSTEM_TEMPLATE_REQUIRES_AGENT_SLUG",
                        status=422,
                        title="System Template Requires Agent Slug",
                        detail=(
                            "System templates must specify an agent slug (e.g. '@reality-checker') "
                            "instead of a UUID."
                        ),
                    )
                except ValueError:
                    agent_slug = raw_agent.lstrip("@")
            elif body.agent_slug is not None:
                agent_slug = body.agent_slug.strip().lstrip("@")
            agent_def_id = None
        else:
            # Workspace scope
            target_ws_id = body.workspace_id or caller.workspace_id
            if target_ws_id != caller.workspace_id and not is_server_admin:
                raise ProblemException(
                    code="CROSS_WORKSPACE_FORBIDDEN",
                    status=403,
                    title="Cross Workspace Forbidden",
                    detail="Access to target workspace forbidden.",
                )
            if not (is_server_admin or is_ws_admin):
                raise ProblemException(
                    code="INSUFFICIENT_CAPABILITY",
                    status=403,
                    title="Insufficient Capability",
                    detail="Operation requires WORKSPACE_ADMIN or SERVER_ADMIN role.",
                )
            body.workspace_id = target_ws_id

            agent_def_id = body.agent_definition_id
            agent_slug = body.agent_slug.strip().lstrip("@") if body.agent_slug else None

            if body.agent is not None:
                raw_agent = body.agent.strip()
                try:
                    agent_def_id = uuid.UUID(raw_agent)
                except ValueError:
                    agent_slug = raw_agent.lstrip("@")
                    ad_stmt = select(AgentDefinition).where(
                        AgentDefinition.workspace_id == target_ws_id,
                        AgentDefinition.slug == agent_slug,
                    )
                    ad_row = (await session.execute(ad_stmt)).scalar_one_or_none()
                    if ad_row is not None:
                        agent_def_id = ad_row.id

            if agent_def_id is not None:
                ad_stmt = select(AgentDefinition).where(
                    AgentDefinition.id == agent_def_id,
                    AgentDefinition.workspace_id == target_ws_id,
                )
                agent_row = (await session.execute(ad_stmt)).scalar_one_or_none()
                if agent_row is None:
                    raise ProblemException(
                        code="AGENT_NOT_FOUND",
                        status=422,
                        title="Agent Not Found",
                        detail=f"Agent definition '{agent_def_id}' not found in target workspace.",
                    )
                if agent_row.slug and not agent_slug:
                    agent_slug = agent_row.slug
                if agent_row.harness_kind == "cli_pipe":
                    try:
                        assert_runtime_argv(agent_row)
                    except CliPolicyError as exc:
                        raise ProblemException(
                            code="CLI_POLICY_VIOLATION",
                            status=422,
                            title="CLI Policy Violation",
                            detail=exc.detail,
                        ) from exc

        await _assert_unique_name(session, body.scope_kind, body.workspace_id, clean_name)

        wasm_bytes = await _validate_wasm_sha(
            session,
            body.wasm_module_sha256,
            body.scope_kind,
            body.workspace_id,
            caller.principal_id,
        )

        template = DefaultWorkflowHook(
            scope_kind=body.scope_kind,
            workspace_id=body.workspace_id,
            name=clean_name,
            from_state_name=clean_from_state,
            to_state_name=clean_to_state,
            hook_kind=hook_kind,
            sort_rank=body.sort_rank,
            is_enabled=body.is_enabled,
            wasm_module_sha256=wasm_bytes,
            agent_definition_id=agent_def_id,
            agent_slug=agent_slug,
            allowed_mutable_fields=clean_fields,
            failure_policy=body.failure_policy,
            timeout_ms=body.timeout_ms,
            max_rework_attempts=body.max_rework_attempts,
            created_by=caller.principal_id,
        )
        session.add(template)
        await session.flush()
        await session.commit()
        return _serialize_template(template)


@router.patch(
    "/{template_id}",
    response_model=DefaultWorkflowHookResponse,
    summary="Update a default workflow hook template",
)
async def admin_update_default_hook(  # noqa: PLR0915
    template_id: uuid.UUID,
    body: DefaultWorkflowHookUpdateRequest,
    caller: Caller,
    session: Session,
) -> DefaultWorkflowHookResponse:
    """Update an existing default workflow hook template.

    Requires appropriate admin role and AAL2.
    """
    async with timing_floor(floor_ms=25.0):
        template = await session.get(DefaultWorkflowHook, template_id)
        if template is None:
            not_found()

        is_server_admin, is_ws_admin = await _get_admin_roles(session)
        if template.scope_kind == "system":
            if not is_server_admin:
                raise ProblemException(
                    code="INSUFFICIENT_CAPABILITY",
                    status=403,
                    title="Insufficient Capability",
                    detail="Operation requires SERVER_ADMIN role.",
                )
        else:
            if template.workspace_id != caller.workspace_id and not is_server_admin:
                raise ProblemException(
                    code="CROSS_WORKSPACE_FORBIDDEN",
                    status=403,
                    title="Cross Workspace Forbidden",
                    detail="Access to target workspace forbidden.",
                )
            if not (is_server_admin or is_ws_admin):
                raise ProblemException(
                    code="INSUFFICIENT_CAPABILITY",
                    status=403,
                    title="Insufficient Capability",
                    detail="Operation requires WORKSPACE_ADMIN or SERVER_ADMIN role.",
                )

        if body.name is not None:
            clean_name = body.name.strip()
            await _assert_unique_name(
                session,
                template.scope_kind,
                template.workspace_id,
                clean_name,
                exclude_id=template.id,
            )
            template.name = clean_name

        if "from_state_name" in body.model_fields_set:
            template.from_state_name = (
                None
                if body.from_state_name is None or body.from_state_name.strip() in ("", "*")
                else body.from_state_name.strip()
            )
        if body.to_state_name is not None:
            template.to_state_name = body.to_state_name.strip()
        if body.hook_kind is not None:
            template.hook_kind = _normalize_hook_kind(body.hook_kind)
        if body.sort_rank is not None:
            template.sort_rank = body.sort_rank
        if body.is_enabled is not None:
            template.is_enabled = body.is_enabled

        if "wasm_module_sha256" in body.model_fields_set:
            template.wasm_module_sha256 = await _validate_wasm_sha(
                session,
                body.wasm_module_sha256,
                template.scope_kind,
                template.workspace_id,
                caller.principal_id,
            )

        if template.scope_kind == "system":
            if body.agent_definition_id is not None:
                raise ProblemException(
                    code="SYSTEM_TEMPLATE_REQUIRES_AGENT_SLUG",
                    status=422,
                    title="System Template Requires Agent Slug",
                    detail=(
                        "System templates must not specify an agent_definition_id; "
                        "use agent_slug instead."
                    ),
                )
            if body.agent is not None:
                raw_agent = body.agent.strip()
                try:
                    uuid.UUID(raw_agent)
                    raise ProblemException(
                        code="SYSTEM_TEMPLATE_REQUIRES_AGENT_SLUG",
                        status=422,
                        title="System Template Requires Agent Slug",
                        detail=(
                            "System templates must specify an agent slug (e.g. '@reality-checker') "
                            "instead of a UUID."
                        ),
                    )
                except ValueError:
                    template.agent_slug = raw_agent.lstrip("@")
                    template.agent_definition_id = None
            elif "agent_slug" in body.model_fields_set:
                template.agent_slug = (
                    body.agent_slug.strip().lstrip("@") if body.agent_slug else None
                )
                template.agent_definition_id = None
        else:  # noqa: PLR5501
            # Workspace template agent handling
            if body.agent is not None:
                raw_agent = body.agent.strip()
                try:
                    agent_u = uuid.UUID(raw_agent)
                    stmt = select(AgentDefinition).where(
                        AgentDefinition.id == agent_u,
                        AgentDefinition.workspace_id == template.workspace_id,
                    )
                    ad_row = (await session.execute(stmt)).scalar_one_or_none()
                    if ad_row is None:
                        raise ProblemException(
                            code="AGENT_NOT_FOUND",
                            status=422,
                            title="Agent Not Found",
                            detail=f"Agent definition '{agent_u}' not found in workspace.",
                        )
                    template.agent_definition_id = ad_row.id
                    template.agent_slug = ad_row.slug
                    if ad_row.harness_kind == "cli_pipe":
                        try:
                            assert_runtime_argv(ad_row)
                        except CliPolicyError as exc:
                            raise ProblemException(
                                code="CLI_POLICY_VIOLATION",
                                status=422,
                                title="CLI Policy Violation",
                                detail=exc.detail,
                            ) from exc
                except ValueError:
                    clean_slug = raw_agent.lstrip("@")
                    template.agent_slug = clean_slug
                    stmt = select(AgentDefinition).where(
                        AgentDefinition.workspace_id == template.workspace_id,
                        AgentDefinition.slug == clean_slug,
                    )
                    ad_row = (await session.execute(stmt)).scalar_one_or_none()
                    template.agent_definition_id = ad_row.id if ad_row is not None else None
                    if ad_row is not None and ad_row.harness_kind == "cli_pipe":
                        try:
                            assert_runtime_argv(ad_row)
                        except CliPolicyError as exc:
                            raise ProblemException(
                                code="CLI_POLICY_VIOLATION",
                                status=422,
                                title="CLI Policy Violation",
                                detail=exc.detail,
                            ) from exc
            elif "agent_definition_id" in body.model_fields_set:
                if body.agent_definition_id is not None:
                    stmt = select(AgentDefinition).where(
                        AgentDefinition.id == body.agent_definition_id,
                        AgentDefinition.workspace_id == template.workspace_id,
                    )
                    ad_row = (await session.execute(stmt)).scalar_one_or_none()
                    if ad_row is None:
                        raise ProblemException(
                            code="AGENT_NOT_FOUND",
                            status=422,
                            title="Agent Not Found",
                            detail=(
                                f"Agent definition '{body.agent_definition_id}' "
                                "not found in workspace."
                            ),
                        )
                    template.agent_definition_id = ad_row.id
                    template.agent_slug = ad_row.slug
                    if ad_row.harness_kind == "cli_pipe":
                        try:
                            assert_runtime_argv(ad_row)
                        except CliPolicyError as exc:
                            raise ProblemException(
                                code="CLI_POLICY_VIOLATION",
                                status=422,
                                title="CLI Policy Violation",
                                detail=exc.detail,
                            ) from exc
                else:
                    template.agent_definition_id = None
            elif "agent_slug" in body.model_fields_set:
                updated_slug = body.agent_slug.strip().lstrip("@") if body.agent_slug else None
                template.agent_slug = updated_slug
                if updated_slug:
                    stmt = select(AgentDefinition).where(
                        AgentDefinition.workspace_id == template.workspace_id,
                        AgentDefinition.slug == updated_slug,
                    )
                    ad_row = (await session.execute(stmt)).scalar_one_or_none()
                    template.agent_definition_id = ad_row.id if ad_row is not None else None
                else:
                    template.agent_definition_id = None

        if body.allowed_mutable_fields is not None:
            template.allowed_mutable_fields = _validate_mutable_fields(body.allowed_mutable_fields)
        if body.failure_policy is not None:
            template.failure_policy = body.failure_policy
        if "timeout_ms" in body.model_fields_set:
            template.timeout_ms = body.timeout_ms
        if body.max_rework_attempts is not None:
            template.max_rework_attempts = body.max_rework_attempts

        await session.flush()
        await session.commit()
        return _serialize_template(template)


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a default workflow hook template",
)
async def admin_delete_default_hook(
    template_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> Response:
    """Delete a default workflow hook template. Requires appropriate admin role and AAL2."""
    async with timing_floor(floor_ms=25.0):
        template = await session.get(DefaultWorkflowHook, template_id)
        if template is None:
            not_found()

        is_server_admin, is_ws_admin = await _get_admin_roles(session)
        if template.scope_kind == "system":
            if not is_server_admin:
                raise ProblemException(
                    code="INSUFFICIENT_CAPABILITY",
                    status=403,
                    title="Insufficient Capability",
                    detail="Operation requires SERVER_ADMIN role.",
                )
        else:
            if template.workspace_id != caller.workspace_id and not is_server_admin:
                raise ProblemException(
                    code="CROSS_WORKSPACE_FORBIDDEN",
                    status=403,
                    title="Cross Workspace Forbidden",
                    detail="Access to target workspace forbidden.",
                )
            if not (is_server_admin or is_ws_admin):
                raise ProblemException(
                    code="INSUFFICIENT_CAPABILITY",
                    status=403,
                    title="Insufficient Capability",
                    detail="Operation requires WORKSPACE_ADMIN or SERVER_ADMIN role.",
                )

        await session.delete(template)
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Workspace-scoped convenience endpoints
# =============================================================================


async def _resolve_workspace_id(
    session: AsyncSession, caller: PrincipalContext, workspace_ref: str
) -> uuid.UUID:
    if workspace_ref in ("current", "@current"):
        return caller.workspace_id
    try:
        ws_id = uuid.UUID(workspace_ref)
        if ws_id == caller.workspace_id:
            return ws_id
    except ValueError:
        pass
    stmt = select(Workspace.id).where(
        (Workspace.id == caller.workspace_id) & (Workspace.slug == workspace_ref)
    )
    found = (await session.execute(stmt)).scalar_one_or_none()
    if found is not None:
        return found
    raise not_found()


@workspace_router.get(
    "",
    response_model=list[DefaultWorkflowHookResponse],
    summary="List default workflow hook templates for workspace",
)
async def workspace_list_default_hooks(
    workspace: str,
    caller: Caller,
    session: Session,
    include_system: Annotated[bool, Query()] = True,
) -> list[DefaultWorkflowHookResponse]:
    """List default workflow hook templates for workspace."""
    async with timing_floor(floor_ms=25.0):
        ws_id = await _resolve_workspace_id(session, caller, workspace)
        is_server_admin, is_ws_admin = await _get_admin_roles(session)
        if not (is_server_admin or is_ws_admin):
            raise ProblemException(
                code="INSUFFICIENT_CAPABILITY",
                status=403,
                title="Insufficient Capability",
                detail="Workspace admin role required.",
            )

        stmt = select(DefaultWorkflowHook)
        if include_system:
            stmt = stmt.where(
                (DefaultWorkflowHook.scope_kind == "system")
                | (
                    (DefaultWorkflowHook.scope_kind == "workspace")
                    & (DefaultWorkflowHook.workspace_id == ws_id)
                )
            )
        else:
            stmt = stmt.where(
                (DefaultWorkflowHook.scope_kind == "workspace")
                & (DefaultWorkflowHook.workspace_id == ws_id)
            )

        stmt = stmt.order_by(
            DefaultWorkflowHook.sort_rank.asc(), DefaultWorkflowHook.created_at.asc()
        )
        rows = list((await session.execute(stmt)).scalars().all())
        return [_serialize_template(r) for r in rows]


@workspace_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DefaultWorkflowHookResponse,
    summary="Create a default workflow hook template for workspace",
)
async def workspace_create_default_hook(
    workspace: str,
    body: DefaultWorkflowHookCreateRequest,
    caller: Caller,
    session: Session,
) -> DefaultWorkflowHookResponse:
    """Create a default workflow hook template scoped to this workspace."""
    async with timing_floor(floor_ms=25.0):
        ws_id = await _resolve_workspace_id(session, caller, workspace)
        body.scope_kind = "workspace"
        body.workspace_id = ws_id
        return await admin_create_default_hook(body, caller, session)


@workspace_router.patch(
    "/{template_id}",
    response_model=DefaultWorkflowHookResponse,
    summary="Update a workspace default workflow hook template",
)
async def workspace_update_default_hook(
    workspace: str,
    template_id: uuid.UUID,
    body: DefaultWorkflowHookUpdateRequest,
    caller: Caller,
    session: Session,
) -> DefaultWorkflowHookResponse:
    """Update a workspace default workflow hook template."""
    async with timing_floor(floor_ms=25.0):
        ws_id = await _resolve_workspace_id(session, caller, workspace)
        template = await session.get(DefaultWorkflowHook, template_id)
        if template is None or template.workspace_id != ws_id:
            not_found()
        return await admin_update_default_hook(template_id, body, caller, session)


@workspace_router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workspace default workflow hook template",
)
async def workspace_delete_default_hook(
    workspace: str,
    template_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> Response:
    """Delete a workspace default workflow hook template."""
    async with timing_floor(floor_ms=25.0):
        ws_id = await _resolve_workspace_id(session, caller, workspace)
        template = await session.get(DefaultWorkflowHook, template_id)
        if template is None or template.workspace_id != ws_id:
            not_found()
        return await admin_delete_default_hook(template_id, caller, session)
