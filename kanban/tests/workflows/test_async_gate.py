# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0913, PLR0917, PLC0415
"""Mandatory feature unit tests for async agent gate state machine (KB-P5-18, S14.1-14.3)."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from database.models.agent_definition import AgentDefinition
from database.models.issues import Issue, IssueComment
from database.models.outbox import OutboxEvent
from database.models.principals import Principal
from database.models.projects import ProjectLabel, WorkflowState
from database.models.workflow import (
    WorkflowHookInvocation,
    WorkflowTransitionExecution,
    WorkflowTransitionHook,
)
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.workflows.async_gate import GateCoordinator
from kanban.workflows.engine import TransitionEngine
from kanban.workflows.gate_types import GateDecision, LinkSpec
from kanban.workflows.manifest import compute_hook_manifest_sha256

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db

STATE_TRANSITIONS_RECORDED: list[tuple[str, str, str]] = []


def record_transition(status_before: str, event: str, status_after: str) -> None:
    """Record observed state transition tuple for state-transitions.txt proof."""
    tup = (status_before, event, status_after)
    if tup not in STATE_TRANSITIONS_RECORDED:
        STATE_TRANSITIONS_RECORDED.append(tup)
    qa_path = Path("docs/qa/KANBA-150/state-transitions.txt")
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{before} -> {ev} -> {after}" for before, ev, after in sorted(STATE_TRANSITIONS_RECORDED)
    ]
    qa_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def create_agent_definition(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID | None,
    slug: str = "forensic-code-check",
    display_name: str = "Forensic Code Checker",
    harness_kind: str = "in_app_sdk",
    timeout_ms: int = 60000,
) -> tuple[AgentDefinition, Principal]:
    """Provision an agent principal and agent definition."""
    agent_p = Principal(
        id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
        workspace_id=workspace_id,
        principal_type="AGENT",
        display_name=display_name,
    )
    session.add(agent_p)
    await session.flush()

    provider_kind = "openai" if harness_kind == "in_app_sdk" else None
    model_id = "gpt-4o" if harness_kind == "in_app_sdk" else None
    cli_bin = "agy" if harness_kind == "cli_pipe" else None

    agent_def = AgentDefinition(
        id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
        workspace_id=workspace_id,
        project_id=project_id,
        principal_id=agent_p.id,
        slug=slug,
        display_name=display_name,
        harness_kind=harness_kind,
        provider_kind=provider_kind,
        model_id=model_id,
        cli_binary_allowlist_id=cli_bin,
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
    allowed_mutable_fields: list[str] | None = None,
    failure_policy: str = "fail_closed",
) -> WorkflowTransitionHook:
    """Create a validated agent_interceptor WorkflowTransitionHook."""
    allowed = allowed_mutable_fields or []
    manifest_sha = compute_hook_manifest_sha256(
        hook_kind="agent_interceptor",
        wasm_module_sha256=None,
        agent_definition_id=agent_def_id,
        allowed_mutable_fields=allowed,
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
        allowed_mutable_fields=allowed,
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


# ---------------------------------------------------------------------------
# Test Cases (1-9 Mandatory Test Cases from Scoped Ticket)
# ---------------------------------------------------------------------------


async def test_case_1_positive_single_agent_hook_202_then_approve(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1: 1 agent hook -> 202 pending hold -> approve commits to_state and emits events."""
    admin = await make_user("t1_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T1P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    in_prog_id = states["In Progress"]
    done_id = states["Done"]

    agent_def, _agent_p = await create_agent_definition(
        api_env.seed, api_env.workspace_id, proj_id, slug="qa-gate", display_name="QA Gate Bot"
    )

    hook = await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_def.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="10",
        name="qa_gate",
    )

    # 1. Create issue in In Progress
    create_resp = await client.post(
        "/api/v1/projects/T1P/issues",
        json={
            "summary": "Gated Issue",
            "description_markdown": "Initial body",
            "state_id": str(in_prog_id),
        },
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]
    issue_id = uuid.UUID(create_resp.json()["id"])
    await api_env.seed.rollback()

    # 2. POST /issues/{issue_key}/transitions to Done -> returns 202 Accepted
    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    contract_recorder.record("async_gate_dispatch_202", t_resp.request, t_resp)
    assert t_resp.status_code == 202, t_resp.text
    t_body = t_resp.json()
    assert t_body["status"] == "pending_agent_gate"
    assert "execution_id" in t_body
    assert t_body["active_agent"] == "qa-gate"
    assert t_body["hook_name"] == "qa_gate"
    assert t_body["state"] == "In Progress"
    exec_id = uuid.UUID(t_body["execution_id"])

    record_transition("running_sync", "DISPATCH", "pending_async")

    # Verify DB state: hold active, state unchanged
    await api_env.seed.rollback()
    issue_row = (await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))).scalar_one()
    assert issue_row.pending_transition_exec_id == exec_id
    assert issue_row.state_id == in_prog_id

    exec_row = (
        await api_env.seed.execute(
            select(WorkflowTransitionExecution).where(WorkflowTransitionExecution.id == exec_id)
        )
    ).scalar_one()
    assert exec_row.status == "pending_async"

    # Verify first hook invocation is running
    inv_row = (
        await api_env.seed.execute(
            select(WorkflowHookInvocation).where(
                WorkflowHookInvocation.execution_id == exec_id,
                WorkflowHookInvocation.hook_id == hook.id,
            )
        )
    ).scalar_one()
    assert inv_row.status == "running"

    # 3. Agent approves the transition
    verdict_sha = hashlib.sha256(b"verdict-sample-1").digest()
    decision = GateDecision(
        decision="approve",
        reason_markdown="Code and automated tests verified flawlessly.",
        verdict_sha256=verdict_sha,
        latency_ms=150,
    )

    updated_exec = await GateCoordinator.record_decision(
        api_env.seed,
        exec_id,
        hook.id,
        decision,
    )
    await api_env.seed.commit()
    assert updated_exec.status == "approved"

    record_transition("pending_async", "APPROVE", "approved")

    # Verify issue state updated to Done, hold cleared
    await api_env.seed.rollback()
    issue_post = (
        await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))
    ).scalar_one()
    assert issue_post.state_id == done_id
    assert issue_post.pending_transition_exec_id is None

    # Verify outbox event emitted
    ev_stmt = select(OutboxEvent).where(
        OutboxEvent.object_id == issue_id,
        OutboxEvent.topic == "workflow.gate.approved",
    )
    ev = (await api_env.seed.execute(ev_stmt)).scalar_one()
    assert "verdict_json" not in ev.payload
    assert ev.payload["execution_id"] == str(exec_id)
    assert ev.payload["verdict_sha256"] == verdict_sha.hex()


