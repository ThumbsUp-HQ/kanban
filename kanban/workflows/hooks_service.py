# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: C901, PLR0912, PLR0915, E501, SIM105, PERF401
"""Service for workflow hook lifecycle, access control, and manifest auditing (KB-P5-17b)."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select, text

from database.models.agent_definition import AgentDefinition
from database.models.projects import WorkflowState
from database.models.wasm_module import ApprovedWasmModule
from database.models.workflow import WorkflowTransitionHook
from kanban.agents.cli_policy import CliPolicyError, assert_runtime_argv
from kanban.api.problems import ProblemException, not_found
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.projects import get_project_or_404
from kanban.workflows.builtins import seed_builtin_wasm
from kanban.workflows.manifest import compute_hook_manifest_sha256
from kanban.workflows.mutations import IMMUTABLE_FIELDS, is_in_mutable_universe

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

logger = logging.getLogger(__name__)

AAL2_MIN_LEVEL: Final[int] = 2
SHA256_BYTE_LEN: Final[int] = 32

HookKind = Literal["sync_validator", "sync_mutator", "agent_interceptor"]
FailurePolicy = Literal["fail_closed", "fail_open_warn"]


class WorkflowHookCreateRequest(BaseModel):
    """Payload for creating/attaching a workflow hook."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=120, description="Unique hook name")
    from_state: str | None = Field(
        default=None,
        description="Source state name, UUID, or null/'*' for wildcard",
    )
    to_state: str = Field(min_length=1, description="Target state name or UUID")
    hook_kind: HookKind = Field(
        description="Hook kind: sync_validator, sync_mutator, or agent_interceptor"
    )
    failure_policy: FailurePolicy = Field(
        default="fail_closed",
        description="Failure policy: fail_closed or fail_open_warn",
    )
    wasm_module_sha256: str | None = Field(
        default=None,
        description="32-byte hex SHA-256 of approved WASM module (required for sync hooks)",
    )
    agent: str | None = Field(
        default=None,
        description="Agent definition UUID or slug (required for agent_interceptor)",
    )
    allowed_mutable_fields: list[str] = Field(
        default_factory=list,
        description="List of fields this mutator is permitted to modify",
    )
    timeout_ms: int | None = Field(
        default=None,
        ge=1,
        le=300000,
        description="Optional timeout in milliseconds",
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional description of the hook's purpose",
    )


class WorkflowHookUpdateRequest(BaseModel):
    """Payload for updating an existing workflow hook."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    failure_policy: FailurePolicy | None = Field(default=None)
    allowed_mutable_fields: list[str] | None = Field(default=None)
    wasm_module_sha256: str | None = Field(default=None)
    agent: str | None = Field(default=None)
    timeout_ms: int | None = Field(default=None, ge=1, le=300000)
    description: str | None = Field(default=None, max_length=1000)


class WorkflowHookReorderRequest(BaseModel):
    """Payload for atomically reordering hooks for a transition."""

    model_config = ConfigDict(extra="forbid", strict=True)

    transition: dict[str, str | None] = Field(
        description="Transition specification: {'from_state': ..., 'to_state': ...}",
    )
    ordered_hook_ids: list[str] = Field(
        min_length=1,
        description="Exact list of all hook IDs for this transition in desired execution order",
    )


class WorkflowHookResponse(BaseModel):
    """Serialized workflow hook representation."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    from_state: str | None
    to_state: str
    hook_kind: str
    sort_rank: str
    failure_policy: str
    manifest_sha256: str
    is_enabled: bool
    allowed_mutable_fields: list[str]
    description: str | None = None
    wasm_module_sha256: str | None = None
    wasm_module_name: str | None = None
    target_latency_budget: str | None = None
    agent_slug: str | None = None
    agent_display_name: str | None = None
    harness_kind: str | None = None
    provider_kind: str | None = None
    model_id: str | None = None
    cli_binary_allowlist_id: str | None = None
    cli_args: list[str] | None = None
    timeout_ms: int | None = None
    repo_binding_slug: str | None = None
    repo_access_mode: str | None = None
    mcp_access_summary: str | None = None


