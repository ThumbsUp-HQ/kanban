# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Transition engine and synchronous Tier A hook pipeline (KB-P5-17a, S14.1, S14.2)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Protocol

from sqlalchemy import or_, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from database.models.issues import Issue, IssueAssignee, IssueComment, IssueLabel
from database.models.projects import Project, ProjectLabel, ProjectPriority, WorkflowState
from database.models.wasm_module import ApprovedWasmModule
from database.models.workflow import (
    WorkflowHookInvocation,
    WorkflowTransitionExecution,
    WorkflowTransitionHook,
)
from kanban.api.problems import ProblemException, not_found
from kanban.content.normalize import normalize_to_markdown
from kanban.sandbox.wasm_runner import TierAWasmRunner, WasmRunError, WasmRunLimits
from kanban.security.permissions import Capability, evaluate_capabilities
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.issue_keys import resolve_issue_ref
from kanban.workflows.manifest import compute_hook_manifest_sha256
from kanban.workflows.mutations import apply_field_updates, validate_field_updates

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

logger = logging.getLogger(__name__)

SYNC_TOTAL_BUDGET_MS: float = 25.0
MAX_TRANSITION_HOP_DEPTH: Final[int] = 3


@dataclass(slots=True)
class TransitionOutcome:
    """Result of requesting a workflow transition."""

    status_code: int = 200
    execution_id: uuid.UUID | None = None
    status: str = "approved"
    state: str | None = None
    to_state_id: uuid.UUID | None = None
    from_state_id: uuid.UUID | None = None
    reason: str | None = None
    hook_name: str | None = None
    error_code: str | None = None
    sync_duration_ms: float = 0.0
    field_updates: dict[str, Any] = field(default_factory=dict)


class AsyncGateDispatcher(Protocol):
    """Protocol for dispatching asynchronous AI/CLI agent transition helpers."""

    async def dispatch(
        self,
        session: AsyncSession,
        execution: WorkflowTransitionExecution,
        hooks: Sequence[WorkflowTransitionHook],
        caller: PrincipalContext,
    ) -> TransitionOutcome:
        """Dispatch async agent gate execution, returning 202 or handling error."""
        ...


class FailClosedAsyncGateDispatcher:
    """Default fallback dispatcher marking execution cancelled.

    Returns 409 AGENT_GATE_NOT_CONFIGURED.
    """

    async def dispatch(
        self,
        session: AsyncSession,
        execution: WorkflowTransitionExecution,
        hooks: Sequence[WorkflowTransitionHook],
        caller: PrincipalContext,
    ) -> TransitionOutcome:
        """Cancel execution and reject with 409 AGENT_GATE_NOT_CONFIGURED (replaced by KB-P5-18)."""
        del hooks, caller
        execution.status = "cancelled"
        execution.completed_at = dt.datetime.now(dt.UTC)
        await session.flush()
        raise ProblemException(
            code="AGENT_GATE_NOT_CONFIGURED",
            status=409,
            title="Agent Gate Not Configured",
            detail="Async agent gate dispatch is not configured on this host (KB-P5-18 required)",
        )


class WasmRunnerProtocol(Protocol):
    """Protocol for synchronously executing WebAssembly modules."""

    def run_sync(
        self,
        wasm_bytes: bytes | bytearray,
        input_bytes: bytes,
        limits: WasmRunLimits | None = None,
    ) -> object:
        """Execute wasm guest synchronously."""
        ...


_WASM_BYTES_CACHE: dict[bytes, bytes] = {}