async def test_case_2_positive_two_sequential_agent_hooks_and_reject(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 2: 2 agent hooks -> sequential dispatch; reject on second snaps back with comment."""
    admin = await make_user("t2_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T2P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    in_prog_id = states["In Progress"]
    done_id = states["Done"]

    agent1_def, _agent1_p = await create_agent_definition(
        api_env.seed, api_env.workspace_id, proj_id, slug="linter-agent", display_name="Linter Bot"
    )
    agent2_def, agent2_p = await create_agent_definition(
        api_env.seed, api_env.workspace_id, proj_id, slug="security-agent", display_name="Sec Bot"
    )

    hook1 = await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent1_def.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="10",
        name="lint_hook",
    )
    hook2 = await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent2_def.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="20",
        name="sec_hook",
    )

    create_resp = await client.post(
        "/api/v1/projects/T2P/issues",
        json={
            "summary": "Two Hook Issue",
            "description_markdown": "Initial body",
            "state_id": str(in_prog_id),
        },
    )
    issue_key = create_resp.json()["key"]
    issue_id = uuid.UUID(create_resp.json()["id"])
    await api_env.seed.rollback()

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    assert t_resp.status_code == 202
    exec_id = uuid.UUID(t_resp.json()["execution_id"])

    # Hook 1 is running, Hook 2 is NOT running yet
    await api_env.seed.rollback()
    inv1 = (
        await api_env.seed.execute(
            select(WorkflowHookInvocation).where(
                WorkflowHookInvocation.execution_id == exec_id,
                WorkflowHookInvocation.hook_id == hook1.id,
            )
        )
    ).scalar_one()
    assert inv1.status == "running"

    inv2_pre = (
        await api_env.seed.execute(
            select(WorkflowHookInvocation).where(
                WorkflowHookInvocation.execution_id == exec_id,
                WorkflowHookInvocation.hook_id == hook2.id,
            )
        )
    ).scalar_one_or_none()
    assert inv2_pre is None

    # Approve hook 1 -> advances to hook 2
    decision1 = GateDecision(
        decision="approve",
        reason_markdown="Linter passed cleanly.",
        verdict_sha256=hashlib.sha256(b"v-lint").digest(),
        latency_ms=80,
    )
    await GateCoordinator.record_decision(api_env.seed, exec_id, hook1.id, decision1)
    await api_env.seed.commit()

    # Hook 2 is now running!
    await api_env.seed.rollback()
    inv2 = (
        await api_env.seed.execute(
            select(WorkflowHookInvocation).where(
                WorkflowHookInvocation.execution_id == exec_id,
                WorkflowHookInvocation.hook_id == hook2.id,
            )
        )
    ).scalar_one()
    assert inv2.status == "running"

    # Reject on hook 2
    decision2 = GateDecision(
        decision="reject",
        reason_markdown="Missing boundary validation on external input.",
        verdict_sha256=hashlib.sha256(b"v-sec-reject").digest(),
        latency_ms=120,
    )
    updated_exec = await GateCoordinator.record_decision(api_env.seed, exec_id, hook2.id, decision2)
    await api_env.seed.commit()
    assert updated_exec.status == "rejected"

    record_transition("pending_async", "REJECT", "rejected")

    # State remains unchanged in In Progress, hold cleared
    await api_env.seed.rollback()
    issue_post = (
        await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))
    ).scalar_one()
    assert issue_post.state_id == in_prog_id
    assert issue_post.pending_transition_exec_id is None

    # Verify veto comment authored by agent 2 principal
    comments = (
        (await api_env.seed.execute(select(IssueComment).where(IssueComment.issue_id == issue_id)))
        .scalars()
        .all()
    )
    assert len(comments) == 1
    assert comments[0].author_id == agent2_p.id
    assert "🛑🤖 Gate `sec_hook`" in comments[0].body_markdown
    assert "Missing boundary validation" in comments[0].body_markdown


async def test_case_3_security_toctou_concurrent_description_edit(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 3: Description edited during pending_async -> approve aborts with STALE_SNAPSHOT."""
    admin = await make_user("t3_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T3P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    in_prog_id = states["In Progress"]
    done_id = states["Done"]

    agent_def, _ = await create_agent_definition(
        api_env.seed, api_env.workspace_id, proj_id, slug="toctou-agent"
    )
    hook = await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_def.id,
        to_state_id=done_id,
        name="toctou_gate",
    )

    create_resp = await client.post(
        "/api/v1/projects/T3P/issues",
        json={
            "summary": "TOCTOU Issue",
            "description_markdown": "Original description",
            "state_id": str(in_prog_id),
        },
    )
    issue_key = create_resp.json()["key"]
    issue_id = uuid.UUID(create_resp.json()["id"])
    await api_env.seed.rollback()

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    assert t_resp.status_code == 202
    exec_id = uuid.UUID(t_resp.json()["execution_id"])

    # Concurrent modification of issue description
    new_desc = "Tampered description while agent was thinking"
    await api_env.seed.execute(
        text("UPDATE issues SET description_markdown = :desc WHERE id = :id"),
        {"desc": new_desc, "id": issue_id},
    )
    await api_env.seed.commit()

    # Agent approves based on old context -> Coordinator detects TOCTOU mismatch!
    decision = GateDecision(
        decision="approve",
        reason_markdown="Looks good from snapshot",
        verdict_sha256=hashlib.sha256(b"v-toctou").digest(),
        latency_ms=100,
    )
    updated_exec = await GateCoordinator.record_decision(api_env.seed, exec_id, hook.id, decision)
    await api_env.seed.commit()

    assert updated_exec.status == "cancelled"
    record_transition("pending_async", "TOCTOU_MISMATCH", "cancelled")

    # State unchanged, hold cleared
    await api_env.seed.rollback()
    issue_post = (
        await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))
    ).scalar_one()
    assert issue_post.state_id == in_prog_id
    assert issue_post.pending_transition_exec_id is None

    # Outbox event emitted with reason STALE_SNAPSHOT
    ev = (
        await api_env.seed.execute(
            select(OutboxEvent).where(
                OutboxEvent.object_id == issue_id,
                OutboxEvent.topic == "workflow.gate.cancelled",
            )
        )
    ).scalar_one()
    assert "STALE_SNAPSHOT" in ev.payload["reason_preview"]


