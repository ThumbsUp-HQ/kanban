# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Mandatory feature unit tests for dynamic MCP connection scoping (KB-P4-15, S11.1)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import yaml

from mcp.app import create_mcp_app
from mcp.auth import McpAuthContext, McpAuthMiddleware
from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.registry import Surface, ToolSpec
from mcp.scoping import (
    ConnectionScope,
    ScopeMode,
    enforce_connection_scope_on_tool_call,
    intersect_key_and_connection_scope,
    parse_connection_scope,
)
from mcp.settings import McpSettings
from mcp.surfaces.agent import create_agent_registry


def _build_scoping_test_env(  # noqa: C901
    introspect_db: dict[str, dict[str, Any]] | None = None,
) -> tuple[httpx.AsyncClient, list[dict[str, Any]]]:
    """Construct test MCP app wired with mock upstream simulating kanban-api."""
    recorded_upstream_calls: list[dict[str, Any]] = []

    tokens_db = introspect_db or {
        "kb_agt_global_key": {
            "active": True,
            "principal_id": "00000000-0000-0000-0000-000000000001",
            "workspace_id": "00000000-0000-0000-0000-000000000002",
            "token_kind": "api_key",
            "scope_tier": "global",
            "scopes": ["agent:read", "agent:write"],
        },
        "kb_agt_ws_kanban_key": {
            "active": True,
            "principal_id": "00000000-0000-0000-0000-000000000001",
            "workspace_id": "00000000-0000-0000-0000-000000000002",
            "workspace_slug": "kanban",
            "token_kind": "api_key",
            "scope_tier": "workspace",
            "scopes": ["agent:read", "agent:write"],
        },
        "kb_agt_proj_key": {
            "active": True,
            "principal_id": "00000000-0000-0000-0000-000000000001",
            "workspace_id": "00000000-0000-0000-0000-000000000002",
            "workspace_slug": "kanban",
            "allowed_projects": ["KANBA"],
            "token_kind": "api_key",
            "scope_tier": "project",
            "scopes": ["agent:read", "agent:write"],
        },
    }

    async def mock_handler(request: httpx.Request) -> httpx.Response:  # noqa: C901, PLR0911, PLR0912
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

        # 1. Introspection
        if url_path == "/internal/v1/mcp/introspect":
            token = str(body.get("token") or "")
            intro = tokens_db.get(token, {"active": False})
            return httpx.Response(200, json=intro)

        # 2. Search issues
        if url_path == "/api/v1/search/issues":
            proj = body.get("project")
            if proj == "KANBA":
                return httpx.Response(
                    200,
                    json={
                        "total": 1,
                        "items": [
                            {
                                "kind": "issue",
                                "id": "00000000-0000-0000-0000-000000000010",
                                "key": "KANBA-4",
                                "title": "Auth Setup",
                                "summary": "Auth Setup",
                                "project_identifier": "KANBA",
                                "workspace": "kanban",
                                "score": 1.0,
                                "state": "open",
                            }
                        ],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "total": 2,
                    "items": [
                        {
                            "kind": "issue",
                            "id": "00000000-0000-0000-0000-000000000010",
                            "key": "KANBA-4",
                            "title": "Auth Setup",
                            "summary": "Auth Setup",
                            "project_identifier": "KANBA",
                            "workspace": "kanban",
                            "score": 1.0,
                            "state": "open",
                        },
                        {
                            "kind": "issue",
                            "id": "00000000-0000-0000-0000-000000000020",
                            "key": "NETALERTXN-12",
                            "title": "Net Alert",
                            "summary": "Net Alert",
                            "project_identifier": "NETALERTXN",
                            "workspace": "general",
                            "score": 0.9,
                            "state": "open",
                        },
                    ],
                },
            )

        # 3. Resolve
        if url_path == "/api/v1/resolve":
            kind = request.url.params.get("kind")
            ref = request.url.params.get("ref")
            ws_param = request.url.params.get("workspace")
            ws_header = request.headers.get("x-kb-scope-workspace")
            effective_ws = ws_param or ws_header

            if kind == "project":
                return httpx.Response(
                    200,
                    json={
                        "id": "00000000-0000-0000-0000-000000000003",
                        "kind": "project",
                        "key": ref,
                        "title": f"Project {ref}",
                    },
                )

            if kind == "issue":
                if ref == "NETALERTXN-12":
                    return httpx.Response(
                        200,
                        json={
                            "id": "00000000-0000-0000-0000-000000000020",
                            "kind": "issue",
                            "key": "NETALERTXN-12",
                            "title": "Net Alert",
                            "workspace": "general",
                        },
                    )
                if ref == "API-1":
                    if effective_ws == "ws-prod":
                        return httpx.Response(
                            200,
                            json={
                                "id": "00000000-0000-0000-0000-000000000030",
                                "kind": "issue",
                                "key": "API-1",
                                "title": "Prod API Service",
                                "workspace": "ws-prod",
                            },
                        )
                    if effective_ws == "ws-stage":
                        return httpx.Response(
                            200,
                            json={
                                "id": "00000000-0000-0000-0000-000000000031",
                                "kind": "issue",
                                "key": "API-1",
                                "title": "Staging API Service",
                                "workspace": "ws-stage",
                            },
                        )
                    return httpx.Response(
                        409,
                        headers={"Content-Type": "application/problem+json"},
                        json={
                            "type": "urn:kanban:problem:AMBIGUOUS_IDENTIFIER",
                            "code": "AMBIGUOUS_IDENTIFIER",
                            "status": 409,
                            "title": "Ambiguous Identifier",
                            "detail": "Issue key 'API-1' exists in multiple authorized workspaces",
                            "candidates": [
                                {
                                    "workspace": "ws-prod",
                                    "key": "API-1",
                                    "title": "Prod API Service",
                                },
                                {
                                    "workspace": "ws-stage",
                                    "key": "API-1",
                                    "title": "Staging API Service",
                                },
                            ],
                            "hint": "pass workspace=<slug> or connect via /mcp/agent/w/<slug>",
                        },
                    )

        # 4. Direct Issue read
        if url_path.startswith("/api/v1/issues/"):
            issue_ref = url_path.rsplit("/", 1)[-1]
            ws_param = request.url.params.get("workspace")
            ws_header = request.headers.get("x-kb-scope-workspace")
            effective_ws = ws_param or ws_header

            if issue_ref == "NETALERTXN-12":
                return httpx.Response(
                    200,
                    json={
                        "id": "00000000-0000-0000-0000-000000000020",
                        "key": "NETALERTXN-12",
                        "summary": "Net Alert",
                        "state": "open",
                        "priority": "high",
                        "workspace": "general",
                    },
                )
            if issue_ref == "API-1":
                if effective_ws == "ws-prod":
                    return httpx.Response(
                        200,
                        json={
                            "id": "00000000-0000-0000-0000-000000000030",
                            "key": "API-1",
                            "summary": "Prod API Service",
                            "state": "open",
                            "priority": "high",
                            "workspace": "ws-prod",
                        },
                    )
                return httpx.Response(
                    409,
                    headers={"Content-Type": "application/problem+json"},
                    json={
                        "type": "urn:kanban:problem:AMBIGUOUS_IDENTIFIER",
                        "code": "AMBIGUOUS_IDENTIFIER",
                        "status": 409,
                        "title": "Ambiguous Identifier",
                        "detail": "Issue key 'API-1' exists in multiple authorized workspaces",
                        "candidates": [
                            {"workspace": "ws-prod", "key": "API-1", "title": "Prod API Service"},
                            {
                                "workspace": "ws-stage",
                                "key": "API-1",
                                "title": "Staging API Service",
                            },
                        ],
                        "hint": "pass workspace=<slug> or connect via /mcp/agent/w/<slug>",
                    },
                )

        # 5. Create ticket / issues
        if url_path == "/api/v1/issues" and request.method == "POST":
            return httpx.Response(
                201,
                json={
                    "id": "00000000-0000-0000-0000-000000000099",
                    "key": "KANBA-1",
                    "summary": body.get("summary", "New Ticket"),
                    "workspace": "kanban",
                },
            )

        return httpx.Response(404, json={"detail": "Not found"})

    transport = httpx.MockTransport(mock_handler)
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    kanban_client = KanbanApiClient(settings, transport=transport)

    # Agent registry with search_tickets, read_ticket, plus create_ticket and update_ticket
    agent_reg = create_agent_registry()

    async def _mock_create_ticket(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "key": f"{args.get('project', 'UNKNOWN')}-1",
            "title": args.get("title", ""),
            "project": args.get("project"),
        }

    async def _mock_update_ticket(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "key": args.get("identifier"),
            "status": "updated",
        }

    agent_reg.register(
        ToolSpec(
            name="create_ticket",
            description="Create ticket in project",
            surface=Surface.AGENT,
            input_schema={"type": "object"},
            handler=_mock_create_ticket,
        )
    )
    agent_reg.register(
        ToolSpec(
            name="update_ticket",
            description="Update ticket by identifier",
            surface=Surface.AGENT,
            input_schema={"type": "object"},
            handler=_mock_update_ticket,
        )
    )
    agent_reg.freeze()

    base_app = create_mcp_app(
        settings=settings,
        agent_registry=agent_reg,
        internal_client=kanban_client,
    )
    middleware = McpAuthMiddleware(
        base_app,
        surface=Surface.AGENT,
        internal_client=kanban_client,
        settings=settings,
    )

    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=middleware), base_url="http://test"
    )
    return client, recorded_upstream_calls


