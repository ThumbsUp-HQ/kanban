# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: PLR0913, PLR0917, ANN401, PLC0415, D401, ERA001
"""Feature unit tests for workflow hooks REST API endpoints (KB-P5-17b)."""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING, Any

import pytest
import wasmtime
from sqlalchemy import select

from database.models.agent_definition import AgentDefinition
from database.models.projects import WorkflowState
from database.models.repo_binding import ProjectRepoBinding
from database.models.wasm_module import ApprovedWasmModule

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _make_wasm_bytes(json_payload: str = '{"allow": true}') -> bytes:
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
    name: str = "test-validator.wasm",
    wasm_bytes: bytes | None = None,
) -> str:
    """Seed an ApprovedWasmModule and return its hex SHA-256."""
    raw = wasm_bytes or _make_wasm_bytes('{"allow": true}')
    sha = hashlib.sha256(raw).digest()
    mod = ApprovedWasmModule(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        project_id=project_id,
        sha256=sha,
        name=name,
        wasm_bytes=raw,
        approved_by_id=admin_id,
    )
    session.add(mod)
    await session.commit()
    return sha.hex()


async def _seed_agent_definition(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    admin_id: uuid.UUID,
    slug: str = "qa-gatekeeper",
    name: str = "QA Gatekeeper",
    repo_access_mode: str = "none",
    timeout_ms: int = 60000,
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
        repo_access_mode=repo_access_mode,
        timeout_ms=timeout_ms,
    )
    session.add(agent)
    await session.commit()
    return agent_id


@pytest.fixture
async def workflow_api_setup(
    api_env: ApiEnv,
    make_user: Any,
    make_project: Any,
) -> dict[str, Any]:
    """Setup project, users with various roles, and workflow states."""
    admin: SeededUser = await make_user("wfadmin")
    member: SeededUser = await make_user("wfmember")
    outsider: SeededUser = await make_user("outsider")

    project_id = await make_project(
        "WFAPI",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", member: "MEMBER"},
    )

    # Query auto-created states for this project
    session = api_env.seed
    states_res = await session.execute(
        select(WorkflowState).where(WorkflowState.project_id == project_id)
    )
    states_by_name = {st.name: st for st in states_res.scalars().all()}

    # Add In QA state if not already present
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

    wasm_sha_hex = await _seed_approved_wasm(session, api_env.workspace_id, project_id, admin.id)
    agent_id = await _seed_agent_definition(session, api_env.workspace_id, admin.id)

    return {
        "admin": admin,
        "member": member,
        "outsider": outsider,
        "project_id": project_id,
        "states_by_name": states_by_name,
        "wasm_sha_hex": wasm_sha_hex,
        "agent_id": agent_id,
    }


@pytest.mark.asyncio
async def test_list_workflow_hooks_empty(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
) -> None:
    """Empty list returns empty list of transition rules."""
    admin = workflow_api_setup["admin"]
    client: httpx.AsyncClient = as_principal(admin, aal_level=1)

    resp = await client.get("/api/v1/projects/WFAPI/workflow-hooks")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_workflow_hooks_anti_enumeration(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
) -> None:
    """Non-admin and outsider users receive 404 Not Found to prevent enumeration."""
    member = workflow_api_setup["member"]
    outsider = workflow_api_setup["outsider"]

    # Member -> 404
    client_member = as_principal(member, aal_level=2)
    resp = await client_member.get("/api/v1/projects/WFAPI/workflow-hooks")
    assert resp.status_code == 404

    # Outsider -> 404
    client_outsider = as_principal(outsider, aal_level=2)
    resp = await client_outsider.get("/api/v1/projects/WFAPI/workflow-hooks")
    assert resp.status_code == 404

    # Unknown project -> 404
    client_admin = as_principal(workflow_api_setup["admin"], aal_level=2)
    resp = await client_admin.get("/api/v1/projects/NONEXISTENT/workflow-hooks")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_attach_workflow_hook_aal2_required(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
) -> None:
    """Attaching a workflow hook requires AAL2 elevation (403 AAL2_REQUIRED)."""
    admin = workflow_api_setup["admin"]
    # aal_level=1
    client = as_principal(admin, aal_level=1)

    payload = {
        "name": "Require Proof",
        "to_state": "In QA",
        "hook_kind": "sync_validator",
        "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
    }
    resp = await client.post("/api/v1/projects/WFAPI/workflow-hooks", json=payload)
    assert resp.status_code == 403
    assert "AAL2_REQUIRED" in resp.text


