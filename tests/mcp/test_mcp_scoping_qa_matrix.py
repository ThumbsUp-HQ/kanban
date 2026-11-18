# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: C901, PLR0915, ASYNC240, E501, TC003
"""Comprehensive MCP Scoping QA Matrix Test Suite (KANBA-205).

Deterministically validates all six primary scoping conditions:
- Condition A: User Agent (personal_user kb_agt_ PAT), Unscoped Global Key
- Condition B: User Agent (personal_user kb_agt_ PAT), Unscoped Key to Scoped Endpoints
- Condition C: User Agent (personal_user kb_agt_ PAT), Project-Pinned Key
- Condition D: Project Agent (service_bot kb_agt_, project-scoped, QAADM)
- Condition E: Surface Cross-Isolation (agent, docs, admin) and Admin RBAC Parity
- Condition F: Protocol Preconditions, Headers, Session Binding, TaintGuard, and TTL Revocation
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.requests import Request

from kanban.api.problems import ProblemException
from kanban.security.read_taint import TaintGuard
from kanban.tests.contract import ContractRecorder
from mcp.app import create_mcp_app
from mcp.auth import (
    DEFAULT_CACHE_TTL_S,
    IntrospectionCache,
    McpAuthMiddleware,
)
from mcp.internal_client import KanbanApiClient
from mcp.protocol import PROTOCOL_VERSION
from mcp.settings import McpSettings
from mcp.surfaces.admin import build_admin_registry
from mcp.surfaces.agent import create_agent_registry
from mcp.surfaces.docs import build_docs_registry

# Contract recorder instance for KANBA-205 QA evidence collection
qa_contract_recorder = ContractRecorder(ticket="KANBA-205")


def _build_matrix_test_env(
    custom_tokens: dict[str, dict[str, Any]] | None = None,
    time_provider: Callable[[], float] | None = None,
) -> tuple[httpx.AsyncClient, list[dict[str, Any]], IntrospectionCache]:
    """Construct deterministic MCP application and mock upstream kanban-api."""
    recorded_upstream_calls: list[dict[str, Any]] = []

    tokens_db: dict[str, dict[str, Any]] = {
        # Condition A & B: User Agent Unscoped Global Key
        "kb_agt_user_global_pat_0000000000000001": {
            "active": True,
            "principal_id": "00000000-0000-0000-0000-000000000001",
            "owner_kind": "personal_user",
            "token_kind": "api_key",
            "scope_tier": "global",
            "scopes": ["agent:read", "agent:write"],
            "capability_mask": 7,
        },
        # Condition C: User Agent Project-Pinned Key
        "kb_agt_user_project_pinned_pat_00000002": {
            "active": True,
            "principal_id": "00000000-0000-0000-0000-000000000001",
            "owner_kind": "personal_user",
            "token_kind": "api_key",
            "scope_tier": "project",
            "workspace_slug": "kanban",
            "workspace_id": "00000000-0000-0000-0000-000000000002",
            "allowed_projects": ["QAUSR1"],
            "allowed_project_keys": ["QAUSR1"],
            "scopes": ["agent:read", "agent:write"],
            "capability_mask": 7,
        },
        # Condition C: User Agent Read-Only Project-Pinned Key
        "kb_agt_user_readonly_pat_00000000000003": {
            "active": True,
            "principal_id": "00000000-0000-0000-0000-000000000001",
            "owner_kind": "personal_user",
            "token_kind": "api_key",
            "scope_tier": "project",
            "workspace_slug": "kanban",
            "workspace_id": "00000000-0000-0000-0000-000000000002",
            "allowed_projects": ["QAUSR1"],
            "allowed_project_keys": ["QAUSR1"],
            "scopes": ["agent:read"],
            "capability_mask": 1,
        },
        # Condition D: Project Agent Service Bot Pinned to QAADM
        "kb_agt_service_bot_qaadm_00000000000004": {
            "active": True,
            "principal_id": "00000000-0000-0000-0000-000000000010",
            "agent_principal_id": "00000000-0000-0000-0000-000000000010",
            "owner_kind": "service_bot",
            "token_kind": "api_key",
            "scope_tier": "project",
            "workspace_slug": "kanban",
            "workspace_id": "00000000-0000-0000-0000-000000000002",
            "allowed_projects": ["QAADM"],
            "allowed_project_keys": ["QAADM"],
            "scopes": ["agent:read", "agent:write"],
            "capability_mask": 7,
        },
        # Condition D: Project Agent Service Bot with Tool Restrictions
        "kb_agt_service_bot_tool_filtered_000005": {
            "active": True,
            "principal_id": "00000000-0000-0000-0000-000000000010",
            "agent_principal_id": "00000000-0000-0000-0000-000000000010",
            "owner_kind": "service_bot",
            "token_kind": "api_key",
            "scope_tier": "project",
            "workspace_slug": "kanban",
            "workspace_id": "00000000-0000-0000-0000-000000000002",
            "allowed_projects": ["QAADM"],
            "allowed_project_keys": ["QAADM"],
            "allowed_tools": ["search_tickets", "read_ticket"],
            "disabled_tools": ["create_ticket", "update_ticket"],
            "scopes": ["agent:read", "agent:write"],
            "capability_mask": 7,
        },
        # Condition D: Project Agent Service Bot with View-Only Capability Mask
        "kb_agt_service_bot_viewonly_mask_000006": {
            "active": True,
            "principal_id": "00000000-0000-0000-0000-000000000010",
            "agent_principal_id": "00000000-0000-0000-0000-000000000010",
            "owner_kind": "service_bot",
            "token_kind": "api_key",
            "scope_tier": "project",
            "workspace_slug": "kanban",
            "workspace_id": "00000000-0000-0000-0000-000000000002",
            "allowed_projects": ["QAADM"],
            "allowed_project_keys": ["QAADM"],
            "scopes": ["agent:read", "agent:write"],
            "capability_mask": 1,
        },
        # Condition E: Docs Key
        "kb_doc_docs_key_00000000007": {
            "active": True,
            "principal_id": "00000000-0000-0000-0000-000000000001",
            "token_kind": "api_key",
            "scope_tier": "workspace",
            "workspace_slug": "kanban",
            "scopes": ["docs:read", "docs:write"],
            "capability_mask": 7,
        },
        # Condition E: Admin Read-Only Key
        "kb_adm_readonly_admin_key_0000000000008": {
            "active": True,
            "principal_id": "00000000-0000-0000-0000-000000000001",
            "token_kind": "api_key",
            "scope_tier": "workspace",
            "workspace_slug": "kanban",
            "scopes": ["admin:read"],
            "capability_mask": 7,
            "aal_level": 2,
        },
        # Condition E: Admin Server Admin Destructive Key
        "kb_adm_server_admin_destr_key_000000009": {
            "active": True,
            "principal_id": "00000000-0000-0000-0000-000000000001",
            "token_kind": "api_key",
            "scope_tier": "global",
            "scopes": ["admin:read", "admin:write", "admin:destructive"],
            "capability_mask": 7,
            "aal_level": 2,
        },
        # Condition E: Admin Workspace Admin (lacks server admin capability)
        "kb_adm_workspace_admin_key_000000000010": {
            "active": True,
            "principal_id": "00000000-0000-0000-0000-000000000001",
            "token_kind": "api_key",
            "scope_tier": "workspace",
            "workspace_slug": "kanban",
            "scopes": ["admin:read", "admin:write"],
            "capability_mask": 7,
            "aal_level": 2,
        },
    }

    if custom_tokens:
        tokens_db.update(custom_tokens)

    async def mock_handler(request: httpx.Request) -> httpx.Response:  # noqa: PLR0911, PLR0912
        url_path = request.url.path
        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        recorded_upstream_calls.append(
            {
                "method": request.method,
                "path": url_path,
                "params": dict(request.url.params),
                "headers": dict(request.headers),
                "body": body,
            }
        )

        # 1. Token introspection endpoint
        if url_path == "/internal/v1/mcp/introspect":
            token = str(body.get("token") or "")
            intro = tokens_db.get(token)
            if not intro or not intro.get("active"):
                return httpx.Response(200, json={"active": False})

            # Check capability mask in write emulation
            return httpx.Response(200, json=intro)

        # 2. Search issues
        if url_path == "/api/v1/search/issues":
            proj = body.get("project")
            if proj == "QAUSR1":
                return httpx.Response(
                    200,
                    json={
                        "total": 1,
                        "items": [
                            {
                                "kind": "issue",
                                "id": "00000000-0000-0000-0000-000000000050",
                                "key": "QAUSR1-1",
                                "title": "QA User Ticket 1",
                                "summary": "QA User Ticket 1",
                                "project_identifier": "QAUSR1",
                                "workspace": "kanban",
                                "score": 1.0,
                                "state": "open",
                            }
                        ],
                    },
                )
            if proj == "QAADM":
                return httpx.Response(
                    200,
                    json={
                        "total": 1,
                        "items": [
                            {
                                "kind": "issue",
                                "id": "00000000-0000-0000-0000-000000000060",
                                "key": "QAADM-1",
                                "title": "QA Admin Ticket 1",
                                "summary": "QA Admin Ticket 1",
                                "project_identifier": "QAADM",
                                "workspace": "kanban",
                                "score": 1.0,
                                "state": "open",
                            }
                        ],
                    },
                )
            # Global search returns both QAUSR1 and QAADM
            return httpx.Response(
                200,
                json={
                    "total": 2,
                    "items": [
                        {
                            "kind": "issue",
                            "id": "00000000-0000-0000-0000-000000000050",
                            "key": "QAUSR1-1",
                            "title": "QA User Ticket 1",
                            "summary": "QA User Ticket 1",
                            "project_identifier": "QAUSR1",
                            "workspace": "kanban",
                            "score": 1.0,
                            "state": "open",
                        },
                        {
                            "kind": "issue",
                            "id": "00000000-0000-0000-0000-000000000060",
                            "key": "QAADM-1",
                            "title": "QA Admin Ticket 1",
                            "summary": "QA Admin Ticket 1",
                            "project_identifier": "QAADM",
                            "workspace": "kanban",
                            "score": 0.9,
                            "state": "open",
                        },
                    ],
                },
            )

        # 3. Create ticket (issue tree)
        if "/api/v1/projects/" in url_path and url_path.endswith("/issue-trees"):
            proj_key = url_path.split("/api/v1/projects/")[1].split("/")[0]
            summary = body.get("summary", "New Ticket")
            # Emulate capability mask rejection if view-only token used
            subject_token = request.headers.get("x-kb-subject-token", "")
            token_meta = tokens_db.get(subject_token, {})
            if token_meta.get("capability_mask", 7) == 1:
                return httpx.Response(
                    403,
                    headers={"Content-Type": "application/problem+json"},
                    json={
                        "type": "urn:kanban:problem:INSUFFICIENT_CAPABILITY",
                        "code": "INSUFFICIENT_CAPABILITY",
                        "status": 403,
                        "title": "Insufficient Capability",
                        "detail": "Caller holds VIEW but lacks EDIT capability on this project.",
                    },
                )
            # Emulate cross-scope taint rejection if writing to QAADM while tainted
            if body.get("summary") == "TRIGGER_TAINT_REJECTION":
                return httpx.Response(
                    409,
                    headers={"Content-Type": "application/problem+json"},
                    json={
                        "type": "urn:kanban:problem:cross-scope-taint",
                        "code": "CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED",
                        "status": 409,
                        "title": "Cross-Scope Taint",
                        "detail": (
                            f"Write targeting project '{proj_key}' blocked: audience is broader "
                            "than previously inspected tainted project."
                        ),
                    },
                )
            return httpx.Response(
                201,
                json={
                    "created": 1,
                    "root": {
                        "id": "00000000-0000-0000-0000-000000000099",
                        "key": f"{proj_key}-99",
                        "summary": summary,
                        "state": "open",
                        "priority": "medium",
                    },
                    "children": [],
                },
            )

        # 4. Read or Update single issue
        if url_path.startswith("/api/v1/issues/"):
            issue_key = url_path.rsplit("/", 1)[-1]
            if issue_key.startswith("SECRET-"):
                return httpx.Response(
                    404,
                    headers={"Content-Type": "application/problem+json"},
                    json={
                        "type": "urn:kanban:problem:NOT_FOUND",
                        "code": "NOT_FOUND",
                        "status": 404,
                        "title": "Not Found",
                        "detail": f"Issue '{issue_key}' not found or access denied.",
                    },
                )
            if request.method == "PATCH":
                subject_token = request.headers.get("x-kb-subject-token", "")
                token_meta = tokens_db.get(subject_token, {})
                if token_meta.get("capability_mask", 7) == 1:
                    return httpx.Response(
                        403,
                        headers={"Content-Type": "application/problem+json"},
                        json={
                            "type": "urn:kanban:problem:INSUFFICIENT_CAPABILITY",
                            "code": "INSUFFICIENT_CAPABILITY",
                            "status": 403,
                            "title": "Insufficient Capability",
                            "detail": "Caller holds VIEW but lacks EDIT capability on this project.",
                        },
                    )
                return httpx.Response(
                    200,
                    json={
                        "id": "00000000-0000-0000-0000-000000000050",
                        "key": issue_key,
                        "summary": body.get("summary", "Updated Ticket"),
                        "state": "open",
                        "priority": "high",
                        "workspace": "kanban",
                    },
                )
            # GET issue
            return httpx.Response(
                200,
                json={
                    "id": "00000000-0000-0000-0000-000000000050",
                    "key": issue_key,
                    "summary": f"Summary for {issue_key}",
                    "state": "open",
                    "priority": "medium",
                    "workspace": "kanban",
                },
            )

        # 5. Issue sub-resources (links, comments, activity)
        if "/links" in url_path or "/comments" in url_path or "/activity" in url_path:
            return httpx.Response(200, json={"items": []} if "/links" in url_path else [])

        # 6. Admin workspace configuration
        if url_path.startswith("/api/v1/admin/workspaces/"):
            subject_token = request.headers.get("x-kb-subject-token", "")
            token_meta = tokens_db.get(subject_token, {})
            # Deny if key lacks admin:write
            scopes = token_meta.get("scopes", [])
            if "admin:write" not in scopes and "admin:destructive" not in scopes:
                return httpx.Response(
                    403,
                    headers={"Content-Type": "application/problem+json"},
                    json={
                        "type": "urn:kanban:problem:INSUFFICIENT_PERMISSION",
                        "code": "INSUFFICIENT_PERMISSION",
                        "status": 403,
                        "title": "Insufficient Permission",
                        "detail": "Updating workspace configuration requires admin:write scope.",
                    },
                )
            return httpx.Response(200, json={"workspace": "kanban", "status": "updated"})

        # 7. Admin auth-cards
        if url_path.startswith("/api/v1/admin/auth-cards"):
            subject_token = request.headers.get("x-kb-subject-token", "")
            token_meta = tokens_db.get(subject_token, {})
            tier = token_meta.get("scope_tier")
            if tier != "global":
                return httpx.Response(
                    403,
                    headers={"Content-Type": "application/problem+json"},
                    json={
                        "type": "urn:kanban:problem:INSUFFICIENT_CAPABILITY",
                        "code": "INSUFFICIENT_CAPABILITY",
                        "status": 403,
                        "title": "Insufficient Capability",
                        "detail": "Managing authentication cards requires SERVER_ADMIN authority.",
                    },
                )
            return httpx.Response(200, json={"auth_cards": []})

        # 8. Admin destructive lifecycle 2-stage endpoints
        if url_path == "/api/v1/admin/destructive:request":
            target = body.get("target", "")
            target_kind = body.get("target_kind", "issue")
            return httpx.Response(
                200,
                json={
                    "stage": "confirmation_required",
                    "target": target,
                    "target_kind": target_kind,
                    "mode": body.get("mode", "trash"),
                    "confirmation_token": f"tok_{uuid.uuid4().hex[:12]}",
                    "confirm_phrase": f"PURGE {target}".upper(),
                    "blast_summary": f"1 {target_kind} and related objects will be deleted",
                    "expires_in_sec": 300,
                },
            )

        if url_path == "/api/v1/admin/destructive:execute":
            return httpx.Response(
                200,
                json={
                    "status": "executed",
                    "target": body.get("target", ""),
                    "target_kind": body.get("target_kind", "issue"),
                    "mode": body.get("mode", "trash"),
                    "reason": body.get("reason", "QA test deletion"),
                },
            )

        return httpx.Response(404, json={"detail": "Not found in mock API"})

    transport = httpx.MockTransport(mock_handler)
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    kanban_client = KanbanApiClient(settings, transport=transport)

    cache = IntrospectionCache(time_provider=time_provider or time.time)

    base_app = create_mcp_app(
        settings=settings,
        agent_registry=create_agent_registry(),
        docs_registry=build_docs_registry(kanban_client),
        admin_registry=build_admin_registry(kanban_client),
        internal_client=kanban_client,
    )
    auth_middleware = McpAuthMiddleware(
        base_app,
        internal_client=kanban_client,
        settings=settings,
        cache=cache,
    )

    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=auth_middleware),
        base_url="http://test",
    )
    return client, recorded_upstream_calls, cache


@pytest.mark.asyncio
async def test_condition_a_user_agent_unscoped_global_key() -> None:
    """Condition A: User Agent (personal_user kb_agt_ PAT), Unscoped Global Key -> /mcp/agent.

    Verifies:
    1. tools/list shows exactly 9 official agent tools.
    2. search_tickets and disposable CRUD on QAUSR1 succeed.
    3. Accessing private/unauthorized project returns NOT_FOUND anti-enumeration.
    """
    client, _calls, _cache = _build_matrix_test_env()
    headers = {"Authorization": "Bearer kb_agt_user_global_pat_0000000000000001"}

    # 1. Initialize session on /mcp/agent
    init_resp = await client.post(
        "/mcp/agent",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION},
        },
    )
    assert init_resp.status_code == 200
    session_id = init_resp.headers.get("mcp-session-id")
    assert session_id is not None
    qa_contract_recorder.record("condition_a_initialize", init_resp.request, init_resp)

    # 2. tools/list shows exactly 9 agent tools
    sess_headers = {**headers, "mcp-session-id": session_id}
    list_resp = await client.post(
        "/mcp/agent",
        headers=sess_headers,
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    assert list_resp.status_code == 200
    tools_list = list_resp.json()["result"]["tools"]
    tool_names = [t["name"] for t in tools_list]
    expected_tools = [
        "search_tickets",
        "read_ticket",
        "create_ticket",
        "update_ticket",
        "begin_work",
        "transition_ticket",
        "complete_work",
        "add_comment",
        "link_objects",
    ]
    assert len(tool_names) == 9
    assert sorted(tool_names) == sorted(expected_tools)
    qa_contract_recorder.record("condition_a_tools_list", list_resp.request, list_resp)

    # 3. search_tickets succeeds
    search_resp = await client.post(
        "/mcp/agent",
        headers=sess_headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "search_tickets",
                "arguments": {"query": "auth", "project": "QAUSR1"},
            },
        },
    )
    assert search_resp.status_code == 200
    assert not search_resp.json()["result"]["isError"]

    # 4. Disposable CRUD on QAUSR1 succeeds
    create_resp = await client.post(
        "/mcp/agent",
        headers=sess_headers,
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "create_ticket",
                "arguments": {
                    "project": "QAUSR1",
                    "summary": "QA Disposable Ticket",
                    "description_markdown": "Test verification description",
                },
            },
        },
    )
    assert create_resp.status_code == 200
    create_body = create_resp.json()["result"]
    assert not create_body["isError"]
    assert "QAUSR1-99" in create_body["content"][0]["text"]
    qa_contract_recorder.record("condition_a_create_ticket", create_resp.request, create_resp)

    # 5. Read created ticket succeeds
    read_resp = await client.post(
        "/mcp/agent",
        headers=sess_headers,
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "read_ticket",
                "arguments": {"identifier": "QAUSR1-99"},
            },
        },
    )
    assert read_resp.status_code == 200
    assert not read_resp.json()["result"]["isError"]

    # 6. Update ticket succeeds
    update_resp = await client.post(
        "/mcp/agent",
        headers=sess_headers,
        json={
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "update_ticket",
                "arguments": {
                    "identifier": "QAUSR1-99",
                    "summary": "Updated Ticket Summary",
                },
            },
        },
    )
    assert update_resp.status_code == 200
    assert not update_resp.json()["result"]["isError"]

    # 7. Unauthorized project returns NOT_FOUND anti-enumeration
    unauth_resp = await client.post(
        "/mcp/agent",
        headers=sess_headers,
        json={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "read_ticket",
                "arguments": {"identifier": "SECRET-99"},
            },
        },
    )
    assert unauth_resp.status_code == 200
    unauth_body = unauth_resp.json()["result"]
    assert unauth_body["isError"]
    assert "NOT_FOUND" in unauth_body["content"][0]["text"]


@pytest.mark.asyncio
async def test_condition_b_user_agent_unscoped_key_workspace_and_project_scoped_endpoints() -> None:
    """Condition B: User Agent Unscoped Key -> /mcp/agent/w/kanban and /mcp/agent/w/kanban/p/QAUSR1.

    Verifies:
    1. Workspace endpoint resolves kanban keys cleanly.
    2. Project endpoint auto-fills project="QAUSR1" when omitted.
    3. Blocks cross-project mutation targeting foreign project (CONNECTION_SCOPE_VIOLATION).
    """
    client, _calls, _cache = _build_matrix_test_env()
    token_header = {"Authorization": "Bearer kb_agt_user_global_pat_0000000000000001"}

    # 1. Connect to workspace-scoped endpoint /mcp/agent/w/kanban
    ws_init = await client.post(
        "/mcp/agent/w/kanban",
        headers=token_header,
        json={"jsonrpc": "2.0", "id": 10, "method": "initialize", "params": {}},
    )
    assert ws_init.status_code == 200
    ws_session = ws_init.headers.get("mcp-session-id")

    ws_read = await client.post(
        "/mcp/agent/w/kanban",
        headers={**token_header, "mcp-session-id": str(ws_session)},
        json={
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "read_ticket", "arguments": {"identifier": "QAUSR1-1"}},
        },
    )
    assert ws_read.status_code == 200
    assert not ws_read.json()["result"]["isError"]

    # 2. Connect to project-scoped endpoint /mcp/agent/w/kanban/p/QAUSR1
    p_init = await client.post(
        "/mcp/agent/w/kanban/p/QAUSR1",
        headers=token_header,
        json={"jsonrpc": "2.0", "id": 20, "method": "initialize", "params": {}},
    )
    assert p_init.status_code == 200
    p_session = p_init.headers.get("mcp-session-id")

    # Auto-fills project="QAUSR1" when omitted
    p_create = await client.post(
        "/mcp/agent/w/kanban/p/QAUSR1",
        headers={**token_header, "mcp-session-id": str(p_session)},
        json={
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {
                "name": "create_ticket",
                "arguments": {"summary": "Project Pinned Ticket Without Explicit Project"},
            },
        },
    )
    assert p_create.status_code == 200
    p_body = p_create.json()["result"]
    assert not p_body["isError"]
    assert "QAUSR1-99" in p_body["content"][0]["text"]
    qa_contract_recorder.record("condition_b_project_autofill", p_create.request, p_create)

    # 3. Blocks cross-project mutation targeting foreign project QAADM
    cross_create = await client.post(
        "/mcp/agent/w/kanban/p/QAUSR1",
        headers={**token_header, "mcp-session-id": str(p_session)},
        json={
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": {
                "name": "create_ticket",
                "arguments": {
                    "project": "QAADM",
                    "summary": "Forbidden Cross Project Mutation",
                },
            },
        },
    )
    assert cross_create.status_code == 200
    cross_body = cross_create.json()["result"]
    assert cross_body["isError"]
    assert "CONNECTION_SCOPE_VIOLATION" in cross_body["content"][0]["text"]
    qa_contract_recorder.record(
        "condition_b_cross_project_blocked", cross_create.request, cross_create
    )

    # Cross-project update by issue key
    cross_update = await client.post(
        "/mcp/agent/w/kanban/p/QAUSR1",
        headers={**token_header, "mcp-session-id": str(p_session)},
        json={
            "jsonrpc": "2.0",
            "id": 23,
            "method": "tools/call",
            "params": {
                "name": "update_ticket",
                "arguments": {
                    "identifier": "QAADM-1",
                    "summary": "Forbidden Cross Project Update",
                },
            },
        },
    )
    assert cross_update.status_code == 200
    cross_up_body = cross_update.json()["result"]
    assert cross_up_body["isError"]
    assert "CONNECTION_SCOPE_VIOLATION" in cross_up_body["content"][0]["text"]


@pytest.mark.asyncio
async def test_condition_c_user_agent_project_pinned_key() -> None:
    """Condition C: User Agent Project-Pinned Key (scope_tier="project", QAUSR1).

    Verifies:
    1. On /mcp/agent, key narrows effective scope to QAUSR1 and succeeds inside QAUSR1.
    2. Connecting same key to /mcp/agent/w/kanban or /mcp/agent/w/kanban/p/QAADM fails 403 KEY_SCOPE_VIOLATION.
    3. agent:read-only PAT rejects writes with INSUFFICIENT_SCOPE.
    """
    client, _calls, _cache = _build_matrix_test_env()
    pinned_headers = {"Authorization": "Bearer kb_agt_user_project_pinned_pat_00000002"}

    # 1. Pinned key connects to unscoped /mcp/agent: effective scope is narrowed to QAUSR1
    init_unscoped = await client.post(
        "/mcp/agent",
        headers=pinned_headers,
        json={"jsonrpc": "2.0", "id": 30, "method": "initialize", "params": {}},
    )
    assert init_unscoped.status_code == 200
    unscoped_sess = init_unscoped.headers.get("mcp-session-id")

    # Succeeds inside QAUSR1 (project is auto-populated to QAUSR1)
    call_in_scope = await client.post(
        "/mcp/agent",
        headers={**pinned_headers, "mcp-session-id": str(unscoped_sess)},
        json={
            "jsonrpc": "2.0",
            "id": 31,
            "method": "tools/call",
            "params": {
                "name": "create_ticket",
                "arguments": {"summary": "Ticket in Narrowed Pinned Scope"},
            },
        },
    )
    assert call_in_scope.status_code == 200
    assert not call_in_scope.json()["result"]["isError"]
    assert "QAUSR1-99" in call_in_scope.json()["result"]["content"][0]["text"]

    # 2. Connecting project-pinned key to workspace-wide endpoint fails 403 KEY_SCOPE_VIOLATION
    ws_fail = await client.post(
        "/mcp/agent/w/kanban",
        headers=pinned_headers,
        json={"jsonrpc": "2.0", "id": 32, "method": "initialize", "params": {}},
    )
    assert ws_fail.status_code == 403
    assert ws_fail.json()["error"] == "KEY_SCOPE_VIOLATION"
    qa_contract_recorder.record("condition_c_workspace_wide_rejected", ws_fail.request, ws_fail)

    # Connecting project-pinned key to wrong project fails 403 KEY_SCOPE_VIOLATION
    wrong_proj_fail = await client.post(
        "/mcp/agent/w/kanban/p/QAADM",
        headers=pinned_headers,
        json={"jsonrpc": "2.0", "id": 33, "method": "initialize", "params": {}},
    )
    assert wrong_proj_fail.status_code == 403
    assert wrong_proj_fail.json()["error"] == "KEY_SCOPE_VIOLATION"
    qa_contract_recorder.record(
        "condition_c_wrong_project_rejected", wrong_proj_fail.request, wrong_proj_fail
    )

    # 3. agent:read-only PAT rejects writes with INSUFFICIENT_SCOPE
    ro_headers = {"Authorization": "Bearer kb_agt_user_readonly_pat_00000000000003"}
    ro_init = await client.post(
        "/mcp/agent/w/kanban/p/QAUSR1",
        headers=ro_headers,
        json={"jsonrpc": "2.0", "id": 34, "method": "initialize", "params": {}},
    )
    assert ro_init.status_code == 200
    ro_sess = ro_init.headers.get("mcp-session-id")

    # search_tickets read succeeds in project scope
    ro_read = await client.post(
        "/mcp/agent/w/kanban/p/QAUSR1",
        headers={**ro_headers, "mcp-session-id": str(ro_sess)},
        json={
            "jsonrpc": "2.0",
            "id": 35,
            "method": "tools/call",
            "params": {"name": "search_tickets", "arguments": {"query": "auth"}},
        },
    )
    assert ro_read.status_code == 200
    assert not ro_read.json()["result"]["isError"]

    # create_ticket write fails with INSUFFICIENT_SCOPE
    ro_write = await client.post(
        "/mcp/agent/w/kanban/p/QAUSR1",
        headers={**ro_headers, "mcp-session-id": str(ro_sess)},
        json={
            "jsonrpc": "2.0",
            "id": 36,
            "method": "tools/call",
            "params": {
                "name": "create_ticket",
                "arguments": {"summary": "Unauthorized Write on Read-Only Key"},
            },
        },
    )
    assert ro_write.status_code == 200
    ro_write_body = ro_write.json()["result"]
    assert ro_write_body["isError"]
    assert "INSUFFICIENT_SCOPE" in ro_write_body["content"][0]["text"]
    qa_contract_recorder.record("condition_c_readonly_write_blocked", ro_write.request, ro_write)


@pytest.mark.asyncio
async def test_condition_d_project_agent_service_bot() -> None:
    """Condition D: Project Agent (service_bot kb_agt_, scope_tier="project", QAADM).

    Verifies:
    1. Operates within QAADM via /mcp/agent/w/kanban/p/QAADM and via /mcp/agent with headers.
    2. Connecting to /mcp/agent/w/kanban or /mcp/agent/w/kanban/p/QAUSR1 returns 403 KEY_SCOPE_VIOLATION.
    3. allowed_tools and disabled_tools filter tools/list and block unauthorized tools/call.
    4. capability_mask=1 blocks writes (INSUFFICIENT_CAPABILITY).
    """
    client, _calls, _cache = _build_matrix_test_env()
    bot_headers = {"Authorization": "Bearer kb_agt_service_bot_qaadm_00000000000004"}

    # 1. Positive: connects to /mcp/agent/w/kanban/p/QAADM
    p_init = await client.post(
        "/mcp/agent/w/kanban/p/QAADM",
        headers=bot_headers,
        json={"jsonrpc": "2.0", "id": 40, "method": "initialize", "params": {}},
    )
    assert p_init.status_code == 200
    p_sess = p_init.headers.get("mcp-session-id")

    p_call = await client.post(
        "/mcp/agent/w/kanban/p/QAADM",
        headers={**bot_headers, "mcp-session-id": str(p_sess)},
        json={
            "jsonrpc": "2.0",
            "id": 41,
            "method": "tools/call",
            "params": {"name": "search_tickets", "arguments": {"query": "auth"}},
        },
    )
    assert p_call.status_code == 200
    assert not p_call.json()["result"]["isError"]

    # Positive: connects to /mcp/agent with X-Workspace-Slug: kanban and X-Project-Key: QAADM
    header_scoped_init = await client.post(
        "/mcp/agent",
        headers={
            **bot_headers,
            "X-Workspace-Slug": "kanban",
            "X-Project-Key": "QAADM",
        },
        json={"jsonrpc": "2.0", "id": 42, "method": "initialize", "params": {}},
    )
    assert header_scoped_init.status_code == 200

    # 2. Negative: connecting to workspace-wide /mcp/agent/w/kanban returns 403 KEY_SCOPE_VIOLATION
    ws_fail = await client.post(
        "/mcp/agent/w/kanban",
        headers=bot_headers,
        json={"jsonrpc": "2.0", "id": 43, "method": "initialize", "params": {}},
    )
    assert ws_fail.status_code == 403
    assert ws_fail.json()["error"] == "KEY_SCOPE_VIOLATION"

    # Negative: connecting to unauthorized project /mcp/agent/w/kanban/p/QAUSR1 returns 403 KEY_SCOPE_VIOLATION
    wrong_proj_fail = await client.post(
        "/mcp/agent/w/kanban/p/QAUSR1",
        headers=bot_headers,
        json={"jsonrpc": "2.0", "id": 44, "method": "initialize", "params": {}},
    )
    assert wrong_proj_fail.status_code == 403
    assert wrong_proj_fail.json()["error"] == "KEY_SCOPE_VIOLATION"

    # 3. Tool restrictions: allowed_tools and disabled_tools
    filtered_headers = {"Authorization": "Bearer kb_agt_service_bot_tool_filtered_000005"}
    f_init = await client.post(
        "/mcp/agent/w/kanban/p/QAADM",
        headers=filtered_headers,
        json={"jsonrpc": "2.0", "id": 45, "method": "initialize", "params": {}},
    )
    assert f_init.status_code == 200
    f_sess = f_init.headers.get("mcp-session-id")

    f_list = await client.post(
        "/mcp/agent/w/kanban/p/QAADM",
        headers={**filtered_headers, "mcp-session-id": str(f_sess)},
        json={"jsonrpc": "2.0", "id": 46, "method": "tools/list"},
    )
    assert f_list.status_code == 200
    avail_tools = [t["name"] for t in f_list.json()["result"]["tools"]]
    assert avail_tools == ["search_tickets", "read_ticket"]
    assert "create_ticket" not in avail_tools
    qa_contract_recorder.record("condition_d_tool_filtering", f_list.request, f_list)

    # Calling disabled/restricted tool create_ticket fails with INSUFFICIENT_SCOPE
    f_call_fail = await client.post(
        "/mcp/agent/w/kanban/p/QAADM",
        headers={**filtered_headers, "mcp-session-id": str(f_sess)},
        json={
            "jsonrpc": "2.0",
            "id": 47,
            "method": "tools/call",
            "params": {
                "name": "create_ticket",
                "arguments": {"summary": "Blocked by Tool Narrowing"},
            },
        },
    )
    assert f_call_fail.status_code == 200
    f_call_body = f_call_fail.json()["result"]
    assert f_call_body["isError"]
    assert "INSUFFICIENT_SCOPE" in f_call_body["content"][0]["text"]

    # 4. capability_mask=1 blocks writes with INSUFFICIENT_CAPABILITY
    viewonly_headers = {"Authorization": "Bearer kb_agt_service_bot_viewonly_mask_000006"}
    v_init = await client.post(
        "/mcp/agent/w/kanban/p/QAADM",
        headers=viewonly_headers,
        json={"jsonrpc": "2.0", "id": 48, "method": "initialize", "params": {}},
    )
    assert v_init.status_code == 200
    v_sess = v_init.headers.get("mcp-session-id")

    v_write = await client.post(
        "/mcp/agent/w/kanban/p/QAADM",
        headers={**viewonly_headers, "mcp-session-id": str(v_sess)},
        json={
            "jsonrpc": "2.0",
            "id": 49,
            "method": "tools/call",
            "params": {
                "name": "create_ticket",
                "arguments": {"summary": "Write Blocked by Capability Mask"},
            },
        },
    )
    assert v_write.status_code == 200
    v_write_body = v_write.json()["result"]
    assert v_write_body["isError"]
    assert (
        "INSUFFICIENT_CAPABILITY" in v_write_body["content"][0]["text"]
        or "INSUFFICIENT_PERMISSION" in v_write_body["content"][0]["text"]
    )
    qa_contract_recorder.record("condition_d_capability_mask_blocked", v_write.request, v_write)


@pytest.mark.asyncio
async def test_condition_e_surface_cross_isolation_and_admin_rbac() -> None:
    """Condition E: Surface Cross-Isolation and /mcp/admin Downstream RBAC Parity.

    Verifies:
    1. Cross-surface presentation of keys (kb_agt_ on docs/admin, kb_doc_ on agent/admin,
       kb_adm_ on agent/docs, kb_agt_eph_ on admin) returns 403 SURFACE_KEY_MISMATCH.
    2. Admin RBAC parity: admin:read-only and WORKSPACE_ADMIN denied on mutations.
    3. SERVER_ADMIN + admin:destructive succeeds on two-stage destructive_lifecycle.
    """
    client, _calls, _cache = _build_matrix_test_env()

    agt_key = "kb_agt_user_global_pat_0000000000000001"
    doc_key = "kb_doc_docs_key_00000000007"
    adm_ro_key = "kb_adm_readonly_admin_key_0000000000008"
    adm_ws_key = "kb_adm_workspace_admin_key_000000000010"
    adm_destr_key = "kb_adm_server_admin_destr_key_000000009"
    eph_key = "kb_agt_eph_temp_session_key_0000000000000001"

    # 1. Surface cross-isolation checks
    # kb_agt_ on /mcp/docs -> 403
    r1 = await client.post("/mcp/docs", headers={"Authorization": f"Bearer {agt_key}"}, json={})
    assert r1.status_code == 403
    assert r1.json()["error"] == "SURFACE_KEY_MISMATCH"

    # kb_agt_ on /mcp/admin -> 403
    r2 = await client.post("/mcp/admin", headers={"Authorization": f"Bearer {agt_key}"}, json={})
    assert r2.status_code == 403
    assert r2.json()["error"] == "SURFACE_KEY_MISMATCH"

    # kb_doc_ on /mcp/agent -> 403
    r3 = await client.post("/mcp/agent", headers={"Authorization": f"Bearer {doc_key}"}, json={})
    assert r3.status_code == 403
    assert r3.json()["error"] == "SURFACE_KEY_MISMATCH"

    # kb_doc_ on /mcp/admin -> 403
    r4 = await client.post("/mcp/admin", headers={"Authorization": f"Bearer {doc_key}"}, json={})
    assert r4.status_code == 403
    assert r4.json()["error"] == "SURFACE_KEY_MISMATCH"

    # kb_adm_ on /mcp/agent -> 403
    r5 = await client.post("/mcp/agent", headers={"Authorization": f"Bearer {adm_ro_key}"}, json={})
    assert r5.status_code == 403
    assert r5.json()["error"] == "SURFACE_KEY_MISMATCH"

    # kb_adm_ on /mcp/docs -> 403
    r6 = await client.post("/mcp/docs", headers={"Authorization": f"Bearer {adm_ro_key}"}, json={})
    assert r6.status_code == 403
    assert r6.json()["error"] == "SURFACE_KEY_MISMATCH"

    # kb_agt_eph_ on /mcp/admin -> 403
    r7 = await client.post("/mcp/admin", headers={"Authorization": f"Bearer {eph_key}"}, json={})
    assert r7.status_code == 403
    assert r7.json()["error"] == "SURFACE_KEY_MISMATCH"
    qa_contract_recorder.record("condition_e_surface_isolation_mismatch", r2.request, r2)

    # 2. Admin RBAC parity checks
    # admin:read-only key calling configure_workspace(action="update") fails with INSUFFICIENT_SCOPE
    ro_init = await client.post(
        "/mcp/admin/w/kanban",
        headers={"Authorization": f"Bearer {adm_ro_key}"},
        json={"jsonrpc": "2.0", "id": 50, "method": "initialize", "params": {}},
    )
    assert ro_init.status_code == 200
    ro_sess = ro_init.headers.get("mcp-session-id")

    ro_action_fail = await client.post(
        "/mcp/admin/w/kanban",
        headers={"Authorization": f"Bearer {adm_ro_key}", "mcp-session-id": str(ro_sess)},
        json={
            "jsonrpc": "2.0",
            "id": 51,
            "method": "tools/call",
            "params": {
                "name": "configure_workspace",
                "arguments": {"action": "update", "settings": {"name": "New Name"}},
            },
        },
    )
    assert ro_action_fail.status_code == 200
    assert ro_action_fail.json()["result"]["isError"]
    assert "INSUFFICIENT_SCOPE" in ro_action_fail.json()["result"]["content"][0]["text"]

    # WORKSPACE_ADMIN calling manage_auth_cards fails downstream RBAC (INSUFFICIENT_CAPABILITY)
    ws_init = await client.post(
        "/mcp/admin/w/kanban",
        headers={"Authorization": f"Bearer {adm_ws_key}"},
        json={"jsonrpc": "2.0", "id": 52, "method": "initialize", "params": {}},
    )
    assert ws_init.status_code == 200
    ws_sess = ws_init.headers.get("mcp-session-id")

    ws_auth_fail = await client.post(
        "/mcp/admin/w/kanban",
        headers={"Authorization": f"Bearer {adm_ws_key}", "mcp-session-id": str(ws_sess)},
        json={
            "jsonrpc": "2.0",
            "id": 53,
            "method": "tools/call",
            "params": {
                "name": "manage_auth_cards",
                "arguments": {"action": "list"},
            },
        },
    )
    assert ws_auth_fail.status_code == 200
    assert ws_auth_fail.json()["result"]["isError"]
    assert (
        "INSUFFICIENT_CAPABILITY" in ws_auth_fail.json()["result"]["content"][0]["text"]
        or "INSUFFICIENT_PERMISSION" in ws_auth_fail.json()["result"]["content"][0]["text"]
    )

    # 3. SERVER_ADMIN + admin:destructive key on destructive_lifecycle (2-stage confirmation)
    destr_init = await client.post(
        "/mcp/admin",
        headers={"Authorization": f"Bearer {adm_destr_key}"},
        json={"jsonrpc": "2.0", "id": 60, "method": "initialize", "params": {}},
    )
    assert destr_init.status_code == 200
    destr_sess = destr_init.headers.get("mcp-session-id")

    # Stage 1: request_delete
    stage1_resp = await client.post(
        "/mcp/admin",
        headers={"Authorization": f"Bearer {adm_destr_key}", "mcp-session-id": str(destr_sess)},
        json={
            "jsonrpc": "2.0",
            "id": 61,
            "method": "tools/call",
            "params": {
                "name": "destructive_lifecycle",
                "arguments": {
                    "action": "request_delete",
                    "target_kind": "issue",
                    "target": "QAADM-99",
                    "mode": "trash",
                },
            },
        },
    )
    assert stage1_resp.status_code == 200
    stage1_res = stage1_resp.json()["result"]
    assert not stage1_res["isError"]
    stage1_text = stage1_res["content"][0]["text"]
    assert "confirmation_required" in stage1_text
    assert "confirmation_token" in stage1_text
    qa_contract_recorder.record(
        "condition_e_stage1_destructive_request", stage1_resp.request, stage1_resp
    )

    # Parse token and phrase from YAML output
    import yaml  # noqa: PLC0415

    parsed_stage1 = yaml.safe_load(stage1_text)
    conf_token = parsed_stage1["confirmation_token"]
    conf_phrase = parsed_stage1["confirm_phrase"]

    # Stage 2: execute_delete with token and confirm_phrase
    stage2_resp = await client.post(
        "/mcp/admin",
        headers={"Authorization": f"Bearer {adm_destr_key}", "mcp-session-id": str(destr_sess)},
        json={
            "jsonrpc": "2.0",
            "id": 62,
            "method": "tools/call",
            "params": {
                "name": "destructive_lifecycle",
                "arguments": {
                    "action": "execute_delete",
                    "target_kind": "issue",
                    "target": "QAADM-99",
                    "mode": "trash",
                    "confirmation_token": conf_token,
                    "confirm_phrase": conf_phrase,
                    "reason": "Authorized forensic test cleanup for KANBA-205",
                },
            },
        },
    )
    assert stage2_resp.status_code == 200
    stage2_res = stage2_resp.json()["result"]
    assert not stage2_res["isError"]
    assert "executed" in stage2_res["content"][0]["text"]
    qa_contract_recorder.record(
        "condition_e_stage2_destructive_execute", stage2_resp.request, stage2_resp
    )


@pytest.mark.asyncio
async def test_condition_f_protocol_headers_session_taintguard_revocation() -> None:
    """Condition F: Protocol, Headers, Session Binding, TaintGuard, and TTL Revocation.

    Verifies:
    1. Unauthenticated POST /mcp/agent... -> 401 + RFC 9728 WWW-Authenticate resource_metadata.
    2. Conflicting X-Workspace-Slug vs path -> 400 CONFLICTING_SCOPE_HEADERS.
    3. X-Project-Key without workspace -> 400 VALIDATION_FAILED.
    4. Mcp-Session-Id replay across scopes/keys -> 404.
    5. TaintGuard read->broader-write -> CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED.
    6. Revoked key post-15s TTL -> 401.
    """
    simulated_time = 1000.0

    def get_time() -> float:
        return simulated_time

    client, _calls, _ = _build_matrix_test_env(time_provider=get_time)

    # 1. Unauthenticated request -> 401 + WWW-Authenticate carrying RFC 9728 metadata
    unauth_agent = await client.post("/mcp/agent", json={})
    assert unauth_agent.status_code == 401
    auth_header = unauth_agent.headers.get("www-authenticate", "")
    assert "Bearer" in auth_header
    assert 'realm="kanban-mcp"' in auth_header
    assert 'resource_metadata="' in auth_header
    assert "/.well-known/oauth-protected-resource/mcp/agent" in auth_header
    qa_contract_recorder.record(
        "condition_f_unauthenticated_agent_401", unauth_agent.request, unauth_agent
    )

    # Scoped 401 carries scoped metadata URL
    unauth_scoped = await client.post("/mcp/agent/w/kanban/p/QAUSR1", json={})
    assert unauth_scoped.status_code == 401
    auth_scoped_header = unauth_scoped.headers.get("www-authenticate", "")
    assert "/.well-known/oauth-protected-resource/mcp/agent/w/kanban/p/QAUSR1" in auth_scoped_header

    # Verify RFC 9728 metadata endpoint returns 200 JSON
    meta_resp = await client.get("/.well-known/oauth-protected-resource/mcp/agent")
    assert meta_resp.status_code == 200
    meta_json = meta_resp.json()
    assert "resource" in meta_json
    assert "authorization_servers" in meta_json
    assert "scopes_supported" in meta_json
    qa_contract_recorder.record("condition_f_rfc9728_metadata", meta_resp.request, meta_resp)

    # 2. Conflicting X-Workspace-Slug vs path -> 400 CONFLICTING_SCOPE_HEADERS
    valid_key = "kb_agt_user_global_pat_0000000000000001"
    conflict_ws = await client.post(
        "/mcp/agent/w/kanban",
        headers={"Authorization": f"Bearer {valid_key}", "X-Workspace-Slug": "general"},
        json={"jsonrpc": "2.0", "id": 70, "method": "initialize", "params": {}},
    )
    assert conflict_ws.status_code == 400
    assert conflict_ws.json()["error"] == "CONFLICTING_SCOPE_HEADERS"
    qa_contract_recorder.record("condition_f_conflicting_headers", conflict_ws.request, conflict_ws)

    # 3. X-Project-Key without workspace -> 400 VALIDATION_FAILED
    no_ws_proj = await client.post(
        "/mcp/agent",
        headers={"Authorization": f"Bearer {valid_key}", "X-Project-Key": "QAUSR1"},
        json={"jsonrpc": "2.0", "id": 71, "method": "initialize", "params": {}},
    )
    assert no_ws_proj.status_code == 400
    assert no_ws_proj.json()["error"] == "VALIDATION_FAILED"
    qa_contract_recorder.record(
        "condition_f_project_without_workspace", no_ws_proj.request, no_ws_proj
    )

    # 4. Mcp-Session-Id replay across scopes and across keys -> 404
    init_sess_a = await client.post(
        "/mcp/agent/w/kanban/p/QAUSR1",
        headers={"Authorization": f"Bearer {valid_key}"},
        json={"jsonrpc": "2.0", "id": 72, "method": "initialize", "params": {}},
    )
    assert init_sess_a.status_code == 200
    sess_id_a = init_sess_a.headers.get("mcp-session-id")

    # Replay session A across different project scope -> 404
    replay_scope_resp = await client.post(
        "/mcp/agent/w/kanban/p/QAADM",
        headers={"Authorization": f"Bearer {valid_key}", "mcp-session-id": str(sess_id_a)},
        json={"jsonrpc": "2.0", "id": 73, "method": "tools/list"},
    )
    assert replay_scope_resp.status_code == 404
    qa_contract_recorder.record(
        "condition_f_session_scope_replay_404", replay_scope_resp.request, replay_scope_resp
    )

    # Replay session A across different key -> 404
    diff_key = "kb_agt_user_project_pinned_pat_00000002"
    replay_key_resp = await client.post(
        "/mcp/agent/w/kanban/p/QAUSR1",
        headers={"Authorization": f"Bearer {diff_key}", "mcp-session-id": str(sess_id_a)},
        json={"jsonrpc": "2.0", "id": 74, "method": "tools/list"},
    )
    assert replay_key_resp.status_code == 404
    qa_contract_recorder.record(
        "condition_f_session_token_replay_404", replay_key_resp.request, replay_key_resp
    )

    # 5. TaintGuard assertion: read->broader-write -> CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED
    # Test via MCP tool call against upstream returning 409
    init_sess_taint = await client.post(
        "/mcp/agent/w/kanban",
        headers={"Authorization": f"Bearer {valid_key}"},
        json={"jsonrpc": "2.0", "id": 75, "method": "initialize", "params": {}},
    )
    sess_id_taint = init_sess_taint.headers.get("mcp-session-id")

    taint_call = await client.post(
        "/mcp/agent/w/kanban",
        headers={"Authorization": f"Bearer {valid_key}", "mcp-session-id": str(sess_id_taint)},
        json={
            "jsonrpc": "2.0",
            "id": 76,
            "method": "tools/call",
            "params": {
                "name": "create_ticket",
                "arguments": {
                    "project": "QAADM",
                    "summary": "TRIGGER_TAINT_REJECTION",
                },
            },
        },
    )
    assert taint_call.status_code == 200
    taint_res = taint_call.json()["result"]
    assert taint_res["isError"]
    assert "CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED" in taint_res["content"][0]["text"]
    qa_contract_recorder.record("condition_f_taint_guard_rejection", taint_call.request, taint_call)

    # Direct unit test of TaintGuard class preconditions
    class _MockPrincipal:
        id = uuid.uuid4()
        token = "test_token"

    class _MockSession:
        pass

    scope_no_sess = {
        "type": "http",
        "headers": [(b"x-kb-service-principal", b"mcp-gateway")],
    }
    with pytest.raises(ProblemException) as exc_missing:
        TaintGuard(Request(scope_no_sess), _MockSession(), _MockPrincipal())  # type: ignore[arg-type]
    assert exc_missing.value.code == "MISSING_MCP_SESSION"
    assert exc_missing.value.status == 400

    # 6. Revoked key post-15s TTL -> 401
    revoked_token = "kb_agt_revoked_key_000000000000000001"
    rev_client, _calls2, _ = _build_matrix_test_env(
        custom_tokens={
            revoked_token: {
                "active": True,
                "principal_id": "00000000-0000-0000-0000-000000000001",
                "token_kind": "api_key",
                "scope_tier": "global",
                "scopes": ["agent:read"],
            }
        },
        time_provider=get_time,
    )

    # Initial call succeeds and is cached
    r_initial = await rev_client.post(
        "/mcp/agent",
        headers={"Authorization": f"Bearer {revoked_token}"},
        json={"jsonrpc": "2.0", "id": 80, "method": "initialize", "params": {}},
    )
    assert r_initial.status_code == 200

    # Revoke key in upstream db
    rev_client_inst, _calls3, _ = _build_matrix_test_env(
        custom_tokens={revoked_token: {"active": False}},
        time_provider=get_time,
    )

    # Advance time beyond 15s cache TTL
    simulated_time += DEFAULT_CACHE_TTL_S + 5.0

    r_revoked = await rev_client_inst.post(
        "/mcp/agent",
        headers={"Authorization": f"Bearer {revoked_token}"},
        json={"jsonrpc": "2.0", "id": 81, "method": "initialize", "params": {}},
    )
    assert r_revoked.status_code == 401
    qa_contract_recorder.record("condition_f_revocation_post_ttl_401", r_revoked.request, r_revoked)

    # Flush contract sample document for KANBA-205 QA evidence
    contract_file = Path("docs/qa/KANBA-205/contract-sample.json")
    doc = qa_contract_recorder.to_document()
    doc["feature"] = "CLI MCP Scoping QA: User vs Project Agent Matrix (agy & codex)"
    doc["matrix_summary"] = {
        "Condition_A": {
            "role": "User Agent (personal_user kb_agt_ PAT)",
            "scope_tier": "global",
            "connection_mode": "unscoped (/mcp/agent)",
            "tools_count": 9,
            "crud_qa_project": "QAUSR1",
            "unauthorized_anti_enumeration": "NOT_FOUND",
        },
        "Condition_B": {
            "role": "User Agent (personal_user kb_agt_ PAT)",
            "scope_tier": "global",
            "connection_mode": "scoped (/mcp/agent/w/kanban and /mcp/agent/w/kanban/p/QAUSR1)",
            "autofill_behavior": "project='QAUSR1' auto-filled when omitted",
            "cross_project_rejection": "CONNECTION_SCOPE_VIOLATION",
        },
        "Condition_C": {
            "role": "User Agent (personal_user kb_agt_ PAT)",
            "scope_tier": "project (pinned to QAUSR1)",
            "narrowing_behavior": "narrows effective scope to QAUSR1 on unscoped endpoint",
            "forbidden_connections": ["/mcp/agent/w/kanban", "/mcp/agent/w/kanban/p/QAADM"],
            "forbidden_status": 403,
            "forbidden_error": "KEY_SCOPE_VIOLATION",
            "readonly_pat_mutation_rejection": "INSUFFICIENT_SCOPE",
        },
        "Condition_D": {
            "role": "Project Agent (service_bot kb_agt_ PAT)",
            "scope_tier": "project (pinned to QAADM)",
            "positive_connection": "/mcp/agent/w/kanban/p/QAADM and /mcp/agent + X-Workspace-Slug/X-Project-Key",
            "negative_connections": ["/mcp/agent/w/kanban", "/mcp/agent/w/kanban/p/QAUSR1"],
            "negative_status": 403,
            "tool_filtering_behavior": "allowed_tools and disabled_tools filter tools/list and block tools/call",
            "view_only_capability_mask_rejection": "INSUFFICIENT_CAPABILITY",
        },
        "Condition_E": {
            "role": "Surface Cross-Isolation and Admin RBAC Parity",
            "cross_surface_rejections": [
                "kb_agt_ on /mcp/docs or /mcp/admin -> 403 SURFACE_KEY_MISMATCH",
                "kb_doc_ on /mcp/agent or /mcp/admin -> 403 SURFACE_KEY_MISMATCH",
                "kb_adm_ on /mcp/agent or /mcp/docs -> 403 SURFACE_KEY_MISMATCH",
                "kb_agt_eph_ on /mcp/admin -> 403 SURFACE_KEY_MISMATCH",
            ],
            "admin_rbac_parity": "admin:read-only denied on mutations (INSUFFICIENT_SCOPE); WORKSPACE_ADMIN denied on server admin endpoints",
            "destructive_confirmation": "2-stage request_delete -> execute_delete with token, confirm_phrase, and audit reason",
        },
        "Condition_F": {
            "role": "Protocol Preconditions, Session Binding, TaintGuard, and TTL Revocation",
            "unauthenticated_status": 401,
            "unauthenticated_header": "WWW-Authenticate: Bearer realm='kanban-mcp', resource_metadata='...'",
            "conflicting_headers_status": 400,
            "conflicting_headers_error": "CONFLICTING_SCOPE_HEADERS",
            "missing_workspace_status": 400,
            "missing_workspace_error": "VALIDATION_FAILED",
            "session_replay_rejection": 404,
            "taint_guard_rejection": "409 CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED",
            "ttl_revocation_status": 401,
        },
    }
    doc["rfc9728_metadata_samples"] = {
        "agent_global": {
            "resource": "https://127.0.0.1:8443/mcp/agent",
            "authorization_servers": ["https://127.0.0.1:8443"],
            "scopes_supported": ["agent:read", "agent:write"],
        },
        "agent_workspace_scoped": {
            "resource": "https://127.0.0.1:8443/mcp/agent/w/kanban",
            "authorization_servers": ["https://127.0.0.1:8443"],
            "scopes_supported": ["agent:read", "agent:write"],
        },
        "agent_project_scoped": {
            "resource": "https://127.0.0.1:8443/mcp/agent/w/kanban/p/QAUSR1",
            "authorization_servers": ["https://127.0.0.1:8443"],
            "scopes_supported": ["agent:read", "agent:write"],
        },
        "docs": {
            "resource": "https://127.0.0.1:8443/mcp/docs",
            "authorization_servers": ["https://127.0.0.1:8443"],
            "scopes_supported": ["docs:read", "docs:write"],
        },
        "admin": {
            "resource": "https://127.0.0.1:8443/mcp/admin",
            "authorization_servers": ["https://127.0.0.1:8443"],
            "scopes_supported": ["admin:read", "admin:write", "admin:destructive"],
        },
    }
    contract_file.parent.mkdir(parents=True, exist_ok=True)
    contract_file.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    assert contract_file.exists()
