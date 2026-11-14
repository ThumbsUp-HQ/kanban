# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/admin override_ticket_provenance tool (KB-P4-11, S11.4)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
import yaml

from mcp.app import create_mcp_app
from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.settings import McpSettings
from mcp.surfaces.admin import build_admin_registry
from mcp.surfaces.admin.override_ticket_provenance import (
    override_ticket_provenance,
)


def _build_test_harness(
    mock_handler: Any,  # noqa: ANN401
    *,
    auth_enabled: bool = False,
    token_scopes: list[str] | None = None,
) -> tuple[httpx.AsyncClient, KanbanApiClient]:
    """Construct in-memory MCP admin test harness."""
    scopes = token_scopes or ["admin:read", "admin:write", "admin:destructive"]

    def _dispatch(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/internal/v1/mcp/introspect":
            return httpx.Response(
                200,
                json={
                    "active": True,
                    "principal_id": str(uuid.uuid4()),
                    "workspace_id": str(uuid.uuid4()),
                    "surface": "admin",
                    "scopes": scopes,
                },
            )
        if path == "/api/v1/auth/session":
            return httpx.Response(200, json={"csrf_token": "mock-csrf-token"})
        return mock_handler(request)  # type: ignore[no-any-return]

    mock_transport = httpx.MockTransport(_dispatch)
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=auth_enabled)
    kanban_client = KanbanApiClient(settings, transport=mock_transport)

    admin_reg = build_admin_registry(kanban_client)
    app = create_mcp_app(
        settings=settings,
        admin_registry=admin_reg,
        internal_client=kanban_client,
    )

    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )
    return client, kanban_client


async def _init_mcp_session(client: httpx.AsyncClient, token: str | None = None) -> str:
    """Initialize MCP protocol session on /mcp/admin."""
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = await client.post(
        "/mcp/admin",
        headers=headers,
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
    )
    assert resp.status_code == 200, resp.text
    session_id = resp.headers.get("mcp-session-id")
    assert session_id is not None
    return str(session_id)


async def _call_admin_tool(
    client: httpx.AsyncClient,
    session_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    token: str | None = None,
) -> dict[str, Any]:
    """Execute tools/call over MCP JSON-RPC protocol."""
    headers = {"mcp-session-id": session_id}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = await client.post(
        "/mcp/admin",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "result" in data, data
    res: dict[str, Any] = data["result"]
    return res


@pytest.mark.asyncio
async def test_tool_help() -> None:
    """Verify help action provides self-describing documentation."""
    help_out = await override_ticket_provenance({"action": "help"})
    assert help_out["tool"] == "override_ticket_provenance"
    assert "override_creator" in help_out["actions"]
    assert "override_hard_wip_move" in help_out["actions"]
    assert "unarchive_issue" in help_out["actions"]


@pytest.mark.asyncio
async def test_override_creator_positive() -> None:
    """Verify positive override_creator call flow and YAML formatting."""
    captured_requests: list[httpx.Request] = []

    def _handler(req: httpx.Request) -> httpx.Response:
        captured_requests.append(req)
        if req.method == "PATCH" and req.url.path == "/api/v1/issues/KAN-142/created-by":
            body = json.loads(req.content.decode("utf-8"))
            assert body["created_by"] == "@maya"
            assert body["reason"] == "Imported from Plane under bot account"
            return httpx.Response(
                200,
                json={
                    "issue_key": "KAN-142",
                    "original_created_by": "@bot-import",
                    "created_by": "@maya",
                    "reason": "Imported from Plane under bot account",
                },
            )
        return httpx.Response(404, json={"detail": "Not found"})

    _, client = _build_test_harness(_handler)

    res = await override_ticket_provenance(
        {
            "action": "override_creator",
            "issue": "KAN-142",
            "new_creator": "@maya",
            "reason": "Imported from Plane under bot account",
        },
        client=client,
    )
    assert res["status"] == "creator_overridden"
    assert res["issue"] == "KAN-142"
    assert res["original_created_by"] == "@bot-import"
    assert res["created_by"] == "@maya"
    assert res["reason"] == "Imported from Plane under bot account"


@pytest.mark.asyncio
async def test_override_hard_wip_move_positive() -> None:
    """Verify override_hard_wip_move resolving workflow state and bypassing WIP limit."""
    state_uuid = str(uuid.uuid4())

    def _handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.path == "/api/v1/issues/KAN-142":
            return httpx.Response(
                200,
                json={
                    "id": str(uuid.uuid4()),
                    "key": "KAN-142",
                    "project_id": "proj-uuid-1",
                },
            )
        if req.method == "GET" and req.url.path == "/api/v1/projects/proj-uuid-1/states":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": state_uuid, "name": "In Progress", "group": "started"},
                        {"id": str(uuid.uuid4()), "name": "Done", "group": "completed"},
                    ]
                },
            )
        if req.method == "POST" and req.url.path == "/api/v1/issues/KAN-142/move":
            body = json.loads(req.content.decode("utf-8"))
            assert body["target_state_id"] == state_uuid
            assert body["wip_override_reason"] == "Urgent production hotfix override"
            assert body["after_issue"] == "KAN-10"
            return httpx.Response(
                200,
                json={
                    "issue_key": "KAN-142",
                    "target_state_id": state_uuid,
                    "resulting_count": 6,
                    "hard_limit": 5,
                },
            )
        return httpx.Response(404, json={"detail": "Not found"})

    _, client = _build_test_harness(_handler)

    res = await override_ticket_provenance(
        {
            "action": "override_hard_wip_move",
            "issue": "KAN-142",
            "target_state": "In Progress",
            "after_issue": "KAN-10",
            "reason": "Urgent production hotfix override",
        },
        client=client,
    )
    assert res["status"] == "wip_overridden_moved"
    assert res["issue"] == "KAN-142"
    assert res["state"] == "In Progress"
    assert res["hard_limit"] == 5
    assert res["resulting_count"] == 6