@pytest.mark.asyncio
async def test_case_1_positive_global_meatloaf_bot_flow() -> None:
    """Test Case 1: Positive (Global meatloaf-bot Flow).

    Global key connects to /mcp/agent, runs search_tickets(query="auth") returning YAML rows
    tagged with workspace: kanban (KANBA-4) and workspace: general (NETALERTXN-12), and reads
    NETALERTXN-12 directly without specifying workspace because NETALERTXN is globally unique.
    """
    client, _upstream_calls = _build_scoping_test_env()
    headers = {"Authorization": "Bearer kb_agt_global_key"}

    # 1. Initialize on /mcp/agent (Global)
    init_resp = await client.post(
        "/mcp/agent",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "meatloaf-bot", "version": "1.0"},
            },
        },
    )
    assert init_resp.status_code == 200
    session_id = init_resp.headers.get("mcp-session-id")
    assert session_id is not None
    session_headers = {**headers, "mcp-session-id": session_id}

    # 2. search_tickets(query="auth")
    search_resp = await client.post(
        "/mcp/agent",
        headers=session_headers,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "search_tickets", "arguments": {"query": "auth"}},
        },
    )
    assert search_resp.status_code == 200
    result_data = search_resp.json()["result"]
    assert result_data["isError"] is False
    yaml_text = result_data["content"][0]["text"]
    parsed_yaml = yaml.safe_load(yaml_text)

    # Verify YAML contains both workspaces
    items = parsed_yaml.get("items", [])
    assert len(items) == 2
    ws_keys = {(it.get("workspace"), it.get("key")) for it in items}
    assert ("kanban", "KANBA-4") in ws_keys
    assert ("general", "NETALERTXN-12") in ws_keys

    # 3. read_ticket("NETALERTXN-12") without workspace
    read_resp = await client.post(
        "/mcp/agent",
        headers=session_headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "read_ticket", "arguments": {"identifier": "NETALERTXN-12"}},
        },
    )
    assert read_resp.status_code == 200
    read_data = read_resp.json()["result"]
    assert read_data["isError"] is False
    read_yaml = yaml.safe_load(read_data["content"][0]["text"])
    assert read_yaml["key"] == "NETALERTXN-12"
    assert read_yaml["workspace"] == "general"