class TransitionEngine:
    """Synchronous Tier A validator/mutator transition engine and gate coordinator (KB-P5-17a)."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        wasm_runner: WasmRunnerProtocol | None = None,
        async_dispatcher: AsyncGateDispatcher | None = None,
    ) -> None:
        """Initialize TransitionEngine bound to session."""
        self.session = session
        self.wasm_runner: WasmRunnerProtocol = wasm_runner or TierAWasmRunner.get_instance()
        if async_dispatcher is None:
            from kanban.workflows.async_gate import AgentGateDispatcher  # noqa: PLC0415

            async_dispatcher = AgentGateDispatcher()
        self.async_dispatcher: AsyncGateDispatcher = async_dispatcher

    @classmethod
    async def request_transition(  # noqa: PLR0913, PLR0917
        cls,
        session: AsyncSession,
        issue_key: str,
        to_state: str | uuid.UUID,
        actor: PrincipalContext,
        if_match: str | None = None,
        parent_execution_id: uuid.UUID | None = None,
        comment_markdown: str | None = None,
        *,
        wasm_runner: WasmRunnerProtocol | None = None,
        async_dispatcher: AsyncGateDispatcher | None = None,
    ) -> TransitionOutcome:
        """Delegate to TransitionEngine instance."""
        engine = cls(session, wasm_runner=wasm_runner, async_dispatcher=async_dispatcher)
        return await engine.execute_transition(
            issue_key=issue_key,
            to_state=to_state,
            actor=actor,
            if_match=if_match,
            parent_execution_id=parent_execution_id,
            comment_markdown=comment_markdown,
        )

    async def execute_transition(  # noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917
        self,
        issue_key: str,
        to_state: str | uuid.UUID,
        actor: PrincipalContext,
        if_match: str | None = None,
        parent_execution_id: uuid.UUID | None = None,
        comment_markdown: str | None = None,
    ) -> TransitionOutcome:
        """Execute state transition pipeline under S14.1 / S14.2 invariants."""
        session = self.session

        # 1. Resolve issue and capabilities
        issue = await resolve_issue_ref(session, actor, issue_key)

        caps = await evaluate_capabilities(session, actor, issue.id)
        if Capability.VIEW not in caps or Capability.TRANSITION not in caps:
            not_found()

        # Lock issue row
        locked_stmt = select(Issue).where(Issue.id == issue.id).with_for_update()
        locked_issue = (await session.execute(locked_stmt)).scalar_one_or_none()
        if locked_issue is None:  # pragma: no cover
            not_found()
        issue = locked_issue

        # Description ETag check (If-Match accepts composite compute_issue_etag
        # or backward-compatible description_sha256)
        current_sha256_hex = issue.description_sha256.hex() if issue.description_sha256 else ""
        from kanban.services.issues import serialize_issue  # noqa: PLC0415

        current_serialized = await serialize_issue(session, actor, issue)
        current_etag = current_serialized.etag or f'"{current_sha256_hex}"'
        current_etag_hex = current_etag.strip('"')

        if if_match is not None:
            raw_etag = if_match.strip()
            if raw_etag.startswith("W/"):
                raw_etag = raw_etag[2:].strip()
            client_hex = raw_etag.strip('"')
            if client_hex.lower() not in (current_etag_hex.lower(), current_sha256_hex.lower()):
                raise ProblemException(
                    code="PRECONDITION_FAILED",
                    status=412,
                    title="Precondition Failed",
                    detail="Current description ETag does not match If-Match header",
                    current_etag=current_etag,
                )

        if issue.pending_transition_exec_id is not None:
            raise ProblemException(
                code="TRANSITION_PENDING",
                status=409,
                title="Transition Pending",
                detail="A transition execution is already pending on this issue",
            )

        # Resolve target state
        target_state = await self._resolve_target_state(session, issue.project_id, to_state)
        from_state = await session.get(WorkflowState, issue.state_id)
        if from_state is None:  # pragma: no cover
            raise ProblemException(
                code="INVALID_STATE",
                status=422,
                title="Invalid State",
                detail="Current issue state could not be found",
            )

        # 2. Hop depth calculation
        hop_depth = 0
        if parent_execution_id is not None:
            parent = await session.get(WorkflowTransitionExecution, parent_execution_id)
            if parent is None:
                raise ProblemException(
                    code="INVALID_PARENT_EXECUTION",
                    status=422,
                    title="Invalid Parent Execution",
                    detail="parent_execution_id not found",
                )
            hop_depth = parent.hop_depth + 1

        if hop_depth > MAX_TRANSITION_HOP_DEPTH:
            raise ProblemException(
                code="HOP_DEPTH_EXCEEDED",
                status=422,
                title="Hop Depth Exceeded",
                detail=f"Transition hop depth exceeds maximum limit of {MAX_TRANSITION_HOP_DEPTH}",
            )

        # 3. Insert execution record
        desc_bytes = (issue.description_markdown or "").encode("utf-8")
        issue_body_sha256 = issue.description_sha256 or hashlib.sha256(desc_bytes).digest()

        execution = WorkflowTransitionExecution(
            id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
            workspace_id=issue.workspace_id,
            project_id=issue.project_id,
            issue_id=issue.id,
            invoking_principal_id=actor.principal_id,
            from_state_id=issue.state_id,
            to_state_id=target_state.id,
            status="running_sync",
            hop_depth=hop_depth,
            issue_body_sha256_snapshot=issue_body_sha256,
        )
        session.add(execution)
        try:
            await session.flush()
        except (IntegrityError, DBAPIError) as exc:
            if "wte_one_pending" in str(exc).lower():
                raise ProblemException(
                    code="TRANSITION_PENDING",
                    status=409,
                    title="Transition Pending",
                    detail="A transition execution is already pending on this issue",
                ) from exc
            raise

        # Set transaction-local execution ID for DB guard trigger
        await session.execute(
            text("SELECT set_config('app.transition_exec_id', :val, true)"),
            {"val": str(execution.id)},
        )

        # 4. Load enabled hooks ordered sort_rank COLLATE "C", id
        hooks_stmt = (
            select(WorkflowTransitionHook)
            .where(
                WorkflowTransitionHook.project_id == issue.project_id,
                WorkflowTransitionHook.to_state_id == target_state.id,
                WorkflowTransitionHook.is_enabled.is_(True),
                or_(
                    WorkflowTransitionHook.from_state_id == issue.state_id,
                    WorkflowTransitionHook.from_state_id.is_(None),
                ),
            )
            .order_by(WorkflowTransitionHook.sort_rank.collate("C"), WorkflowTransitionHook.id)
        )
        hooks = list((await session.execute(hooks_stmt)).scalars().all())

        sync_hooks = [h for h in hooks if h.hook_kind in ("sync_validator", "sync_mutator")]
        agent_hooks = [h for h in hooks if h.hook_kind == "agent_interceptor"]

        # 5. Build hook input payload
        hook_input_dict = await self._build_hook_input(
            session=session,
            issue=issue,
            from_state=from_state,
            to_state=target_state,
            actor=actor,
        )
        hook_input_bytes = json.dumps(hook_input_dict, sort_keys=True).encode("utf-8")

        # Execute Tier A synchronous hook pipeline within 25ms cumulative Wasm execution budget
        cumulative_wasm_ms: float = 0.0

        for hook in sync_hooks:
            # Recompute manifest SHA-256 for runtime tamper check
            recomputed_hash = compute_hook_manifest_sha256(
                hook_kind=hook.hook_kind,
                wasm_module_sha256=hook.wasm_module_sha256,
                agent_definition_id=hook.agent_definition_id,
                allowed_mutable_fields=hook.allowed_mutable_fields,
                failure_policy=hook.failure_policy,
                from_state_id=hook.from_state_id,
                to_state_id=hook.to_state_id,
            )
            if recomputed_hash != hook.manifest_sha256:
                await self._record_invocation(
                    session=session,
                    workspace_id=issue.workspace_id,
                    execution_id=execution.id,
                    hook=hook,
                    status="error",
                    error_code="HOOK_MANIFEST_MISMATCH",
                    duration_us=0,
                )
                execution.status = "rejected"
                execution.verdict_json = {
                    "decision": "reject",
                    "reason": f"Cryptographic manifest mismatch on hook '{hook.name}'",
                }
                execution.completed_at = dt.datetime.now(dt.UTC)
                await session.flush()
                raise ProblemException(
                    code="HOOK_MANIFEST_MISMATCH",
                    status=422,
                    title="Hook Manifest Mismatch",
                    detail=f"Cryptographic manifest mismatch on hook '{hook.name}'",
                    extra={"hook_name": hook.name},
                )

            # Check remaining 25ms cumulative Wasm budget
            elapsed_ms = cumulative_wasm_ms
            remaining_ms = SYNC_TOTAL_BUDGET_MS - elapsed_ms
            if remaining_ms <= 0.0:
                await self._handle_hook_failure(
                    session=session,
                    issue=issue,
                    execution=execution,
                    hook=hook,
                    error_code="SYNC_HOOK_BUDGET_EXCEEDED",
                    detail=f"Sync hook budget of {SYNC_TOTAL_BUDGET_MS}ms exceeded",
                    duration_us=int(elapsed_ms * 1000),
                )
                continue

            # Fetch wasm module bytes
            wasm_bytes = await self._fetch_wasm_bytes(
                session, issue.workspace_id, hook.wasm_module_sha256
            )
            if wasm_bytes is None:
                await self._handle_hook_failure(
                    session=session,
                    issue=issue,
                    execution=execution,
                    hook=hook,
                    error_code="SYNC_HOOK_OUTPUT_INVALID",
                    detail="Approved wasm module binary not found",
                    duration_us=0,
                )
                continue

            # Execute guest wasm synchronously
            t0 = time.perf_counter()
            timeout_int = max(1, int(remaining_ms))
            limits = WasmRunLimits(timeout_ms=min(500, timeout_int))
            try:
                res = self.wasm_runner.run_sync(wasm_bytes, hook_input_bytes, limits=limits)
                raw_dur_ms = getattr(res, "duration_ms", None)
                hook_ms = (
                    float(raw_dur_ms)
                    if isinstance(raw_dur_ms, (int, float))
                    else (time.perf_counter() - t0) * 1000.0
                )
                cumulative_wasm_ms += hook_ms
                duration_us = max(1, int(hook_ms * 1_000.0))
                output_raw = (
                    getattr(res, "output_bytes", res) if hasattr(res, "output_bytes") else res
                )
                output_str = (
                    output_raw.decode("utf-8")
                    if isinstance(output_raw, (bytes, bytearray))
                    else str(output_raw)
                )
                output_json = json.loads(output_str)
                if not isinstance(output_json, dict):
                    msg = "Output must be a JSON object"
                    raise TypeError(msg)  # noqa: TRY301
            except WasmRunError as ex:
                hook_ms = (time.perf_counter() - t0) * 1000.0
                cumulative_wasm_ms += hook_ms
                duration_us = max(1, int(hook_ms * 1_000.0))
                err_code = (
                    "SYNC_HOOK_BUDGET_EXCEEDED"
                    if ex.code in ("SCRIPT_TIMEOUT", "SCRIPT_FUEL_EXHAUSTED")
                    else "SYNC_HOOK_OUTPUT_INVALID"
                )
                await self._handle_hook_failure(
                    session=session,
                    issue=issue,
                    execution=execution,
                    hook=hook,
                    error_code=err_code,
                    detail=ex.message,
                    duration_us=duration_us,
                )
                continue
            except Exception as ex:  # noqa: BLE001
                duration_us = max(1, int((time.perf_counter() - t0) * 1_000_000))
                await self._handle_hook_failure(
                    session=session,
                    issue=issue,
                    execution=execution,
                    hook=hook,
                    error_code="SYNC_HOOK_OUTPUT_INVALID",
                    detail=f"Hook execution failed: {ex}",
                    duration_us=duration_us,
                )
                continue

            # Evaluate guest decision
            is_allow = output_json.get("decision") == "allow" or output_json.get("allowed") is True
            is_reject = (
                output_json.get("decision") == "reject" or output_json.get("allowed") is False
            )

            if not (is_allow or is_reject):
                await self._handle_hook_failure(
                    session=session,
                    issue=issue,
                    execution=execution,
                    hook=hook,
                    error_code="SYNC_HOOK_OUTPUT_INVALID",
                    detail="Hook returned output without valid decision or allowed field",
                    duration_us=duration_us,
                )
                continue

            if is_reject:
                raw_reason = str(output_json.get("reason") or "Transition rejected by hook")
                clean_reason = raw_reason.strip()[:2000]
                await self._record_invocation(
                    session=session,
                    workspace_id=issue.workspace_id,
                    execution_id=execution.id,
                    hook=hook,
                    status="rejected",
                    error_code=None,
                    output_json={"decision": "reject", "reason": clean_reason},
                    duration_us=duration_us,
                )
                execution.status = "rejected"
                execution.verdict_json = {
                    "decision": "reject",
                    "reason": clean_reason,
                }
                execution.completed_at = dt.datetime.now(dt.UTC)
                await session.flush()
                await record_activity(
                    session=session,
                    workspace_id=issue.workspace_id,
                    object_id=issue.id,
                    actor_principal_id=actor.principal_id,
                    event_type=ActivityEventType.SYNC_HOOK_REJECTED,
                    payload={"hook_name": hook.name, "reason": clean_reason},
                )
                raise ProblemException(
                    code="TRANSITION_REJECTED_BY_HOOK",
                    status=422,
                    title="Transition Rejected by Hook",
                    detail=clean_reason,
                    extra={"hook_name": hook.name, "reason": clean_reason},
                )

            # Mutator field_updates validation and application
            if hook.hook_kind == "sync_mutator" and "field_updates" in output_json:
                field_updates = output_json.get("field_updates")
                if isinstance(field_updates, dict) and field_updates:
                    try:
                        validate_field_updates(hook.allowed_mutable_fields, field_updates)
                    except ProblemException:
                        if hook.failure_policy == "fail_open_warn":
                            await self._record_invocation(
                                session=session,
                                workspace_id=issue.workspace_id,
                                execution_id=execution.id,
                                hook=hook,
                                status="error",
                                error_code="HOOK_MUTATION_NOT_ALLOWED",
                                duration_us=duration_us,
                            )
                            await record_activity(
                                session=session,
                                workspace_id=issue.workspace_id,
                                object_id=issue.id,
                                actor_principal_id=actor.principal_id,
                                event_type=ActivityEventType.HOOK_FAIL_OPEN_WARN,
                                payload={
                                    "hook_name": hook.name,
                                    "error": "HOOK_MUTATION_NOT_ALLOWED",
                                },
                            )
                            continue
                        await self._record_invocation(
                            session=session,
                            workspace_id=issue.workspace_id,
                            execution_id=execution.id,
                            hook=hook,
                            status="error",
                            error_code="HOOK_MUTATION_NOT_ALLOWED",
                            duration_us=duration_us,
                        )
                        execution.status = "rejected"
                        execution.completed_at = dt.datetime.now(dt.UTC)
                        await session.flush()
                        raise

                    await apply_field_updates(session, issue, field_updates, actor)
                    await self._record_invocation(
                        session=session,
                        workspace_id=issue.workspace_id,
                        execution_id=execution.id,
                        hook=hook,
                        status="mutated",
                        output_json=output_json,
                        duration_us=duration_us,
                    )
                    continue

            # Standard allowed validator/mutator outcome
            await self._record_invocation(
                session=session,
                workspace_id=issue.workspace_id,
                execution_id=execution.id,
                hook=hook,
                status="allowed",
                output_json=output_json,
                duration_us=duration_us,
            )

        sync_duration_ms = cumulative_wasm_ms

        # 6. Check for asynchronous agent interceptors
        if agent_hooks:
            return await self.async_dispatcher.dispatch(session, execution, agent_hooks, actor)

        # 7. No async gates: commit state change
        old_state_id = issue.state_id
        issue.state_id = target_state.id
        execution.status = "approved"
        execution.completed_at = dt.datetime.now(dt.UTC)

        if comment_markdown:
            norm_comment = normalize_to_markdown(comment_markdown)
            if norm_comment:
                comment = IssueComment(
                    workspace_id=issue.workspace_id,
                    issue_id=issue.id,
                    author_id=actor.principal_id,
                    body_markdown=norm_comment,
                )
                session.add(comment)

        await session.flush()

        await record_activity(
            session=session,
            workspace_id=issue.workspace_id,
            object_id=issue.id,
            actor_principal_id=actor.principal_id,
            event_type=ActivityEventType.ISSUE_STATE_CHANGED,
            payload={
                "from_state_id": str(old_state_id),
                "to_state_id": str(target_state.id),
                "from_state": from_state.name,
                "to_state": target_state.name,
            },
        )

        return TransitionOutcome(
            status_code=200,
            execution_id=execution.id,
            status="approved",
            state=target_state.name,
            to_state_id=target_state.id,
            from_state_id=old_state_id,
            sync_duration_ms=sync_duration_ms,
        )

    async def _resolve_target_state(
        self,
        session: AsyncSession,
        project_id: uuid.UUID,
        to_state: str | uuid.UUID,
    ) -> WorkflowState:
        """Resolve destination WorkflowState by UUID or exact name."""
        if isinstance(to_state, uuid.UUID):
            st = await session.get(WorkflowState, to_state)
            if st is not None and st.project_id == project_id:
                return st
        elif isinstance(to_state, str):
            state_str = to_state.strip()
            try:
                state_uuid = uuid.UUID(state_str)
                st = await session.get(WorkflowState, state_uuid)
                if st is not None and st.project_id == project_id:
                    return st
            except ValueError:
                pass

            stmt = select(WorkflowState).where(
                WorkflowState.project_id == project_id,
                WorkflowState.name.ilike(state_str),
            )
            found = (await session.execute(stmt)).scalar_one_or_none()
            if found is not None:
                return found

        raise ProblemException(
            code="INVALID_STATE",
            status=422,
            title="Invalid State",
            detail=f"Target state '{to_state}' does not exist in this project",
        )

    async def _fetch_wasm_bytes(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        wasm_module_sha256: bytes | None,
    ) -> bytes | None:
        """Query approved wasm module binary by sha256 with in-memory caching."""
        if wasm_module_sha256 is None:
            return None
        cached = _WASM_BYTES_CACHE.get(wasm_module_sha256)
        if cached is not None:
            return cached
        stmt = select(ApprovedWasmModule.wasm_bytes).where(
            ApprovedWasmModule.workspace_id == workspace_id,
            ApprovedWasmModule.sha256 == wasm_module_sha256,
        )
        res = (await session.execute(stmt)).scalar_one_or_none()
        if res is not None:
            _WASM_BYTES_CACHE[wasm_module_sha256] = bytes(res)
        return res

    async def _handle_hook_failure(  # noqa: PLR0913, PLR0917
        self,
        session: AsyncSession,
        issue: Issue,
        execution: WorkflowTransitionExecution,
        hook: WorkflowTransitionHook,
        error_code: str,
        detail: str,
        duration_us: int,
    ) -> None:
        """Handle synchronous hook budget, execution, or validation failure."""
        if hook.failure_policy == "fail_open_warn":
            await self._record_invocation(
                session=session,
                workspace_id=issue.workspace_id,
                execution_id=execution.id,
                hook=hook,
                status="error",
                error_code=error_code,
                duration_us=duration_us,
            )
            await record_activity(
                session=session,
                workspace_id=issue.workspace_id,
                object_id=issue.id,
                actor_principal_id=execution.invoking_principal_id,
                event_type=ActivityEventType.HOOK_FAIL_OPEN_WARN,
                payload={"hook_name": hook.name, "error_code": error_code, "detail": detail},
            )
            return

        await self._record_invocation(
            session=session,
            workspace_id=issue.workspace_id,
            execution_id=execution.id,
            hook=hook,
            status="error",
            error_code=error_code,
            duration_us=duration_us,
        )
        execution.status = "rejected"
        execution.completed_at = dt.datetime.now(dt.UTC)
        await session.flush()
        raise ProblemException(
            code=error_code,
            status=422,
            title="Sync Hook Error",
            detail=detail,
            extra={"hook_name": hook.name},
        )

    async def _record_invocation(  # noqa: PLR0913, PLR0917
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        execution_id: uuid.UUID,
        hook: WorkflowTransitionHook,
        status: str,
        error_code: str | None = None,
        output_json: dict[str, Any] | None = None,
        duration_us: int | None = None,
    ) -> None:
        """Persist a single WorkflowHookInvocation row."""
        inv = WorkflowHookInvocation(
            id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
            workspace_id=workspace_id,
            execution_id=execution_id,
            hook_id=hook.id,
            hook_kind=hook.hook_kind,
            status=status,
            error_code=error_code,
            output_json=output_json,
            duration_us=duration_us,
            completed_at=dt.datetime.now(dt.UTC),
        )
        session.add(inv)

    async def _build_hook_input(
        self,
        session: AsyncSession,
        issue: Issue,
        from_state: WorkflowState,
        to_state: WorkflowState,
        actor: PrincipalContext,
    ) -> dict[str, Any]:
        """Construct the kb-sync-hook-input/v1 JSON input payload."""
        prio = await session.get(ProjectPriority, issue.priority_id)
        prio_slug = prio.slug if prio else "normal"

        labels_stmt = (
            select(ProjectLabel.name)
            .join(IssueLabel, IssueLabel.label_id == ProjectLabel.id)
            .where(IssueLabel.issue_id == issue.id)
        )
        labels = list((await session.execute(labels_stmt)).scalars().all())

        assignees_stmt = select(IssueAssignee).where(IssueAssignee.issue_id == issue.id)
        assignees = list((await session.execute(assignees_stmt)).scalars().all())
        assignees_list: list[str] = [
            str(a.principal_id) if a.principal_id else (a.free_text_assignee or "")
            for a in assignees
        ]

        # Fetch project identifier for issue key
        proj_ident = (
            await session.execute(select(Project.identifier).where(Project.id == issue.project_id))
        ).scalar_one_or_none()
        issue_key = f"{proj_ident}-{issue.sequence_id}" if proj_ident else str(issue.id)

        return {
            "contract": "kb-sync-hook-input/v1",
            "schema": "kb-sync-hook-input/v1",
            "issue": {
                "id": str(issue.id),
                "key": issue_key,
                "summary": issue.summary,
                "description_markdown": issue.description_markdown,
                "priority": prio_slug,
                "labels": labels,
                "assignees": assignees_list,
                "custom_fields": {},
            },
            "transition": {
                "from_state": {"id": str(from_state.id), "name": from_state.name},
                "to_state": {"id": str(to_state.id), "name": to_state.name},
            },
            "actor": {
                "principal_id": str(actor.principal_id),
                "role": "MEMBER",
            },
        }
