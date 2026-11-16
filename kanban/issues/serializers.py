# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Issue serializer models and helpers for workflow gates (KB-P5-18, S11.2, S14.1)."""

from __future__ import annotations

import datetime as dt
import uuid  # noqa: TC003
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from database.models.agent_definition import AgentDefinition
from database.models.workflow import (
    WorkflowHookInvocation,
    WorkflowTransitionExecution,
    WorkflowTransitionHook,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from database.models.issues import Issue


def compute_harness_label_for_agent(agent_def: AgentDefinition | None) -> str:
    """Compute human-facing harness label for display and event payloads."""
    if agent_def is None:
        return "in_app_sdk"
    if agent_def.harness_kind == "cli_pipe":
        bin_id = agent_def.cli_binary_allowlist_id or "cli"
        if bin_id in ("agy", "codex"):
            return f"cli: {bin_id} -p"
        return f"cli: {bin_id}"
    if agent_def.harness_kind == "in_app_sdk":
        return agent_def.provider_kind or "sdk"
    if agent_def.harness_kind == "remote_runner":
        return f"remote: {agent_def.remote_runner_pool_slug or 'runner'}"
    return agent_def.harness_kind


class PendingGateSummary(BaseModel):
    """Active asynchronous agent transition gate hold metadata."""

    model_config = ConfigDict(extra="forbid")

    execution_id: uuid.UUID
    hook_name: str
    agent_slug: str
    harness_label: str
    started_at: dt.datetime
    deadline_at: dt.datetime


class LatestGateVerdictSummary(BaseModel):
    """Latest completed agent transition gate verdict summary."""

    model_config = ConfigDict(extra="forbid")

    decision: str
    hook_name: str
    completed_at: dt.datetime
    latency_ms: int
    verdict_sha256: str


async def resolve_pending_gate(
    session: AsyncSession,
    issue: Issue,
) -> PendingGateSummary | None:
    """Resolve pending gate metadata if an async transition hold is active."""
    if not issue.pending_transition_exec_id:
        return None

    stmt = (
        select(
            WorkflowTransitionExecution,
            WorkflowHookInvocation,
            WorkflowTransitionHook,
            AgentDefinition,
        )
        .join(
            WorkflowHookInvocation,
            WorkflowHookInvocation.execution_id == WorkflowTransitionExecution.id,
        )
        .join(
            WorkflowTransitionHook,
            WorkflowTransitionHook.id == WorkflowHookInvocation.hook_id,
        )
        .outerjoin(
            AgentDefinition,
            AgentDefinition.id == WorkflowTransitionHook.agent_definition_id,
        )
        .where(
            WorkflowTransitionExecution.id == issue.pending_transition_exec_id,
            WorkflowTransitionExecution.status == "pending_async",
            WorkflowHookInvocation.status == "running",
        )
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if not row:
        return None

    execution, invocation, hook, agent_def = row
    timeout_ms = agent_def.timeout_ms if agent_def and agent_def.timeout_ms else 60000
    deadline_at = invocation.started_at + dt.timedelta(milliseconds=timeout_ms)
    agent_slug = agent_def.slug if agent_def else "agent"
    harness_label = compute_harness_label_for_agent(agent_def)

    return PendingGateSummary(
        execution_id=execution.id,
        hook_name=hook.name,
        agent_slug=agent_slug,
        harness_label=harness_label,
        started_at=invocation.started_at,
        deadline_at=deadline_at,
    )


async def resolve_latest_gate_verdict(
    session: AsyncSession,
    issue: Issue,
) -> LatestGateVerdictSummary | None:
    """Resolve latest terminal gate verdict for this issue."""
    stmt = (
        select(WorkflowTransitionExecution)
        .where(
            WorkflowTransitionExecution.issue_id == issue.id,
            WorkflowTransitionExecution.status.in_(["approved", "rejected", "timed_out"]),
            WorkflowTransitionExecution.verdict_json.is_not(None),
        )
        .order_by(
            WorkflowTransitionExecution.completed_at.desc().nullslast(),
            WorkflowTransitionExecution.created_at.desc(),
        )
        .limit(1)
    )
    execution = (await session.execute(stmt)).scalar_one_or_none()
    if not execution or not execution.verdict_json:
        return None

    v = execution.verdict_json
    decision = str(v.get("decision", execution.status))
    hook_name = str(v.get("hook_name", "agent_gate"))
    completed_at = execution.completed_at or execution.created_at
    latency_ms = int(v.get("latency_ms", 0))
    verdict_sha256 = str(v.get("verdict_sha256", ""))

    return LatestGateVerdictSummary(
        decision=decision,
        hook_name=hook_name,
        completed_at=completed_at,
        latency_ms=latency_ms,
        verdict_sha256=verdict_sha256,
    )