@pytest.mark.asyncio
async def test_case_2_positive_ambiguous_global_key_disambiguation() -> None:
    """Test Case 2: Positive (Ambiguous Global Key Disambiguation).

    Two workspaces (ws-prod, ws-stage) both have project API and issue API-1.
    read_ticket("API-1") on global /mcp/agent returns AMBIGUOUS_IDENTIFIER listing both workspaces;
    read_ticket("API-1", workspace="ws-prod") returns 200 YAML for ws-prod.
    """
    client, _upstream_calls = _build_scoping_test_env()
    headers = {"Authorization": "Bearer kb_agt_global_key"}

    init_resp = await client.post(
        "/mcp/agent",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        },
    )
    session_id = init_resp.headers.get("mcp-session-id")
    session_headers = {**headers, "mcp-session-id": session_id}

    # 1. Ambiguous resolution: read_ticket("API-1") without workspace
    ambig_resp = await client.post(
        "/mcp/agent",
        headers=session_headers,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "read_ticket", "arguments": {"identifier": "API-1"}},
        },
    )
    assert ambig_resp.status_code == 200
    ambig_data = ambig_resp.json()["result"]
    assert ambig_data["isError"] is True
    ambig_yaml = yaml.safe_load(ambig_data["content"][0]["text"])
    err_obj = ambig_yaml.get("error", ambig_yaml)
    assert err_obj["code"] == "AMBIGUOUS_IDENTIFIER"
    candidates = err_obj.get("candidates", [])
    assert len(candidates) == 2
    ws_set = {c.get("workspace") for c in candidates}
    assert ws_set == {"ws-prod", "ws-stage"}

    # 2. Disambiguated resolution: read_ticket("API-1", workspace="ws-prod")
    scoped_resp = await client.post(
        "/mcp/agent",
        headers=session_headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "read_ticket",
                "arguments": {"identifier": "API-1", "workspace": "ws-prod"},
            },
        },
    )
    assert scoped_resp.status_code == 200
    scoped_data = scoped_resp.json()["result"]
    assert scoped_data["isError"] is False
    scoped_yaml = yaml.safe_load(scoped_data["content"][0]["text"])
    assert scoped_yaml["key"] == "API-1"
    assert scoped_yaml["workspace"] == "ws-prod"