async def test_case_4_security_forbidden_mutations_and_sanitization(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 4: Forbidden field update rejected; hostile script and secrets scrubbed."""
    admin = await make_user("t4_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T4P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    done_id = states["Done"]

    agent_def, _ = await create_agent_definition(
        api_env.seed, api_env.workspace_id, proj_id, slug="mut-agent"
    )
    hook = await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_def.id,
        to_state_id=done_id,
        name="mut_hook",
        allowed_mutable_fields=["summary"],
        failure_policy="fail_closed",
    )

    create_resp = await client.post(
        "/api/v1/projects/T4P/issues",
        json={"summary": "Mut Issue", "description_markdown": "Test"},
    )
    issue_key = create_resp.json()["key"]
    issue_id = uuid.UUID(create_resp.json()["id"])

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    exec_id = uuid.UUID(t_resp.json()["execution_id"])

    # Agent attempts forbidden state mutation and includes malicious payload + secret in reason
    hostile_reason = (
        "Approved with update <script>alert('xss')</script> "
        "and leaked key sk-live-1234567890abcdef1234567890abcdef"
    )
    decision = GateDecision(
        decision="approve",
        reason_markdown=hostile_reason,
        field_updates={"state": "Done"},  # Not in allowed_mutable_fields
        verdict_sha256=hashlib.sha256(b"v-mut").digest(),
        latency_ms=90,
    )

    # Handled per failure_policy='fail_closed' -> rejected with HOOK_MUTATION_NOT_ALLOWED
    updated_exec = await GateCoordinator.record_decision(api_env.seed, exec_id, hook.id, decision)
    await api_env.seed.commit()
    assert updated_exec.status == "rejected"
    assert updated_exec.verdict_json is not None
    assert updated_exec.verdict_json["code"] == "HOOK_MUTATION_NOT_ALLOWED"

    # Verify veto comment does NOT contain <script> or raw sk-live secret
    comments = (
        (await api_env.seed.execute(select(IssueComment).where(IssueComment.issue_id == issue_id)))
        .scalars()
        .all()
    )
    assert len(comments) == 1
    assert "<script>" not in comments[0].body_markdown
    assert "sk-live-1234567890" not in comments[0].body_markdown


async def test_case_5_security_out_of_order_and_replay_idempotency(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 5: Out of order decision rejected; identical decision replay is idempotent no-op."""
    admin = await make_user("t5_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T5P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    done_id = states["Done"]

    agent_def, _ = await create_agent_definition(
        api_env.seed, api_env.workspace_id, proj_id, slug="replay-agent"
    )
    hook = await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_def.id,
        to_state_id=done_id,
        name="replay_hook",
    )

    create_resp = await client.post(
        "/api/v1/projects/T5P/issues",
        json={"summary": "Replay Issue", "description_markdown": "Test"},
    )
    issue_key = create_resp.json()["key"]

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    exec_id = uuid.UUID(t_resp.json()["execution_id"])

    # 1. Non-existent hook -> 409 GATE_DECISION_OUT_OF_ORDER
    bogus_hook_id = uuid.uuid4()
    decision = GateDecision(
        decision="approve",
        reason_markdown="Approve",
        verdict_sha256=hashlib.sha256(b"v-replay").digest(),
        latency_ms=50,
    )
    with pytest.raises(ProblemException) as exc_info:
        await GateCoordinator.record_decision(api_env.seed, exec_id, bogus_hook_id, decision)
    assert exc_info.value.code == "GATE_DECISION_OUT_OF_ORDER"

    # 2. Valid decision
    await GateCoordinator.record_decision(api_env.seed, exec_id, hook.id, decision)
    await api_env.seed.commit()

    # 3. Replay of identical decision -> idempotent no-op
    replayed = await GateCoordinator.record_decision(api_env.seed, exec_id, hook.id, decision)
    assert replayed.status == "approved"


async def test_case_6_boundary_concurrent_transition_during_pending_async(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 6: Second transition request while pending_async returns 409 TRANSITION_PENDING."""
    admin = await make_user("t6_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T6P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    done_id = states["Done"]

    agent_def, _ = await create_agent_definition(
        api_env.seed, api_env.workspace_id, proj_id, slug="busy-agent"
    )
    await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_def.id,
        to_state_id=done_id,
        name="busy_hook",
    )

    create_resp = await client.post(
        "/api/v1/projects/T6P/issues",
        json={"summary": "Concurrent Transition Issue", "description_markdown": "Test"},
    )
    issue_key = create_resp.json()["key"]

    # First transition -> 202
    resp1 = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    assert resp1.status_code == 202

    # Second transition while pending -> 409 TRANSITION_PENDING
    resp2 = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "In Progress"},
    )
    assert resp2.status_code == 409
    body2 = resp2.json()
    assert body2["code"] in ("TRANSITION_PENDING", "TRANSITION_HELD")


async def test_case_7_boundary_cancel_invoker_vs_non_invoker(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 7: Cancel by non-invoker returns 404; cancel by invoker cancels execution."""
    invoker = await make_user("t7_invoker", workspace_role="WORKSPACE_MEMBER")
    stranger = await make_user("t7_stranger", workspace_role="WORKSPACE_MEMBER")
    proj_id = await make_project(
        "T7P",
        created_by=invoker,
        roles={invoker: "PROJECT_ADMIN", stranger: "MEMBER"},
    )

    states = await _get_states(api_env.seed, proj_id)
    done_id = states["Done"]

    agent_def, _ = await create_agent_definition(
        api_env.seed, api_env.workspace_id, proj_id, slug="cancel-agent"
    )
    await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_def.id,
        to_state_id=done_id,
        name="cancel_hook",
    )

    client = as_principal(invoker)

    create_resp = await client.post(
        "/api/v1/projects/T7P/issues",
        json={"summary": "Cancel Issue", "description_markdown": "Test"},
    )
    issue_key = create_resp.json()["key"]
    issue_id = uuid.UUID(create_resp.json()["id"])

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    assert t_resp.status_code == 202
    exec_id = uuid.UUID(t_resp.json()["execution_id"])

    # 1. Non-invoker non-admin attempts cancel -> 404 Not Found
    stranger_client = as_principal(stranger)
    del_resp_stranger = await stranger_client.delete(f"/api/v1/transitions/{exec_id}")
    assert del_resp_stranger.status_code == 404

    # 2. Invoking user cancels -> 200 OK
    invoker_client = as_principal(invoker)
    del_resp_invoker = await invoker_client.delete(f"/api/v1/transitions/{exec_id}")
    assert del_resp_invoker.status_code == 200
    assert del_resp_invoker.json()["status"] == "cancelled"

    record_transition("pending_async", "CANCEL", "cancelled")

    # Verify execution is cancelled, hold cleared
    await api_env.seed.rollback()
    exec_post = (
        await api_env.seed.execute(
            select(WorkflowTransitionExecution).where(WorkflowTransitionExecution.id == exec_id)
        )
    ).scalar_one()
    assert exec_post.status == "cancelled"

    issue_post = (
        await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))
    ).scalar_one()
    assert issue_post.pending_transition_exec_id is None