@pytest.mark.asyncio
async def test_attach_workflow_hook_validations(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
) -> None:
    """Test validation errors for hook attachment."""
    admin = workflow_api_setup["admin"]
    client = as_principal(admin, aal_level=2)

    # 1. Missing WASM for sync_validator
    resp1 = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "No WASM",
            "to_state": "In QA",
            "hook_kind": "sync_validator",
        },
    )
    assert resp1.status_code == 422

    # 2. Unapproved WASM SHA
    fake_sha = "00" * 32
    resp2 = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Bad WASM",
            "to_state": "In QA",
            "hook_kind": "sync_validator",
            "wasm_module_sha256": fake_sha,
        },
    )
    assert resp2.status_code == 422
    assert "WASM_MODULE_NOT_APPROVED" in resp2.text

    # 3. Missing agent for agent_interceptor
    resp3 = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "No Agent",
            "to_state": "In QA",
            "hook_kind": "agent_interceptor",
        },
    )
    assert resp3.status_code == 422

    # 4. Unknown agent
    resp4 = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Unknown Agent",
            "to_state": "In QA",
            "hook_kind": "agent_interceptor",
            "agent": "nonexistent-agent-slug",
        },
    )
    assert resp4.status_code == 422
    assert "AGENT_NOT_FOUND" in resp4.text

    # 5. Disallowed mutable field
    resp5 = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Bad Field",
            "to_state": "In QA",
            "hook_kind": "sync_mutator",
            "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
            "allowed_mutable_fields": ["description", "id", "state"],
        },
    )
    assert resp5.status_code == 422
    assert "MUTABLE_FIELD_NOT_ALLOWED" in resp5.text


@pytest.mark.asyncio
async def test_attach_and_list_workflow_hooks_success(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
) -> None:
    """Attach sync_validator, sync_mutator, and agent_interceptor, and verify listing."""
    admin = workflow_api_setup["admin"]
    client = as_principal(admin, aal_level=2)

    # 1. Attach sync_validator on (In Progress -> In QA)
    v_resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Validate Proof",
            "from_state": "In Progress",
            "to_state": "In QA",
            "hook_kind": "sync_validator",
            "failure_policy": "fail_closed",
            "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
            "description": "Validates QA proof link exists",
        },
    )
    assert v_resp.status_code == 201
    v_data = v_resp.json()
    assert v_data["name"] == "Validate Proof"
    assert v_data["from_state"] == "In Progress"
    assert v_data["to_state"] == "In QA"
    assert v_data["hook_kind"] == "sync_validator"
    assert "< 25.0 ms" in v_data["target_latency_budget"]
    assert v_data["is_enabled"] is True
    assert v_data["manifest_sha256"] is not None

    # 2. Attach sync_mutator on (* -> In QA)
    m_resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Auto Tag",
            "to_state": "In QA",
            "hook_kind": "sync_mutator",
            "failure_policy": "fail_open_warn",
            "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
            "allowed_mutable_fields": ["labels", "priority"],
        },
    )
    assert m_resp.status_code == 201
    m_data = m_resp.json()
    assert m_data["from_state"] is None
    assert m_data["to_state"] == "In QA"
    assert m_data["hook_kind"] == "sync_mutator"
    assert "priority" in m_data["allowed_mutable_fields"]

    # 3. Attach agent_interceptor on (In QA -> Done)
    a_resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "QA Agent Gate",
            "from_state": "In QA",
            "to_state": "Done",
            "hook_kind": "agent_interceptor",
            "agent": "qa-gatekeeper",
        },
    )
    assert a_resp.status_code == 201
    a_data = a_resp.json()
    assert a_data["hook_kind"] == "agent_interceptor"
    assert "< 180.0 s" in a_data["target_latency_budget"]
    assert a_data["agent_slug"] == "qa-gatekeeper"
    assert a_data["timeout_ms"] == 60000

    # 4. List hooks - should return transition rules grouped by (from_state, to_state)
    list_resp = await client.get("/api/v1/projects/WFAPI/workflow-hooks")
    assert list_resp.status_code == 200
    rules = list_resp.json()
    assert len(rules) == 3

    agent_hooks = [h for r in rules for h in r["hooks"] if h["hook_kind"] == "agent_interceptor"]
    assert len(agent_hooks) == 1
    assert agent_hooks[0]["timeout_ms"] == 60000
    assert agent_hooks[0]["agent_slug"] == "qa-gatekeeper"

    # Check rule shapes
    for rule in rules:
        assert "from_state" in rule
        assert "to_state" in rule
        assert "active_hook_count" in rule
        assert "hooks" in rule
        assert isinstance(rule["hooks"], list)


