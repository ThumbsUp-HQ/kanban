# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0913, PLR0917, ARG001, ANN401, PLC0415, D401, PLR0915, TRY003, EM101
"""Comprehensive unit and integration tests for dry_run transition pipeline (KB-P5-17b).

Verifies strict non-persistence guarantees, step-by-step hook execution simulation,
synthetic issue provisioning, mutator and validator execution, and rowcount invariance.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING, Any

import pytest
import wasmtime
from sqlalchemy import func, select, text

from database.models.activity import ActivityRecord
from database.models.agent_definition import AgentDefinition
from database.models.issues import Issue
from database.models.projects import ProjectPriority, WorkflowState
from database.models.spine import ObjectRecord
from database.models.wasm_module import ApprovedWasmModule
from database.models.workflow import (
    WorkflowHookInvocation,
    WorkflowTransitionExecution,
    WorkflowTransitionHook,
)
from kanban.workflows.manifest import compute_hook_manifest_sha256

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _make_wat_bytes(json_payload: str) -> bytes:
    """Compile a minimal WASM module that outputs json_payload."""
    escaped = json_payload.replace('"', '\\"')
    byte_len = len(json_payload.encode("utf-8"))
    wat = f"""(module
  (import "env" "kb_output" (func $kb_output (param i32 i32)))
  (memory (export "memory") 1)
  (data (i32.const 1024) "{escaped}")
  (func (export "kb_alloc") (param $len i32) (result i32) i32.const 2048)
  (func (export "kb_run") (param $ptr i32) (param $len i32) (result i32)
    (call $kb_output (i32.const 1024) (i32.const {byte_len}))
    i32.const 0
  )
)
"""
    return bytes(wasmtime.wat2wasm(wat))


async def _seed_approved_wasm(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    admin_id: uuid.UUID,
    name: str,
    wasm_bytes: bytes,
) -> bytes:
    """Seed an ApprovedWasmModule and return its raw 32-byte sha256."""
    sha = hashlib.sha256(wasm_bytes).digest()
    mod = ApprovedWasmModule(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        project_id=project_id,
        sha256=sha,
        name=name,
        wasm_bytes=wasm_bytes,
        approved_by_id=admin_id,
    )
    session.add(mod)
    await session.commit()
    return sha


async def _seed_agent_definition(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    admin_id: uuid.UUID,
    slug: str = "qa-interceptor",
    name: str = "QA Interceptor Agent",
) -> uuid.UUID:
    """Seed an AgentDefinition and return its ID."""
    agent_id = uuid.uuid4()
    agent = AgentDefinition(
        id=agent_id,
        workspace_id=workspace_id,
        principal_id=admin_id,
        slug=slug,
        display_name=name,
        harness_kind="in_app_sdk",
        provider_kind="openai",
        model_id="gpt-4o",
    )
    session.add(agent)
    await session.commit()
    return agent_id


@pytest.fixture
async def dry_run_env(
    api_env: ApiEnv,
    make_user: Any,
    make_project: Any,
) -> dict[str, Any]:
    """Setup project, admin and member principals, states, approved wasm modules, and hooks."""
    admin: SeededUser = await make_user("dr_admin")
    member: SeededUser = await make_user("dr_member")

    project_id = await make_project(
        "DRPROJ",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", member: "MEMBER"},
    )

    session = api_env.seed
    states_res = await session.execute(
        select(WorkflowState).where(WorkflowState.project_id == project_id)
    )
    states_by_name = {st.name: st for st in states_res.scalars().all()}

    # Ensure In QA exists
    if "In QA" not in states_by_name:
        in_qa_state = WorkflowState(
            id=uuid.uuid4(),
            workspace_id=api_env.workspace_id,
            project_id=project_id,
            name="In QA",
            state_group="started",
            color_hex="#8b5cf6",
            sort_order=35,
        )
        session.add(in_qa_state)
        await session.commit()
        states_by_name["In QA"] = in_qa_state

    # Seed wasm modules: pass, mutate, reject
    pass_wasm = _make_wat_bytes('{"allow": true}')
    mutate_wasm = _make_wat_bytes('{"mutations": {"priority": "urgent"}}')
    reject_wasm = _make_wat_bytes('{"allow": false, "reason": "Missing forensic proof"}')

    pass_sha = await _seed_approved_wasm(
        session, api_env.workspace_id, project_id, admin.id, "pass.wasm", pass_wasm
    )
    mutate_sha = await _seed_approved_wasm(
        session, api_env.workspace_id, project_id, admin.id, "mutate.wasm", mutate_wasm
    )
    reject_sha = await _seed_approved_wasm(
        session, api_env.workspace_id, project_id, admin.id, "reject.wasm", reject_wasm
    )

    agent_id = await _seed_agent_definition(session, api_env.workspace_id, admin.id)

    return {
        "admin": admin,
        "member": member,
        "project_id": project_id,
        "states": states_by_name,
        "pass_sha": pass_sha,
        "mutate_sha": mutate_sha,
        "reject_sha": reject_sha,
        "agent_id": agent_id,
        "api_env": api_env,
    }


async def _get_table_counts(session: AsyncSession, workspace_id: uuid.UUID) -> dict[str, int]:
    """Snapshot row counts across critical tables for this workspace."""
    issues_cnt = await session.scalar(
        select(func.count(Issue.id)).where(Issue.workspace_id == workspace_id)
    )
    exec_cnt = await session.scalar(
        select(func.count(WorkflowTransitionExecution.id)).where(
            WorkflowTransitionExecution.workspace_id == workspace_id
        )
    )
    inv_cnt = await session.scalar(
        select(func.count(WorkflowHookInvocation.id)).where(
            WorkflowHookInvocation.workspace_id == workspace_id
        )
    )
    act_cnt = await session.scalar(
        select(func.count(ActivityRecord.id)).where(ActivityRecord.workspace_id == workspace_id)
    )
    obj_cnt = await session.scalar(
        select(func.count(ObjectRecord.id)).where(ObjectRecord.workspace_id == workspace_id)
    )
    return {
        "issues": issues_cnt or 0,
        "workflow_transition_executions": exec_cnt or 0,
        "workflow_hook_invocations": inv_cnt or 0,
        "activity_records": act_cnt or 0,
        "objects": obj_cnt or 0,
    }


@pytest.mark.asyncio
async def test_dry_run_access_control(
    dry_run_env: dict[str, Any],
    as_principal: Any,
) -> None:
    """Non-admin callers receive 404 to prevent enumeration (S3.4)."""
    member: SeededUser = dry_run_env["member"]
    client: httpx.AsyncClient = as_principal(member, aal_level=2)

    resp = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "sample_ticket": {
                "summary": "Test Ticket",
                "description_markdown": "Sample description",
                "priority": "medium",
                "labels": [],
            },
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dry_run_validation_errors(
    dry_run_env: dict[str, Any],
    as_principal: Any,
) -> None:
    """Validate mutual exclusivity of sample_ticket and issue_key, and description size limit."""
    admin: SeededUser = dry_run_env["admin"]
    client: httpx.AsyncClient = as_principal(admin, aal_level=2)

    # 1. Both provided -> 422
    resp_both = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "issue_key": "DRPROJ-1",
            "sample_ticket": {
                "summary": "Test Ticket",
                "description_markdown": "Sample description",
                "priority": "medium",
                "labels": [],
            },
        },
    )
    assert resp_both.status_code == 422
    assert "INVALID_DRY_RUN_INPUT" in resp_both.text

    # 2. Neither provided -> 422
    resp_neither = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
        },
    )
    assert resp_neither.status_code == 422
    assert "INVALID_DRY_RUN_INPUT" in resp_neither.text

    # 3. Description > 1 MiB -> 422
    resp_large = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "sample_ticket": {
                "summary": "Huge",
                "description_markdown": "a" * (1024 * 1024 + 5),
                "priority": "medium",
                "labels": [],
            },
        },
    )
    assert resp_large.status_code == 422
    assert "DESCRIPTION_TOO_LARGE" in resp_large.text


@pytest.mark.asyncio
async def test_dry_run_pipeline_steps_and_rowcount_invariance(
    dry_run_env: dict[str, Any],
    as_principal: Any,
) -> None:
    """Execute dry-run with validator, mutator, and agent hooks, and verify zero persistence."""
    api_env: ApiEnv = dry_run_env["api_env"]
    admin: SeededUser = dry_run_env["admin"]
    session: AsyncSession = api_env.seed
    project_id: uuid.UUID = dry_run_env["project_id"]
    states: dict[str, WorkflowState] = dry_run_env["states"]

    in_progress = states["In Progress"]
    in_qa = states["In QA"]

    # 1. Attach validator hook (pass)
    h1_id = uuid.uuid4()
    h1 = WorkflowTransitionHook(
        id=h1_id,
        workspace_id=admin.workspace_id,
        project_id=project_id,
        from_state_id=in_progress.id,
        to_state_id=in_qa.id,
        sort_rank="0000000000000001",
        name="Validator Pass",
        hook_kind="sync_validator",
        is_enabled=True,
        wasm_module_sha256=dry_run_env["pass_sha"],
        failure_policy="fail_closed",
        manifest_sha256=compute_hook_manifest_sha256(
            from_state_id=in_progress.id,
            to_state_id=in_qa.id,
            hook_kind="sync_validator",
            wasm_module_sha256=dry_run_env["pass_sha"],
            failure_policy="fail_closed",
        ),
    )
    session.add(h1)

    # 2. Attach mutator hook (mutates priority)
    h2_id = uuid.uuid4()
    h2 = WorkflowTransitionHook(
        id=h2_id,
        workspace_id=admin.workspace_id,
        project_id=project_id,
        from_state_id=in_progress.id,
        to_state_id=in_qa.id,
        sort_rank="0000000000000002",
        name="Mutator Set Urgent",
        hook_kind="sync_mutator",
        is_enabled=True,
        wasm_module_sha256=dry_run_env["mutate_sha"],
        allowed_mutable_fields=["priority"],
        failure_policy="fail_closed",
        manifest_sha256=compute_hook_manifest_sha256(
            from_state_id=in_progress.id,
            to_state_id=in_qa.id,
            hook_kind="sync_mutator",
            wasm_module_sha256=dry_run_env["mutate_sha"],
            allowed_mutable_fields=["priority"],
            failure_policy="fail_closed",
        ),
    )
    session.add(h2)

    # 3. Attach agent interceptor hook
    h3_id = uuid.uuid4()
    h3 = WorkflowTransitionHook(
        id=h3_id,
        workspace_id=admin.workspace_id,
        project_id=project_id,
        from_state_id=in_progress.id,
        to_state_id=in_qa.id,
        sort_rank="0000000000000003",
        name="Agent QA Gate",
        hook_kind="agent_interceptor",
        is_enabled=True,
        agent_definition_id=dry_run_env["agent_id"],
        failure_policy="fail_closed",
        manifest_sha256=compute_hook_manifest_sha256(
            from_state_id=in_progress.id,
            to_state_id=in_qa.id,
            hook_kind="agent_interceptor",
            agent_definition_id=dry_run_env["agent_id"],
            failure_policy="fail_closed",
        ),
    )
    session.add(h3)
    await session.commit()

    # Capture initial rowcounts BEFORE dry run
    counts_before = await _get_table_counts(session, admin.workspace_id)

    client: httpx.AsyncClient = as_principal(admin, aal_level=2)
    resp = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "sample_ticket": {
                "summary": "Simulation Ticket",
                "description_markdown": "Should execute validator, mutator, and skip agent async",
                "priority": "medium",
                "labels": ["bug"],
            },
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["would_commit"] is True
    assert len(data["steps"]) == 3

    # Step 1: Validator
    step1 = data["steps"][0]
    assert step1["order"] == 1
    assert step1["name"] == "Validator Pass"
    assert step1["hook_kind"] == "sync_validator"
    assert step1["result"] == "allowed"

    # Step 2: Mutator
    step2 = data["steps"][1]
    assert step2["order"] == 2
    assert step2["name"] == "Mutator Set Urgent"
    assert step2["hook_kind"] == "sync_mutator"
    assert step2["result"] == "mutated"
    assert step2["field_updates"] is not None
    assert step2["field_updates"].get("priority") == "urgent"

    # Step 3: Agent Interceptor
    step3 = data["steps"][2]
    assert step3["order"] == 3
    assert step3["name"] == "Agent QA Gate"
    assert step3["hook_kind"] == "agent_interceptor"
    assert step3["result"] == "skipped_async"
    assert step3["cli_command"] is not None
    assert "validate-transition" in step3["cli_command"]

    # Capture rowcounts AFTER dry run
    counts_after = await _get_table_counts(session, admin.workspace_id)

    # CRITICAL INVARIANT: Row counts must be 100% identical
    assert counts_after == counts_before, (
        f"Row counts modified during dry-run! Before: {counts_before}, After: {counts_after}"
    )


@pytest.mark.asyncio
async def test_dry_run_rejection_step(
    dry_run_env: dict[str, Any],
    as_principal: Any,
) -> None:
    """When a validator rejects, result is 'rejected', would_commit is False, and remaining hooks do not execute."""
    api_env: ApiEnv = dry_run_env["api_env"]
    admin: SeededUser = dry_run_env["admin"]
    session: AsyncSession = api_env.seed
    project_id: uuid.UUID = dry_run_env["project_id"]
    states: dict[str, WorkflowState] = dry_run_env["states"]

    in_progress = states["In Progress"]
    in_qa = states["In QA"]

    # Attach rejecting validator
    h_rej = WorkflowTransitionHook(
        id=uuid.uuid4(),
        workspace_id=admin.workspace_id,
        project_id=project_id,
        from_state_id=in_progress.id,
        to_state_id=in_qa.id,
        sort_rank="0000000000000001",
        name="Strict Reject Hook",
        hook_kind="sync_validator",
        is_enabled=True,
        wasm_module_sha256=dry_run_env["reject_sha"],
        failure_policy="fail_closed",
        manifest_sha256=compute_hook_manifest_sha256(
            from_state_id=in_progress.id,
            to_state_id=in_qa.id,
            hook_kind="sync_validator",
            wasm_module_sha256=dry_run_env["reject_sha"],
            failure_policy="fail_closed",
        ),
    )
    session.add(h_rej)
    await session.commit()

    counts_before = await _get_table_counts(session, admin.workspace_id)

    client: httpx.AsyncClient = as_principal(admin, aal_level=2)
    resp = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "sample_ticket": {
                "summary": "Rejected Sample",
                "description_markdown": "No proof link",
                "priority": "medium",
                "labels": [],
            },
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["would_commit"] is False
    assert len(data["steps"]) == 1
    assert data["steps"][0]["result"] == "rejected"
    assert data["steps"][0]["reason"] == "Missing forensic proof"

    counts_after = await _get_table_counts(session, admin.workspace_id)
    assert counts_after == counts_before


@pytest.mark.asyncio
async def test_dry_run_with_existing_issue(
    dry_run_env: dict[str, Any],
    as_principal: Any,
) -> None:
    """Execute dry-run simulation against an existing issue in the database without modifying it."""
    api_env: ApiEnv = dry_run_env["api_env"]
    admin: SeededUser = dry_run_env["admin"]
    session: AsyncSession = api_env.seed
    project_id: uuid.UUID = dry_run_env["project_id"]
    states: dict[str, WorkflowState] = dry_run_env["states"]

    in_progress = states["In Progress"]
    in_qa = states["In QA"]

    # 1. Attach validator hook on (In Progress -> In QA)
    h_val = WorkflowTransitionHook(
        id=uuid.uuid4(),
        workspace_id=admin.workspace_id,
        project_id=project_id,
        from_state_id=in_progress.id,
        to_state_id=in_qa.id,
        sort_rank="0000000000000001",
        name="Validator For Existing Issue",
        hook_kind="sync_validator",
        is_enabled=True,
        wasm_module_sha256=dry_run_env["pass_sha"],
        failure_policy="fail_closed",
        manifest_sha256=compute_hook_manifest_sha256(
            from_state_id=in_progress.id,
            to_state_id=in_qa.id,
            hook_kind="sync_validator",
            wasm_module_sha256=dry_run_env["pass_sha"],
            failure_policy="fail_closed",
        ),
    )
    session.add(h_val)

    # 2. Seed an actual issue
    seq_val = await session.scalar(
        text("SELECT allocate_issue_sequence(:proj)"),
        {"proj": project_id},
    )
    issue_ckey = f"DRPROJ-{seq_val}"
    reg_row = await session.execute(
        text(
            "SELECT register_object("
            "  CAST('issue' AS object_kind), :ws, :proj, :key, :title, :creator"
            ")"
        ),
        {
            "ws": admin.workspace_id,
            "proj": project_id,
            "key": issue_ckey,
            "title": "Real Existing Issue",
            "creator": admin.id,
        },
    )
    issue_id = reg_row.scalar_one()

    # Query project's default priority
    prio_id = await session.scalar(
        select(ProjectPriority.id).where(
            ProjectPriority.project_id == project_id,
            ProjectPriority.is_default == True,  # noqa: E712
        )
    )
    if prio_id is None:
        prio_id = await session.scalar(
            select(ProjectPriority.id).where(ProjectPriority.project_id == project_id).limit(1)
        )

    real_issue = Issue(
        id=issue_id,
        workspace_id=admin.workspace_id,
        project_id=project_id,
        sequence_id=seq_val,
        summary="Real Existing Issue",
        description_markdown="This issue lives in the DB",
        state_id=in_progress.id,
        priority_id=prio_id,
        created_by_id=admin.id,
        board_rank=f"{seq_val:016d}",
    )
    session.add(real_issue)
    await session.commit()

    # Capture initial row counts and state
    counts_before = await _get_table_counts(session, admin.workspace_id)

    client: httpx.AsyncClient = as_principal(admin, aal_level=2)
    resp = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "issue_key": issue_ckey,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["would_commit"] is True
    assert len(data["steps"]) == 1
    assert data["steps"][0]["result"] == "allowed"

    # Verify existing issue state in DB was NOT changed
    stmt = select(Issue.state_id).where(Issue.id == issue_id)
    current_state_id = (await session.execute(stmt)).scalar_one()
    assert current_state_id == in_progress.id

    # Verify counts unchanged
    counts_after = await _get_table_counts(session, admin.workspace_id)
    assert counts_after == counts_before


@pytest.mark.asyncio
async def test_dry_run_failure_policies_and_edge_cases(
    dry_run_env: dict[str, Any],
    as_principal: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test dry run failure policies: fail_open_warn, budget exceeded, manifest mismatch, missing wasm."""
    admin: SeededUser = dry_run_env["admin"]
    session: AsyncSession = dry_run_env["api_env"].seed
    project_id: uuid.UUID = dry_run_env["project_id"]
    in_progress: WorkflowState = dry_run_env["states"]["In Progress"]
    in_qa: WorkflowState = dry_run_env["states"]["In QA"]
    wasm_sha: bytes = dry_run_env["pass_sha"]
    client: httpx.AsyncClient = as_principal(admin, aal_level=2)

    # 1. Sample ticket with unknown priority falls back to default priority
    resp_unknown_prio = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "sample_ticket": {
                "summary": "Unknown Priority Ticket",
                "description_markdown": "Test prio fallback",
                "priority": "nonexistent_prio",
                "labels": [],
            },
        },
    )
    assert resp_unknown_prio.status_code == 200
    assert resp_unknown_prio.json()["would_commit"] is True

    # 2. Missing WASM binary in ApprovedWasmModule (fail_closed and fail_open_warn)
    missing_wasm_sha = b"\xaa" * 32
    missing_hook_fc = WorkflowTransitionHook(
        workspace_id=admin.workspace_id,
        project_id=project_id,
        name="Missing Wasm FC",
        from_state_id=in_progress.id,
        to_state_id=in_qa.id,
        hook_kind="sync_validator",
        failure_policy="fail_closed",
        is_enabled=True,
        sort_rank="0000000000000050",
        manifest_sha256=compute_hook_manifest_sha256(
            from_state_id=in_progress.id,
            to_state_id=in_qa.id,
            hook_kind="sync_validator",
            failure_policy="fail_closed",
            wasm_module_sha256=missing_wasm_sha,
            allowed_mutable_fields=None,
            agent_definition_id=None,
        ),
        wasm_module_sha256=missing_wasm_sha,
    )
    session.add(missing_hook_fc)
    await session.commit()

    resp_missing_wasm = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "sample_ticket": {
                "summary": "Missing Wasm",
                "description_markdown": "Details",
            },
        },
    )
    assert resp_missing_wasm.status_code == 200
    data_missing = resp_missing_wasm.json()
    assert data_missing["would_commit"] is False
    assert any("WASM module binary not found" in s.get("reason", "") for s in data_missing["steps"])

    # Update to fail_open_warn
    missing_hook_fc.failure_policy = "fail_open_warn"
    await session.commit()

    # 3. Manifest mismatch: tamper manifest_sha256
    missing_hook_fc.wasm_module_sha256 = wasm_sha
    missing_hook_fc.failure_policy = "fail_closed"
    missing_hook_fc.manifest_sha256 = b"\x99" * 32  # tampered
    await session.commit()

    resp_tamper = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "sample_ticket": {
                "summary": "Tampered Manifest",
                "description_markdown": "Details",
            },
        },
    )
    assert resp_tamper.status_code == 200
    data_tamper = resp_tamper.json()
    assert data_tamper["would_commit"] is False
    assert any("HOOK_MANIFEST_MISMATCH" in s.get("reason", "") for s in data_tamper["steps"])

    # Change to fail_open_warn on manifest mismatch
    missing_hook_fc.failure_policy = "fail_open_warn"
    await session.commit()
    resp_tamper_fo = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "sample_ticket": {
                "summary": "Tampered Manifest FO",
                "description_markdown": "Details",
            },
        },
    )
    assert resp_tamper_fo.status_code == 200

    # Clean up tampered hook
    await session.delete(missing_hook_fc)
    await session.commit()

    # 4. Budget exceeded (fail_closed and fail_open_warn)
    budget_hook = WorkflowTransitionHook(
        workspace_id=admin.workspace_id,
        project_id=project_id,
        name="Budget Hook",
        from_state_id=in_progress.id,
        to_state_id=in_qa.id,
        hook_kind="sync_validator",
        failure_policy="fail_closed",
        is_enabled=True,
        sort_rank="0000000000000010",
        manifest_sha256=compute_hook_manifest_sha256(
            from_state_id=in_progress.id,
            to_state_id=in_qa.id,
            hook_kind="sync_validator",
            failure_policy="fail_closed",
            wasm_module_sha256=wasm_sha,
            allowed_mutable_fields=None,
            agent_definition_id=None,
        ),
        wasm_module_sha256=wasm_sha,
    )
    session.add(budget_hook)
    await session.commit()

    monkeypatch.setattr("kanban.workflows.dry_run.SYNC_HOOK_BUDGET_US", -1)
    resp_budget = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "sample_ticket": {
                "summary": "Budget Exceeded",
                "description_markdown": "Details",
            },
        },
    )
    assert resp_budget.status_code == 200
    data_budget = resp_budget.json()
    assert data_budget["would_commit"] is False
    assert any("SYNC_HOOK_BUDGET_EXCEEDED" in s.get("reason", "") for s in data_budget["steps"])

    # Fail open warn on budget exceeded
    budget_hook.failure_policy = "fail_open_warn"
    budget_hook.manifest_sha256 = compute_hook_manifest_sha256(
        from_state_id=in_progress.id,
        to_state_id=in_qa.id,
        hook_kind="sync_validator",
        failure_policy="fail_open_warn",
        wasm_module_sha256=wasm_sha,
        allowed_mutable_fields=None,
        agent_definition_id=None,
    )
    await session.commit()
    resp_budget_fo = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "sample_ticket": {
                "summary": "Budget Exceeded FO",
                "description_markdown": "Details",
            },
        },
    )
    assert resp_budget_fo.status_code == 200
    data_budget_fo = resp_budget_fo.json()
    assert data_budget_fo["would_commit"] is True
    assert any(
        "fail_open_warn: SYNC_HOOK_BUDGET_EXCEEDED" in s.get("reason", "")
        for s in data_budget_fo["steps"]
    )

    await session.delete(budget_hook)
    await session.commit()