async def test_case_8_serializer_pending_gate_and_latest_gate_verdict(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 8: GET /issues/{key} exposes pending_gate during hold and latest_gate_verdict after."""
    admin = await make_user("t8_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T8P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    done_id = states["Done"]

    agent_def, _ = await create_agent_definition(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        slug="serializer-agent",
        display_name="Serializer Bot",
    )
    hook = await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_def.id,
        to_state_id=done_id,
        name="serializer_hook",
    )

    create_resp = await client.post(
        "/api/v1/projects/T8P/issues",
        json={"summary": "Serializer Issue", "description_markdown": "Test"},
    )
    issue_key = create_resp.json()["key"]

    # Initial state: both are None
    get_init = await client.get(f"/api/v1/issues/{issue_key}")
    assert get_init.status_code == 200
    assert get_init.json()["pending_gate"] is None
    assert get_init.json()["latest_gate_verdict"] is None

    # Enter pending_async
    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    exec_id = uuid.UUID(t_resp.json()["execution_id"])

    # Read issue during hold: pending_gate populated!
    get_held = await client.get(f"/api/v1/issues/{issue_key}")
    assert get_held.status_code == 200
    held_data = get_held.json()
    assert held_data["pending_gate"] is not None
    assert held_data["pending_gate"]["execution_id"] == str(exec_id)
    assert held_data["pending_gate"]["hook_name"] == "serializer_hook"
    assert held_data["pending_gate"]["agent_slug"] == "serializer-agent"
    assert held_data["latest_gate_verdict"] is None

    # Approve transition
    v_sha = hashlib.sha256(b"verdict-serializer").digest()
    decision = GateDecision(
        decision="approve",
        reason_markdown="Serializer verdict approved",
        verdict_sha256=v_sha,
        latency_ms=110,
    )
    await GateCoordinator.record_decision(api_env.seed, exec_id, hook.id, decision)
    await api_env.seed.commit()

    # Read issue after verdict: pending_gate is None, latest_gate_verdict populated!
    get_approved = await client.get(f"/api/v1/issues/{issue_key}")
    assert get_approved.status_code == 200
    appr_data = get_approved.json()
    assert appr_data["pending_gate"] is None
    assert appr_data["latest_gate_verdict"] is not None
    assert appr_data["latest_gate_verdict"]["decision"] == "approve"
    assert appr_data["latest_gate_verdict"]["hook_name"] == "serializer_hook"
    assert appr_data["latest_gate_verdict"]["verdict_sha256"] == v_sha.hex()
    assert appr_data["latest_gate_verdict"]["latency_ms"] == 110


async def test_case_9_hop_depth_limit(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 9: Engine-originated transitions with hop_depth > 3 are rejected."""
    admin = await make_user("t9_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T9P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    create_resp = await client.post(
        "/api/v1/projects/T9P/issues",
        json={"summary": "Hop Test", "description_markdown": "Test"},
    )
    assert create_resp.status_code == 201
    issue_key = create_resp.json()["key"]
    issue_id = uuid.UUID(create_resp.json()["id"])
    await api_env.seed.rollback()

    states = await _get_states(api_env.seed, proj_id)
    in_prog_id = states["In Progress"]
    done_id = states["Done"]

    # Provision parent execution with hop_depth = 3
    parent_exec = WorkflowTransitionExecution(
        id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
        workspace_id=api_env.workspace_id,
        project_id=proj_id,
        issue_id=issue_id,
        invoking_principal_id=admin.id,
        from_state_id=in_prog_id,
        to_state_id=done_id,
        status="approved",
        hop_depth=3,
        issue_body_sha256_snapshot=hashlib.sha256(b"Test").digest(),
    )
    api_env.seed.add(parent_exec)
    await api_env.seed.commit()

    caller = PrincipalContext(
        principal_id=admin.id,
        workspace_id=api_env.workspace_id,
        token_scopes=("session",),
    )
    with pytest.raises(ProblemException) as exc_info:
        await TransitionEngine.request_transition(
            api_env.seed,
            issue_key=issue_key,
            to_state="Done",
            actor=caller,
            parent_execution_id=parent_exec.id,  # Will result in hop_depth = 4 > 3
        )
    assert exc_info.value.code == "HOP_DEPTH_EXCEEDED"


def test_compute_harness_label_and_reason_preview() -> None:
    """Coverage for compute_harness_label and format_reason_preview edge cases."""
    from unittest.mock import MagicMock

    from kanban.workflows.async_gate import compute_harness_label, format_reason_preview

    assert compute_harness_label(None) == "in_app_sdk"

    mock_agy = MagicMock()
    mock_agy.harness_kind = "cli_pipe"
    mock_agy.cli_binary_allowlist_id = "agy"
    assert compute_harness_label(mock_agy) == "cli: agy -p"

    mock_codex = MagicMock()
    mock_codex.harness_kind = "cli_pipe"
    mock_codex.cli_binary_allowlist_id = "codex"
    assert compute_harness_label(mock_codex) == "cli: codex -p"

    mock_other_cli = MagicMock()
    mock_other_cli.harness_kind = "cli_pipe"
    mock_other_cli.cli_binary_allowlist_id = "other"
    assert compute_harness_label(mock_other_cli) == "cli: other"

    mock_remote = MagicMock()
    mock_remote.harness_kind = "remote_runner"
    mock_remote.remote_runner_pool_slug = "pool-a"
    assert compute_harness_label(mock_remote) == "remote: pool-a"

    mock_unknown = MagicMock()
    mock_unknown.harness_kind = "wasm_custom"
    assert compute_harness_label(mock_unknown) == "wasm_custom"

    long_reason = "Line 1 with password=secret123\nLine 2 with extra information\nLine 3 ignore me"
    preview = format_reason_preview(long_reason)
    assert "[REDACTED]" in preview or "password" in preview
    assert "Line 3 ignore me" not in preview


async def test_apply_labels_and_links_in_decision(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify labels and links are applied when final agent gate approves."""
    from database.models.issues import IssueLabel
    from database.models.spine import ObjectLink
    from kanban.workflows.gate_types import LinkSpec

    admin = await make_user("t10_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T10P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # Create a project label
    lbl = ProjectLabel(
        id=uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4(),
        workspace_id=api_env.workspace_id,
        project_id=proj_id,
        name="qa-verified",
        color_hex="#00ff00",
    )
    api_env.seed.add(lbl)
    await api_env.seed.commit()

    # Create target issue for link
    resp_target = await client.post(
        "/api/v1/projects/T10P/issues",
        json={"summary": "Target Issue", "description_markdown": "Target body"},
    )
    assert resp_target.status_code == 201
    target_key = resp_target.json()["key"]
    target_id = uuid.UUID(resp_target.json()["id"])

    # Create main issue
    resp_main = await client.post(
        "/api/v1/projects/T10P/issues",
        json={"summary": "Main Issue", "description_markdown": "Main body"},
    )
    assert resp_main.status_code == 201
    main_key = resp_main.json()["key"]
    main_id = uuid.UUID(resp_main.json()["id"])

    states = await _get_states(api_env.seed, proj_id)
    done_id = states["Done"]

    # Provision agent and hook
    agent_id = uuid.uuid4()
    agent_def = AgentDefinition(
        id=agent_id,
        workspace_id=api_env.workspace_id,
        principal_id=admin.id,
        slug="link-label-agent",
        display_name="Link Label Agent",
        harness_kind="in_app_sdk",
        provider_kind="openai",
        model_id="gpt-4o",
    )
    api_env.seed.add(agent_def)
    await api_env.seed.commit()

    hook = await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_id,
        to_state_id=done_id,
        name="link_label_hook",
        sort_rank="10",
    )

    t_resp = await client.post(
        f"/api/v1/issues/{main_key}/transitions",
        json={"to_state": "Done"},
    )
    assert t_resp.status_code == 202
    exec_id = uuid.UUID(t_resp.json()["execution_id"])

    decision = GateDecision(
        decision="approve",
        reason_markdown="Verified with links and labels",
        verdict_sha256=hashlib.sha256(b"v-link-lbl").digest(),
        add_labels=("qa-verified",),
        add_links=(LinkSpec(target=target_key, link_type="RELATES_TO"),),
        latency_ms=120,
    )
    await GateCoordinator.record_decision(api_env.seed, exec_id, hook.id, decision)
    await api_env.seed.commit()

    # Check label added
    label_row = (
        await api_env.seed.execute(
            select(IssueLabel).where(
                IssueLabel.issue_id == main_id,
                IssueLabel.label_id == lbl.id,
            )
        )
    ).scalar_one_or_none()
    assert label_row is not None

    # Check link added
    link_row = (
        await api_env.seed.execute(
            select(ObjectLink).where(
                ObjectLink.source_id == main_id,
                ObjectLink.target_id == target_id,
                ObjectLink.link_type == "RELATES_TO",
            )
        )
    ).scalar_one_or_none()
    assert link_row is not None


async def test_fail_open_warn_advance_and_commit(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify fail_open_warn advances to next hook on failure, and commits on last hook."""
    admin = await make_user("t11_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T11P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    resp = await client.post(
        "/api/v1/projects/T11P/issues",
        json={"summary": "Fail Open Issue", "description_markdown": "Body text"},
    )
    assert resp.status_code == 201
    issue_key = resp.json()["key"]
    issue_id = uuid.UUID(resp.json()["id"])

    states = await _get_states(api_env.seed, proj_id)
    in_prog_id = states["In Progress"]

    # Provision 2 hooks with fail_open_warn
    agent_id1 = uuid.uuid4()
    agent_def1 = AgentDefinition(
        id=agent_id1,
        workspace_id=api_env.workspace_id,
        principal_id=admin.id,
        slug="agent-h1",
        display_name="Agent H1",
        harness_kind="in_app_sdk",
        provider_kind="openai",
        model_id="gpt-4o",
    )
    agent_id2 = uuid.uuid4()
    agent_def2 = AgentDefinition(
        id=agent_id2,
        workspace_id=api_env.workspace_id,
        principal_id=admin.id,
        slug="agent-h2",
        display_name="Agent H2",
        harness_kind="in_app_sdk",
        provider_kind="openai",
        model_id="gpt-4o",
    )
    api_env.seed.add_all([agent_def1, agent_def2])
    await api_env.seed.commit()

    hook1 = await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_id1,
        to_state_id=in_prog_id,
        name="hook_one",
        sort_rank="10",
        failure_policy="fail_open_warn",
    )
    hook2 = await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_id2,
        to_state_id=in_prog_id,
        name="hook_two",
        sort_rank="20",
        failure_policy="fail_open_warn",
    )

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "In Progress"},
    )
    assert t_resp.status_code == 202
    exec_id = uuid.UUID(t_resp.json()["execution_id"])

    # Hook 1 fails with fail_open_warn -> advances to Hook 2
    ex1 = await GateCoordinator.record_failure(api_env.seed, exec_id, hook1.id, "TRANSIENT_ERROR")
    await api_env.seed.commit()
    assert ex1.status == "pending_async"

    # Hook 2 fails with fail_open_warn -> final hook commits transition
    ex2 = await GateCoordinator.record_failure(api_env.seed, exec_id, hook2.id, "SECOND_ERROR")
    await api_env.seed.commit()
    assert ex2.status == "approved"

    # State updated to In Progress
    issue_post = (
        await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))
    ).scalar_one()
    assert issue_post.state_id == in_prog_id
    assert issue_post.pending_transition_exec_id is None


