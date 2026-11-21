# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Background runner executing GateWorker against asynchronous transition gates (S14.3, KAN-45)."""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, text

from agent.gates.worker import GateWorker, HarnessRegistry
from database.models.agent_definition import AgentDefinition
from database.models.issues import Issue
from database.models.projects import Project, WorkflowState
from database.models.workflow import (
    WorkflowHookInvocation,
    WorkflowTransitionExecution,
    WorkflowTransitionHook,
)
from database.session import RLSContext, RLSSessionFactory
from kanban.workflows.async_gate import GateCoordinator

if TYPE_CHECKING:
    from agent.context.transition_context import RepoContext

logger = logging.getLogger(__name__)

__all__ = [
    "GateWorkerRunner",
    "start_gate_worker",
]


class GateWorkerRunner:
    """Consumes pending transition gate invocations and coordinates asynchronous decisions."""

    def __init__(
        self,
        session_factory: RLSSessionFactory | None = None,
        harness_registry: HarnessRegistry | None = None,
        poll_interval_s: float = 1.0,
        workspace_id: uuid.UUID | None = None,
        admin_principal_id: uuid.UUID | None = None,
    ) -> None:
        """Initialize runner with session factory, harness registry, and poll interval."""
        self.session_factory = session_factory
        self.registry = harness_registry or HarnessRegistry()
        self.poll_interval_s = poll_interval_s
        self.workspace_id = workspace_id
        self.admin_principal_id = admin_principal_id
        self.worker = GateWorker(
            registry=self.registry,
            coordinator=self,
            entity_loader=self._load_entities,
        )
        self._active_invocations: set[uuid.UUID] = set()
        self._execution_contexts: dict[uuid.UUID, dict[str, Any]] = {}

    @property
    def active_invocations(self) -> frozenset[uuid.UUID]:
        """Active leased invocation IDs currently being processed."""
        return frozenset(self._active_invocations)

    async def _resolve_workspace_and_admin(
        self,
    ) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        """Resolve target workspace and administrative/agent principal."""
        ws_id = self.workspace_id
        admin_pid = self.admin_principal_id

        if ws_id is not None and admin_pid is not None:
            return ws_id, admin_pid

        if self.session_factory is None:
            return ws_id, admin_pid

        engine = getattr(self.session_factory, "engine", None) or getattr(
            self.session_factory, "_engine", None
        )
        if engine is not None:
            try:
                async with engine.connect() as conn:
                    if ws_id is None:
                        res = await conn.execute(text("SELECT get_default_workspace_id()"))
                        ws_id = res.scalar()
                    if admin_pid is None:
                        res = await conn.execute(
                            text("SELECT principal_id FROM kb_auth.local_get_credential('admin')")
                        )
                        row = res.first()
                        if row is not None:
                            admin_pid = row[0]
            except Exception as exc:  # noqa: BLE001
                logger.debug("Could not resolve workspace/admin from DB: %s", exc)

        return ws_id, admin_pid

    async def record_decision(
        self, execution_id: object, hook_id: object, decision: object
    ) -> None:
        """Forward validated decision to GateCoordinator within an authorized RLS session."""
        if self.session_factory is None:
            return

        exec_uuid = (
            execution_id
            if isinstance(execution_id, uuid.UUID)
            else (uuid.UUID(str(execution_id)) if execution_id else None)
        )
        ctx_info = self._execution_contexts.get(exec_uuid, {}) if exec_uuid else {}
        ws_id = ctx_info.get("workspace_id") or self.workspace_id or uuid.UUID(int=0)
        p_id = (
            ctx_info.get("admin_principal_id")
            or self.admin_principal_id
            or ctx_info.get("agent_principal_id")
            or uuid.UUID(int=0)
        )

        admin_ctx = RLSContext(
            principal_id=p_id,
            workspace_id=ws_id,
            token_scopes=("admin",),
            aal_level=2,
        )
        async with self.session_factory.session(admin_ctx) as session:
            await GateCoordinator.record_decision(
                session=session,
                execution_id=execution_id,  # type: ignore[arg-type]
                hook_id=hook_id,  # type: ignore[arg-type]
                decision=decision,  # type: ignore[arg-type]
            )
            await session.commit()

    async def record_failure(
        self,
        execution_id: object,
        hook_id: object,
        code: str,
        *,
        invocation_id: uuid.UUID | str | None = None,
        detail: str | None = None,
    ) -> None:
        """Forward failure or timeout to GateCoordinator within an authorized RLS session."""
        if self.session_factory is None:
            return

        exec_uuid = (
            execution_id
            if isinstance(execution_id, uuid.UUID)
            else (uuid.UUID(str(execution_id)) if execution_id else None)
        )
        ctx_info = self._execution_contexts.get(exec_uuid, {}) if exec_uuid else {}
        ws_id = ctx_info.get("workspace_id") or self.workspace_id or uuid.UUID(int=0)
        p_id = (
            ctx_info.get("admin_principal_id")
            or self.admin_principal_id
            or ctx_info.get("agent_principal_id")
            or uuid.UUID(int=0)
        )

        admin_ctx = RLSContext(
            principal_id=p_id,
            workspace_id=ws_id,
            token_scopes=("admin",),
            aal_level=2,
        )
        async with self.session_factory.session(admin_ctx) as session:
            if invocation_id is not None:
                await GateCoordinator(session).record_failure(
                    invocation_id=invocation_id,
                    error_code=code,
                    detail=detail,
                )
            else:
                await GateCoordinator.record_failure(
                    session=session,
                    execution_id=execution_id,  # type: ignore[arg-type]
                    hook_id=hook_id,  # type: ignore[arg-type]
                    code=code,
                    detail=detail,
                )
            await session.commit()

    async def _load_entities(
        self, event: object
    ) -> tuple[object, object, object, RepoContext | None, object]:
        """Load execution, issue, agent_def, and metadata from database."""
        payload: dict[str, Any] = (
            event
            if isinstance(event, dict)
            else (
                getattr(event, "payload", {})
                if isinstance(getattr(event, "payload", None), dict)
                else {}
            )
        )
        execution_id_str = str(payload.get("execution_id") or getattr(event, "execution_id", ""))
        hook_id_str = str(payload.get("hook_id") or getattr(event, "hook_id", ""))
        agent_def_id_str = str(
            payload.get("agent_definition_id") or getattr(event, "agent_definition_id", "")
        )

        if self.session_factory is None:
            return (
                payload.get("execution"),
                payload.get("issue"),
                payload.get("agent_def"),
                None,
                payload.get("mcp_urls"),
            )

        exec_uuid = uuid.UUID(execution_id_str) if execution_id_str else None
        ctx_info = self._execution_contexts.get(exec_uuid, {}) if exec_uuid else {}
        ws_id_val = payload.get("workspace_id")
        ws_id = (
            (uuid.UUID(str(ws_id_val)) if ws_id_val else None)
            or ctx_info.get("workspace_id")
            or self.workspace_id
            or uuid.UUID(int=0)
        )
        admin_pid_val = payload.get("admin_principal_id")
        agent_pid_val = payload.get("agent_principal_id")
        p_id = (
            (uuid.UUID(str(admin_pid_val)) if admin_pid_val else None)
            or ctx_info.get("admin_principal_id")
            or self.admin_principal_id
            or (uuid.UUID(str(agent_pid_val)) if agent_pid_val else None)
            or ctx_info.get("agent_principal_id")
            or uuid.UUID(int=0)
        )

        admin_ctx = RLSContext(
            principal_id=p_id,
            workspace_id=ws_id,
            token_scopes=("admin",),
            aal_level=2,
        )
        async with self.session_factory.session(admin_ctx) as session:
            exec_uuid_val = uuid.UUID(execution_id_str)
            hook_uuid_val = uuid.UUID(hook_id_str)
            execution = await session.get(WorkflowTransitionExecution, exec_uuid_val)
            hook = await session.get(WorkflowTransitionHook, hook_uuid_val)
            agent_def = (
                await session.get(AgentDefinition, uuid.UUID(agent_def_id_str))
                if agent_def_id_str
                else (
                    await session.get(AgentDefinition, hook.agent_definition_id)
                    if hook and hook.agent_definition_id
                    else None
                )
            )
            issue = await session.get(Issue, execution.issue_id) if execution else None
            project = await session.get(Project, execution.project_id) if execution else None
            from_state = (
                await session.get(WorkflowState, execution.from_state_id) if execution else None
            )
            to_state = (
                await session.get(WorkflowState, execution.to_state_id) if execution else None
            )

            exec_dict = {
                "id": str(execution.id) if execution else execution_id_str,
                "project_key": project.identifier if project else "KAN",
                "from_state": from_state.name if from_state else "Unknown",
                "to_state": to_state.name if to_state else "Done",
                "actor": str(execution.invoking_principal_id) if execution else "@system",
                "allowed_mutable_fields": (
                    hook.allowed_mutable_fields if hook else ("labels", "priority")
                ),
            }
            issue_dict = {
                "key": (
                    f"{project.identifier}-{issue.sequence_id}"
                    if project and issue
                    else str(issue.id if issue else "")
                ),
                "summary": issue.summary if issue else "",
                "description_markdown": issue.description_markdown if issue else "",
            }
            agent_dict = {
                "slug": agent_def.slug if agent_def else "agent",
                "harness_kind": agent_def.harness_kind if agent_def else "in_app_sdk",
                "timeout_ms": agent_def.timeout_ms if agent_def else 60000,
                "repo_access_mode": agent_def.repo_access_mode if agent_def else "read-only",
                "cli_binary_allowlist_id": (
                    agent_def.cli_binary_allowlist_id if agent_def else None
                ),
                "model_identifier": agent_def.model_id if agent_def else None,
            }
            return exec_dict, issue_dict, agent_dict, None, None

    async def poll_once(self) -> int:  # noqa: C901, PLR0912, PLR0915
        """Poll for pending running gate hook invocations with lease claiming and timeout sweep."""
        if self.session_factory is None:
            return 0

        handled = 0
        now = dt.datetime.now(dt.UTC)

        ws_id, admin_pid = await self._resolve_workspace_and_admin()
        bound_ws = ws_id or uuid.UUID(int=0)
        bound_pid = admin_pid or uuid.UUID(int=0)

        # 1. Short read transaction to claim/resolve invocations with
        # ZERO row locks held across dispatch
        admin_ctx = RLSContext(
            principal_id=bound_pid,
            workspace_id=bound_ws,
            token_scopes=("admin",),
            aal_level=2,
        )

        expired_candidates: list[dict[str, Any]] = []
        active_candidates: list[dict[str, Any]] = []

        async with self.session_factory.session(admin_ctx) as session:
            # Query ONLY valid status 'running' and hook_kind 'agent_interceptor'
            sweep_stmt = (
                select(WorkflowHookInvocation)
                .where(
                    WorkflowHookInvocation.status == "running",
                    WorkflowHookInvocation.hook_kind == "agent_interceptor",
                )
                .order_by(WorkflowHookInvocation.started_at)
                .limit(50)
            )
            raw_candidates = list((await session.execute(sweep_stmt)).scalars().all())

            for inv in raw_candidates:
                agent_pid = None
                agent_def_id = None
                timeout_ms = 60000
                if hasattr(session, "get"):
                    try:
                        hook = await session.get(WorkflowTransitionHook, inv.hook_id)
                        if hook and hook.agent_definition_id:
                            agent_def_id = hook.agent_definition_id
                            agent_def = await session.get(AgentDefinition, hook.agent_definition_id)
                            if agent_def:
                                agent_pid = agent_def.principal_id
                                if agent_def.timeout_ms:
                                    timeout_ms = agent_def.timeout_ms
                    except (AttributeError, KeyError, TypeError) as exc:
                        logger.debug("Failed resolving hook agent info for sweep: %s", exc)

                deadline = getattr(inv, "deadline_at", None)
                if deadline is None and getattr(inv, "started_at", None) is not None:
                    deadline = inv.started_at + dt.timedelta(milliseconds=timeout_ms)

                info = {
                    "invocation_id": inv.id,
                    "execution_id": inv.execution_id,
                    "hook_id": inv.hook_id,
                    "workspace_id": getattr(inv, "workspace_id", bound_ws),
                    "agent_definition_id": agent_def_id,
                    "agent_principal_id": agent_pid,
                    "admin_principal_id": bound_pid,
                    "deadline_at": deadline,
                    "started_at": getattr(inv, "started_at", now),
                }
                if deadline is not None and deadline < now:
                    expired_candidates.append(info)
                elif inv.status == "running":
                    active_candidates.append(info)

        # Notice: The read session above is COMMITTED and CLOSED!
        # ZERO row locks are held on PostgreSQL across dispatch!

        # 2. Process expired invocations (GATE_TIMEOUT)
        for item in expired_candidates:
            inv_id = item["invocation_id"]
            exec_id = item["execution_id"]
            hook_id = item["hook_id"]
            if inv_id in self._active_invocations:
                continue

            self._active_invocations.add(inv_id)
            self._execution_contexts[exec_id] = item
            try:
                await self.record_failure(
                    exec_id,
                    hook_id,
                    "GATE_TIMEOUT",
                    invocation_id=inv_id,
                    detail="Async agent gate exceeded deadline_at",
                )
                handled += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("Error recording gate timeout failure: %s", exc)
            finally:
                self._active_invocations.discard(inv_id)
                self._execution_contexts.pop(exec_id, None)

        # 3. Dispatch active non-expired invocations with in-memory lease guard
        for item in active_candidates:
            inv_id = item["invocation_id"]
            exec_id = item["execution_id"]
            hook_id = item["hook_id"]
            if inv_id in self._active_invocations:
                continue

            self._active_invocations.add(inv_id)
            self._execution_contexts[exec_id] = item
            event = {
                "execution_id": str(exec_id),
                "hook_id": str(hook_id),
                "agent_definition_id": (
                    str(item["agent_definition_id"]) if item.get("agent_definition_id") else ""
                ),
                "workspace_id": str(item["workspace_id"]),
                "agent_principal_id": (
                    str(item["agent_principal_id"]) if item.get("agent_principal_id") else ""
                ),
                "admin_principal_id": (
                    str(item["admin_principal_id"]) if item.get("admin_principal_id") else ""
                ),
            }
            try:
                await self.worker.handle_dispatch(event)
                handled += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("Error handling gate dispatch: %s", exc)
            finally:
                self._active_invocations.discard(inv_id)
                self._execution_contexts.pop(exec_id, None)

        return handled

    async def run(self, stop_event: asyncio.Event) -> None:
        """Run runner poll loop until stop_event is set."""
        while not stop_event.is_set():
            try:
                await self.poll_once()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Gate worker runner poll iteration error: %s", exc)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop_event.wait(), timeout=self.poll_interval_s)


async def start_gate_worker(
    app: object,
    session_target: RLSSessionFactory | None = None,
    workspace_id: uuid.UUID | None = None,
    admin_principal_id: uuid.UUID | None = None,
) -> tuple[asyncio.Task[None], asyncio.Event]:
    """Start background gate worker task during application lifespan."""
    stop_event = asyncio.Event()
    sf = session_target
    if sf is None and hasattr(app, "state"):
        sf = getattr(app.state, "session_factory", None)
    runner = GateWorkerRunner(
        session_factory=sf,
        workspace_id=workspace_id,
        admin_principal_id=admin_principal_id,
    )
    task = asyncio.create_task(runner.run(stop_event))
    return task, stop_event
