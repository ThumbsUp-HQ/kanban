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

from sqlalchemy import select

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
    ) -> None:
        """Initialize runner with session factory, harness registry, and poll interval."""
        self.session_factory = session_factory
        self.registry = harness_registry or HarnessRegistry()
        self.poll_interval_s = poll_interval_s
        self.worker = GateWorker(
            registry=self.registry,
            coordinator=self,
            entity_loader=self._load_entities,
        )
        self._active_invocations: set[uuid.UUID] = set()

    @property
    def active_invocations(self) -> frozenset[uuid.UUID]:
        """Active leased invocation IDs currently being processed."""
        return frozenset(self._active_invocations)

    async def record_decision(
        self, execution_id: object, hook_id: object, decision: object
    ) -> None:
        """Forward validated decision to GateCoordinator within an administrative session."""
        if self.session_factory is None:
            return

        admin_ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
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

    async def record_failure(self, execution_id: object, hook_id: object, code: str) -> None:
        """Forward failure or timeout to GateCoordinator within an administrative session."""
        if self.session_factory is None:
            return

        admin_ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
            token_scopes=("admin",),
            aal_level=2,
        )
        async with self.session_factory.session(admin_ctx) as session:
            await GateCoordinator.record_failure(
                session=session,
                execution_id=execution_id,  # type: ignore[arg-type]
                hook_id=hook_id,  # type: ignore[arg-type]
                code=code,
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

        admin_ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
            token_scopes=("admin",),
            aal_level=2,
        )
        async with self.session_factory.session(admin_ctx) as session:
            exec_uuid = uuid.UUID(execution_id_str)
            hook_uuid = uuid.UUID(hook_id_str)
            execution = await session.get(WorkflowTransitionExecution, exec_uuid)
            hook = await session.get(WorkflowTransitionHook, hook_uuid)
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

    async def poll_once(self) -> int:  # noqa: C901
        """Poll for pending running gate hook invocations with lease claiming and timeout sweep."""
        if self.session_factory is None:
            return 0

        admin_ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
            token_scopes=("admin",),
            aal_level=2,
        )
        handled = 0
        now = dt.datetime.now(dt.UTC)

        async with self.session_factory.session(admin_ctx) as session:
            # 1. Sweep expired invocations with SKIP LOCKED
            sweep_stmt = (
                select(WorkflowHookInvocation)
                .where(
                    WorkflowHookInvocation.status.in_(["running", "pending_async"]),
                    WorkflowHookInvocation.hook_kind == "agent_interceptor",
                )
                .with_for_update(skip_locked=True)
                .order_by(WorkflowHookInvocation.started_at)
                .limit(50)
            )
            candidates = list((await session.execute(sweep_stmt)).scalars().all())
            expired_invs: list[WorkflowHookInvocation] = []
            active_invs: list[WorkflowHookInvocation] = []

            for inv in candidates:
                deadline = getattr(inv, "deadline_at", None)
                if deadline is None:
                    hook = await session.get(WorkflowTransitionHook, inv.hook_id)
                    agent_def = (
                        await session.get(AgentDefinition, hook.agent_definition_id)
                        if hook and hook.agent_definition_id
                        else None
                    )
                    timeout_ms = (
                        agent_def.timeout_ms if agent_def and agent_def.timeout_ms else 60000
                    )
                    if inv.started_at is not None:
                        deadline = inv.started_at + dt.timedelta(milliseconds=timeout_ms)

                if deadline is not None and deadline < now:
                    expired_invs.append(inv)
                elif inv.status == "running":
                    active_invs.append(inv)

            # Record failure for expired invocations
            for inv in expired_invs:
                try:
                    await GateCoordinator(session).record_failure(
                        invocation_id=inv.id,
                        error_code="GATE_TIMEOUT",
                        detail="Async agent gate exceeded deadline_at",
                    )
                    self._active_invocations.discard(inv.id)
                    handled += 1
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Error recording gate timeout failure: %s", exc)

            # 2. Dispatch active non-expired invocations with in-memory lease guard
            for inv in active_invs:
                if inv.id in self._active_invocations:
                    # Already claimed and executing; prevent double-dispatch
                    continue

                self._active_invocations.add(inv.id)
                event = {
                    "execution_id": str(inv.execution_id),
                    "hook_id": str(inv.hook_id),
                }
                try:
                    await self.worker.handle_dispatch(event)
                    handled += 1
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Error handling gate dispatch: %s", exc)
                finally:
                    self._active_invocations.discard(inv.id)

            await session.commit()
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
    app: object, session_target: RLSSessionFactory | None = None
) -> tuple[asyncio.Task[None], asyncio.Event]:
    """Start background gate worker task during application lifespan."""
    stop_event = asyncio.Event()
    sf = session_target
    if sf is None and hasattr(app, "state"):
        sf = getattr(app.state, "session_factory", None)
    runner = GateWorkerRunner(session_factory=sf)
    task = asyncio.create_task(runner.run(stop_event))
    return task, stop_event
