# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Background sweeper terminating timed out async agent gate executions (KB-P5-18)."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from database.models.agent_definition import AgentDefinition
from database.models.projects import Project
from database.models.workflow import (
    WorkflowHookInvocation,
    WorkflowTransitionExecution,
    WorkflowTransitionHook,
)
from kanban.workflows.async_gate import GateCoordinator

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class GateTimeoutSweeper:
    """Sweeper detecting and failing timed-out async agent gate invocations (KB-P5-18, S14.1)."""

    @classmethod
    async def run_once(
        cls,
        session: AsyncSession,
        now: dt.datetime | None = None,
    ) -> int:
        """Find pending_async executions whose running invocation exceeded deadline_at."""
        if now is None:
            now = dt.datetime.now(dt.UTC)

        fallback_deadline = WorkflowHookInvocation.started_at + func.make_interval(
            0,
            0,
            0,
            0,
            0,
            0,
            func.coalesce(
                WorkflowTransitionHook.timeout_ms,
                Project.default_gate_timeout_ms,
                AgentDefinition.timeout_ms,
                60000,
            )
            / 1000.0,
        )
        effective_deadline = func.coalesce(
            WorkflowHookInvocation.deadline_at,
            fallback_deadline,
        )

        stmt = (
            select(
                WorkflowHookInvocation.execution_id,
                WorkflowHookInvocation.hook_id,
            )
            .join(
                WorkflowTransitionExecution,
                WorkflowTransitionExecution.id == WorkflowHookInvocation.execution_id,
            )
            .join(
                WorkflowTransitionHook,
                WorkflowTransitionHook.id == WorkflowHookInvocation.hook_id,
            )
            .join(
                Project,
                Project.id == WorkflowTransitionExecution.project_id,
            )
            .outerjoin(
                AgentDefinition,
                AgentDefinition.id == WorkflowTransitionHook.agent_definition_id,
            )
            .where(
                WorkflowTransitionExecution.status == "pending_async",
                WorkflowHookInvocation.status == "running",
                effective_deadline <= now,
            )
            .with_for_update(of=WorkflowHookInvocation, skip_locked=True)
            .limit(100)
        )

        rows = (await session.execute(stmt)).all()
        processed = 0
        for exec_id, hook_id in rows:
            await GateCoordinator.record_failure(session, exec_id, hook_id, "TIMED_OUT")
            processed += 1

        if processed > 0:
            await session.flush()

        return processed