@pytest.mark.asyncio
async def test_unarchive_issue_positive() -> None:
    """Verify positive unarchive_issue action flow."""

    def _handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST" and req.url.path == "/api/v1/issues/KAN-142/unarchive":
            body = json.loads(req.content.decode("utf-8"))
            assert body["reason"] == "Reopening ticket for verification"
            assert body["admin_override"] is True
            return httpx.Response(
                200,
                json={
                    "key": "KAN-142",
                    "status": "unarchived",
                },
            )
        return httpx.Response(404, json={"detail": "Not found"})

    _, client = _build_test_harness(_handler)

    res = await override_ticket_provenance(
        {
            "action": "unarchive_issue",
            "issue": "KAN-142",
            "reason": "Reopening ticket for verification",
        },
        client=client,
    )
    assert res["status"] == "issue_unarchived"
    assert res["issue"] == "KAN-142"
    assert res["reason"] == "Reopening ticket for verification"


@pytest.mark.asyncio
async def test_unarchive_issue_not_archived_conflict() -> None:
    """Verify 409 NOT_ARCHIVED mapped from upstream unarchive endpoint."""

    def _handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST" and req.url.path == "/api/v1/issues/KAN-142/unarchive":
            return httpx.Response(
                409,
                json={
                    "type": "https://errors.kanban.local/not-archived",
                    "title": "Not Archived",
                    "status": 409,
                    "code": "NOT_ARCHIVED",
                    "detail": "Issue is not archived",
                },
            )
        return httpx.Response(404, json={"detail": "Not found"})

    _, client = _build_test_harness(_handler)

    with pytest.raises(KbMcpError) as exc_info:
        await override_ticket_provenance(
            {
                "action": "unarchive_issue",
                "issue": "KAN-142",
                "reason": "Attempting unarchive on active ticket",
            },
            client=client,
        )
    assert exc_info.value.code == McpErrorCode.NOT_ARCHIVED