@pytest.mark.asyncio
async def test_agent_interceptor_hook_with_repo_binding_and_timeout(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
    api_env: ApiEnv,
) -> None:
    """Agent interceptor reflects custom timeout and repo binding.

    Validates that repo_access_mode is not none and is properly reflected.
    """
    admin = workflow_api_setup["admin"]
    client = as_principal(admin, aal_level=2)

    await _seed_agent_definition(
        api_env.seed,
        api_env.workspace_id,
        admin.id,
        slug="ro-coder",
        name="RO Coder",
        repo_access_mode="ro_vfs_mount",
        timeout_ms=180000,
    )

    repo_binding = ProjectRepoBinding(
        id=uuid.uuid4(),
        workspace_id=api_env.workspace_id,
        project_id=workflow_api_setup["project_id"],
        slug="frontend-core",
        remote_url="https://github.com/example/frontend.git",
        default_ref="main",
        access_mode="bare_git_tools",
        created_by=admin.id,
    )
    api_env.seed.add(repo_binding)
    await api_env.seed.commit()

    resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "RO Coder Gate",
            "from_state": "In QA",
            "to_state": "Done",
            "hook_kind": "agent_interceptor",
            "agent": "ro-coder",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["hook_kind"] == "agent_interceptor"
    assert data["timeout_ms"] == 180000
    assert data["repo_access_mode"] == "ro_vfs_mount"
    assert data["repo_binding_slug"] == "frontend-core"


@pytest.mark.asyncio
async def test_update_workflow_hook(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
) -> None:
    """Update hook parameters (name, description, mutable_fields, timeout)."""
    admin = workflow_api_setup["admin"]
    client = as_principal(admin, aal_level=2)

    # Attach mutator hook
    att_resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Initial Name",
            "to_state": "Done",
            "hook_kind": "sync_mutator",
            "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
            "allowed_mutable_fields": ["priority"],
        },
    )
    assert att_resp.status_code == 201
    hook_id = att_resp.json()["id"]

    # Update: invalid mutable field -> 422
    bad_up = await client.patch(
        f"/api/v1/workflow-hooks/{hook_id}",
        json={"allowed_mutable_fields": ["id"]},
    )
    assert bad_up.status_code == 422

    # Valid update
    up_resp = await client.patch(
        f"/api/v1/workflow-hooks/{hook_id}",
        json={
            "name": "Updated Name",
            "failure_policy": "fail_closed",
            "allowed_mutable_fields": ["priority", "cycle"],
        },
    )
    assert up_resp.status_code == 200
    updated = up_resp.json()
    assert updated["name"] == "Updated Name"
    assert updated["failure_policy"] == "fail_closed"
    assert "cycle" in updated["allowed_mutable_fields"]


@pytest.mark.asyncio
async def test_enable_disable_workflow_hook(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
) -> None:
    """Disable and enable a workflow hook."""
    admin = workflow_api_setup["admin"]
    client = as_principal(admin, aal_level=2)

    att_resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Toggle Hook",
            "to_state": "Done",
            "hook_kind": "sync_validator",
            "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
        },
    )
    hook_id = att_resp.json()["id"]
    assert att_resp.json()["is_enabled"] is True

    # Disable
    dis_resp = await client.post(f"/api/v1/workflow-hooks/{hook_id}/disable")
    assert dis_resp.status_code == 200
    assert dis_resp.json()["is_enabled"] is False

    # Enable
    en_resp = await client.post(f"/api/v1/workflow-hooks/{hook_id}/enable")
    assert en_resp.status_code == 200
    assert en_resp.json()["is_enabled"] is True