@pytest.mark.asyncio
async def test_case_3_positive_project_pinned_repo_config() -> None:
    """Test Case 3: Positive (Project-Pinned Zero-Script Repo Config).

    Global or workspace key connects to /mcp/agent/w/kanban/p/KANBA (and repeat test via
    /mcp/agent + X-Workspace-Slug: kanban + X-Project-Key: KANBA); create_ticket(title="Test")
    without project= auto-fills project="KANBA", and search_tickets() returns only KANBA-* issues.
    """
    client, _upstream_calls = _build_scoping_test_env()
    headers = {"Authorization": "Bearer kb_agt_global_key"}

    # Part A: URL Path Scoping (/mcp/agent/w/kanban/p/KANBA)
    init_path = await client.post(
        "/mcp/agent/w/kanban/p/KANBA",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "ide-agent", "version": "1.0"},
            },
        },
    )
    assert init_path.status_code == 200
    sess_path = init_path.headers.get("mcp-session-id")
    assert sess_path is not None
    sess_headers_path = {**headers, "mcp-session-id": sess_path}

    # create_ticket(title="Test Issue") without project -> auto-fills project="KANBA"
    create_resp = await client.post(
        "/mcp/agent/w/kanban/p/KANBA",
        headers=sess_headers_path,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "create_ticket",
                "arguments": {"title": "Test Issue"},
            },
        },
    )
    assert create_resp.status_code == 200
    create_data = create_resp.json()["result"]
    assert create_data["isError"] is False
    create_yaml = yaml.safe_load(create_data["content"][0]["text"])
    assert create_yaml["project"] == "KANBA"
    assert create_yaml["key"] == "KANBA-1"

    # search_tickets() without project -> auto-fills project="KANBA" and returns KANBA-*
    search_resp = await client.post(
        "/mcp/agent/w/kanban/p/KANBA",
        headers=sess_headers_path,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "search_tickets", "arguments": {}},
        },
    )
    assert search_resp.status_code == 200
    search_data = search_resp.json()["result"]
    assert search_data["isError"] is False
    search_yaml = yaml.safe_load(search_data["content"][0]["text"])
    items = search_yaml.get("items", [])
    assert len(items) == 1
    assert items[0]["key"] == "KANBA-4"

    # Part B: Header Scoping (/mcp/agent + X-Workspace-Slug: kanban + X-Project-Key: KANBA)
    header_scope = {
        **headers,
        "X-Workspace-Slug": "kanban",
        "X-Project-Key": "KANBA",
    }
    init_hdr = await client.post(
        "/mcp/agent",
        headers=header_scope,
        json={
            "jsonrpc": "2.0",
            "id": 10,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "ide-agent-headers", "version": "1.0"},
            },
        },
    )
    assert init_hdr.status_code == 200
    sess_hdr = init_hdr.headers.get("mcp-session-id")
    sess_hdr_headers = {**header_scope, "mcp-session-id": sess_hdr}

    create_hdr_resp = await client.post(
        "/mcp/agent",
        headers=sess_hdr_headers,
        json={
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "create_ticket",
                "arguments": {"title": "Header Test Issue"},
            },
        },
    )
    assert create_hdr_resp.status_code == 200
    create_hdr_data = create_hdr_resp.json()["result"]
    assert create_hdr_data["isError"] is False
    create_hdr_yaml = yaml.safe_load(create_hdr_data["content"][0]["text"])
    assert create_hdr_yaml["project"] == "KANBA"