@pytest.mark.asyncio
async def test_security_gates_aal2_and_permissions() -> None:
    """Verify upstream AAL2_REQUIRED and INSUFFICIENT_PERMISSION error code mappings."""

    def _handler_aal2(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "type": "https://errors.kanban.local/aal2-required",
                "title": "AAL2 Required",
                "status": 403,
                "code": "AAL2_REQUIRED",
                "detail": "MFA AAL2 verification required",
            },
        )

    _, client_aal2 = _build_test_harness(_handler_aal2)

    with pytest.raises(KbMcpError) as exc_info:
        await override_ticket_provenance(
            {
                "action": "override_creator",
                "issue": "KAN-142",
                "new_creator": "@maya",
                "reason": "Administrative override under AAL1",
            },
            client=client_aal2,
        )
    assert exc_info.value.code == McpErrorCode.AAL2_REQUIRED

    def _handler_perm(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "type": "https://errors.kanban.local/insufficient-capability",
                "title": "Forbidden",
                "status": 403,
                "code": "INSUFFICIENT_PERMISSION",
                "detail": "Operation requires PROJECT_ADMIN or SERVER_ADMIN",
            },
        )

    _, client_perm = _build_test_harness(_handler_perm)

    with pytest.raises(KbMcpError) as exc_info2:
        await override_ticket_provenance(
            {
                "action": "override_creator",
                "issue": "KAN-142",
                "new_creator": "@maya",
                "reason": "Administrative override non-admin caller",
            },
            client=client_perm,
        )
    assert exc_info2.value.code == McpErrorCode.INSUFFICIENT_PERMISSION


@pytest.mark.asyncio
async def test_creator_override_errors() -> None:
    """Verify CREATOR_UNCHANGED and CREATOR_NOT_ELIGIBLE error mappings."""

    def _handler_unchanged(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "type": "https://errors.kanban.local/creator-unchanged",
                "title": "Conflict",
                "status": 409,
                "code": "CREATOR_UNCHANGED",
                "detail": "New creator matches current creator",
            },
        )

    _, client_unchanged = _build_test_harness(_handler_unchanged)
    with pytest.raises(KbMcpError) as exc_info:
        await override_ticket_provenance(
            {
                "action": "override_creator",
                "issue": "KAN-142",
                "new_creator": "@maya",
                "reason": "Same creator re-application",
            },
            client=client_unchanged,
        )
    assert exc_info.value.code == McpErrorCode.CREATOR_UNCHANGED

    def _handler_ineligible(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "type": "https://errors.kanban.local/creator-not-eligible",
                "title": "Unprocessable Entity",
                "status": 422,
                "code": "CREATOR_NOT_ELIGIBLE",
                "detail": "Principal is not eligible to own tickets",
            },
        )

    _, client_ineligible = _build_test_harness(_handler_ineligible)
    with pytest.raises(KbMcpError) as exc_info2:
        await override_ticket_provenance(
            {
                "action": "override_creator",
                "issue": "KAN-142",
                "new_creator": "@deactivated_user",
                "reason": "Assigning deactivated user",
            },
            client=client_ineligible,
        )
    assert exc_info2.value.code == McpErrorCode.CREATOR_NOT_ELIGIBLE


