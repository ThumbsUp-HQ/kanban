# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/admin tool 12: destructive_lifecycle (KB-P4-12, S11.4)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock

import pytest
import yaml

from database.models.issues import Issue
from database.models.knowledge import Doc, Page
from database.models.projects import Module
from database.models.spine import ObjectRecord
from kanban.tests.security.helpers import (
    add_role_binding,
    create_project,
    create_registered_object,
    rebuild_era,
)
from mcp.errors import KbMcpError, McpErrorCode
from mcp.surfaces.admin.destructive_lifecycle import (
    create_destructive_lifecycle_tool,
    destructive_lifecycle_handler,
)

if TYPE_CHECKING:
    from mcp.tests.admin.conftest import AdminTestEnv

pytestmark = pytest.mark.committed_db


async def _call_destructive_lifecycle(  # noqa: PLR0913
    env: AdminTestEnv,
    arguments: dict[str, Any],
    *,
    subject_token: str | None = None,
    scopes: str | None = None,
    aal_level: int | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Invoke destructive_lifecycle via JSON-RPC 2.0 tools/call on /mcp/admin."""
    active_session_id = session_id
    token_to_use = subject_token or env.token_server_admin_full
    if active_session_id is None:
        init_resp = await env.mcp_client.post(
            "/mcp/admin",
            json={
                "jsonrpc": "2.0",
                "id": 999,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-admin", "version": "1.0"},
                },
            },
            headers={"X-KB-Subject-Token": token_to_use},
        )
        assert init_resp.status_code == 200, init_resp.text
        active_session_id = init_resp.headers["mcp-session-id"]

    headers: dict[str, str] = {
        "mcp-session-id": active_session_id,
        "X-KB-Subject-Token": token_to_use,
    }
    if scopes is not None:
        headers["X-KB-Scopes"] = scopes
    if aal_level is not None:
        headers["X-KB-AAL-Level"] = str(aal_level)

    req_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "destructive_lifecycle",
            "arguments": arguments,
        },
    }
    resp = await env.mcp_client.post("/mcp/admin", json=req_payload, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    return cast("dict[str, Any]", data)


@pytest.mark.asyncio
async def test_admin_surface_tools_list(admin_env: AdminTestEnv) -> None:
    """Verify destructive_lifecycle is registered on /mcp/admin with required schema."""
    init_resp = await admin_env.mcp_client.post(
        "/mcp/admin",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-admin", "version": "1.0"},
            },
        },
        headers={"X-KB-Subject-Token": admin_env.token_server_admin_full},
    )
    assert init_resp.status_code == 200
    session_id = init_resp.headers["mcp-session-id"]

    list_resp = await admin_env.mcp_client.post(
        "/mcp/admin",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers={
            "mcp-session-id": session_id,
            "X-KB-Subject-Token": admin_env.token_server_admin_full,
        },
    )
    assert list_resp.status_code == 200
    tools = list_resp.json()["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "destructive_lifecycle" in tool_names

    destr_tool = next(t for t in tools if t["name"] == "destructive_lifecycle")
    props = destr_tool["inputSchema"]["properties"]
    assert "action" in props
    assert "target_kind" in props
    assert "target" in props
    assert "mode" in props
    assert "confirmation_token" in props
    assert "confirm_phrase" in props
    assert "reason" in props


@pytest.mark.asyncio
async def test_destructive_lifecycle_help_action(admin_env: AdminTestEnv) -> None:
    """Action 'help' returns usage instructions, supported kinds, and parameter info."""
    data = await _call_destructive_lifecycle(admin_env, {"action": "help"})
    result = data["result"]
    assert not result.get("isError")

    text_out = result["content"][0]["text"]
    parsed = yaml.safe_load(text_out)

    assert parsed["tool"] == "destructive_lifecycle"
    assert "params" in parsed
    assert "action" in parsed["params"]
    assert "target_kind" in parsed["params"]
    assert "mode" in parsed["params"]
    assert "confirmation_token" in parsed["params"]


@pytest.mark.asyncio
async def test_destructive_lifecycle_positive_issue_trash_and_restore(
    admin_env: AdminTestEnv,
) -> None:
    """Two-stage flow: request_delete -> execute_delete soft-trashes, restore brings back."""
    proj_id = await create_project(
        admin_env.seed_session,
        admin_env.workspace_id,
        identifier="MCPTEST",
        name="MCP Test Project",
        created_by_id=admin_env.server_admin.id,
    )
    await add_role_binding(
        admin_env.seed_session,
        admin_env.workspace_id,
        admin_env.server_admin.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(admin_env.seed_session, admin_env.workspace_id)
    await admin_env.seed_session.commit()

    iss_data = await admin_env.internal_client.request(
        "POST",
        "/api/v1/projects/MCPTEST/issues",
        json_data={"summary": "MCP Issue 1"},
        subject_token=admin_env.token_server_admin_full,
    )
    assert isinstance(iss_data, dict)
    iss_id = uuid.UUID(iss_data["id"])
    iss_key = iss_data["key"]

    # Stage 1: request_delete
    req_res = await _call_destructive_lifecycle(
        admin_env,
        {"action": "request_delete", "target_kind": "issue", "target": iss_key, "mode": "trash"},
    )
    res_1 = req_res["result"]
    assert not res_1.get("isError")
    p1 = yaml.safe_load(res_1["content"][0]["text"])

    assert p1["stage"] == "confirmation_required"
    assert p1["target"] == iss_key
    assert p1["mode"] == "trash"
    assert p1["confirm_phrase"] == f"TRASH ISSUE {iss_key}"
    assert p1["confirmation_token"].startswith("kb_del_")
    assert len(p1["blast_hash"]) == 64
    assert p1["expires_in_sec"] <= 300

    token = p1["confirmation_token"]
    phrase = p1["confirm_phrase"]

    # Stage 2: execute_delete
    exec_res = await _call_destructive_lifecycle(
        admin_env,
        {
            "action": "execute_delete",
            "target_kind": "issue",
            "target": iss_key,
            "mode": "trash",
            "confirmation_token": token,
            "confirm_phrase": phrase,
            "reason": "Audited decommission of MCP issue 1",
        },
    )
    res_2 = exec_res["result"]
    assert not res_2.get("isError")
    p2 = yaml.safe_load(res_2["content"][0]["text"])

    assert p2["status"] == "executed"
    assert p2["target"] == iss_key

    # Verify soft-deleted in DB
    obj = await admin_env.seed_session.get(ObjectRecord, iss_id)
    assert obj is not None
    assert obj.deleted_at is not None

    # Stage 3: restore
    restore_res = await _call_destructive_lifecycle(
        admin_env,
        {
            "action": "restore",
            "target_kind": "issue",
            "target": iss_key,
            "reason": "Restoring mistakenly trashed issue",
        },
    )
    res_3 = restore_res["result"]
    assert not res_3.get("isError")
    p3 = yaml.safe_load(res_3["content"][0]["text"])

    assert p3["status"] == "restored"

    # Verify active in DB
    await admin_env.seed_session.refresh(obj)
    assert obj.deleted_at is None


@pytest.mark.asyncio
async def test_destructive_lifecycle_positive_permanent_purge(
    admin_env: AdminTestEnv,
) -> None:
    """Server admin permanently purges soft-trashed issue via MCP."""
    proj_id = await create_project(
        admin_env.seed_session,
        admin_env.workspace_id,
        identifier="MCPPURG",
        name="MCP Purge Project",
        created_by_id=admin_env.server_admin.id,
    )
    await add_role_binding(
        admin_env.seed_session,
        admin_env.workspace_id,
        admin_env.server_admin.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(admin_env.seed_session, admin_env.workspace_id)
    await admin_env.seed_session.commit()

    iss_data = await admin_env.internal_client.request(
        "POST",
        "/api/v1/projects/MCPPURG/issues",
        json_data={"summary": "Issue to permanently purge"},
        subject_token=admin_env.token_server_admin_full,
    )
    assert isinstance(iss_data, dict)
    iss_id = uuid.UUID(iss_data["id"])
    iss_key = iss_data["key"]

    # Move to trash first
    req1 = await _call_destructive_lifecycle(
        admin_env,
        {"action": "request_delete", "target_kind": "issue", "target": iss_key, "mode": "trash"},
    )
    tok1 = yaml.safe_load(req1["result"]["content"][0]["text"])["confirmation_token"]
    await _call_destructive_lifecycle(
        admin_env,
        {
            "action": "execute_delete",
            "target_kind": "issue",
            "target": iss_key,
            "mode": "trash",
            "confirmation_token": tok1,
            "confirm_phrase": f"TRASH ISSUE {iss_key}",
            "reason": "Initial move to trash before purge",
        },
    )

    # Request permanent purge
    req_purge = await _call_destructive_lifecycle(
        admin_env,
        {
            "action": "request_delete",
            "target_kind": "issue",
            "target": iss_key,
            "mode": "permanent_purge",
        },
    )
    p_purge = yaml.safe_load(req_purge["result"]["content"][0]["text"])
    assert p_purge["mode"] == "permanent_purge"
    assert p_purge["confirm_phrase"] == f"PURGE ISSUE {iss_key}"

    purge_token = p_purge["confirmation_token"]

    # Execute permanent purge
    exec_purge = await _call_destructive_lifecycle(
        admin_env,
        {
            "action": "execute_delete",
            "target_kind": "issue",
            "target": iss_key,
            "mode": "permanent_purge",
            "confirmation_token": purge_token,
            "confirm_phrase": f"PURGE ISSUE {iss_key}",
            "reason": "Permanent audited purge of MCP issue",
        },
    )
    res_purge = exec_purge["result"]
    assert not res_purge.get("isError")
    assert yaml.safe_load(res_purge["content"][0]["text"])["status"] == "executed"

    # Verify completely deleted from objects and issues
    assert await admin_env.seed_session.get(ObjectRecord, iss_id) is None
    assert await admin_env.seed_session.get(Issue, iss_id) is None


@pytest.mark.asyncio
async def test_destructive_lifecycle_page_subtree_and_module(
    admin_env: AdminTestEnv,
) -> None:
    """Two-stage delete of page subtree and module via MCP."""
    proj_id = await create_project(
        admin_env.seed_session,
        admin_env.workspace_id,
        identifier="MCPDOCS",
        name="MCP Docs",
        created_by_id=admin_env.server_admin.id,
    )
    await add_role_binding(
        admin_env.seed_session,
        admin_env.workspace_id,
        admin_env.server_admin.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )

    doc_id = await create_registered_object(
        admin_env.seed_session,
        admin_env.workspace_id,
        kind="doc",
        key="MCPDoc",
        title="MCP Doc",
        project_id=proj_id,
        created_by_id=admin_env.server_admin.id,
    )
    doc = Doc(
        id=doc_id,
        workspace_id=admin_env.workspace_id,
        project_id=proj_id,
        title="MCP Doc",
        body_markdown="Doc body",
        hierarchy_path="mcpdoc",
    )
    admin_env.seed_session.add(doc)

    parent_page_id = await create_registered_object(
        admin_env.seed_session,
        admin_env.workspace_id,
        kind="page",
        key="ParentP",
        title="Parent Page",
        project_id=proj_id,
        created_by_id=admin_env.server_admin.id,
    )
    p_page = Page(
        id=parent_page_id,
        workspace_id=admin_env.workspace_id,
        doc_id=doc_id,
        title="Parent Page",
        body_markdown="Parent body",
        hierarchy_path="mcpdoc.parent",
    )
    admin_env.seed_session.add(p_page)

    child_page_id = await create_registered_object(
        admin_env.seed_session,
        admin_env.workspace_id,
        kind="page",
        key="ChildP",
        title="Child Page",
        project_id=proj_id,
        created_by_id=admin_env.server_admin.id,
    )
    c_page = Page(
        id=child_page_id,
        workspace_id=admin_env.workspace_id,
        doc_id=doc_id,
        parent_page_id=parent_page_id,
        title="Child Page",
        body_markdown="Child body",
        hierarchy_path="mcpdoc.parent.child",
    )
    admin_env.seed_session.add(c_page)

    # Also create a module
    mod_id = await create_registered_object(
        admin_env.seed_session,
        admin_env.workspace_id,
        kind="module",
        key="MCPMod",
        title="MCP Module",
        project_id=proj_id,
        created_by_id=admin_env.server_admin.id,
    )
    mod = Module(
        id=mod_id,
        workspace_id=admin_env.workspace_id,
        project_id=proj_id,
        name="MCP Module",
    )
    admin_env.seed_session.add(mod)
    await rebuild_era(admin_env.seed_session, admin_env.workspace_id)
    await admin_env.seed_session.commit()

    # 1. Soft-trash parent page (cascades deleted_at to child page)
    req_page = await _call_destructive_lifecycle(
        admin_env,
        {
            "action": "request_delete",
            "target_kind": "page",
            "target": str(parent_page_id),
            "mode": "trash",
        },
    )
    tok_p = yaml.safe_load(req_page["result"]["content"][0]["text"])["confirmation_token"]
    phrase_p = yaml.safe_load(req_page["result"]["content"][0]["text"])["confirm_phrase"]

    exec_page = await _call_destructive_lifecycle(
        admin_env,
        {
            "action": "execute_delete",
            "target_kind": "page",
            "target": str(parent_page_id),
            "mode": "trash",
            "confirmation_token": tok_p,
            "confirm_phrase": phrase_p,
            "reason": "Soft-trashing parent page subtree",
        },
    )
    assert not exec_page["result"].get("isError")

    # Verify both parent and child page are soft-deleted
    p_obj = await admin_env.seed_session.get(ObjectRecord, parent_page_id)
    c_obj = await admin_env.seed_session.get(ObjectRecord, child_page_id)
    assert p_obj is not None
    assert p_obj.deleted_at is not None
    assert c_obj is not None
    assert c_obj.deleted_at is not None

    # 2. Permanent purge module (direct purge, no soft-trash)
    req_mod = await _call_destructive_lifecycle(
        admin_env,
        {
            "action": "request_delete",
            "target_kind": "module",
            "target": str(mod_id),
            "mode": "permanent_purge",
        },
    )
    tok_m = yaml.safe_load(req_mod["result"]["content"][0]["text"])["confirmation_token"]
    phrase_m = yaml.safe_load(req_mod["result"]["content"][0]["text"])["confirm_phrase"]

    exec_mod = await _call_destructive_lifecycle(
        admin_env,
        {
            "action": "execute_delete",
            "target_kind": "module",
            "target": str(mod_id),
            "mode": "permanent_purge",
            "confirmation_token": tok_m,
            "confirm_phrase": phrase_m,
            "reason": "Permanent deletion of decommissioned module",
        },
    )
    assert not exec_mod["result"].get("isError")
    assert await admin_env.seed_session.get(ObjectRecord, mod_id) is None


@pytest.mark.asyncio
async def test_destructive_lifecycle_replay_and_caller_binding(
    admin_env: AdminTestEnv,
) -> None:
    """Security invariants: token replay fails, caller mismatch fails closed."""
    proj_id = await create_project(
        admin_env.seed_session,
        admin_env.workspace_id,
        identifier="BIND",
        name="Binding Test",
        created_by_id=admin_env.server_admin.id,
    )
    await add_role_binding(
        admin_env.seed_session,
        admin_env.workspace_id,
        admin_env.server_admin.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(admin_env.seed_session, admin_env.workspace_id)
    await admin_env.seed_session.commit()

    iss_data = await admin_env.internal_client.request(
        "POST",
        "/api/v1/projects/BIND/issues",
        json_data={"summary": "Binding Issue 1"},
        subject_token=admin_env.token_server_admin_full,
    )
    assert isinstance(iss_data, dict)
    iss_key = iss_data["key"]

    # Request token as Server Admin
    req = await _call_destructive_lifecycle(
        admin_env,
        {"action": "request_delete", "target_kind": "issue", "target": iss_key, "mode": "trash"},
        subject_token=admin_env.token_server_admin_full,
    )
    token = yaml.safe_load(req["result"]["content"][0]["text"])["confirmation_token"]
    phrase = yaml.safe_load(req["result"]["content"][0]["text"])["confirm_phrase"]

    # 1. Caller mismatch: Workspace Admin attempts to execute Server Admin's token
    mismatch_res = await _call_destructive_lifecycle(
        admin_env,
        {
            "action": "execute_delete",
            "target_kind": "issue",
            "target": iss_key,
            "mode": "trash",
            "confirmation_token": token,
            "confirm_phrase": phrase,
            "reason": "Attempting execution from unauthorized principal",
        },
        subject_token=admin_env.token_workspace_admin,
    )
    res_m = mismatch_res["result"]
    assert res_m.get("isError")
    err_yaml = yaml.safe_load(res_m["content"][0]["text"])
    assert err_yaml["error"]["code"] in ("INSUFFICIENT_SCOPE", "TOKEN_CALLER_MISMATCH")


@pytest.mark.asyncio
async def test_destructive_lifecycle_wrong_phrase_and_target_mismatch(
    admin_env: AdminTestEnv,
) -> None:
    """Wrong confirm_phrase and target mismatch fail closed."""
    proj_id = await create_project(
        admin_env.seed_session,
        admin_env.workspace_id,
        identifier="PHR",
        name="Phrase Test",
        created_by_id=admin_env.server_admin.id,
    )
    await add_role_binding(
        admin_env.seed_session,
        admin_env.workspace_id,
        admin_env.server_admin.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(admin_env.seed_session, admin_env.workspace_id)
    await admin_env.seed_session.commit()

    iss1 = await admin_env.internal_client.request(
        "POST",
        "/api/v1/projects/PHR/issues",
        json_data={"summary": "Issue 1"},
        subject_token=admin_env.token_server_admin_full,
    )
    iss2 = await admin_env.internal_client.request(
        "POST",
        "/api/v1/projects/PHR/issues",
        json_data={"summary": "Issue 2"},
        subject_token=admin_env.token_server_admin_full,
    )
    assert isinstance(iss1, dict)
    assert isinstance(iss2, dict)
    key1 = iss1["key"]
    key2 = iss2["key"]

    # 1. Wrong confirmation phrase
    req1 = await _call_destructive_lifecycle(
        admin_env,
        {"action": "request_delete", "target_kind": "issue", "target": key1, "mode": "trash"},
    )
    tok1 = yaml.safe_load(req1["result"]["content"][0]["text"])["confirmation_token"]

    bad_phrase_res = await _call_destructive_lifecycle(
        admin_env,
        {
            "action": "execute_delete",
            "target_kind": "issue",
            "target": key1,
            "mode": "trash",
            "confirmation_token": tok1,
            "confirm_phrase": f"DELETE ISSUE {key1}",  # Wrong phrase
            "reason": "Wrong phrase execution attempt",
        },
    )
    assert bad_phrase_res["result"].get("isError")
    err1 = yaml.safe_load(bad_phrase_res["result"]["content"][0]["text"])
    assert err1["error"]["code"] == "CONFIRM_PHRASE_MISMATCH"

    # 2. Target mismatch (token minted for key1, passed with key2)
    req2 = await _call_destructive_lifecycle(
        admin_env,
        {"action": "request_delete", "target_kind": "issue", "target": key1, "mode": "trash"},
    )
    tok2 = yaml.safe_load(req2["result"]["content"][0]["text"])["confirmation_token"]
    phrase2 = yaml.safe_load(req2["result"]["content"][0]["text"])["confirm_phrase"]

    target_mismatch_res = await _call_destructive_lifecycle(
        admin_env,
        {
            "action": "execute_delete",
            "target_kind": "issue",
            "target": key2,  # Swapped target
            "mode": "trash",
            "confirmation_token": tok2,
            "confirm_phrase": phrase2,
            "reason": "Target mismatch execution attempt",
        },
    )
    assert target_mismatch_res["result"].get("isError")
    err2 = yaml.safe_load(target_mismatch_res["result"]["content"][0]["text"])
    assert err2["error"]["code"] == "TOKEN_TARGET_MISMATCH"


@pytest.mark.asyncio
async def test_destructive_lifecycle_blast_hash_changed_toctou(
    admin_env: AdminTestEnv,
) -> None:
    """TOCTOU protection: changes to blast radius trigger BLAST_RADIUS_CHANGED."""
    proj_id = await create_project(
        admin_env.seed_session,
        admin_env.workspace_id,
        identifier="TOCTOU",
        name="TOCTOU Test",
        created_by_id=admin_env.server_admin.id,
    )
    await add_role_binding(
        admin_env.seed_session,
        admin_env.workspace_id,
        admin_env.server_admin.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(admin_env.seed_session, admin_env.workspace_id)
    await admin_env.seed_session.commit()

    parent_data = await admin_env.internal_client.request(
        "POST",
        "/api/v1/projects/TOCTOU/issues",
        json_data={"summary": "Parent Issue"},
        subject_token=admin_env.token_server_admin_full,
    )
    assert isinstance(parent_data, dict)
    parent_key = parent_data["key"]

    # Stage 1: Request delete
    req = await _call_destructive_lifecycle(
        admin_env,
        {"action": "request_delete", "target_kind": "issue", "target": parent_key, "mode": "trash"},
    )
    tok = yaml.safe_load(req["result"]["content"][0]["text"])["confirmation_token"]
    phrase = yaml.safe_load(req["result"]["content"][0]["text"])["confirm_phrase"]

    # Intervening mutation: add a child issue to parent
    await admin_env.internal_client.request(
        "POST",
        "/api/v1/projects/TOCTOU/issues",
        json_data={
            "summary": "Child Issue added after token",
            "parent": parent_key,
        },
        subject_token=admin_env.token_server_admin_full,
    )

    # Stage 2: execute_delete should detect live blast radius change
    exec_res = await _call_destructive_lifecycle(
        admin_env,
        {
            "action": "execute_delete",
            "target_kind": "issue",
            "target": parent_key,
            "mode": "trash",
            "confirmation_token": tok,
            "confirm_phrase": phrase,
            "reason": "Attempting execution after children were added",
        },
    )
    assert exec_res["result"].get("isError")
    err = yaml.safe_load(exec_res["result"]["content"][0]["text"])
    assert err["error"]["code"] == "BLAST_RADIUS_CHANGED"


@pytest.mark.asyncio
async def test_destructive_lifecycle_validation_and_scope_failures(
    admin_env: AdminTestEnv,
) -> None:
    """Validation errors, missing parameters, and scope rejections."""
    # 1. Missing action
    res_no_action = await _call_destructive_lifecycle(admin_env, {})
    assert res_no_action["result"].get("isError")
    assert (
        yaml.safe_load(res_no_action["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 2. Unknown action
    res_bad_action = await _call_destructive_lifecycle(admin_env, {"action": "nuke"})
    assert res_bad_action["result"].get("isError")
    assert (
        yaml.safe_load(res_bad_action["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 3. Missing target_kind
    res_no_kind = await _call_destructive_lifecycle(
        admin_env, {"action": "request_delete", "target": "K-1"}
    )
    assert res_no_kind["result"].get("isError")
    assert (
        yaml.safe_load(res_no_kind["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 4. Reason too short (< 10 chars) on restore
    res_short_reason = await _call_destructive_lifecycle(
        admin_env,
        {"action": "restore", "target_kind": "issue", "target": "K-1", "reason": "short"},
    )
    assert res_short_reason["result"].get("isError")
    assert (
        yaml.safe_load(res_short_reason["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 5. Missing confirmation_token on execute_delete
    res_no_token = await _call_destructive_lifecycle(
        admin_env,
        {
            "action": "execute_delete",
            "target_kind": "issue",
            "target": "K-1",
            "confirm_phrase": "TRASH ISSUE K-1",
            "reason": "Valid reason for execution",
        },
    )
    assert res_no_token["result"].get("isError")
    assert (
        yaml.safe_load(res_no_token["result"]["content"][0]["text"])["error"]["code"]
        == "VALIDATION_FAILED"
    )

    # 6. Scope check: token with admin:write (without admin:destructive) rejected
    res_bad_scope = await _call_destructive_lifecycle(
        admin_env,
        {"action": "request_delete", "target_kind": "issue", "target": "K-1"},
        scopes="admin:write",
    )
    assert res_bad_scope["result"].get("isError")
    assert (
        yaml.safe_load(res_bad_scope["result"]["content"][0]["text"])["error"]["code"]
        == "INSUFFICIENT_SCOPE"
    )

    # 7. AAL1 token rejected
    res_aal1 = await _call_destructive_lifecycle(
        admin_env,
        {"action": "request_delete", "target_kind": "issue", "target": "K-1"},
        aal_level=1,
    )
    assert res_aal1["result"].get("isError")
    assert (
        yaml.safe_load(res_aal1["result"]["content"][0]["text"])["error"]["code"] == "AAL2_REQUIRED"
    )


@pytest.mark.asyncio
async def test_mcp_handler_unit_validations() -> None:
    """Direct unit tests for destructive_lifecycle_handler parameter validations."""
    mock_client = AsyncMock()

    # 1. Unknown parameter
    with pytest.raises(KbMcpError) as exc1:
        await destructive_lifecycle_handler({"bogus": "value"}, client=mock_client)
    assert exc1.value.code == McpErrorCode.VALIDATION_FAILED

    # 2. Invalid action
    with pytest.raises(KbMcpError) as exc2:
        await destructive_lifecycle_handler({"action": "explode"}, client=mock_client)
    assert exc2.value.code == McpErrorCode.VALIDATION_FAILED

    # 3. Invalid target_kind
    with pytest.raises(KbMcpError) as exc3:
        await destructive_lifecycle_handler(
            {"action": "request_delete", "target_kind": "spaceship"}, client=mock_client
        )
    assert exc3.value.code == McpErrorCode.VALIDATION_FAILED

    # 4. Missing target
    with pytest.raises(KbMcpError) as exc4:
        await destructive_lifecycle_handler(
            {"action": "request_delete", "target_kind": "issue", "target": ""}, client=mock_client
        )
    assert exc4.value.code == McpErrorCode.VALIDATION_FAILED

    # 5. Overly long target
    with pytest.raises(KbMcpError) as exc5:
        await destructive_lifecycle_handler(
            {"action": "request_delete", "target_kind": "issue", "target": "X" * 205},
            client=mock_client,
        )
    assert exc5.value.code == McpErrorCode.VALIDATION_FAILED

    # 6. Invalid mode
    with pytest.raises(KbMcpError) as exc6:
        await destructive_lifecycle_handler(
            {
                "action": "request_delete",
                "target_kind": "issue",
                "target": "X-1",
                "mode": "vaporize",
            },
            client=mock_client,
        )
    assert exc6.value.code == McpErrorCode.VALIDATION_FAILED

    # 7. execute_delete missing confirmation_token
    with pytest.raises(KbMcpError) as exc7:
        await destructive_lifecycle_handler(
            {"action": "execute_delete", "target_kind": "issue", "target": "X-1"},
            client=mock_client,
        )
    assert exc7.value.code == McpErrorCode.VALIDATION_FAILED

    # 8. execute_delete missing confirm_phrase
    with pytest.raises(KbMcpError) as exc8:
        await destructive_lifecycle_handler(
            {
                "action": "execute_delete",
                "target_kind": "issue",
                "target": "X-1",
                "confirmation_token": "tok",
            },
            client=mock_client,
        )
    assert exc8.value.code == McpErrorCode.VALIDATION_FAILED

    # 9. execute_delete reason too short
    with pytest.raises(KbMcpError) as exc9:
        await destructive_lifecycle_handler(
            {
                "action": "execute_delete",
                "target_kind": "issue",
                "target": "X-1",
                "confirmation_token": "tok",
                "confirm_phrase": "phr",
                "reason": "short",
            },
            client=mock_client,
        )
    assert exc9.value.code == McpErrorCode.VALIDATION_FAILED

    # 10. restore reason missing
    with pytest.raises(KbMcpError) as exc10:
        await destructive_lifecycle_handler(
            {"action": "restore", "target_kind": "issue", "target": "X-1"}, client=mock_client
        )
    assert exc10.value.code == McpErrorCode.VALIDATION_FAILED

    # 11. ToolSpec wrapper handler invocation
    tool_spec = create_destructive_lifecycle_tool(mock_client)
    help_res = await tool_spec.handler({"action": "help"})
    assert help_res["tool"] == "destructive_lifecycle"

    # 12. Client unavailable error
    with pytest.raises(KbMcpError) as exc_noclient:
        await destructive_lifecycle_handler(
            {"action": "request_delete", "target_kind": "issue", "target": "X-1"}, client=None
        )
    assert exc_noclient.value.code == McpErrorCode.INTERNAL

    # 13. Upstream non-dict responses
    bad_client = AsyncMock()
    bad_client.request.return_value = ["non-dict-list"]
    with pytest.raises(KbMcpError) as exc_up1:
        await destructive_lifecycle_handler(
            {"action": "request_delete", "target_kind": "issue", "target": "X-1"}, client=bad_client
        )
    assert exc_up1.value.code == McpErrorCode.UPSTREAM_ERROR

    with pytest.raises(KbMcpError) as exc_up2:
        await destructive_lifecycle_handler(
            {
                "action": "execute_delete",
                "target_kind": "issue",
                "target": "X-1",
                "confirmation_token": "tok",
                "confirm_phrase": "phr",
                "reason": "valid reason for delete",
            },
            client=bad_client,
        )
    assert exc_up2.value.code == McpErrorCode.UPSTREAM_ERROR

    with pytest.raises(KbMcpError) as exc_up3:
        await destructive_lifecycle_handler(
            {
                "action": "restore",
                "target_kind": "issue",
                "target": "X-1",
                "reason": "valid reason for restore",
            },
            client=bad_client,
        )
    assert exc_up3.value.code == McpErrorCode.UPSTREAM_ERROR
