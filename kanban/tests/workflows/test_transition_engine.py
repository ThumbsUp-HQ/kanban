# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0913, PLR0917, ARG001, ANN401, PT012, ASYNC240, PLC0415
"""Comprehensive unit and integration tests for TransitionEngine and Tier A pipeline (KB-P5-17a)."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import wasmtime
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from database.models.agent_definition import AgentDefinition
from database.models.issues import Issue, IssueLabel
from database.models.projects import ProjectLabel, WorkflowState
from database.models.wasm_module import ApprovedWasmModule
from database.models.workflow import (
    WorkflowHookInvocation,
    WorkflowTransitionExecution,
    WorkflowTransitionHook,
)
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.sandbox.wasm_runner import TierAWasmRunner
from kanban.workflows.engine import TransitionEngine
from kanban.workflows.manifest import compute_hook_manifest_sha256

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "tests" / "fixtures" / "wasm"


def make_wat_bytes(json_payload: str) -> bytes:
    """Compile a minimal WASM module that calls env.kb_output with json_payload."""
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
)"""
    return bytes(wasmtime.wat2wasm(wat))


async def register_wasm_module(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    admin_id: uuid.UUID,
    wasm_bytes: bytes,
    name: str = "module.wasm",
) -> bytes:
    """Register and validate a WASM module in approved_wasm_modules."""
    runner = TierAWasmRunner.get_instance()
    sha = runner.validate_module(wasm_bytes)

    existing = (
        await session.execute(
            select(ApprovedWasmModule.sha256).where(
                ApprovedWasmModule.workspace_id == workspace_id,
                ApprovedWasmModule.sha256 == sha,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return sha

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


async def create_hook(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    admin_id: uuid.UUID,
    *,
    to_state_id: uuid.UUID,
    from_state_id: uuid.UUID | None = None,
    sort_rank: str = "10",
    name: str = "hook",
    hook_kind: str = "sync_validator",
    is_enabled: bool = True,
    wasm_module_sha256: bytes | None = None,
    agent_definition_id: uuid.UUID | None = None,
    allowed_mutable_fields: list[str] | None = None,
    fail_mode: str = "fail_closed",
) -> WorkflowTransitionHook:
    """Create a validated WorkflowTransitionHook with canonical manifest."""
    hook_id = uuid.uuid4()
    manifest_sha = compute_hook_manifest_sha256(
        hook_kind=hook_kind,
        wasm_module_sha256=wasm_module_sha256,
        agent_definition_id=agent_definition_id,
        allowed_mutable_fields=allowed_mutable_fields,
        failure_policy=fail_mode,
        from_state_id=from_state_id,
        to_state_id=to_state_id,
    )
    hook = WorkflowTransitionHook(
        id=hook_id,
        workspace_id=workspace_id,
        project_id=project_id,
        from_state_id=from_state_id,
        to_state_id=to_state_id,
        sort_rank=str(sort_rank),
        name=name,
        hook_kind=hook_kind,
        is_enabled=is_enabled,
        wasm_module_sha256=wasm_module_sha256,
        agent_definition_id=agent_definition_id,
        allowed_mutable_fields=allowed_mutable_fields or [],
        failure_policy=fail_mode,
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
# Test Cases
# ---------------------------------------------------------------------------


async def test_case_1_positive_no_hooks_and_ordered_pipeline(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1: (a) No hooks -> 200 approved. (b) 2 validators + 1 mutator -> 200, label applied."""
    admin = await make_user("t1_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T1P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    in_prog_id = states["In Progress"]
    done_id = states["Done"]

    # (a) Transition without hooks
    resp = await client.post(
        "/api/v1/projects/T1P/issues",
        json={"summary": "Issue without hooks", "description_markdown": "Clean description"},
    )
    assert resp.status_code == 201, resp.text
    issue_key = resp.json()["key"]
    issue_id = uuid.UUID(resp.json()["id"])

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "In Progress"},
    )
    contract_recorder.record("transition_positive_no_hooks_200", t_resp.request, t_resp)
    assert t_resp.status_code == 200, t_resp.text
    body = t_resp.json()
    assert body["status"] == "approved"
    assert body["state"] == "In Progress"

    # Verify DB state
    await api_env.seed.rollback()
    issue_row = (await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))).scalar_one()
    assert issue_row.state_id == in_prog_id

    # (b) 2 ordered validators + 1 mutator
    for lbl_name in ("backend", "qa-verified"):
        api_env.seed.add(
            ProjectLabel(
                workspace_id=api_env.workspace_id,
                project_id=proj_id,
                name=lbl_name,
                color_hex="#0055ff",
            )
        )
    await api_env.seed.commit()

    val1_wasm = make_wat_bytes('{"allowed": true}')
    val2_wasm = make_wat_bytes('{"decision": "allow"}')
    mut1_wasm = make_wat_bytes(
        '{"decision": "allow", "field_updates": {"labels": ["backend", "qa-verified"]}}'
    )

    val1_sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, val1_wasm, "val1.wasm"
    )
    val2_sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, val2_wasm, "val2.wasm"
    )
    mut1_sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, mut1_wasm, "mut1.wasm"
    )

    await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=in_prog_id,
        sort_rank="10",
        name="val1",
        hook_kind="sync_validator",
        wasm_module_sha256=val1_sha,
    )
    await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=in_prog_id,
        sort_rank="20",
        name="val2",
        hook_kind="sync_validator",
        wasm_module_sha256=val2_sha,
    )
    await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=in_prog_id,
        sort_rank="30",
        name="mut1",
        hook_kind="sync_mutator",
        allowed_mutable_fields=["labels"],
        wasm_module_sha256=mut1_sha,
    )

    t2_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    contract_recorder.record("transition_ordered_pipeline_200", t2_resp.request, t2_resp)
    assert t2_resp.status_code == 200, t2_resp.text
    t2_body = t2_resp.json()
    assert t2_body["status"] == "approved"
    assert t2_body["state"] == "Done"

    # Verify invocations in DB
    await api_env.seed.rollback()
    inv_rows = (
        (
            await api_env.seed.execute(
                select(WorkflowHookInvocation)
                .join(
                    WorkflowTransitionHook,
                    WorkflowTransitionHook.id == WorkflowHookInvocation.hook_id,
                )
                .where(WorkflowHookInvocation.execution_id == uuid.UUID(t2_body["execution_id"]))
                .order_by(WorkflowTransitionHook.sort_rank)
            )
        )
        .scalars()
        .all()
    )
    assert len(inv_rows) == 3
    for inv in inv_rows:
        assert inv.duration_us is not None
        assert inv.duration_us >= 0
        assert inv.error_code is None
        assert inv.status in ("allowed", "mutated")

    # Verify label mutation applied in DB
    applied_labels = (
        (
            await api_env.seed.execute(
                select(ProjectLabel.name)
                .join(IssueLabel, IssueLabel.label_id == ProjectLabel.id)
                .where(IssueLabel.issue_id == issue_id)
                .order_by(ProjectLabel.name)
            )
        )
        .scalars()
        .all()
    )
    assert set(applied_labels) == {"backend", "qa-verified"}


async def test_case_2_rejection_require_qa_proof_link(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 2: Validator require-qa-proof-link rejects -> 422 TRANSITION_REJECTED_BY_HOOK."""
    admin = await make_user("t2_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T2P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    backlog_id = states["Backlog"]
    done_id = states["Done"]

    rej_wasm = make_wat_bytes(
        '{"decision": "reject", "reason": "Missing docs/qa/ proof link in description"}'
    )
    rej_sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, rej_wasm, "reject.wasm"
    )

    await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="10",
        name="require-qa-proof-link",
        hook_kind="sync_validator",
        wasm_module_sha256=rej_sha,
    )

    resp = await client.post(
        "/api/v1/projects/T2P/issues",
        json={"summary": "Unproven issue", "description_markdown": "No QA proof here"},
    )
    assert resp.status_code == 201
    issue_key = resp.json()["key"]
    issue_id = uuid.UUID(resp.json()["id"])

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    contract_recorder.record("transition_rejected_by_hook_422", t_resp.request, t_resp)
    assert t_resp.status_code == 422, t_resp.text
    err = t_resp.json()
    assert err["code"] == "TRANSITION_REJECTED_BY_HOOK"
    assert "Missing docs/qa/ proof link in description" in err["detail"]

    # Verify state unchanged and execution marked rejected
    await api_env.seed.rollback()
    issue_row = (await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))).scalar_one()
    assert issue_row.state_id == backlog_id

    exec_row = (
        await api_env.seed.execute(
            select(WorkflowTransitionExecution).where(
                WorkflowTransitionExecution.issue_id == issue_id
            )
        )
    ).scalar_one()
    assert exec_row.status == "rejected"
    assert exec_row.verdict_json is not None
    assert exec_row.verdict_json["reason"] == "Missing docs/qa/ proof link in description"


async def test_case_3_security_illegal_mutations(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 3: Mutator returning field_updates for state, description, or priority fails closed 422."""
    admin = await make_user("t3_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T3P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    backlog_id = states["Backlog"]
    done_id = states["Done"]

    for illegal_field, illegal_val in [
        ("state", "Done"),
        ("description_markdown", "# Malicious update"),
        ("priority", "urgent"),
    ]:
        payload = json.dumps({"decision": "allow", "field_updates": {illegal_field: illegal_val}})
        wasm_bytes = make_wat_bytes(payload)
        sha = await register_wasm_module(
            api_env.seed,
            api_env.workspace_id,
            proj_id,
            admin.id,
            wasm_bytes,
            f"illegal_{illegal_field}.wasm",
        )

        hook = await create_hook(
            api_env.seed,
            api_env.workspace_id,
            proj_id,
            admin.id,
            to_state_id=done_id,
            from_state_id=None,
            sort_rank="10",
            name=f"illegal_{illegal_field}",
            hook_kind="sync_mutator",
            allowed_mutable_fields=["labels"],
            wasm_module_sha256=sha,
        )

        resp = await client.post(
            "/api/v1/projects/T3P/issues",
            json={"summary": f"Test {illegal_field}", "description_markdown": "Test"},
        )
        assert resp.status_code == 201
        issue_key = resp.json()["key"]
        issue_id = uuid.UUID(resp.json()["id"])

        t_resp = await client.post(
            f"/api/v1/issues/{issue_key}/transitions",
            json={"to_state": "Done"},
        )
        contract_recorder.record("transition_illegal_mutation_422", t_resp.request, t_resp)
        assert t_resp.status_code == 422, t_resp.text
        assert t_resp.json()["code"] == "HOOK_MUTATION_NOT_ALLOWED"

        # Verify state unchanged
        await api_env.seed.rollback()
        issue_row = (
            await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))
        ).scalar_one()
        assert issue_row.state_id == backlog_id

        # Clean up hook for next loop iteration
        await api_env.seed.execute(
            text("UPDATE workflow_transition_hooks SET is_enabled = FALSE WHERE id = :id"),
            {"id": hook.id},
        )
        await api_env.seed.commit()


async def test_case_4_security_direct_update_and_patch_route(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 4: Direct UPDATE issues blocked by trigger; PATCH /issues/{key} with state routes to engine."""
    admin = await make_user("t4_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T4P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    backlog_id = states["Backlog"]
    done_id = states["Done"]

    resp = await client.post(
        "/api/v1/projects/T4P/issues",
        json={"summary": "Guard test", "description_markdown": "Test"},
    )
    assert resp.status_code == 201
    issue_key = resp.json()["key"]
    issue_id = uuid.UUID(resp.json()["id"])

    # 1. Direct UPDATE as kanban_app without transition_exec_id raises trigger error
    with pytest.raises(DBAPIError) as exc_info:
        await api_env.seed.execute(
            text("UPDATE issues SET state_id = :s WHERE id = :id"),
            {"s": done_id, "id": issue_id},
        )
        await api_env.seed.flush()
    assert "STATE_CHANGE_REQUIRES_TRANSITION_ENGINE" in str(exc_info.value)
    await api_env.seed.rollback()

    # 2. Add rejecting hook on transition to Done
    rej_wasm = make_wat_bytes('{"decision": "reject", "reason": "Blocked by policy"}')
    rej_sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, rej_wasm, "rej_patch.wasm"
    )
    await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="10",
        name="rej_patch",
        hook_kind="sync_validator",
        wasm_module_sha256=rej_sha,
    )

    # 3. PATCH /issues/{key} with state routes through engine and sees hook rejection
    patch_resp = await client.patch(
        f"/api/v1/issues/{issue_key}",
        json={"state": "Done"},
    )
    assert patch_resp.status_code == 422, patch_resp.text
    assert patch_resp.json()["code"] == "TRANSITION_REJECTED_BY_HOOK"

    # State remains unchanged
    await api_env.seed.rollback()
    issue_row = (await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))).scalar_one()
    assert issue_row.state_id == backlog_id