@pytest.mark.asyncio
async def test_case_4_security_monotonic_narrowing_and_cross_project_block() -> None:
    """Test Case 4: Security (Monotonic Narrowing & Cross-Project Block).

    While connected to /mcp/agent/w/kanban/p/KANBA:
    - calling update_ticket("NETALERTXN-1", ...) or create_ticket(project="GENER", ...)
      fails with CONNECTION_SCOPE_VIOLATION.
    - presenting a project=KANBA key to /mcp/agent/w/general fails with
      HTTP 403 KEY_SCOPE_VIOLATION.
    """
    client, _upstream_calls = _build_scoping_test_env()
    headers = {"Authorization": "Bearer kb_agt_global_key"}

    init_resp = await client.post(
        "/mcp/agent/w/kanban/p/KANBA",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "ide-agent", "version": "1.0"},
            },
        },
    )
    sess_id = init_resp.headers.get("mcp-session-id")
    session_headers = {**headers, "mcp-session-id": sess_id}

    # 1. Foreign project mutation via update_ticket("NETALERTXN-1")
    update_resp = await client.post(
        "/mcp/agent/w/kanban/p/KANBA",
        headers=session_headers,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "update_ticket",
                "arguments": {"identifier": "NETALERTXN-1"},
            },
        },
    )
    assert update_resp.status_code == 200
    update_data = update_resp.json()["result"]
    assert update_data["isError"] is True
    update_yaml = yaml.safe_load(update_data["content"][0]["text"])
    err_up = update_yaml.get("error", update_yaml)
    assert err_up["code"] == "CONNECTION_SCOPE_VIOLATION"

    # 2. Foreign project parameter via create_ticket(project="GENER")
    create_resp = await client.post(
        "/mcp/agent/w/kanban/p/KANBA",
        headers=session_headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "create_ticket",
                "arguments": {"project": "GENER", "title": "Illegal Project"},
            },
        },
    )
    assert create_resp.status_code == 200
    create_data = create_resp.json()["result"]
    assert create_data["isError"] is True
    create_yaml = yaml.safe_load(create_data["content"][0]["text"])
    err_cr = create_yaml.get("error", create_yaml)
    assert err_cr["code"] == "CONNECTION_SCOPE_VIOLATION"

    # 3. Presenting single-project key (project=KANBA in workspace=kanban) to /mcp/agent/w/general
    proj_headers = {"Authorization": "Bearer kb_agt_proj_key"}
    violation_resp = await client.post(
        "/mcp/agent/w/general",
        headers=proj_headers,
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "bad-agent", "version": "1.0"},
            },
        },
    )
    assert violation_resp.status_code == 403
    v_data = violation_resp.json()
    assert v_data["error"] == "KEY_SCOPE_VIOLATION"