@pytest.mark.asyncio
async def test_delete_workflow_hook(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
) -> None:
    """Delete a workflow hook and verify removal."""
    admin = workflow_api_setup["admin"]
    client = as_principal(admin, aal_level=2)

    att_resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Delete Me",
            "to_state": "Done",
            "hook_kind": "sync_validator",
            "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
        },
    )
    hook_id = att_resp.json()["id"]

    # Delete
    del_resp = await client.delete(f"/api/v1/workflow-hooks/{hook_id}")
    assert del_resp.status_code == 204

    # Verify gone
    list_resp = await client.get("/api/v1/projects/WFAPI/workflow-hooks")
    assert list_resp.status_code == 200
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_reorder_workflow_hooks(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
) -> None:
    """Atomically reorder hooks within a transition."""
    admin = workflow_api_setup["admin"]
    client = as_principal(admin, aal_level=2)

    # Attach two hooks on (* -> Done)
    h1_resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "First Hook",
            "to_state": "Done",
            "hook_kind": "sync_validator",
            "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
        },
    )
    h1_id = h1_resp.json()["id"]

    h2_resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Second Hook",
            "to_state": "Done",
            "hook_kind": "sync_validator",
            "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
        },
    )
    h2_id = h2_resp.json()["id"]

    # Mismatched hook set -> 422 REORDER_SET_MISMATCH
    bad_reorder = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks/reorder",
        json={
            "transition": {"from_state": None, "to_state": "Done"},
            "ordered_hook_ids": [h1_id],  # Missing h2_id!
        },
    )
    assert bad_reorder.status_code == 422
    assert "REORDER_SET_MISMATCH" in bad_reorder.text

    # Valid reverse reorder
    reorder_resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks/reorder",
        json={
            "transition": {"from_state": None, "to_state": "Done"},
            "ordered_hook_ids": [h2_id, h1_id],
        },
    )
    assert reorder_resp.status_code == 200
    reordered_hooks = reorder_resp.json()
    assert len(reordered_hooks) == 2
    assert reordered_hooks[0]["id"] == h2_id
    assert reordered_hooks[1]["id"] == h1_id


@pytest.mark.asyncio
async def test_dry_run_endpoint(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
) -> None:
    """Dry-run endpoint tests: validation, sample_ticket execution, and would_commit flag."""
    admin = workflow_api_setup["admin"]
    client = as_principal(admin, aal_level=1)

    # 1. Reject if both sample_ticket and issue_key
    resp_both = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "Done",
            "issue_key": "WFAPI-1",
            "sample_ticket": {
                "summary": "Sample",
                "description_markdown": "Test",
                "priority": "medium",
                "labels": [],
            },
        },
    )
    assert resp_both.status_code == 422

    # 2. Reject if neither sample_ticket nor issue_key
    resp_neither = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "Done",
        },
    )
    assert resp_neither.status_code == 422

    # 3. Reject description > 1 MiB
    resp_large = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "Done",
            "sample_ticket": {
                "summary": "Huge Ticket",
                "description_markdown": "x" * (1024 * 1024 + 10),
                "priority": "medium",
                "labels": [],
            },
        },
    )
    assert resp_large.status_code == 422

    # 4. Valid sample ticket dry run
    resp_valid = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks/dry-run",
        json={
            "from_state": "In Progress",
            "to_state": "Done",
            "sample_ticket": {
                "summary": "Valid Sample",
                "description_markdown": "A test sample ticket",
                "priority": "high",
                "labels": [],
            },
        },
    )
    assert resp_valid.status_code == 200
    data = resp_valid.json()
    assert "steps" in data
    assert "would_commit" in data
    assert data["would_commit"] is True