class TransitionRule(BaseModel):
    """Workflow hooks grouped by (from_state, to_state) transition."""

    from_state: str | None
    to_state: str
    active_hook_count: int
    hooks: list[WorkflowHookResponse]


def _parse_sha256_hex(hex_str: str) -> bytes:
    """Parse and validate 32-byte hex string."""
    clean = hex_str.strip().lower()
    try:
        raw = bytes.fromhex(clean)
    except ValueError as exc:
        msg = f"Invalid hex for wasm_module_sha256: {hex_str}"
        raise ProblemException(
            code="WASM_MODULE_NOT_APPROVED",
            status=422,
            title="Invalid WASM SHA256",
            detail=msg,
        ) from exc
    if len(raw) != SHA256_BYTE_LEN:
        msg = "WASM SHA256 must be 32 bytes (64 hex characters)"
        raise ProblemException(
            code="WASM_MODULE_NOT_APPROVED",
            status=422,
            title="Invalid WASM SHA256",
            detail=msg,
        )
    return raw


def _validate_mutable_fields(fields: list[str]) -> list[str]:
    """Validate allowed_mutable_fields against MUTABLE_FIELD_UNIVERSE and immutability invariants."""
    clean_fields: list[str] = []
    for f in fields:
        f_clean = f.strip()
        if not f_clean:
            continue
        if f_clean in IMMUTABLE_FIELDS:
            msg = f"Field '{f_clean}' is immutable to preserve zero-TOCTOU guarantees"
            raise ProblemException(
                code="MUTABLE_FIELD_NOT_ALLOWED",
                status=422,
                title="Mutable Field Not Allowed",
                detail=msg,
            )
        if not is_in_mutable_universe(f_clean):
            msg = f"Field '{f_clean}' is not in MUTABLE_FIELD_UNIVERSE"
            raise ProblemException(
                code="MUTABLE_FIELD_NOT_ALLOWED",
                status=422,
                title="Mutable Field Not Allowed",
                detail=msg,
            )
        if f_clean not in clean_fields:
            clean_fields.append(f_clean)
    return clean_fields