@pytest.mark.asyncio
async def test_case_5_security_conflicting_headers_and_session_replay() -> None:
    """Test Case 5: Security (Conflicting Headers & Session Replay).

    - POST /mcp/agent/w/kanban with X-Workspace-Slug: general -> HTTP 400 CONFLICTING_SCOPE_HEADERS.
    - POST /mcp/agent with X-Project-Key without workspace -> HTTP 400 VALIDATION_FAILED.
    - Replaying an Mcp-Session-Id from /w/kanban/p/KANBA on /mcp/agent -> HTTP 404.
    """
    client, _upstream_calls = _build_scoping_test_env()
    headers = {"Authorization": "Bearer kb_agt_global_key"}

    # 1. Conflict between URL path workspace (/w/kanban) and header (X-Workspace-Slug: general)
    conflict_headers = {
        **headers,
        "X-Workspace-Slug": "general",
    }
    conflict_resp = await client.post(
        "/mcp/agent/w/kanban",
        headers=conflict_headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "confused-client", "version": "1.0"},
            },
        },
    )
    assert conflict_resp.status_code == 400
    c_data = conflict_resp.json()
    assert c_data["error"] == "CONFLICTING_SCOPE_HEADERS"

    # 2. X-Project-Key without workspace
    naked_proj_headers = {
        **headers,
        "X-Project-Key": "KANBA",
    }
    naked_resp = await client.post(
        "/mcp/agent",
        headers=naked_proj_headers,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "naked-proj-client", "version": "1.0"},
            },
        },
    )
    assert naked_resp.status_code == 400
    n_data = naked_resp.json()
    assert n_data["error"] == "VALIDATION_FAILED"

    # 3. Session Replay across scopes
    init_scoped = await client.post(
        "/mcp/agent/w/kanban/p/KANBA",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "scoped-client", "version": "1.0"},
            },
        },
    )
    assert init_scoped.status_code == 200
    scoped_session_id = init_scoped.headers.get("mcp-session-id")
    assert scoped_session_id is not None

    # Replay session ID on global /mcp/agent -> HTTP 404
    replay_resp = await client.post(
        "/mcp/agent",
        headers={**headers, "mcp-session-id": scoped_session_id},
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "search_tickets", "arguments": {}},
        },
    )
    assert replay_resp.status_code == 404

    # Replay session ID on foreign project /mcp/agent/w/kanban/p/OTHER -> HTTP 404
    replay_proj_resp = await client.post(
        "/mcp/agent/w/kanban/p/OTHER",
        headers={**headers, "mcp-session-id": scoped_session_id},
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "search_tickets", "arguments": {}},
        },
    )
    assert replay_proj_resp.status_code == 404


def test_scoping_header_path_project_mismatch() -> None:
    """Conflicting project in URL path and header raises CONFLICTING_SCOPE_HEADERS."""
    with pytest.raises(KbMcpError) as exc_info:
        parse_connection_scope(
            "/mcp/agent/w/kanban/p/KANBA",
            {"x-project-key": "OTHER", "x-workspace-slug": "kanban"},
        )
    assert exc_info.value.code == McpErrorCode.CONFLICTING_SCOPE_HEADERS


def test_intersect_key_and_connection_scope_token_inheritance() -> None:
    """Tokens with workspace or project scope inherit their scope in global connection mode."""
    # Project-pinned token inheriting in global mode
    proj_ctx = McpAuthContext(
        token="test",  # noqa: S106
        token_sha256=b"123",
        surface=Surface.AGENT,
        scopes=frozenset({"agent:read"}),
        workspace_slug="kanban",
        scope_tier="project",
        allowed_projects=["KANBA"],
    )
    narrowed = intersect_key_and_connection_scope(proj_ctx, ConnectionScope(ScopeMode.GLOBAL))
    assert narrowed.is_project
    assert narrowed.workspace_slug == "kanban"
    assert narrowed.project_key == "KANBA"

    # Workspace-pinned token inheriting in global mode
    ws_ctx = McpAuthContext(
        token="test",  # noqa: S106
        token_sha256=b"123",
        surface=Surface.AGENT,
        scopes=frozenset({"agent:read"}),
        workspace_slug="kanban",
        scope_tier="workspace",
    )
    narrowed_ws = intersect_key_and_connection_scope(ws_ctx, ConnectionScope(ScopeMode.GLOBAL))
    assert narrowed_ws.is_workspace
    assert narrowed_ws.workspace_slug == "kanban"


