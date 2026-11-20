# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: PLR0913, PLR0917
"""Mandatory unit tests for GateTimeoutSweeper (KB-P5-18, S14.1)."""

from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from database.models.agent_definition import AgentDefinition
from database.models.issues import Issue, IssueComment
from database.models.outbox import OutboxEvent
from database.models.principals import Principal
from database.models.projects import WorkflowState
from database.models.workflow import (
    WorkflowHookInvocation,
    WorkflowTransitionExecution,
    WorkflowTransitionHook,
)
from kanban.workflows.gate_sweeper import GateTimeoutSweeper
from kanban.workflows.manifest import compute_hook_manifest_sha256

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def record_transition(status_before: str, event: str, status_after: str) -> None:
    """Append transition to state-transitions.txt proof file."""
    qa_path = Path("docs/qa/KANBA-150/state-transitions.txt")
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = qa_path.read_text(encoding="utf-8").splitlines() if qa_path.exists() else []
    tup_line = f"{status_before} -> {event} -> {status_after}"
    if tup_line not in existing_lines:
        existing_lines.append(tup_line)
    qa_path.write_text("\n".join(sorted(existing_lines)) + "\n", encoding="utf-8")


async def create_agent_definition(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID | None,
    slug: str = "sweeper-agent",
    display_name: str = "Sweeper Bot",
    timeout_ms: int = 5000,
) -> tuple[AgentDefinition, Principal]:
    """Provision agent definition."""
    agent_p = Principal(
        id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
        workspace_id=workspace_id,
        principal_type="AGENT",
        display_name=display_name,
    )
    session.add(agent_p)
    await session.flush()

    agent_def = AgentDefinition(
        id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
        workspace_id=workspace_id,
        project_id=project_id,
        principal_id=agent_p.id,
        slug=slug,
        display_name=display_name,
        harness_kind="in_app_sdk",
        provider_kind="openai",
        model_id="gpt-4o",
        timeout_ms=timeout_ms,
    )
    session.add(agent_def)
    await session.commit()
    return agent_def, agent_p


async def create_agent_hook(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    agent_def_id: uuid.UUID,
    *,
    to_state_id: uuid.UUID,
    from_state_id: uuid.UUID | None = None,
    sort_rank: str = "10",
    name: str = "agent_gate",
    failure_policy: str = "fail_closed",
) -> WorkflowTransitionHook:
    """Create agent hook."""
    manifest_sha = compute_hook_manifest_sha256(
        hook_kind="agent_interceptor",
        wasm_module_sha256=None,
        agent_definition_id=agent_def_id,
        allowed_mutable_fields=[],
        failure_policy=failure_policy,
        from_state_id=from_state_id,
        to_state_id=to_state_id,
    )
    hook = WorkflowTransitionHook(
        id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
        workspace_id=workspace_id,
        project_id=project_id,
        from_state_id=from_state_id,
        to_state_id=to_state_id,
        sort_rank=sort_rank,
        name=name,
        hook_kind="agent_interceptor",
        is_enabled=True,
        wasm_module_sha256=None,
        agent_definition_id=agent_def_id,
        allowed_mutable_fields=[],
        failure_policy=failure_policy,
        manifest_sha256=manifest_sha,
    )
    session.add(hook)
    await session.commit()
    return hook