@pytest.mark.asyncio
async def test_input_validations() -> None:
    """Verify client-side schema and input parameter validations."""
    _, client = _build_test_harness(lambda _r: httpx.Response(200, json={}))

    # 1. Missing action
    with pytest.raises(KbMcpError) as exc:
        await override_ticket_provenance({}, client=client)
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # 2. Unknown action
    with pytest.raises(KbMcpError) as exc:
        await override_ticket_provenance({"action": "unknown_action"}, client=client)
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # 3. Missing issue
    with pytest.raises(KbMcpError) as exc:
        await override_ticket_provenance(
            {"action": "override_creator", "new_creator": "@maya", "reason": "Valid reason length"},
            client=client,
        )
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # 4. Missing reason
    with pytest.raises(KbMcpError) as exc:
        await override_ticket_provenance(
            {"action": "override_creator", "issue": "KAN-142", "new_creator": "@maya"},
            client=client,
        )
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # 5. Short reason (< 10 chars)
    with pytest.raises(KbMcpError) as exc:
        await override_ticket_provenance(
            {
                "action": "override_creator",
                "issue": "KAN-142",
                "new_creator": "@maya",
                "reason": "short",
            },
            client=client,
        )
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # 6. Missing new_creator on override_creator
    with pytest.raises(KbMcpError) as exc:
        await override_ticket_provenance(
            {
                "action": "override_creator",
                "issue": "KAN-142",
                "reason": "Valid reason length here",
            },
            client=client,
        )
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED

    # 7. Missing target_state on override_hard_wip_move
    with pytest.raises(KbMcpError) as exc:
        await override_ticket_provenance(
            {
                "action": "override_hard_wip_move",
                "issue": "KAN-142",
                "reason": "Valid reason length here",
            },
            client=client,
        )
    assert exc.value.code == McpErrorCode.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_mcp_protocol_http_and_transcript_integration() -> None:
    """Verify execution through JSON-RPC HTTP transport, registering with transcript recorder."""
    state_uuid = str(uuid.uuid4())

    def _handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if req.method == "PATCH" and path == "/api/v1/issues/KAN-142/created-by":
            return httpx.Response(
                200,
                json={
                    "issue_key": "KAN-142",
                    "original_created_by": "@bot-import",
                    "created_by": "@maya",
                    "reason": "Imported from Plane under bot account",
                },
            )
        if req.method == "GET" and path == "/api/v1/issues/KAN-142":
            return httpx.Response(
                200,
                json={"id": str(uuid.uuid4()), "key": "KAN-142", "project_id": "proj-uuid-1"},
            )
        if req.method == "GET" and path == "/api/v1/projects/proj-uuid-1/states":
            return httpx.Response(
                200,
                json={"items": [{"id": state_uuid, "name": "In Progress"}]},
            )
        if req.method == "POST" and path == "/api/v1/issues/KAN-142/move":
            return httpx.Response(
                200,
                json={
                    "issue_key": "KAN-142",
                    "target_state_id": state_uuid,
                    "resulting_count": 6,
                    "hard_limit": 5,
                },
            )
        if req.method == "POST" and path == "/api/v1/issues/KAN-142/unarchive":
            return httpx.Response(
                200,
                json={"key": "KAN-142", "status": "unarchived"},
            )
        return httpx.Response(404, json={"detail": "Not found"})

    admin_token = "kb_adm_" + "t" * 43
    mcp_http_client, _ = _build_test_harness(_handler, auth_enabled=True)

    async with mcp_http_client:
        # 1. Surface key mismatch on /mcp/admin using kb_agt_ key -> 403
        bad_agent_token = "kb_agt_" + "x" * 43
        res_mismatch = await mcp_http_client.post(
            "/mcp/admin",
            headers={"Authorization": f"Bearer {bad_agent_token}"},
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
        )
        assert res_mismatch.status_code == 403
        assert res_mismatch.json() == {"error": "SURFACE_KEY_MISMATCH"}

        # 2. Valid initialize session with kb_adm_ key
        sess_id = await _init_mcp_session(mcp_http_client, token=admin_token)

        # 3. Action 1: override_creator
        res_oc = await _call_admin_tool(
            mcp_http_client,
            sess_id,
            "override_ticket_provenance",
            {
                "action": "override_creator",
                "issue": "KAN-142",
                "new_creator": "@maya",
                "reason": "Imported from Plane under bot account",
            },
            token=admin_token,
        )
        assert res_oc["isError"] is False
        parsed_yaml_oc = yaml.safe_load(res_oc["content"][0]["text"])
        assert parsed_yaml_oc["status"] == "creator_overridden"
        assert parsed_yaml_oc["created_by"] == "@maya"

        # 4. Action 2: override_hard_wip_move
        res_wip = await _call_admin_tool(
            mcp_http_client,
            sess_id,
            "override_ticket_provenance",
            {
                "action": "override_hard_wip_move",
                "issue": "KAN-142",
                "target_state": "In Progress",
                "reason": "Emergency security vulnerability fix",
            },
            token=admin_token,
        )
        assert res_wip["isError"] is False
        parsed_yaml_wip = yaml.safe_load(res_wip["content"][0]["text"])
        assert parsed_yaml_wip["status"] == "wip_overridden_moved"
        assert parsed_yaml_wip["hard_limit"] == 5
        assert parsed_yaml_wip["resulting_count"] == 6

        # 5. Action 3: unarchive_issue
        res_un = await _call_admin_tool(
            mcp_http_client,
            sess_id,
            "override_ticket_provenance",
            {
                "action": "unarchive_issue",
                "issue": "KAN-142",
                "reason": "Re-auditing completed deliverable",
            },
            token=admin_token,
        )
        assert res_un["isError"] is False
        parsed_yaml_un = yaml.safe_load(res_un["content"][0]["text"])
        assert parsed_yaml_un["status"] == "issue_unarchived"