class WorkflowHookService:
    """Encapsulates workflow hook management, access control, and auditing."""

    @staticmethod
    async def is_project_admin(session: AsyncSession, project_id: uuid.UUID) -> bool:
        """Return True if caller holds admin capability on the project."""
        stmt = text(
            "SELECT app_principal_has_role(:project_id, "
            "ARRAY['PROJECT_ADMIN', 'WORKSPACE_ADMIN', 'SERVER_ADMIN']) "
            "OR app_has_object_capability(:project_id, 64)"
        )
        return bool((await session.execute(stmt, {"project_id": project_id})).scalar_one())

    @classmethod
    async def require_admin(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        project_id: uuid.UUID,
    ) -> None:
        """Enforce PROJECT_ADMIN role; raises 404 on failure to prevent enumeration."""
        del caller
        if not await cls.is_project_admin(session, project_id):
            not_found()

    @staticmethod
    def require_aal2(caller: PrincipalContext) -> None:
        """Ensure caller has active AAL2 session for mutating operations."""
        if caller.aal_level < AAL2_MIN_LEVEL:
            raise ProblemException(
                code="AAL2_REQUIRED",
                status=403,
                title="AAL2 Authentication Required",
                detail="This operation requires multi-factor authentication (AAL2).",
            )

    @classmethod
    async def resolve_state(
        cls,
        session: AsyncSession,
        project_id: uuid.UUID,
        state_ref: str | None,
        *,
        allow_wildcard: bool = False,
    ) -> tuple[uuid.UUID | None, str | None]:
        """Resolve state name or UUID within a project."""
        if state_ref is None or state_ref.strip() in ("", "*"):
            if allow_wildcard:
                return None, None
            raise ProblemException(
                code="INVALID_STATE",
                status=422,
                title="Invalid State",
                detail="to_state cannot be wildcard",
            )

        ref_str = state_ref.strip()
        state_id: uuid.UUID | None = None
        try:
            state_id = uuid.UUID(ref_str)
        except ValueError:
            pass

        if state_id is not None:
            stmt = select(WorkflowState.id, WorkflowState.name).where(
                WorkflowState.project_id == project_id,
                WorkflowState.id == state_id,
            )
        else:
            stmt = select(WorkflowState.id, WorkflowState.name).where(
                WorkflowState.project_id == project_id,
                func.lower(WorkflowState.name) == ref_str.lower(),
            )

        row = (await session.execute(stmt)).first()
        if row is None:
            raise ProblemException(
                code="INVALID_STATE",
                status=422,
                title="Invalid State",
                detail=f"State '{state_ref}' does not belong to the target project",
            )
        return row[0], row[1]

    @classmethod
    async def serialize_hook(
        cls,
        session: AsyncSession,
        hook: WorkflowTransitionHook,
        *,
        states_map: dict[uuid.UUID, str] | None = None,
    ) -> WorkflowHookResponse:
        """Serialize a WorkflowTransitionHook row into a presentation DTO."""
        from_name: str | None = None
        if hook.from_state_id is not None:
            if states_map and hook.from_state_id in states_map:
                from_name = states_map[hook.from_state_id]
            else:
                from_name = await session.scalar(
                    select(WorkflowState.name).where(WorkflowState.id == hook.from_state_id)
                )

        to_name = (
            states_map.get(hook.to_state_id, "")
            if states_map and hook.to_state_id in states_map
            else await session.scalar(
                select(WorkflowState.name).where(WorkflowState.id == hook.to_state_id)
            )
            or ""
        )

        wasm_name: str | None = None
        target_budget: str | None = None
        if hook.wasm_module_sha256 is not None:
            mod_stmt = select(ApprovedWasmModule.name).where(
                ApprovedWasmModule.workspace_id == hook.workspace_id,
                ApprovedWasmModule.sha256 == hook.wasm_module_sha256,
            )
            wasm_name = (await session.execute(mod_stmt)).scalar_one_or_none()
            target_budget = "< 25.0 ms (Tier A)"
        elif hook.agent_definition_id is not None:
            target_budget = "< 180.0 s (Tier B)"

        agent_slug: str | None = None
        agent_display_name: str | None = None
        harness_kind: str | None = None
        provider_kind: str | None = None
        model_id: str | None = None
        cli_bin_id: str | None = None
        cli_args: list[str] | None = None
        mcp_summary: str | None = None
        timeout_ms: int | None = None
        repo_binding_slug: str | None = None
        repo_access_mode: str | None = None

        if hook.agent_definition_id is not None:
            agent_stmt = select(AgentDefinition).where(
                AgentDefinition.id == hook.agent_definition_id,
                AgentDefinition.workspace_id == hook.workspace_id,
            )
            agent_def = (await session.execute(agent_stmt)).scalar_one_or_none()
            if agent_def is not None:
                agent_slug = agent_def.slug
                agent_display_name = agent_def.display_name
                harness_kind = agent_def.harness_kind
                provider_kind = agent_def.provider_kind
                model_id = agent_def.model_id
                cli_bin_id = agent_def.cli_binary_allowlist_id
                if isinstance(agent_def.cli_args_json, list):
                    cli_args = [str(x) for x in agent_def.cli_args_json]
                mcp_summary = f"{len(agent_def.mcp_allowed_tools)} tools"
                timeout_ms = agent_def.timeout_ms
                repo_access_mode = agent_def.repo_access_mode

                if agent_def.repo_access_mode != "none":
                    from database.models.repo_binding import ProjectRepoBinding  # noqa: PLC0415

                    repo_stmt = (
                        select(ProjectRepoBinding.slug)
                        .where(ProjectRepoBinding.project_id == hook.project_id)
                        .limit(1)
                    )
                    repo_binding_slug = (await session.execute(repo_stmt)).scalar_one_or_none()

        wasm_hex = hook.wasm_module_sha256.hex() if hook.wasm_module_sha256 else None
        manifest_hex = hook.manifest_sha256.hex()

        return WorkflowHookResponse(
            id=str(hook.id),
            name=hook.name,
            from_state=from_name,
            to_state=to_name,
            hook_kind=hook.hook_kind,
            sort_rank=hook.sort_rank,
            failure_policy=hook.failure_policy,
            manifest_sha256=manifest_hex,
            is_enabled=hook.is_enabled,
            allowed_mutable_fields=hook.allowed_mutable_fields,
            wasm_module_sha256=wasm_hex,
            wasm_module_name=wasm_name,
            target_latency_budget=target_budget,
            agent_slug=agent_slug,
            agent_display_name=agent_display_name,
            harness_kind=harness_kind,
            provider_kind=provider_kind,
            model_id=model_id,
            cli_binary_allowlist_id=cli_bin_id,
            cli_args=cli_args,
            mcp_access_summary=mcp_summary,
            timeout_ms=timeout_ms,
            repo_binding_slug=repo_binding_slug,
            repo_access_mode=repo_access_mode,
        )

    @classmethod
    async def list_hooks(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        project_ref: str,
    ) -> list[TransitionRule]:
        """List workflow hooks for a project grouped by transition. S3.4: 404 for non-admins."""
        project = await get_project_or_404(session, caller, project_ref)
        await cls.require_admin(session, caller, project.id)

        # Pre-cache states
        states_stmt = select(WorkflowState.id, WorkflowState.name).where(
            WorkflowState.project_id == project.id
        )
        states_rows = (await session.execute(states_stmt)).all()
        states_map = {row[0]: row[1] for row in states_rows}

        # Query all hooks for this project
        stmt = (
            select(WorkflowTransitionHook)
            .where(
                WorkflowTransitionHook.project_id == project.id,
                WorkflowTransitionHook.workspace_id == caller.workspace_id,
            )
            .order_by(
                WorkflowTransitionHook.to_state_id,
                WorkflowTransitionHook.from_state_id.nulls_first(),
                WorkflowTransitionHook.sort_rank,
            )
        )
        hooks = list((await session.execute(stmt)).scalars().all())

        # Group by (from_state_id, to_state_id)
        grouped: dict[tuple[uuid.UUID | None, uuid.UUID], list[WorkflowTransitionHook]] = {}
        for h in hooks:
            key = (h.from_state_id, h.to_state_id)
            grouped.setdefault(key, []).append(h)

        rules: list[TransitionRule] = []
        for (from_id, to_id), group_hooks in grouped.items():
            from_name = states_map.get(from_id) if from_id else None
            to_name = states_map.get(to_id, "")
            serialized_hooks: list[WorkflowHookResponse] = []
            for gh in group_hooks:
                serialized_hooks.append(
                    await cls.serialize_hook(session, gh, states_map=states_map)
                )

            active_count = sum(1 for gh in group_hooks if gh.is_enabled)
            rules.append(
                TransitionRule(
                    from_state=from_name,
                    to_state=to_name,
                    active_hook_count=active_count,
                    hooks=serialized_hooks,
                )
            )

        return rules

    @classmethod
    async def create_hook(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        project_ref: str,
        payload: WorkflowHookCreateRequest,
    ) -> WorkflowHookResponse:
        """Create and attach a new workflow hook."""
        project = await get_project_or_404(session, caller, project_ref)
        await cls.require_admin(session, caller, project.id)
        cls.require_aal2(caller)

        from_id, _ = await cls.resolve_state(
            session, project.id, payload.from_state, allow_wildcard=True
        )
        to_id, _ = await cls.resolve_state(
            session, project.id, payload.to_state, allow_wildcard=False
        )

        clean_fields = _validate_mutable_fields(payload.allowed_mutable_fields)

        wasm_sha_bytes: bytes | None = None
        agent_def_id: uuid.UUID | None = None

        if payload.hook_kind in ("sync_validator", "sync_mutator"):
            if not payload.wasm_module_sha256:
                raise ProblemException(
                    code="WASM_MODULE_NOT_APPROVED",
                    status=422,
                    title="Missing WASM Module",
                    detail="wasm_module_sha256 is required for sync validator and mutator hooks",
                )
            wasm_sha_bytes = _parse_sha256_hex(payload.wasm_module_sha256)

            # Validate approved WASM module
            mod_stmt = select(ApprovedWasmModule).where(
                ApprovedWasmModule.workspace_id == caller.workspace_id,
                ApprovedWasmModule.sha256 == wasm_sha_bytes,
            )
            approved_mod = (await session.execute(mod_stmt)).scalar_one_or_none()
            if approved_mod is None:
                approved_mod = await seed_builtin_wasm(
                    session,
                    caller.workspace_id,
                    caller.principal_id,
                    wasm_sha_bytes,
                    project_id=project.id,
                )
            if approved_mod is None:
                raise ProblemException(
                    code="WASM_MODULE_NOT_APPROVED",
                    status=422,
                    title="WASM Module Not Approved",
                    detail="WASM module SHA-256 is not approved in this workspace",
                )
            if payload.agent is not None:
                raise ProblemException(
                    code="INVALID_HOOK_CONFIG",
                    status=422,
                    title="Invalid Hook Configuration",
                    detail="Sync hooks must not specify an agent definition",
                )

        elif payload.hook_kind == "agent_interceptor":
            if not payload.agent:
                raise ProblemException(
                    code="AGENT_NOT_FOUND",
                    status=422,
                    title="Missing Agent",
                    detail="agent parameter is required for agent_interceptor hooks",
                )
            agent_str = payload.agent.strip()
            agent_u: uuid.UUID | None = None
            try:
                agent_u = uuid.UUID(agent_str)
            except ValueError:
                pass

            if agent_u is not None:
                agent_stmt = select(AgentDefinition).where(
                    AgentDefinition.workspace_id == caller.workspace_id,
                    AgentDefinition.id == agent_u,
                )
            else:
                agent_stmt = select(AgentDefinition).where(
                    AgentDefinition.workspace_id == caller.workspace_id,
                    AgentDefinition.slug == agent_str,
                )

            agent_row = (await session.execute(agent_stmt)).scalar_one_or_none()
            if agent_row is None:
                raise ProblemException(
                    code="AGENT_NOT_FOUND",
                    status=422,
                    title="Agent Not Found",
                    detail=f"Agent definition '{payload.agent}' not found in workspace",
                )

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

            agent_def_id = agent_row.id
            if payload.wasm_module_sha256 is not None:
                raise ProblemException(
                    code="INVALID_HOOK_CONFIG",
                    status=422,
                    title="Invalid Hook Configuration",
                    detail="Agent interceptors must not specify a wasm_module_sha256",
                )

        # Compute next sort_rank (append after highest existing in this transition)
        rank_stmt = select(func.max(WorkflowTransitionHook.sort_rank)).where(
            WorkflowTransitionHook.project_id == project.id,
            WorkflowTransitionHook.to_state_id == to_id,
        )
        if from_id is None:
            rank_stmt = rank_stmt.where(WorkflowTransitionHook.from_state_id.is_(None))
        else:
            rank_stmt = rank_stmt.where(WorkflowTransitionHook.from_state_id == from_id)

        max_rank = (await session.execute(rank_stmt)).scalar_one_or_none()
        if max_rank is None:
            sort_rank = "0000000000000001"
        else:
            try:
                num = int(max_rank)
                sort_rank = f"{num + 1:016d}"
            except ValueError:
                sort_rank = f"{max_rank}_1"

        if to_id is None:
            raise ProblemException(
                code="INVALID_STATE",
                status=422,
                title="Invalid State",
                detail="to_state must not be null",
            )
        manifest_sha = compute_hook_manifest_sha256(
            from_state_id=from_id,
            to_state_id=to_id,
            hook_kind=payload.hook_kind,
            wasm_module_sha256=wasm_sha_bytes,
            agent_definition_id=agent_def_id,
            allowed_mutable_fields=clean_fields,
            failure_policy=payload.failure_policy,
        )

        hook = WorkflowTransitionHook(
            workspace_id=caller.workspace_id,
            project_id=project.id,
            name=payload.name.strip(),
            from_state_id=from_id,
            to_state_id=to_id,
            hook_kind=payload.hook_kind,
            sort_rank=sort_rank,
            is_enabled=True,
            wasm_module_sha256=wasm_sha_bytes,
            agent_definition_id=agent_def_id,
            allowed_mutable_fields=clean_fields,
            failure_policy=payload.failure_policy,
            manifest_sha256=manifest_sha,
        )
        session.add(hook)
        await session.flush()

        await record_activity(
            session=session,
            workspace_id=caller.workspace_id,
            object_id=project.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.WORKFLOW_HOOK_ATTACHED,
            payload={
                "hook_id": str(hook.id),
                "name": hook.name,
                "hook_kind": hook.hook_kind,
                "from_state_id": str(from_id) if from_id else None,
                "to_state_id": str(to_id),
                "manifest_sha256": manifest_sha.hex(),
            },
        )

        return await cls.serialize_hook(session, hook)

    @classmethod
    async def update_hook(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        hook_id_str: str,
        payload: WorkflowHookUpdateRequest,
    ) -> WorkflowHookResponse:
        """Update an existing workflow hook and recompute manifest if config changed."""
        try:
            hook_u = uuid.UUID(hook_id_str.strip())
        except ValueError as exc:
            raise ProblemException(
                code="INVALID_HOOK_ID",
                status=422,
                title="Invalid Hook ID",
                detail="Hook ID must be a valid UUID",
            ) from exc

        hook_stmt = select(WorkflowTransitionHook).where(
            WorkflowTransitionHook.id == hook_u,
            WorkflowTransitionHook.workspace_id == caller.workspace_id,
        )
        hook = (await session.execute(hook_stmt)).scalar_one_or_none()
        if hook is None:
            not_found()

        await cls.require_admin(session, caller, hook.project_id)
        cls.require_aal2(caller)

        old_manifest_hex = hook.manifest_sha256.hex()
        needs_manifest_recompute = False

        if payload.name is not None:
            hook.name = payload.name.strip()

        if payload.failure_policy is not None and payload.failure_policy != hook.failure_policy:
            hook.failure_policy = payload.failure_policy
            needs_manifest_recompute = True

        if payload.allowed_mutable_fields is not None:
            clean_fields = _validate_mutable_fields(payload.allowed_mutable_fields)
            if clean_fields != hook.allowed_mutable_fields:
                hook.allowed_mutable_fields = clean_fields
                needs_manifest_recompute = True

        if payload.wasm_module_sha256 is not None:
            wasm_sha_bytes = _parse_sha256_hex(payload.wasm_module_sha256)
            mod_stmt = select(ApprovedWasmModule).where(
                ApprovedWasmModule.workspace_id == caller.workspace_id,
                ApprovedWasmModule.sha256 == wasm_sha_bytes,
            )
            approved_mod = (await session.execute(mod_stmt)).scalar_one_or_none()
            if approved_mod is None:
                approved_mod = await seed_builtin_wasm(
                    session,
                    caller.workspace_id,
                    caller.principal_id,
                    wasm_sha_bytes,
                    project_id=hook.project_id,
                )
            if approved_mod is None:
                raise ProblemException(
                    code="WASM_MODULE_NOT_APPROVED",
                    status=422,
                    title="WASM Module Not Approved",
                    detail="WASM module SHA-256 is not approved in this workspace",
                )
            if hook.hook_kind not in ("sync_validator", "sync_mutator"):
                raise ProblemException(
                    code="INVALID_HOOK_CONFIG",
                    status=422,
                    title="Invalid Hook Configuration",
                    detail="Cannot assign WASM module to non-sync hook",
                )
            hook.wasm_module_sha256 = wasm_sha_bytes
            needs_manifest_recompute = True

        if payload.agent is not None:
            agent_str = payload.agent.strip()
            agent_u: uuid.UUID | None = None
            try:
                agent_u = uuid.UUID(agent_str)
            except ValueError:
                pass

            if agent_u is not None:
                agent_stmt = select(AgentDefinition).where(
                    AgentDefinition.workspace_id == caller.workspace_id,
                    AgentDefinition.id == agent_u,
                )
            else:
                agent_stmt = select(AgentDefinition).where(
                    AgentDefinition.workspace_id == caller.workspace_id,
                    AgentDefinition.slug == agent_str,
                )

            agent_row = (await session.execute(agent_stmt)).scalar_one_or_none()
            if agent_row is None:
                raise ProblemException(
                    code="AGENT_NOT_FOUND",
                    status=422,
                    title="Agent Not Found",
                    detail=f"Agent definition '{payload.agent}' not found in workspace",
                )
            if hook.hook_kind != "agent_interceptor":
                raise ProblemException(
                    code="INVALID_HOOK_CONFIG",
                    status=422,
                    title="Invalid Hook Configuration",
                    detail="Cannot assign agent to sync hook",
                )
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

            hook.agent_definition_id = agent_row.id
            needs_manifest_recompute = True

        if needs_manifest_recompute:
            new_manifest_sha = compute_hook_manifest_sha256(
                from_state_id=hook.from_state_id,
                to_state_id=hook.to_state_id,
                hook_kind=hook.hook_kind,
                wasm_module_sha256=hook.wasm_module_sha256,
                agent_definition_id=hook.agent_definition_id,
                allowed_mutable_fields=hook.allowed_mutable_fields,
                failure_policy=hook.failure_policy,
            )
            hook.manifest_sha256 = new_manifest_sha

        await session.flush()

        await record_activity(
            session=session,
            workspace_id=caller.workspace_id,
            object_id=hook.project_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.WORKFLOW_HOOK_UPDATED,
            payload={
                "hook_id": str(hook.id),
                "name": hook.name,
                "before_manifest_sha256": old_manifest_hex,
                "after_manifest_sha256": hook.manifest_sha256.hex(),
            },
        )

        return await cls.serialize_hook(session, hook)

    @classmethod
    async def set_enabled(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        hook_id_str: str,
        *,
        is_enabled: bool,
    ) -> WorkflowHookResponse:
        """Enable or disable a workflow hook."""
        try:
            hook_u = uuid.UUID(hook_id_str.strip())
        except ValueError as exc:
            raise ProblemException(
                code="INVALID_HOOK_ID",
                status=422,
                title="Invalid Hook ID",
                detail="Hook ID must be a valid UUID",
            ) from exc

        hook_stmt = select(WorkflowTransitionHook).where(
            WorkflowTransitionHook.id == hook_u,
            WorkflowTransitionHook.workspace_id == caller.workspace_id,
        )
        hook = (await session.execute(hook_stmt)).scalar_one_or_none()
        if hook is None:
            not_found()

        await cls.require_admin(session, caller, hook.project_id)
        cls.require_aal2(caller)

        hook.is_enabled = is_enabled
        await session.flush()

        evt = (
            ActivityEventType.WORKFLOW_HOOK_ENABLED
            if is_enabled
            else ActivityEventType.WORKFLOW_HOOK_DISABLED
        )
        await record_activity(
            session=session,
            workspace_id=caller.workspace_id,
            object_id=hook.project_id,
            actor_principal_id=caller.principal_id,
            event_type=evt,
            payload={
                "hook_id": str(hook.id),
                "name": hook.name,
                "manifest_sha256": hook.manifest_sha256.hex(),
            },
        )
        return await cls.serialize_hook(session, hook)

    @classmethod
    async def delete_hook(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        hook_id_str: str,
    ) -> dict[str, Any]:
        """Delete/detach a workflow hook."""
        try:
            hook_u = uuid.UUID(hook_id_str.strip())
        except ValueError as exc:
            raise ProblemException(
                code="INVALID_HOOK_ID",
                status=422,
                title="Invalid Hook ID",
                detail="Hook ID must be a valid UUID",
            ) from exc

        hook_stmt = select(WorkflowTransitionHook).where(
            WorkflowTransitionHook.id == hook_u,
            WorkflowTransitionHook.workspace_id == caller.workspace_id,
        )
        hook = (await session.execute(hook_stmt)).scalar_one_or_none()
        if hook is None:
            not_found()

        await cls.require_admin(session, caller, hook.project_id)
        cls.require_aal2(caller)

        preview = {
            "id": str(hook.id),
            "name": hook.name,
            "project_id": str(hook.project_id),
            "manifest_sha256": hook.manifest_sha256.hex(),
        }

        await session.execute(
            delete(WorkflowTransitionHook).where(WorkflowTransitionHook.id == hook.id)
        )
        await session.flush()

        await record_activity(
            session=session,
            workspace_id=caller.workspace_id,
            object_id=hook.project_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.WORKFLOW_HOOK_DETACHED,
            payload=preview,
        )

        return {"status": "detached", "hook": preview}

    @classmethod
    async def reorder_hooks(
        cls,
        session: AsyncSession,
        caller: PrincipalContext,
        project_ref: str,
        payload: WorkflowHookReorderRequest,
    ) -> list[WorkflowHookResponse]:
        """Atomically reorder hooks for a transition."""
        project = await get_project_or_404(session, caller, project_ref)
        await cls.require_admin(session, caller, project.id)
        cls.require_aal2(caller)

        from_val = payload.transition.get("from_state")
        to_val = payload.transition.get("to_state")
        if not to_val:
            raise ProblemException(
                code="INVALID_TRANSITION",
                status=422,
                title="Invalid Transition",
                detail="to_state is required in transition",
            )

        from_id, _ = await cls.resolve_state(session, project.id, from_val, allow_wildcard=True)
        to_id, _ = await cls.resolve_state(session, project.id, to_val, allow_wildcard=False)

        # Parse requested hook UUIDs
        try:
            requested_uuids = [uuid.UUID(h_id.strip()) for h_id in payload.ordered_hook_ids]
        except ValueError as exc:
            raise ProblemException(
                code="REORDER_SET_MISMATCH",
                status=422,
                title="Invalid Hook ID in Reorder",
                detail="All ordered_hook_ids must be valid UUIDs",
            ) from exc

        # Query existing hooks for this exact transition
        stmt = select(WorkflowTransitionHook).where(
            WorkflowTransitionHook.project_id == project.id,
            WorkflowTransitionHook.workspace_id == caller.workspace_id,
            WorkflowTransitionHook.to_state_id == to_id,
        )
        if from_id is None:
            stmt = stmt.where(WorkflowTransitionHook.from_state_id.is_(None))
        else:
            stmt = stmt.where(WorkflowTransitionHook.from_state_id == from_id)

        existing_hooks = list((await session.execute(stmt)).scalars().all())
        existing_ids = {h.id for h in existing_hooks}
        requested_set = set(requested_uuids)

        if existing_ids != requested_set or len(requested_uuids) != len(existing_hooks):
            raise ProblemException(
                code="REORDER_SET_MISMATCH",
                status=422,
                title="Reorder Set Mismatch",
                detail="ordered_hook_ids must match current hook set for this transition exactly",
            )

        # Map hooks by ID
        hook_by_id = {h.id: h for h in existing_hooks}
        updated_hooks: list[WorkflowTransitionHook] = []
        for idx, h_id in enumerate(requested_uuids):
            hook_row = hook_by_id[h_id]
            hook_row.sort_rank = f"{idx + 1:016d}"
            updated_hooks.append(hook_row)

        await session.flush()

        await record_activity(
            session=session,
            workspace_id=caller.workspace_id,
            object_id=project.id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.WORKFLOW_HOOK_REORDERED,
            payload={
                "from_state_id": str(from_id) if from_id else None,
                "to_state_id": str(to_id),
                "ordered_hook_ids": [str(u) for u in requested_uuids],
            },
        )

        res: list[WorkflowHookResponse] = []
        for uh in updated_hooks:
            res.append(await cls.serialize_hook(session, uh))
        return res