async def _get_states(session: AsyncSession, project_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """Fetch workflow state IDs by name."""
    await session.rollback()
    stmt = select(WorkflowState.name, WorkflowState.id).where(
        WorkflowState.project_id == project_id
    )
    rows = (await session.execute(stmt)).all()
    return {str(r[0]): r[1] for r in rows}


async def test_sweeper_frozen_clock_fail_closed(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Sweeper at deadline_at - 100ms is a no-op; at deadline_at + 1ms terminates with timed_out."""
    admin = await make_user("sw_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("SWP", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    in_prog_id = states["In Progress"]
    done_id = states["Done"]

    # 5,000 ms timeout
    agent_def, agent_p = await create_agent_definition(
        api_env.seed, api_env.workspace_id, proj_id, slug="slow-agent", timeout_ms=5000
    )
    hook = await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_def.id,
        to_state_id=done_id,
        failure_policy="fail_closed",
        name="slow_gate",
    )

    create_resp = await client.post(
        "/api/v1/projects/SWP/issues",
        json={
            "summary": "Sweeper Issue",
            "description_markdown": "Test",
            "state_id": str(in_prog_id),
        },
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]
    issue_id = uuid.UUID(create_resp.json()["id"])
    await api_env.seed.rollback()

    # Enter pending_async
    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    assert t_resp.status_code == 202
    exec_id = uuid.UUID(t_resp.json()["execution_id"])

    await api_env.seed.rollback()
    inv = (
        await api_env.seed.execute(
            select(WorkflowHookInvocation).where(
                WorkflowHookInvocation.execution_id == exec_id,
                WorkflowHookInvocation.hook_id == hook.id,
            )
        )
    ).scalar_one()
    started_at = inv.started_at

    # 1. Clock at deadline - 100ms -> sweeper does nothing (returns 0)
    clock_before = started_at + dt.timedelta(milliseconds=4900)
    swept_before = await GateTimeoutSweeper.run_once(api_env.seed, now=clock_before)
    await api_env.seed.commit()
    assert swept_before == 0

    await api_env.seed.rollback()
    exec_check = (
        await api_env.seed.execute(
            select(WorkflowTransitionExecution).where(WorkflowTransitionExecution.id == exec_id)
        )
    ).scalar_one()
    assert exec_check.status == "pending_async"

    # 2. Clock at deadline + 1ms -> sweeper detects timeout!
    clock_after = started_at + dt.timedelta(milliseconds=5001)
    swept_after = await GateTimeoutSweeper.run_once(api_env.seed, now=clock_after)
    await api_env.seed.commit()
    assert swept_after == 1

    record_transition("pending_async", "TIMEOUT", "timed_out")

    # Verify execution is timed_out, hold cleared, comment posted
    await api_env.seed.rollback()
    exec_post = (
        await api_env.seed.execute(
            select(WorkflowTransitionExecution).where(WorkflowTransitionExecution.id == exec_id)
        )
    ).scalar_one()
    assert exec_post.status == "timed_out"

    issue_post = (
        await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))
    ).scalar_one()
    assert issue_post.state_id == in_prog_id
    assert issue_post.pending_transition_exec_id is None

    comments = (
        (await api_env.seed.execute(select(IssueComment).where(IssueComment.issue_id == issue_id)))
        .scalars()
        .all()
    )
    assert len(comments) == 1
    assert "Gate timed out after 5000 ms" in comments[0].body_markdown
    assert comments[0].author_id == agent_p.id

    # Verify outbox event emitted
    ev = (
        await api_env.seed.execute(
            select(OutboxEvent).where(
                OutboxEvent.object_id == issue_id,
                OutboxEvent.topic == "workflow.gate.timed_out",
            )
        )
    ).scalar_one()
    assert ev.payload["execution_id"] == str(exec_id)
    assert "Gate timed out" in ev.payload["reason_preview"]


async def test_sweeper_fail_open_warn(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Sweeper with fail_open_warn logs warning and commits transition on final hook."""
    admin = await make_user("fo_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("FOP", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    todo_id = states["Todo"]
    in_prog_id = states["In Progress"]

    agent_def, _ = await create_agent_definition(
        api_env.seed, api_env.workspace_id, proj_id, slug="warn-agent", timeout_ms=3000
    )
    hook = await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_def.id,
        to_state_id=in_prog_id,
        failure_policy="fail_open_warn",
        name="warn_gate",
    )

    create_resp = await client.post(
        "/api/v1/projects/FOP/issues",
        json={
            "summary": "Fail Open Issue",
            "description_markdown": "Test",
            "state_id": str(todo_id),
        },
    )
    issue_key = create_resp.json()["key"]
    issue_id = uuid.UUID(create_resp.json()["id"])
    await api_env.seed.rollback()

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "In Progress"},
    )
    assert t_resp.status_code == 202
    exec_id = uuid.UUID(t_resp.json()["execution_id"])

    await api_env.seed.rollback()
    inv = (
        await api_env.seed.execute(
            select(WorkflowHookInvocation).where(
                WorkflowHookInvocation.execution_id == exec_id,
                WorkflowHookInvocation.hook_id == hook.id,
            )
        )
    ).scalar_one()
    started_at = inv.started_at

    clock_after = started_at + dt.timedelta(milliseconds=3005)
    swept = await GateTimeoutSweeper.run_once(api_env.seed, now=clock_after)
    await api_env.seed.commit()
    assert swept == 1

    # In fail_open_warn on single hook, transition is allowed to commit to In Progress!
    await api_env.seed.rollback()
    exec_post = (
        await api_env.seed.execute(
            select(WorkflowTransitionExecution).where(WorkflowTransitionExecution.id == exec_id)
        )
    ).scalar_one()
    assert exec_post.status == "approved"

    issue_post = (
        await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))
    ).scalar_one()
    assert issue_post.state_id == in_prog_id
    assert issue_post.pending_transition_exec_id is None


async def test_sweeper_batching_skip_locked(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Sweeper processes multiple timed out executions within batch limit."""
    admin = await make_user("batch_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("BAP", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    in_prog_id = states["In Progress"]
    done_id = states["Done"]

    agent_def, _ = await create_agent_definition(
        api_env.seed, api_env.workspace_id, proj_id, slug="batch-agent", timeout_ms=2000
    )
    await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_def.id,
        to_state_id=done_id,
        failure_policy="fail_closed",
        name="batch_gate",
    )

    # Create 3 issues and trigger transitions
    for i in range(3):
        c_resp = await client.post(
            "/api/v1/projects/BAP/issues",
            json={
                "summary": f"Batch Issue {i}",
                "description_markdown": "Test",
                "state_id": str(in_prog_id),
            },
        )
        ikey = c_resp.json()["key"]
        t_resp = await client.post(
            f"/api/v1/issues/{ikey}/transitions",
            json={"to_state": "Done"},
        )
        assert t_resp.status_code == 202

    # Forward clock by 10 seconds
    future_clock = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=10)
    swept_count = await GateTimeoutSweeper.run_once(api_env.seed, now=future_clock)
    await api_env.seed.commit()
    assert swept_count == 3