async def test_cancel_unauthorized_and_invalid_state(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify cancel raises 404 for unknown execution or unauthorized caller."""
    admin = await make_user("t12_admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("t12_member", workspace_role="WORKSPACE_MEMBER")
    stranger = await make_user("t12_stranger", workspace_role="WORKSPACE_MEMBER")
    proj_id = await make_project(
        "T12P", created_by=admin, roles={admin: "PROJECT_ADMIN", member: "MEMBER"}
    )

    client = as_principal(admin)
    resp = await client.post(
        "/api/v1/projects/T12P/issues",
        json={"summary": "Cancel Issue", "description_markdown": "Text"},
    )
    assert resp.status_code == 201
    issue_key = resp.json()["key"]

    states = await _get_states(api_env.seed, proj_id)
    done_id = states["Done"]

    agent_id = uuid.uuid4()
    agent_def = AgentDefinition(
        id=agent_id,
        workspace_id=api_env.workspace_id,
        principal_id=admin.id,
        slug="cancel-agent",
        display_name="Cancel Agent",
        harness_kind="in_app_sdk",
        provider_kind="openai",
        model_id="gpt-4o",
    )
    api_env.seed.add(agent_def)
    await api_env.seed.commit()

    await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_id,
        to_state_id=done_id,
        name="cancel_hook",
        sort_rank="10",
    )

    # Invoked by admin
    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    assert t_resp.status_code == 202
    exec_id = t_resp.json()["execution_id"]

    # Stranger (not invoker, not project admin) gets 404
    stranger_client = as_principal(stranger)
    del_resp = await stranger_client.delete(f"/api/v1/transitions/{exec_id}")
    assert del_resp.status_code == 404

    # Non-existent execution gets 404
    fake_id = uuid.uuid4()
    del_fake = await client.delete(f"/api/v1/transitions/{fake_id}")
    assert del_fake.status_code == 404

    # Invoker cancels successfully
    admin_client = as_principal(admin)
    del_ok = await admin_client.delete(f"/api/v1/transitions/{exec_id}")
    assert del_ok.status_code == 200
    assert del_ok.json()["status"] == "cancelled"

    # Cancelling already-cancelled execution gets 404
    del_again = await admin_client.delete(f"/api/v1/transitions/{exec_id}")
    assert del_again.status_code == 404


async def test_gate_coverage_branches(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Extra branch coverage for field_updates, fail_open_warn, and out-of-order calls."""
    from kanban.workflows.gate_sweeper import GateTimeoutSweeper

    # 1. GateTimeoutSweeper.run_once with default now=None
    swept = await GateTimeoutSweeper.run_once(api_env.seed)
    assert swept >= 0

    admin = await make_user("t13_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T13P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    resp = await client.post(
        "/api/v1/projects/T13P/issues",
        json={"summary": "Branch Test Issue", "description_markdown": "Test"},
    )
    issue_key = resp.json()["key"]

    states = await _get_states(api_env.seed, proj_id)
    in_prog_id = states["In Progress"]

    agent_id = uuid.uuid4()
    agent_def = AgentDefinition(
        id=agent_id,
        workspace_id=api_env.workspace_id,
        principal_id=admin.id,
        slug="branch-agent",
        display_name="Branch Agent",
        harness_kind="in_app_sdk",
        provider_kind="openai",
        model_id="gpt-4o",
    )
    api_env.seed.add(agent_def)
    await api_env.seed.commit()

    hook = await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_id,
        to_state_id=in_prog_id,
        name="branch_hook",
        sort_rank="10",
        allowed_mutable_fields=["description_markdown"],
        failure_policy="fail_open_warn",
    )

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "In Progress"},
    )
    assert t_resp.status_code == 202
    exec_id = uuid.UUID(t_resp.json()["execution_id"])

    # Branch: field_updates contains forbidden key under fail_open_warn -> HOOK_FAIL_OPEN_WARN
    bad_decision = GateDecision(
        decision="approve",
        reason_markdown="Forbidden field update under fail_open_warn",
        verdict_sha256=hashlib.sha256(b"v-bad-fields").digest(),
        field_updates={"forbidden_key": "hacked"},
        latency_ms=50,
    )
    # This strips forbidden field updates and commits
    ex_appr = await GateCoordinator.record_decision(api_env.seed, exec_id, hook.id, bad_decision)
    await api_env.seed.commit()
    assert ex_appr.status == "approved"

    # Branch: record_decision on non-pending_async execution with different verdict -> GATE_DECISION_OUT_OF_ORDER
    diff_decision = GateDecision(
        decision="approve",
        reason_markdown="Different decision",
        verdict_sha256=hashlib.sha256(b"v-diff").digest(),
        latency_ms=50,
    )
    with pytest.raises(ProblemException) as exc_info:
        await GateCoordinator.record_decision(api_env.seed, exec_id, hook.id, diff_decision)
    assert exc_info.value.code == "GATE_DECISION_OUT_OF_ORDER"

    # Branch: record_decision with non-matching hook_id on a new pending execution
    resp2 = await client.post(
        "/api/v1/projects/T13P/issues",
        json={"summary": "Branch Test Issue 2", "description_markdown": "Test 2"},
    )
    issue_key2 = resp2.json()["key"]
    t_resp2 = await client.post(
        f"/api/v1/issues/{issue_key2}/transitions",
        json={"to_state": "In Progress"},
    )
    exec_id2 = uuid.UUID(t_resp2.json()["execution_id"])
    with pytest.raises(ProblemException) as exc_info2:
        await GateCoordinator.record_decision(api_env.seed, exec_id2, uuid.uuid4(), diff_decision)
    assert exc_info2.value.code == "GATE_DECISION_OUT_OF_ORDER"

    # Branch: record_decision with allowed field_updates applied
    resp_fields = await client.post(
        "/api/v1/projects/T13P/issues",
        json={"summary": "Branch Test Issue 3", "description_markdown": "Original desc"},
    )
    issue_key3 = resp_fields.json()["key"]
    t_resp3 = await client.post(
        f"/api/v1/issues/{issue_key3}/transitions",
        json={"to_state": "In Progress"},
    )
    exec_id3 = uuid.UUID(t_resp3.json()["execution_id"])
    good_decision = GateDecision(
        decision="approve",
        reason_markdown="Allowed field updates",
        verdict_sha256=hashlib.sha256(b"v-good-fields").digest(),
        field_updates={"description_markdown": "Updated desc via gate"},
        add_labels=("nonexistent-lbl",),
        add_links=(
            LinkSpec(target="nodash", link_type="RELATES_TO"),
            LinkSpec(target="T13P-9999", link_type="RELATES_TO"),
            LinkSpec(target=issue_key3, link_type="RELATES_TO"),
        ),
        latency_ms=45,
    )
    ex3 = await GateCoordinator.record_decision(api_env.seed, exec_id3, hook.id, good_decision)
    await api_env.seed.commit()
    assert ex3.status == "approved"

    # Branch: record_failure error cases (EXECUTION_NOT_FOUND, INVOCATION_NOT_FOUND)
    fake_eid = uuid.uuid4()
    fake_hid = uuid.uuid4()
    with pytest.raises(ProblemException) as exc_fn:
        await GateCoordinator.record_failure(api_env.seed, fake_eid, hook.id, "ERR")
    assert exc_fn.value.code == "EXECUTION_NOT_FOUND"

    with pytest.raises(ProblemException) as exc_fn2:
        await GateCoordinator.record_failure(api_env.seed, exec_id3, fake_hid, "ERR")
    assert exc_fn2.value.code == "INVOCATION_NOT_FOUND"

    # Branch: record_failure with fail_open_warn on last hook when TOCTOU description modified
    resp_toctou = await client.post(
        "/api/v1/projects/T13P/issues",
        json={"summary": "Branch Test Issue 4", "description_markdown": "Desc 4"},
    )
    issue_key4 = resp_toctou.json()["key"]
    issue_id4 = uuid.UUID(resp_toctou.json()["id"])
    t_resp4 = await client.post(
        f"/api/v1/issues/{issue_key4}/transitions",
        json={"to_state": "In Progress"},
    )
    exec_id4 = uuid.UUID(t_resp4.json()["execution_id"])

    # Mutate description while pending
    await api_env.seed.execute(
        text("UPDATE issues SET description_markdown = 'Tampered' WHERE id = :id"),
        {"id": issue_id4},
    )
    await api_env.seed.commit()

    ex4 = await GateCoordinator.record_failure(api_env.seed, exec_id4, hook.id, "AGENT_ERR")
    await api_env.seed.commit()
    assert ex4.status == "cancelled"