@pytest.mark.asyncio
async def test_override_ticket_provenance_edge_cases_and_branches() -> None:  # noqa: C901, PLR0915
    """Exercise remaining edge cases and branches to guarantee >=95% branch coverage."""
    # 1. Missing active client
    with pytest.raises(KbMcpError) as exc:
        await override_ticket_provenance(
            {
                "action": "override_creator",
                "issue": "KAN-1",
                "new_creator": "@maya",
                "reason": "Reason 1234567890",
            },
            client=None,
        )
    assert exc.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    # 2. override_creator malformed response
    _, client_malformed = _build_test_harness(lambda _req: httpx.Response(200, json=["not a dict"]))
    with pytest.raises(KbMcpError) as exc2:
        await override_ticket_provenance(
            {
                "action": "override_creator",
                "issue": "KAN-1",
                "new_creator": "@maya",
                "reason": "Reason 1234567890",
            },
            client=client_malformed,
        )
    assert exc2.value.code == McpErrorCode.UPSTREAM_ERROR

    # 3. Provenance formatting with dict and '1 External Collaborator'
    def _prov_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "key": "KAN-100",
                "provenance": {
                    "original_created_by": {"label": "1 External Collaborator"},
                    "created_by": {"label": "1 External Collaborator"},
                },
            },
        )

    _, client_ext = _build_test_harness(_prov_handler)
    res_ext = await override_ticket_provenance(
        {
            "action": "override_creator",
            "issue": "KAN-100",
            "new_creator": "1 External Collaborator",
            "reason": "External partner provenance test",
        },
        client=client_ext,
    )
    assert res_ext["original_created_by"] == "1 External Collaborator"
    assert res_ext["created_by"] == "1 External Collaborator"

    # 4. override_hard_wip_move: malformed issue response
    _, client_bad_issue = _build_test_harness(lambda _req: httpx.Response(200, json=[]))
    with pytest.raises(KbMcpError) as exc3:
        await override_ticket_provenance(
            {
                "action": "override_hard_wip_move",
                "issue": "KAN-1",
                "target_state": "Todo",
                "reason": "Reason 1234567890",
            },
            client=client_bad_issue,
        )
    assert exc3.value.code == McpErrorCode.UPSTREAM_ERROR

    # 5. override_hard_wip_move: missing project_id
    _, client_no_proj = _build_test_harness(
        lambda _req: httpx.Response(200, json={"id": str(uuid.uuid4()), "key": "KAN-1"})
    )
    with pytest.raises(KbMcpError) as exc4:
        await override_ticket_provenance(
            {
                "action": "override_hard_wip_move",
                "issue": "KAN-1",
                "target_state": "Todo",
                "reason": "Reason 1234567890",
            },
            client=client_no_proj,
        )
    assert exc4.value.code == McpErrorCode.UPSTREAM_ERROR

    # 6. override_hard_wip_move: malformed states response
    def _bad_states_handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v1/issues/KAN-1":
            return httpx.Response(200, json={"key": "KAN-1", "project_id": "p1"})
        return httpx.Response(200, json="invalid states format")

    _, client_bad_states = _build_test_harness(_bad_states_handler)
    with pytest.raises(KbMcpError) as exc5:
        await override_ticket_provenance(
            {
                "action": "override_hard_wip_move",
                "issue": "KAN-1",
                "target_state": "Todo",
                "reason": "Reason 1234567890",
            },
            client=client_bad_states,
        )
    assert exc5.value.code == McpErrorCode.UPSTREAM_ERROR

    # 7. override_hard_wip_move: state not found in project
    def _missing_state_handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v1/issues/KAN-1":
            return httpx.Response(200, json={"key": "KAN-1", "project_id": "p1"})
        return httpx.Response(200, json=[{"id": "s1", "name": "Done"}])

    _, client_missing_state = _build_test_harness(_missing_state_handler)
    with pytest.raises(KbMcpError) as exc6:
        await override_ticket_provenance(
            {
                "action": "override_hard_wip_move",
                "issue": "KAN-1",
                "target_state": "In Review",
                "reason": "Reason 1234567890",
            },
            client=client_missing_state,
        )
    assert exc6.value.code == McpErrorCode.NOT_FOUND

    # 8. override_hard_wip_move: before_issue, wip_warning resulting_count, and malformed move
    def _move_variations_handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/v1/issues/KAN-1":
            return httpx.Response(200, json={"key": "KAN-1", "project_id": "p1"})
        if path == "/api/v1/projects/p1/states":
            return httpx.Response(
                200,
                json=["non-dict-item", {"id": "s1", "name": "In Progress", "wip_hard_limit": 3}],
            )
        if path == "/api/v1/issues/KAN-1/move":
            body = json.loads(req.content.decode("utf-8"))
            assert body["before_issue"] == "KAN-5"
            return httpx.Response(
                200,
                json={"wip_warning": {"resulting_count": 4}},
            )
        return httpx.Response(404)

    _, client_move_vars = _build_test_harness(_move_variations_handler)
    res_vars = await override_ticket_provenance(
        {
            "action": "override_hard_wip_move",
            "issue": "KAN-1",
            "target_state": "s1",
            "before_issue": "KAN-5",
            "reason": "Reason 1234567890",
        },
        client=client_move_vars,
    )
    assert res_vars["status"] == "wip_overridden_moved"
    assert res_vars["resulting_count"] == 4
    assert res_vars["hard_limit"] == 3

    # 8b. override_hard_wip_move: malformed move_resp & fallback resulting_count
    def _move_fallback_handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/v1/issues/KAN-1":
            return httpx.Response(200, json={"key": "KAN-1", "project_id": "p1"})
        if path == "/api/v1/projects/p1/states":
            return httpx.Response(
                200,
                json=[{"id": "s1", "name": "In Progress", "wip_hard_limit": 5}],
            )
        if path == "/api/v1/issues/KAN-1/move":
            return httpx.Response(200, json={"status": "moved"})
        return httpx.Response(404)

    _, client_move_fallback = _build_test_harness(_move_fallback_handler)
    res_fb = await override_ticket_provenance(
        {
            "action": "override_hard_wip_move",
            "issue": "KAN-1",
            "target_state": "s1",
            "reason": "Reason 1234567890",
        },
        client=client_move_fallback,
    )
    assert res_fb["resulting_count"] == 6

    # 8c. override_hard_wip_move: non-dict move_resp
    def _move_non_dict_handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/v1/issues/KAN-1":
            return httpx.Response(200, json={"key": "KAN-1", "project_id": "p1"})
        if path == "/api/v1/projects/p1/states":
            return httpx.Response(
                200,
                json=[{"id": "s1", "name": "In Progress", "wip_hard_limit": 5}],
            )
        if path == "/api/v1/issues/KAN-1/move":
            return httpx.Response(200, json="bad move")
        return httpx.Response(404)

    _, client_move_non_dict = _build_test_harness(_move_non_dict_handler)
    with pytest.raises(KbMcpError) as exc_move_bad:
        await override_ticket_provenance(
            {
                "action": "override_hard_wip_move",
                "issue": "KAN-1",
                "target_state": "s1",
                "reason": "Reason 1234567890",
            },
            client=client_move_non_dict,
        )
    assert exc_move_bad.value.code == McpErrorCode.UPSTREAM_ERROR

    # 9. unarchive_issue malformed response
    _, client_bad_unarchive = _build_test_harness(
        lambda _req: httpx.Response(200, json="not a dict")
    )
    with pytest.raises(KbMcpError) as exc7:
        await override_ticket_provenance(
            {
                "action": "unarchive_issue",
                "issue": "KAN-1",
                "reason": "Reason 1234567890",
            },
            client=client_bad_unarchive,
        )
    assert exc7.value.code == McpErrorCode.UPSTREAM_ERROR