@pytest.mark.asyncio
async def test_dry_run_wasm_exceptions_and_mutation_errors(
    dry_run_env: dict[str, Any],
    as_principal: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test dry run handling of wasm execution exceptions and mutation failure."""
    admin: SeededUser = dry_run_env["admin"]
    session: AsyncSession = dry_run_env["api_env"].seed
    project_id: uuid.UUID = dry_run_env["project_id"]
    in_progress: WorkflowState = dry_run_env["states"]["In Progress"]
    in_qa: WorkflowState = dry_run_env["states"]["In QA"]
    wasm_sha: bytes = dry_run_env["pass_sha"]
    client: httpx.AsyncClient = as_principal(admin, aal_level=2)

    # 1. Attach validator hook
    exc_hook = WorkflowTransitionHook(
        workspace_id=admin.workspace_id,
        project_id=project_id,
        name="Exc Hook",
        from_state_id=in_progress.id,
        to_state_id=in_qa.id,
        hook_kind="sync_validator",
        failure_policy="fail_closed",
        is_enabled=True,
        sort_rank="0000000000000010",
        manifest_sha256=compute_hook_manifest_sha256(
            from_state_id=in_progress.id,
            to_state_id=in_qa.id,
            hook_kind="sync_validator",
            failure_policy="fail_closed",
            wasm_module_sha256=wasm_sha,
            allowed_mutable_fields=None,
            agent_definition_id=None,
        ),
        wasm_module_sha256=wasm_sha,
    )
    session.add(exc_hook)
    await session.commit()

    # Monkeypatch wasm runner to raise RuntimeError
    from kanban.sandbox.wasm_runner import TierAWasmRunner

    runner = TierAWasmRunner.get_instance()

    def mock_run_sync_fail(*args: Any, **kwargs: Any) -> bytes:
        raise RuntimeError("Simulated wasm memory trap")

    monkeypatch.setattr(runner, "run_sync", mock_run_sync_fail)

    # fail_closed -> error
    resp_exc = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "sample_ticket": {"summary": "T", "description_markdown": "D"},
        },
    )
    assert resp_exc.status_code == 200
    data_exc = resp_exc.json()
    assert data_exc["would_commit"] is False
    assert any("Simulated wasm memory trap" in s.get("reason", "") for s in data_exc["steps"])

    # fail_open_warn -> allowed
    exc_hook.failure_policy = "fail_open_warn"
    exc_hook.manifest_sha256 = compute_hook_manifest_sha256(
        from_state_id=in_progress.id,
        to_state_id=in_qa.id,
        hook_kind="sync_validator",
        failure_policy="fail_open_warn",
        wasm_module_sha256=wasm_sha,
        allowed_mutable_fields=None,
        agent_definition_id=None,
    )
    await session.commit()

    resp_exc_fo = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "sample_ticket": {"summary": "T", "description_markdown": "D"},
        },
    )
    assert resp_exc_fo.status_code == 200
    data_exc_fo = resp_exc_fo.json()
    assert data_exc_fo["would_commit"] is True
    assert any(
        "fail_open_warn: Simulated wasm memory trap" in s.get("reason", "")
        for s in data_exc_fo["steps"]
    )

    # 2. Mutator returning invalid field update (e.g. invalid type or not allowed)
    monkeypatch.undo()
    exc_hook.hook_kind = "sync_mutator"
    exc_hook.failure_policy = "fail_closed"
    exc_hook.allowed_mutable_fields = ["labels"]
    exc_hook.manifest_sha256 = compute_hook_manifest_sha256(
        from_state_id=in_progress.id,
        to_state_id=in_qa.id,
        hook_kind="sync_mutator",
        failure_policy="fail_closed",
        wasm_module_sha256=wasm_sha,
        allowed_mutable_fields=["labels"],
        agent_definition_id=None,
    )
    await session.commit()

    # Make run_sync return mutation modifying unapproved field
    def mock_run_sync_mut_invalid(*args: Any, **kwargs: Any) -> bytes:
        import json

        return json.dumps(
            {
                "decision": "mutate",
                "field_updates": {"priority": "urgent"},
            }
        ).encode("utf-8")

    monkeypatch.setattr(runner, "run_sync", mock_run_sync_mut_invalid)

    # fail_closed -> error
    resp_mut_bad = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "sample_ticket": {"summary": "T", "description_markdown": "D"},
        },
    )
    assert resp_mut_bad.status_code == 200
    data_mut_bad = resp_mut_bad.json()
    assert data_mut_bad["would_commit"] is False

    # fail_open_warn -> allowed
    exc_hook.failure_policy = "fail_open_warn"
    exc_hook.manifest_sha256 = compute_hook_manifest_sha256(
        from_state_id=in_progress.id,
        to_state_id=in_qa.id,
        hook_kind="sync_mutator",
        failure_policy="fail_open_warn",
        wasm_module_sha256=wasm_sha,
        allowed_mutable_fields=["labels"],
        agent_definition_id=None,
    )
    await session.commit()

    resp_mut_fo = await client.post(
        "/api/v1/projects/DRPROJ/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "In QA",
            "sample_ticket": {"summary": "T", "description_markdown": "D"},
        },
    )
    assert resp_mut_fo.status_code == 200
    assert resp_mut_fo.json()["would_commit"] is True

    await session.delete(exc_hook)
    await session.commit()