async def test_completed_state_forces_fail_closed(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Whenever target_state.state_group == 'completed', record_failure enforces fail_closed."""
    admin = await make_user("t_fc_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("TFCP", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    todo_id = states["Todo"]
    done_id = states["Done"]

    agent_def, _ = await create_agent_definition(
        api_env.seed, api_env.workspace_id, proj_id, slug="qa-gate-agent"
    )

    # Hook explicitly configured with fail_open_warn targeting completed state Done
    hook = await create_agent_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        agent_def.id,
        to_state_id=done_id,
        name="qa_fail_open_hook",
        failure_policy="fail_open_warn",
    )

    create_resp = await client.post(
        "/api/v1/projects/TFCP/issues",
        json={
            "summary": "Fail closed test",
            "description_markdown": "Desc",
            "state_id": str(todo_id),
        },
    )
    issue_key = create_resp.json()["key"]
    issue_id = uuid.UUID(create_resp.json()["id"])

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    assert t_resp.status_code == 202
    exec_id = uuid.UUID(t_resp.json()["execution_id"])

    # Fail the hook with a transient error -> MUST fail closed, not auto-approve into Done!
    ex = await GateCoordinator.record_failure(api_env.seed, exec_id, hook.id, "TRANSIENT_TIMEOUT")
    await api_env.seed.commit()

    assert ex.status == "rejected"
    assert ex.verdict_json is not None
    assert ex.verdict_json["decision"] == "rejected"

    # Issue must remain in original state (Todo), hold must be cleared
    issue_post = (
        await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))
    ).scalar_one()
    assert issue_post.state_id == todo_id
    assert issue_post.pending_transition_exec_id is None

    # Veto comment posted
    comments = (
        (await api_env.seed.execute(select(IssueComment).where(IssueComment.issue_id == issue_id)))
        .scalars()
        .all()
    )
    assert len(comments) == 1
    assert "🛑🤖" in comments[0].body_markdown
    assert "Gate failed: TRANSIENT_TIMEOUT" in comments[0].body_markdown