def test_intersect_key_and_connection_scope_violations() -> None:
    """Project-pinned tokens cannot connect workspace-wide or to foreign projects."""
    proj_ctx = McpAuthContext(
        token="test",  # noqa: S106
        token_sha256=b"123",
        surface=Surface.AGENT,
        scopes=frozenset({"agent:read"}),
        workspace_slug="kanban",
        scope_tier="project",
        allowed_projects=["KANBA"],
    )
    # Attempt workspace-wide mode
    with pytest.raises(KbMcpError) as exc_ws:
        intersect_key_and_connection_scope(
            proj_ctx, ConnectionScope(ScopeMode.WORKSPACE, workspace_slug="kanban")
        )
    assert exc_ws.value.code == McpErrorCode.KEY_SCOPE_VIOLATION

    # Attempt foreign workspace
    with pytest.raises(KbMcpError) as exc_fws:
        intersect_key_and_connection_scope(
            proj_ctx,
            ConnectionScope(ScopeMode.PROJECT, workspace_slug="other", project_key="KANBA"),
        )
    assert exc_fws.value.code == McpErrorCode.KEY_SCOPE_VIOLATION

    # Attempt foreign project
    with pytest.raises(KbMcpError) as exc_fproj:
        intersect_key_and_connection_scope(
            proj_ctx,
            ConnectionScope(ScopeMode.PROJECT, workspace_slug="kanban", project_key="OTHER"),
        )
    assert exc_fproj.value.code == McpErrorCode.KEY_SCOPE_VIOLATION


def test_enforce_connection_scope_auto_fill_and_parent_identifier() -> None:
    """Project mode auto-fills project and rejects foreign parent/ticket."""
    scope = ConnectionScope(ScopeMode.PROJECT, workspace_slug="kanban", project_key="KANBA")

    # Auto-fill empty project
    args = {"title": "Test", "project": ""}
    enforce_connection_scope_on_tool_call("create_ticket", args, scope)
    assert args["project"] == "KANBA"

    # Block foreign ticket reference in 'ticket' argument
    args_ticket = {"ticket": "OTHER-42"}
    with pytest.raises(KbMcpError) as exc_ticket:
        enforce_connection_scope_on_tool_call("transition_ticket", args_ticket, scope)
    assert exc_ticket.value.code == McpErrorCode.CONNECTION_SCOPE_VIOLATION

    # Block foreign parent reference in 'parent' argument
    args_parent = {"parent": "OTHER-1"}
    with pytest.raises(KbMcpError) as exc_parent:
        enforce_connection_scope_on_tool_call("create_ticket", args_parent, scope)
    assert exc_parent.value.code == McpErrorCode.CONNECTION_SCOPE_VIOLATION

    # Allowed parent reference in current project
    args_valid = {"parent": "KANBA-1", "project": "KANBA"}
    enforce_connection_scope_on_tool_call("create_ticket", args_valid, scope)
    assert args_valid["parent"] == "KANBA-1"

    # Non-mutating tool or non-issue key identifier
    args_other = {"identifier": "custom-uuid-or-slug"}
    enforce_connection_scope_on_tool_call("search_tickets", args_other, scope)


def test_intersect_key_and_connection_scope_workspace_valid() -> None:
    """Workspace token connecting in matching workspace mode succeeds."""
    ws_ctx = McpAuthContext(
        token="test",  # noqa: S106
        token_sha256=b"123",
        surface=Surface.AGENT,
        scopes=frozenset({"agent:read"}),
        workspace_id="00000000-0000-0000-0000-000000000002",
        workspace_slug="kanban",
        scope_tier="workspace",
    )
    res = intersect_key_and_connection_scope(
        ws_ctx, ConnectionScope(ScopeMode.WORKSPACE, workspace_slug="kanban")
    )
    assert res.is_workspace
    assert res.workspace_slug == "kanban"
    assert res.workspace_id == "00000000-0000-0000-0000-000000000002"

    # parse_connection_scope without headers
    res_no_headers = parse_connection_scope("/mcp/agent", None)
    assert res_no_headers.is_global