@pytest.mark.asyncio
async def test_workflow_hook_not_found_and_invalid_ids(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
) -> None:
    """Test 404 not found and 422 invalid UUID on hook operations."""
    admin = workflow_api_setup["admin"]
    client = as_principal(admin, aal_level=2)
    fake_uuid = str(uuid.uuid4())

    # 1. Invalid UUID on enable
    resp = await client.post("/api/v1/workflow-hooks/not-a-uuid/enable")
    assert resp.status_code == 422
    assert "INVALID_HOOK_ID" in resp.text

    # 2. Not found on enable
    resp = await client.post(f"/api/v1/workflow-hooks/{fake_uuid}/enable")
    assert resp.status_code == 404

    # 3. Invalid UUID on delete
    resp = await client.delete("/api/v1/workflow-hooks/not-a-uuid")
    assert resp.status_code == 422
    assert "INVALID_HOOK_ID" in resp.text

    # 4. Not found on delete
    resp = await client.delete(f"/api/v1/workflow-hooks/{fake_uuid}")
    assert resp.status_code == 404

    # 5. Invalid UUID on update
    resp = await client.patch("/api/v1/workflow-hooks/not-a-uuid", json={"name": "new"})
    assert resp.status_code == 422
    assert "INVALID_HOOK_ID" in resp.text

    # 6. Not found on update
    resp = await client.patch(f"/api/v1/workflow-hooks/{fake_uuid}", json={"name": "new"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_workflow_hook_advanced_updates_and_validations(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
) -> None:
    """Test updating failure_policy, allowed_mutable_fields, wasm_sha, agent, and error branches."""
    admin = workflow_api_setup["admin"]
    client = as_principal(admin, aal_level=2)

    # 1. Attach validator hook
    v_resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Val Adv",
            "from_state": "In Progress",
            "to_state": "Done",
            "hook_kind": "sync_validator",
            "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
        },
    )
    assert v_resp.status_code == 201
    val_id = v_resp.json()["id"]

    # 2. Attach mutator hook
    m_resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Mut Adv",
            "from_state": "In Progress",
            "to_state": "Done",
            "hook_kind": "sync_mutator",
            "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
            "allowed_mutable_fields": ["labels"],
        },
    )
    assert m_resp.status_code == 201
    mut_id = m_resp.json()["id"]

    # 3. Attach agent hook
    a_resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Agent Adv",
            "from_state": "In Progress",
            "to_state": "Done",
            "hook_kind": "agent_interceptor",
            "agent": "qa-gatekeeper",
        },
    )
    assert a_resp.status_code == 201
    agent_id = a_resp.json()["id"]

    # 4. Update failure_policy on validator
    up_fp = await client.patch(
        f"/api/v1/workflow-hooks/{val_id}",
        json={"failure_policy": "fail_open_warn"},
    )
    assert up_fp.status_code == 200
    assert up_fp.json()["failure_policy"] == "fail_open_warn"

    # 5. Update allowed_mutable_fields on mutator
    up_mut = await client.patch(
        f"/api/v1/workflow-hooks/{mut_id}",
        json={"allowed_mutable_fields": ["labels", "priority", "cycle"]},
    )
    assert up_mut.status_code == 200
    assert "priority" in up_mut.json()["allowed_mutable_fields"]

    # 6. Reject invalid wasm sha on update (unapproved)
    unapproved_sha = "00" * 32
    up_wasm_bad = await client.patch(
        f"/api/v1/workflow-hooks/{val_id}",
        json={"wasm_module_sha256": unapproved_sha},
    )
    assert up_wasm_bad.status_code == 422
    assert "WASM_MODULE_NOT_APPROVED" in up_wasm_bad.text

    # 7. Reject setting wasm sha on agent interceptor
    up_agent_wasm = await client.patch(
        f"/api/v1/workflow-hooks/{agent_id}",
        json={"wasm_module_sha256": workflow_api_setup["wasm_sha_hex"]},
    )
    assert up_agent_wasm.status_code == 422
    assert "INVALID_HOOK_CONFIG" in up_agent_wasm.text

    # 8. Reject setting agent on sync validator
    up_val_agent = await client.patch(
        f"/api/v1/workflow-hooks/{val_id}",
        json={"agent": "qa-gatekeeper"},
    )
    assert up_val_agent.status_code == 422
    assert "INVALID_HOOK_CONFIG" in up_val_agent.text

    # 9. Reject non-existent agent on agent interceptor
    up_agent_missing = await client.patch(
        f"/api/v1/workflow-hooks/{agent_id}",
        json={"agent": "non-existent-agent-slug"},
    )
    assert up_agent_missing.status_code == 422
    assert "AGENT_NOT_FOUND" in up_agent_missing.text

    # 10. Update agent by valid slug
    up_agent_ok = await client.patch(
        f"/api/v1/workflow-hooks/{agent_id}",
        json={"agent": "qa-gatekeeper"},
    )
    assert up_agent_ok.status_code == 200