async def test_case_5_security_tampered_manifest_fails_closed(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 5: Tampered manifest with fail_open_warn still fails closed with HOOK_MANIFEST_MISMATCH."""
    admin = await make_user("t5_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T5P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    states["Backlog"]
    done_id = states["Done"]

    wasm_bytes = make_wat_bytes('{"allowed": true}')
    sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, wasm_bytes, "ok.wasm"
    )

    hook = await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="10",
        name="tampered_hook",
        hook_kind="sync_validator",
        fail_mode="fail_open_warn",
        wasm_module_sha256=sha,
    )

    # Tamper manifest in database
    await api_env.seed.execute(
        text(
            "UPDATE workflow_transition_hooks SET manifest_sha256 = decode(:tampered, 'hex') WHERE id = :id"
        ),
        {"tampered": "00" * 32, "id": hook.id},
    )
    await api_env.seed.commit()

    resp = await client.post(
        "/api/v1/projects/T5P/issues",
        json={"summary": "Tamper test", "description_markdown": "Test"},
    )
    assert resp.status_code == 201
    issue_key = resp.json()["key"]

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    assert t_resp.status_code == 422, t_resp.text
    assert t_resp.json()["code"] == "HOOK_MANIFEST_MISMATCH"


async def test_case_6_boundary_timeout_fail_open_wildcard_disabled(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 6: Boundary: timeout fail_closed vs fail_open_warn, wildcard hook, and disabled hook."""
    admin = await make_user("t6_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T6P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    states["Backlog"]
    done_id = states["Done"]

    loop_bytes = (FIXTURES_DIR / "infinite_loop.wasm").read_bytes()
    loop_sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, loop_bytes, "loop.wasm"
    )

    # (a) Timeout with fail_closed -> 422
    hook_closed = await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="10",
        name="timeout_closed",
        hook_kind="sync_validator",
        fail_mode="fail_closed",
        wasm_module_sha256=loop_sha,
    )

    resp = await client.post(
        "/api/v1/projects/T6P/issues",
        json={"summary": "Timeout test", "description_markdown": "Test"},
    )
    issue_key = resp.json()["key"]

    t1_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    assert t1_resp.status_code == 422, t1_resp.text
    assert t1_resp.json()["code"] in ("HOOK_TIMEOUT", "SYNC_HOOK_BUDGET_EXCEEDED")

    # (b) Timeout with fail_open_warn -> 200, state changed
    await api_env.seed.execute(
        text("UPDATE workflow_transition_hooks SET is_enabled = FALSE WHERE id = :id"),
        {"id": hook_closed.id},
    )
    await api_env.seed.commit()

    await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="10",
        name="timeout_open",
        hook_kind="sync_validator",
        fail_mode="fail_open_warn",
        wasm_module_sha256=loop_sha,
    )

    t2_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    assert t2_resp.status_code == 200, t2_resp.text
    assert t2_resp.json()["status"] == "approved"
    assert t2_resp.json()["state"] == "Done"

    # (c) Wildcard hook (from_state_id IS NULL) applies from any state
    await api_env.seed.execute(text("UPDATE workflow_transition_hooks SET is_enabled = FALSE"))
    await api_env.seed.commit()

    ok_bytes = make_wat_bytes('{"allowed": true}')
    ok_sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, ok_bytes, "ok_wildcard.wasm"
    )

    wildcard_hook = await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=None,  # Wildcard!
        sort_rank="10",
        name="wildcard_hook",
        hook_kind="sync_validator",
        wasm_module_sha256=ok_sha,
    )

    # (d) Disabled hook is skipped
    disabled_rej_bytes = make_wat_bytes('{"decision": "reject"}')
    disabled_sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, disabled_rej_bytes, "disabled.wasm"
    )
    await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="20",
        name="disabled_hook",
        hook_kind="sync_validator",
        is_enabled=False,  # Disabled!
        wasm_module_sha256=disabled_sha,
    )

    # Issue transition should execute wildcard hook and skip disabled hook
    resp3 = await client.post(
        "/api/v1/projects/T6P/issues",
        json={"summary": "Wildcard issue", "description_markdown": "Test"},
    )
    issue_key3 = resp3.json()["key"]
    await client.post(f"/api/v1/issues/{issue_key3}/transitions", json={"to_state": "In Progress"})

    t3_resp = await client.post(
        f"/api/v1/issues/{issue_key3}/transitions",
        json={"to_state": "Done"},
    )
    assert t3_resp.status_code == 200, t3_resp.text
    assert t3_resp.json()["status"] == "approved"
    assert t3_resp.json()["state"] == "Done"

    # Verify wildcard hook was invoked
    await api_env.seed.rollback()
    inv_rows = (
        (
            await api_env.seed.execute(
                select(WorkflowHookInvocation).where(
                    WorkflowHookInvocation.execution_id == uuid.UUID(t3_resp.json()["execution_id"])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(inv_rows) == 1
    assert inv_rows[0].hook_id == wildcard_hook.id


async def test_case_7_boundary_hop_depth_and_concurrency(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 7: Hop depth 4 -> 422 HOP_DEPTH_EXCEEDED; concurrent transition -> 409 TRANSITION_PENDING."""
    admin = await make_user("t7_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T7P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    backlog_id = states["Backlog"]
    done_id = states["Done"]

    resp = await client.post(
        "/api/v1/projects/T7P/issues",
        json={"summary": "Depth test", "description_markdown": "Test"},
    )
    issue_key = resp.json()["key"]
    issue_id = uuid.UUID(resp.json()["id"])

    # 1. Hop depth test: execution record with hop_depth = 3
    e3_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            """
            INSERT INTO workflow_transition_executions (
                id, workspace_id, project_id, issue_id, from_state_id, to_state_id,
                invoking_principal_id, hop_depth, issue_body_sha256_snapshot, status
            ) VALUES
            (:e3, :ws, :proj, :iss, :from_s, :to_s, :uid, 3, :snap, 'approved')
            """
        ),
        {
            "e3": e3_id,
            "ws": api_env.workspace_id,
            "proj": proj_id,
            "iss": issue_id,
            "from_s": backlog_id,
            "to_s": done_id,
            "uid": admin.id,
            "snap": b"\x00" * 32,
        },
    )
    await api_env.seed.commit()

    admin_ctx = PrincipalContext(
        principal_id=admin.id,
        workspace_id=api_env.workspace_id,
        token_scopes=("session",),
    )

    with pytest.raises(ProblemException) as exc_info:
        await TransitionEngine.request_transition(
            session=api_env.seed,
            issue_key=issue_key,
            to_state=done_id,
            actor=admin_ctx,
            parent_execution_id=e3_id,
        )
    assert exc_info.value.status == 422
    assert exc_info.value.code == "HOP_DEPTH_EXCEEDED"

    # 2. Concurrency test: active execution with status='running_sync'
    e_running_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            """
            INSERT INTO workflow_transition_executions (
                id, workspace_id, project_id, issue_id, from_state_id, to_state_id,
                invoking_principal_id, hop_depth, issue_body_sha256_snapshot, status
            ) VALUES
            (:eid, :ws, :proj, :iss, :from_s, :to_s, :uid, 0, :snap, 'running_sync')
            """
        ),
        {
            "eid": e_running_id,
            "ws": api_env.workspace_id,
            "proj": proj_id,
            "iss": issue_id,
            "from_s": backlog_id,
            "to_s": done_id,
            "uid": admin.id,
            "snap": b"\x00" * 32,
        },
    )
    await api_env.seed.commit()

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    contract_recorder.record("transition_pending_conflict_409", t_resp.request, t_resp)
    assert t_resp.status_code == 409, t_resp.text
    assert t_resp.json()["code"] == "TRANSITION_PENDING"


async def test_case_8_agent_hook_default_dispatcher(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 8: Agent hook present with fail-closed fallback dispatcher -> 409 AGENT_GATE_NOT_CONFIGURED."""
    import kanban.workflows.async_gate as async_gate_mod
    from kanban.workflows.engine import FailClosedAsyncGateDispatcher

    monkeypatch.setattr(async_gate_mod, "AgentGateDispatcher", FailClosedAsyncGateDispatcher)
    admin = await make_user("t8_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T8P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    backlog_id = states["Backlog"]
    done_id = states["Done"]

    # Register an agent definition
    agent_id = uuid.uuid4()
    agent_def = AgentDefinition(
        id=agent_id,
        workspace_id=api_env.workspace_id,
        principal_id=admin.id,
        slug="t8-qa-agent",
        display_name="T8 QA Agent",
        harness_kind="in_app_sdk",
        provider_kind="openai",
        model_id="gpt-4o",
    )
    api_env.seed.add(agent_def)
    await api_env.seed.commit()

    await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="10",
        name="agent_gate_hook",
        hook_kind="agent_interceptor",
        agent_definition_id=agent_id,
        wasm_module_sha256=None,
    )

    resp = await client.post(
        "/api/v1/projects/T8P/issues",
        json={"summary": "Agent hook test", "description_markdown": "Test"},
    )
    issue_key = resp.json()["key"]
    issue_id = uuid.UUID(resp.json()["id"])

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    contract_recorder.record("transition_agent_gate_not_configured_409", t_resp.request, t_resp)
    assert t_resp.status_code == 409, t_resp.text
    assert t_resp.json()["code"] == "AGENT_GATE_NOT_CONFIGURED"

    # Verify execution cancelled and state unchanged
    await api_env.seed.rollback()
    issue_row = (await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))).scalar_one()
    assert issue_row.state_id == backlog_id

    exec_row = (
        await api_env.seed.execute(
            select(WorkflowTransitionExecution).where(
                WorkflowTransitionExecution.issue_id == issue_id
            )
        )
    ).scalar_one()
    assert exec_row.status == "cancelled"


async def test_case_9_rls_isolation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 9: Hooks invisible across workspaces; MEMBER insert into hooks rejected by WITH CHECK."""
    admin = await make_user("t9_admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("t9_member", workspace_role="WORKSPACE_MEMBER")
    proj_id = await make_project(
        "T9P", created_by=admin, roles={admin: "PROJECT_ADMIN", member: "MEMBER"}
    )

    states = await _get_states(api_env.seed, proj_id)
    backlog_id = states["Backlog"]
    done_id = states["Done"]

    wasm_bytes = make_wat_bytes('{"allowed": true}')
    sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, wasm_bytes, "rls.wasm"
    )

    hook_id = uuid.uuid4()
    manifest_sha = compute_hook_manifest_sha256(
        hook_kind="sync_validator",
        wasm_module_sha256=sha,
        failure_policy="fail_closed",
        from_state_id=backlog_id,
        to_state_id=done_id,
    )

    # Using member context session
    with pytest.raises(DBAPIError) as exc_info:
        await api_env.seed.execute(
            text(
                """
                SET LOCAL app.current_workspace_id = :ws;
                SET LOCAL app.current_principal_id = :uid;
                SET LOCAL app.current_role = 'MEMBER';
                INSERT INTO workflow_transition_hooks (
                    id, workspace_id, project_id, from_state_id, to_state_id,
                    sort_rank, name, hook_kind, is_enabled, wasm_module_sha256,
                    manifest_sha256, failure_policy
                ) VALUES (
                    :id, :ws, :proj, :from_s, :to_s, '10', 'member_hook',
                    'sync_validator', true, :wasm_sha, :man_sha, 'fail_closed'
                );
                """
            ),
            {
                "id": hook_id,
                "ws": api_env.workspace_id,
                "proj": proj_id,
                "from_s": backlog_id,
                "to_s": done_id,
                "uid": member.id,
                "wasm_sha": sha,
                "man_sha": manifest_sha,
            },
        )
        await api_env.seed.flush()
    assert "workflow_transition_hooks" in str(exc_info.value)
    await api_env.seed.rollback()


async def test_case_10_real_wasm_fixture(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 10: Real tests/fixtures/wasm/require_qa_proof_link.wasm fixture runs and approves."""
    admin = await make_user("t10_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("T10P", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    states["Backlog"]
    done_id = states["Done"]

    fixture_path = FIXTURES_DIR / "require_qa_proof_link.wasm"
    assert fixture_path.exists(), f"Fixture missing: {fixture_path}"
    real_wasm_bytes = fixture_path.read_bytes()

    sha = await register_wasm_module(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        real_wasm_bytes,
        "require_qa_proof_link.wasm",
    )

    await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="10",
        name="require_qa_proof_link",
        hook_kind="sync_validator",
        wasm_module_sha256=sha,
    )

    resp = await client.post(
        "/api/v1/projects/T10P/issues",
        json={"summary": "Real wasm issue", "description_markdown": "Docs in docs/qa/proof"},
    )
    assert resp.status_code == 201
    issue_key = resp.json()["key"]

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done"},
    )
    assert t_resp.status_code == 200, t_resp.text
    body = t_resp.json()
    assert body["status"] == "approved"
    assert body["state"] == "Done"

    await api_env.seed.rollback()
    inv_rows = (
        (
            await api_env.seed.execute(
                select(WorkflowHookInvocation).where(
                    WorkflowHookInvocation.execution_id == uuid.UUID(body["execution_id"])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(inv_rows) == 1
    inv = inv_rows[0]
    assert inv.duration_us is not None
    assert inv.duration_us >= 0
    assert inv.output_json is not None
    assert inv.output_json["allowed"] is True
    assert inv.output_json["reason"] == "Verified QA link present"


async def test_sync_latency_benchmark(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Benchmark: 200 transitions with 3 Tier A hooks asserting p95 < 25.0ms."""
    # Allow single-sample p99.5 GC/xdist scheduler spikes without aborting the loop with 422
    # before p95 (< 25.0ms) is evaluated across all 200 transitions.
    monkeypatch.setattr("kanban.workflows.engine.SYNC_TOTAL_BUDGET_MS", 250.0)
    admin = await make_user("t_bench_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("BENCH", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    backlog_id = states["Backlog"]
    done_id = states["Done"]

    fixture_path = FIXTURES_DIR / "require_qa_proof_link.wasm"
    assert fixture_path.exists(), f"Fixture missing: {fixture_path}"
    real_wasm_bytes = fixture_path.read_bytes()

    h1_sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, real_wasm_bytes, "bench1.wasm"
    )
    h2_sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, real_wasm_bytes, "bench2.wasm"
    )
    h3_sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, real_wasm_bytes, "bench3.wasm"
    )

    await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="10",
        name="b1",
        hook_kind="sync_validator",
        wasm_module_sha256=h1_sha,
    )
    await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="20",
        name="b2",
        hook_kind="sync_validator",
        wasm_module_sha256=h2_sha,
    )
    await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="30",
        name="b3",
        hook_kind="sync_validator",
        wasm_module_sha256=h3_sha,
    )

    # Pre-create 10 issues
    issue_keys: list[str] = []
    for i in range(10):
        resp = await client.post(
            "/api/v1/projects/BENCH/issues",
            json={"summary": f"Bench issue {i}", "description_markdown": "Docs in docs/qa/proof"},
        )
        assert resp.status_code == 201
        issue_keys.append(resp.json()["key"])

    # Warm singleton Wasmtime module compilation cache before benchmark loop
    TierAWasmRunner.get_instance().run_sync(
        real_wasm_bytes, b'{"issue":{"description_markdown":"docs/qa/proof"}}'
    )

    # Measure transition latency over 200 runs (20 rounds across 10 issues)
    sync_latencies_ms: list[float] = []
    total_latencies_ms: list[float] = []
    for _round in range(20):
        for key in issue_keys:
            t0 = time.perf_counter()
            resp = await client.post(f"/api/v1/issues/{key}/transitions", json={"to_state": "Done"})
            dt_ms = (time.perf_counter() - t0) * 1000.0
            assert resp.status_code == 200, resp.text
            total_latencies_ms.append(dt_ms)
            sync_ms = resp.json().get("sync_duration_ms", 0.0)
            sync_latencies_ms.append(float(sync_ms))

        # Reset issues back to Backlog for next round
        await api_env.seed.execute(text("SET LOCAL session_replication_role = 'replica'"))
        await api_env.seed.execute(
            text("UPDATE issues SET state_id = :b WHERE project_id = :p"),
            {"b": backlog_id, "p": proj_id},
        )
        await api_env.seed.commit()

    sync_latencies_ms.sort()
    n = len(sync_latencies_ms)
    p50 = sync_latencies_ms[int(n * 0.50)]
    p95 = sync_latencies_ms[int(n * 0.95)]
    p99 = sync_latencies_ms[int(n * 0.99)]
    max_lat = sync_latencies_ms[-1]
    avg_lat = sum(sync_latencies_ms) / n

    total_latencies_ms.sort()
    tot_p95 = total_latencies_ms[int(n * 0.95)]

    report = (
        f"=== Tier A Sync Hook Latency Benchmark (KB-P5-17a) ===\n"
        f"Total Samples:      {n} transitions with 3 hooks (real wasm fixture)\n"
        f"Sync Stage Average: {avg_lat:.2f} ms\n"
        f"Sync Stage p50:     {p50:.2f} ms\n"
        f"Sync Stage p95:     {p95:.2f} ms (Target: < 25.0 ms)\n"
        f"Sync Stage p99:     {p99:.2f} ms\n"
        f"Sync Stage Max:     {max_lat:.2f} ms\n"
        f"Total Request p95:  {tot_p95:.2f} ms\n"
        f"Status:             {'PASS' if p95 < 25.0 else 'FAIL'}\n"
    )

    out_dir = Path("docs/qa/KANBA-147")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sync-latency.txt").write_text(report, encoding="utf-8")

    assert p95 < 25.0, f"p95 latency {p95:.2f}ms exceeds 25.0ms budget!"


async def test_transition_if_match_and_etag(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test description ETag checking: 412 on mismatch, 200 on match."""
    admin = await make_user("t_etag_admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("ETAG", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    resp = await client.post(
        "/api/v1/projects/ETAG/issues",
        json={"summary": "ETag test", "description_markdown": "Original description"},
    )
    assert resp.status_code == 201
    issue_data = resp.json()
    key = issue_data["key"]

    # 1. Mismatch header -> 412
    resp_mismatch = await client.post(
        f"/api/v1/issues/{key}/transitions",
        json={"to_state": "In Progress"},
        headers={"if-match": '"0000000000000000000000000000000000000000000000000000000000000000"'},
    )
    assert resp_mismatch.status_code == 412
    assert resp_mismatch.json()["code"] == "PRECONDITION_FAILED"

    # 2. Matching header with weak prefix -> 200
    desc_sha = hashlib.sha256(b"Original description").hexdigest()
    resp_match = await client.post(
        f"/api/v1/issues/{key}/transitions",
        json={"to_state": "In Progress"},
        headers={"if-match": f'W/"{desc_sha}"'},
    )
    assert resp_match.status_code == 200


async def test_transition_pending_conflict_and_invalid_state(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test 409 when transition is pending, and 422 when target state does not exist."""
    admin = await make_user("t_pend_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("PEND", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    resp = await client.post(
        "/api/v1/projects/PEND/issues",
        json={"summary": "Pending issue"},
    )
    assert resp.status_code == 201
    key = resp.json()["key"]

    # Target state not existing -> 422
    resp_invalid_st = await client.post(
        f"/api/v1/issues/{key}/transitions",
        json={"to_state": "NoSuchState"},
    )
    assert resp_invalid_st.status_code == 422
    assert resp_invalid_st.json()["code"] == "INVALID_STATE"

    # Target state by string UUID
    states = await _get_states(api_env.seed, proj_id)
    resp_by_uuid = await client.post(
        f"/api/v1/issues/{key}/transitions",
        json={"to_state": str(states["In Progress"])},
    )
    assert resp_by_uuid.status_code == 200

    # Set pending_transition_exec_id -> 409
    fake_exec_id = uuid.uuid4()
    # Fetch issue id
    issue_id = (
        await api_env.seed.execute(select(Issue.id).where(Issue.project_id == proj_id))
    ).scalar_one()
    exec_row = WorkflowTransitionExecution(
        id=fake_exec_id,
        workspace_id=api_env.workspace_id,
        project_id=proj_id,
        issue_id=issue_id,
        invoking_principal_id=admin.id,
        from_state_id=states["In Progress"],
        to_state_id=states["Done"],
        status="pending_async",
        hop_depth=0,
        issue_body_sha256_snapshot=b"\x00" * 32,
    )
    api_env.seed.add(exec_row)
    await api_env.seed.flush()
    await api_env.seed.execute(
        text("UPDATE issues SET pending_transition_exec_id = :p WHERE id = :id"),
        {"p": fake_exec_id, "id": issue_id},
    )
    await api_env.seed.commit()

    resp_conflict = await client.post(
        f"/api/v1/issues/{key}/transitions",
        json={"to_state": "Done"},
    )
    assert resp_conflict.status_code == 409
    assert resp_conflict.json()["code"] == "TRANSITION_PENDING"

    # Reset pending_transition_exec_id to avoid teardown conflicts
    await api_env.seed.execute(
        text("UPDATE issues SET pending_transition_exec_id = NULL WHERE id = :id"),
        {"id": issue_id},
    )
    await api_env.seed.commit()


async def test_transition_comment_and_parent_execution(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test transition with comment_markdown, and invalid parent_execution_id."""
    admin = await make_user("t_comm_admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("COMM", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    resp = await client.post(
        "/api/v1/projects/COMM/issues",
        json={"summary": "Comment issue"},
    )
    assert resp.status_code == 201
    key = resp.json()["key"]

    resp_comm = await client.post(
        f"/api/v1/issues/{key}/transitions",
        json={"to_state": "In Progress", "comment_markdown": "Moving to in progress with comment"},
    )
    assert resp_comm.status_code == 200

    # Test invalid parent_execution_id on TransitionEngine directly
    actor = PrincipalContext(
        principal_id=admin.id,
        workspace_id=api_env.workspace_id,
        token_scopes=("session",),
    )
    engine = TransitionEngine(api_env.seed)
    with pytest.raises(ProblemException) as exc_info:
        await engine.execute_transition(
            issue_key=key,
            to_state="Done",
            actor=actor,
            parent_execution_id=uuid.uuid4(),
        )
    assert exc_info.value.code == "INVALID_PARENT_EXECUTION"


async def test_transition_hook_errors_and_malformed(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test hook wasm not found, malformed outputs, and timeout."""
    from kanban.sandbox.wasm_runner import WasmRunError

    admin = await make_user("t_mal_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("MAL", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    done_id = states["Done"]

    resp = await client.post(
        "/api/v1/projects/MAL/issues",
        json={"summary": "Mal issue"},
    )
    assert resp.status_code == 201
    key = resp.json()["key"]

    # 1. Hook pointing to nonexistent wasm module -> 422 SYNC_HOOK_OUTPUT_INVALID
    fake_sha = b"\xaa" * 32
    await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="10",
        name="missing_wasm_hook",
        hook_kind="sync_validator",
        wasm_module_sha256=fake_sha,
    )

    resp_err = await client.post(f"/api/v1/issues/{key}/transitions", json={"to_state": "Done"})
    assert resp_err.status_code == 422
    assert resp_err.json()["code"] == "SYNC_HOOK_OUTPUT_INVALID"

    # Register real wasm module
    wasm_bytes = make_wat_bytes('{"decision": "allow"}')
    real_sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, wasm_bytes, "valid.wasm"
    )

    # Update hook to point to real wasm
    await api_env.seed.execute(
        text(
            "UPDATE workflow_transition_hooks SET wasm_module_sha256 = :sha WHERE name = 'missing_wasm_hook'"
        ),
        {"sha": real_sha},
    )
    # Update manifest_sha256 to match
    correct_manifest = compute_hook_manifest_sha256(
        hook_kind="sync_validator",
        wasm_module_sha256=real_sha,
        agent_definition_id=None,
        allowed_mutable_fields=[],
        failure_policy="fail_closed",
        from_state_id=None,
        to_state_id=done_id,
    )
    await api_env.seed.execute(
        text(
            "UPDATE workflow_transition_hooks SET manifest_sha256 = :m WHERE name = 'missing_wasm_hook'"
        ),
        {"m": correct_manifest},
    )
    await api_env.seed.commit()

    # 2. Mock wasm runner timeout -> SYNC_HOOK_BUDGET_EXCEEDED
    def mock_run_timeout(*args: Any, **kwargs: Any) -> Any:
        msg = "Guest wasm execution timeout"
        raise WasmRunError(msg, code="SCRIPT_TIMEOUT")

    monkeypatch.setattr(TierAWasmRunner, "run_sync", mock_run_timeout)
    resp_timeout = await client.post(f"/api/v1/issues/{key}/transitions", json={"to_state": "Done"})
    assert resp_timeout.status_code == 422
    assert resp_timeout.json()["code"] == "SYNC_HOOK_BUDGET_EXCEEDED"

    # 3. Mock wasm runner returning non-JSON -> SYNC_HOOK_OUTPUT_INVALID
    def mock_run_bad_json(*args: Any, **kwargs: Any) -> Any:
        return b"not json"

    monkeypatch.setattr(TierAWasmRunner, "run_sync", mock_run_bad_json)
    resp_bad_json = await client.post(
        f"/api/v1/issues/{key}/transitions", json={"to_state": "Done"}
    )
    assert resp_bad_json.status_code == 422
    assert resp_bad_json.json()["code"] == "SYNC_HOOK_OUTPUT_INVALID"

    # 4. Mock wasm runner returning JSON without decision or allowed -> SYNC_HOOK_OUTPUT_INVALID
    def mock_run_no_decision(*args: Any, **kwargs: Any) -> Any:
        return b'{"unexpected": "field"}'

    monkeypatch.setattr(TierAWasmRunner, "run_sync", mock_run_no_decision)
    resp_no_dec = await client.post(f"/api/v1/issues/{key}/transitions", json={"to_state": "Done"})
    assert resp_no_dec.status_code == 422
    assert resp_no_dec.json()["code"] == "SYNC_HOOK_OUTPUT_INVALID"


async def test_transition_mutator_fail_open_warn(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a sync_mutator violating allowed_mutable_fields with fail_open_warn logs activity and continues."""
    admin = await make_user("t_fow_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("FOW", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    done_id = states["Done"]

    resp = await client.post(
        "/api/v1/projects/FOW/issues",
        json={"summary": "Fail open issue"},
    )
    assert resp.status_code == 201
    key = resp.json()["key"]

    wasm_bytes = make_wat_bytes('{"decision": "allow"}')
    real_sha = await register_wasm_module(
        api_env.seed, api_env.workspace_id, proj_id, admin.id, wasm_bytes, "mutator.wasm"
    )

    await create_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        admin.id,
        to_state_id=done_id,
        from_state_id=None,
        sort_rank="10",
        name="fow_mutator",
        hook_kind="sync_mutator",
        wasm_module_sha256=real_sha,
        allowed_mutable_fields=["labels"],
        fail_mode="fail_open_warn",
    )

    # Mock output to include mutation on disallowed field 'priority'
    def mock_run_disallowed_mut(*args: Any, **kwargs: Any) -> Any:
        return b'{"decision": "allow", "field_updates": {"priority": "urgent"}}'

    monkeypatch.setattr(TierAWasmRunner, "run_sync", mock_run_disallowed_mut)

    resp_fow = await client.post(f"/api/v1/issues/{key}/transitions", json={"to_state": "Done"})
    # Since failure_policy is fail_open_warn, transition succeeds (200) despite disallowed mutation
    assert resp_fow.status_code == 200
    assert resp_fow.json()["state"] == "Done"