@pytest.mark.asyncio
async def test_reorder_hooks_edge_cases(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
) -> None:
    """Test reordering edge cases: missing to_state, invalid UUID, mismatch sets."""
    admin = workflow_api_setup["admin"]
    client = as_principal(admin, aal_level=2)

    # 1. Missing to_state
    resp1 = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks/reorder",
        json={
            "transition": {"from_state": "In Progress"},
            "ordered_hook_ids": [str(uuid.uuid4())],
        },
    )
    assert resp1.status_code == 422
    assert "INVALID_TRANSITION" in resp1.text

    # 2. Invalid UUID in ordered_hook_ids
    resp2 = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks/reorder",
        json={
            "transition": {"from_state": "In Progress", "to_state": "Done"},
            "ordered_hook_ids": ["not-a-uuid"],
        },
    )
    assert resp2.status_code == 422
    assert "REORDER_SET_MISMATCH" in resp2.text

    # 3. Set mismatch (hook ID does not match existing set)
    resp3 = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks/reorder",
        json={
            "transition": {"from_state": "In Progress", "to_state": "Done"},
            "ordered_hook_ids": [str(uuid.uuid4())],
        },
    )
    assert resp3.status_code == 422
    assert "REORDER_SET_MISMATCH" in resp3.text


@pytest.mark.asyncio
async def test_hooks_service_internal_utilities(
    workflow_api_setup: dict[str, Any],
    api_env: Any,
) -> None:
    """Directly test internal parsing, validation, and resolution utilities in hooks_service."""
    from kanban.api.problems import ProblemException
    from kanban.workflows.hooks_service import (
        WorkflowHookService,
        _parse_sha256_hex,
        _validate_mutable_fields,
    )

    # 1. _parse_sha256_hex invalid hex
    with pytest.raises(ProblemException) as exc_hex:
        _parse_sha256_hex("not-hex-string-at-all")
    assert exc_hex.value.code == "WASM_MODULE_NOT_APPROVED"

    # 2. _parse_sha256_hex wrong length (e.g. 4 hex chars = 2 bytes)
    with pytest.raises(ProblemException) as exc_len:
        _parse_sha256_hex("deadbeef")
    assert exc_len.value.code == "WASM_MODULE_NOT_APPROVED"

    # 3. _validate_mutable_fields: empty string ignored, valid field kept
    clean = _validate_mutable_fields(["   ", "labels", "priority"])
    assert clean == ["labels", "priority"]

    # 4. _validate_mutable_fields: immutable field rejected
    with pytest.raises(ProblemException) as exc_imm:
        _validate_mutable_fields(["description"])
    assert exc_imm.value.code == "MUTABLE_FIELD_NOT_ALLOWED"

    # 5. _validate_mutable_fields: non-universe field rejected
    with pytest.raises(ProblemException) as exc_univ:
        _validate_mutable_fields(["arbitrary_unknown_field"])
    assert exc_univ.value.code == "MUTABLE_FIELD_NOT_ALLOWED"

    # 6. WorkflowHookService.resolve_state wildcard to_state rejected
    session = api_env.seed
    proj_id = workflow_api_setup["project_id"]
    with pytest.raises(ProblemException) as exc_wild:
        await WorkflowHookService.resolve_state(session, proj_id, "*", allow_wildcard=False)
    assert exc_wild.value.code == "INVALID_STATE"

    # 7. WorkflowHookService.resolve_state non-existent state rejected
    with pytest.raises(ProblemException) as exc_nostate:
        await WorkflowHookService.resolve_state(session, proj_id, "NonExistentState")
    assert exc_nostate.value.code == "INVALID_STATE"

    # 8. WorkflowHookService.resolve_state by UUID
    st_row = (
        await session.execute(
            select(WorkflowState).where(WorkflowState.project_id == proj_id).limit(1)
        )
    ).scalar_one()
    res_id, res_name = await WorkflowHookService.resolve_state(session, proj_id, str(st_row.id))
    assert res_id == st_row.id
    assert res_name == st_row.name


@pytest.mark.asyncio
async def test_hooks_service_agent_and_sync_cross_configuration_rejections(
    workflow_api_setup: dict[str, Any],
    as_principal: Any,
) -> None:
    """Test rejecting agent on sync hook, wasm on agent hook, and attaching agent by UUID."""
    admin = workflow_api_setup["admin"]
    client = as_principal(admin, aal_level=2)
    agent_id = workflow_api_setup["agent_id"]

    # 1. Sync hook with agent specified -> 422
    resp1 = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Sync With Agent",
            "to_state": "In QA",
            "hook_kind": "sync_validator",
            "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
            "agent": "qa-gatekeeper",
        },
    )
    assert resp1.status_code == 422
    assert "INVALID_HOOK_CONFIG" in resp1.text

    # 2. Agent interceptor with wasm specified -> 422
    resp2 = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Agent With Wasm",
            "to_state": "In QA",
            "hook_kind": "agent_interceptor",
            "agent": "qa-gatekeeper",
            "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
        },
    )
    assert resp2.status_code == 422
    assert "INVALID_HOOK_CONFIG" in resp2.text

    # 3. Agent interceptor specified by UUID -> 201
    resp3 = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Agent By UUID",
            "to_state": "In QA",
            "hook_kind": "agent_interceptor",
            "agent": str(agent_id),
        },
    )
    assert resp3.status_code == 201


async def test_approved_wasm_modules_list_and_builtin_auto_seed(
    workflow_api_setup: dict[str, Any],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify GET /projects/{project}/approved-wasm-modules and auto-seeding built-in formulas."""
    admin = workflow_api_setup["admin"]
    member = workflow_api_setup["member"]
    client = as_principal(admin, aal_level=2)

    # 1. Non-admin caller receives 404/403 anti-enumeration
    member_client = as_principal(member, aal_level=2)
    res_member = await member_client.get("/api/v1/projects/WFAPI/approved-wasm-modules")
    assert res_member.status_code in (403, 404)

    # 2. Admin caller receives seeded built-in formulas list
    client = as_principal(admin, aal_level=2)
    res_admin = await client.get("/api/v1/projects/WFAPI/approved-wasm-modules")
    assert res_admin.status_code == 200
    modules = res_admin.json()
    assert isinstance(modules, list)
    names = [m["name"] for m in modules]
    assert "qa-proof-validator" in names
    assert "security-invariant-validator" in names
    assert "auto-label-mutator" in names

    # 3. Create hook using built-in sha without prior manual seeding succeeds (201)
    qa_sha = "2274a8517568ba72a2aa1bf322bfe14b205ce47b712a0533929e7535010aeede"
    resp_hook = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Builtin QA Hook",
            "to_state": "In QA",
            "hook_kind": "sync_validator",
            "wasm_module_sha256": qa_sha,
        },
    )
    assert resp_hook.status_code == 201
    assert resp_hook.json()["wasm_module_sha256"] == qa_sha


async def test_workflow_hooks_explicit_commit_durability(
    workflow_api_setup: dict[str, Any],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify explicit session.commit() durability across all mutating workflow_hooks endpoints."""
    admin = workflow_api_setup["admin"]
    client = as_principal(admin, aal_level=2)

    # 1. POST /api/v1/projects/{project}/workflow-hooks creates hook
    create_resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Commit Durability Hook 1",
            "from_state": "In Progress",
            "to_state": "In QA",
            "hook_kind": "sync_validator",
            "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
            "description": "Initial description before patch",
        },
    )
    assert create_resp.status_code == 201
    hook_1 = create_resp.json()
    hook_1_id = hook_1["id"]

    # Immediate GET verifies committed durability
    list_resp = await client.get("/api/v1/projects/WFAPI/workflow-hooks")
    assert list_resp.status_code == 200
    groups = list_resp.json()
    hook_ids = [h["id"] for g in groups for h in g["hooks"]]
    assert hook_1_id in hook_ids

    # 2. PATCH /api/v1/workflow-hooks/{hook_id} updates hook
    patch_resp = await client.patch(
        f"/api/v1/workflow-hooks/{hook_1_id}",
        json={
            "name": "Commit Durability Hook 1 Updated",
            "failure_policy": "fail_open_warn",
        },
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Commit Durability Hook 1 Updated"
    assert patch_resp.json()["failure_policy"] == "fail_open_warn"

    # Immediate GET verifies updated state committed
    list_resp2 = await client.get("/api/v1/projects/WFAPI/workflow-hooks")
    assert list_resp2.status_code == 200
    all_hooks = {h["id"]: h for g in list_resp2.json() for h in g["hooks"]}
    assert all_hooks[hook_1_id]["name"] == "Commit Durability Hook 1 Updated"
    assert all_hooks[hook_1_id]["failure_policy"] == "fail_open_warn"

    # 3. POST /api/v1/workflow-hooks/{hook_id}/disable
    disable_resp = await client.post(f"/api/v1/workflow-hooks/{hook_1_id}/disable")
    assert disable_resp.status_code == 200
    assert disable_resp.json()["is_enabled"] is False

    # Immediate GET verifies disabled state committed
    list_resp3 = await client.get("/api/v1/projects/WFAPI/workflow-hooks")
    all_hooks3 = {h["id"]: h for g in list_resp3.json() for h in g["hooks"]}
    assert all_hooks3[hook_1_id]["is_enabled"] is False

    # 4. POST /api/v1/workflow-hooks/{hook_id}/enable
    enable_resp = await client.post(f"/api/v1/workflow-hooks/{hook_1_id}/enable")
    assert enable_resp.status_code == 200
    assert enable_resp.json()["is_enabled"] is True

    # Immediate GET verifies enabled state committed
    list_resp4 = await client.get("/api/v1/projects/WFAPI/workflow-hooks")
    all_hooks4 = {h["id"]: h for g in list_resp4.json() for h in g["hooks"]}
    assert all_hooks4[hook_1_id]["is_enabled"] is True

    # 5. Create second hook on same transition and test reorder durability
    create_resp2 = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks",
        json={
            "name": "Commit Durability Hook 2",
            "from_state": "In Progress",
            "to_state": "In QA",
            "hook_kind": "sync_validator",
            "wasm_module_sha256": workflow_api_setup["wasm_sha_hex"],
        },
    )
    assert create_resp2.status_code == 201
    hook_2_id = create_resp2.json()["id"]

    reorder_resp = await client.post(
        "/api/v1/projects/WFAPI/workflow-hooks/reorder",
        json={
            "transition": {"from_state": "In Progress", "to_state": "In QA"},
            "ordered_hook_ids": [hook_2_id, hook_1_id],
        },
    )
    assert reorder_resp.status_code == 200
    reordered_ids = [h["id"] for h in reorder_resp.json()]
    assert reordered_ids == [hook_2_id, hook_1_id]

    # Immediate GET verifies reordered ranks committed
    list_resp5 = await client.get("/api/v1/projects/WFAPI/workflow-hooks")
    target_group = next(
        g
        for g in list_resp5.json()
        if g["from_state"] == "In Progress" and g["to_state"] == "In QA"
    )
    assert [h["id"] for h in target_group["hooks"]] == [hook_2_id, hook_1_id]

    # 6. DELETE /api/v1/workflow-hooks/{hook_id} durability
    delete_resp = await client.delete(f"/api/v1/workflow-hooks/{hook_1_id}")
    assert delete_resp.status_code == 204

    # Immediate GET verifies deletion committed
    list_resp6 = await client.get("/api/v1/projects/WFAPI/workflow-hooks")
    remaining_ids = [h["id"] for g in list_resp6.json() for h in g["hooks"]]
    assert hook_1_id not in remaining_ids
    assert hook_2_id in remaining_ids

    # Clean up second hook
    await client.delete(f"/api/v1/workflow-hooks/{hook_2_id}")
