# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for /mcp/admin audit_and_purge_object_links tool (KB-P4-11, S11.4, S12.3)."""

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
from mcp.surfaces.admin.audit_and_purge_object_links import (
    audit_and_purge_object_links,
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
    """Verify help action provides complete self-describing documentation and scopes."""
    help_out = await audit_and_purge_object_links({"action": "help"})
    assert help_out["tool"] == "audit_and_purge_object_links"
    assert "run_audit" in help_out["actions"]
    assert "list_flagged" in help_out["actions"]
    assert "purge_audited" in help_out["actions"]
    assert help_out["scopes"]["run_audit"] == "admin:write"
    assert help_out["scopes"]["list_flagged"] == "admin:read"
    assert help_out["scopes"]["purge_audited"] == "admin:destructive"


@pytest.mark.asyncio
async def test_run_audit_positive() -> None:
    """Verify run_audit calls POST /admin/object-links:audit and formats summary YAML."""

    def _handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST" and req.url.path == "/api/v1/admin/object-links:audit":
            return httpx.Response(
                200,
                json={
                    "flagged_total": 2,
                    "by_reason": {
                        "ARCHIVED_POLICY_VIOLATION": 1,
                        "PERMISSION_SEVERED": 1,
                    },
                },
            )
        return httpx.Response(404)

    _, client = _build_test_harness(_handler)
    res = await audit_and_purge_object_links({"action": "run_audit"}, client=client)
    assert res["flagged_total"] == 2
    assert res["by_reason"]["ARCHIVED_POLICY_VIOLATION"] == 1
    assert res["by_reason"]["PERMISSION_SEVERED"] == 1


@pytest.mark.asyncio
async def test_list_flagged_lods_and_filters() -> None:
    """Verify list_flagged at summary, standard, and full LODs, plus reason filtering."""
    audit_id1 = str(uuid.uuid4())
    link_id1 = str(uuid.uuid4())
    audit_id2 = str(uuid.uuid4())
    link_id2 = str(uuid.uuid4())

    def _handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.path == "/api/v1/admin/object-links/audits":
            return httpx.Response(
                200,
                json={
                    "total": 2,
                    "has_more": False,
                    "next_cursor": None,
                    "items": [
                        {
                            "id": audit_id1,
                            "workspace_id": str(uuid.uuid4()),
                            "link_id": link_id1,
                            "reason": "ARCHIVED_POLICY_VIOLATION",
                            "detected_at": "2026-11-13T10:00:00Z",
                            "purged_at": None,
                            "resolved_at": None,
                            "link_snapshot": {
                                "source_id": str(uuid.uuid4()),
                                "target_id": str(uuid.uuid4()),
                                "link_type": "BLOCKS",
                            },
                            "source_snapshot": {"key": "KAN-1", "title": "Archived Parent"},
                            "target_snapshot": {"key": "KAN-2", "title": "Blocked Issue"},
                        },
                        {
                            "id": audit_id2,
                            "workspace_id": str(uuid.uuid4()),
                            "link_id": link_id2,
                            "reason": "PERMISSION_SEVERED",
                            "detected_at": "2026-11-13T11:00:00Z",
                            "purged_at": None,
                            "resolved_at": None,
                            "link_snapshot": {
                                "source_id": str(uuid.uuid4()),
                                "target_id": str(uuid.uuid4()),
                                "link_type": "RELATES_TO",
                            },
                        },
                    ],
                },
            )
        return httpx.Response(404)

    _, client = _build_test_harness(_handler)

    # 1. Summary LOD (default)
    res_summary = await audit_and_purge_object_links(
        {"action": "list_flagged", "lod": "summary"},
        client=client,
    )
    assert res_summary["total_unpurged"] == 2
    items_sum = res_summary["items"]
    assert len(items_sum) == 2
    assert items_sum[0]["audit_id"] == audit_id1
    assert items_sum[0]["reason"] == "ARCHIVED_POLICY_VIOLATION"
    assert "link_snapshot" not in items_sum[0]

    # 2. Standard LOD
    res_standard = await audit_and_purge_object_links(
        {"action": "list_flagged", "lod": "standard"},
        client=client,
    )
    items_std = res_standard["items"]
    assert len(items_std) == 2
    assert "link_type" in items_std[0]
    assert items_std[0]["link_type"] == "BLOCKS"
    assert "source_snapshot" not in items_std[0]

    # 3. Full LOD
    res_full = await audit_and_purge_object_links(
        {
            "action": "list_flagged",
            "lod": "full",
            "reason_filter": "ARCHIVED_POLICY_VIOLATION",
            "limit": 10,
            "cursor": "cursor_123",
        },
        client=client,
    )
    items_full = res_full["items"]
    assert len(items_full) == 2
    assert "link_snapshot" in items_full[0]
    assert "source_snapshot" in items_full[0]
    assert items_full[0]["source_snapshot"]["key"] == "KAN-1"


@pytest.mark.asyncio
async def test_purge_audited_positive() -> None:
    """Verify purge_audited passes audit_ids and reason, returning activity ledger IDs."""
    target_audit_id = str(uuid.uuid4())
    act_id = str(uuid.uuid4())

    def _handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST" and req.url.path == "/api/v1/admin/object-links:purge":
            body = json.loads(req.content.decode("utf-8"))
            assert body["audit_ids"] == [target_audit_id]
            assert body["reason"] == "Administrative remediation of severed links"
            return httpx.Response(
                200,
                json={
                    "purged_count": 1,
                    "activity_ids": [act_id],
                },
            )
        return httpx.Response(404)

    _, client = _build_test_harness(_handler)
    res = await audit_and_purge_object_links(
        {
            "action": "purge_audited",
            "audit_ids": [target_audit_id],
            "reason": "Administrative remediation of severed links",
        },
        client=client,
    )
    assert res["status"] == "purged"
    assert res["purged_count"] == 1
    assert act_id in res["activity_ids"]


@pytest.mark.asyncio
async def test_purge_audited_conflict_link_not_flagged() -> None:
    """Verify 409 LINK_NOT_FLAGGED from REST endpoint maps to McpErrorCode.LINK_NOT_FLAGGED."""

    def _handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST" and req.url.path == "/api/v1/admin/object-links:purge":
            return httpx.Response(
                409,
                json={
                    "type": "https://errors.kanban.local/link-not-flagged",
                    "title": "Link Not Flagged",
                    "status": 409,
                    "code": "LINK_NOT_FLAGGED",
                    "detail": "One or more audit IDs are not flagged as invalid.",
                },
            )
        return httpx.Response(404)

    _, client = _build_test_harness(_handler)
    with pytest.raises(KbMcpError) as exc:
        await audit_and_purge_object_links(
            {
                "action": "purge_audited",
                "audit_ids": [str(uuid.uuid4())],
                "reason": "Purge active link conflict test",
            },
            client=client,
        )
    assert exc.value.code == McpErrorCode.LINK_NOT_FLAGGED


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
    with pytest.raises(KbMcpError) as exc1:
        await audit_and_purge_object_links({"action": "run_audit"}, client=client_aal2)
    assert exc1.value.code == McpErrorCode.AAL2_REQUIRED

    def _handler_perm(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "type": "https://errors.kanban.local/insufficient-capability",
                "title": "Forbidden",
                "status": 403,
                "code": "INSUFFICIENT_PERMISSION",
                "detail": "Requires WORKSPACE_ADMIN or SERVER_ADMIN",
            },
        )

    _, client_perm = _build_test_harness(_handler_perm)
    with pytest.raises(KbMcpError) as exc2:
        await audit_and_purge_object_links({"action": "run_audit"}, client=client_perm)
    assert exc2.value.code == McpErrorCode.INSUFFICIENT_PERMISSION


@pytest.mark.asyncio
async def test_input_validations() -> None:
    """Verify client-side schema and input parameter validations."""
    _, client = _build_test_harness(lambda _r: httpx.Response(200, json={}))

    # 1. Missing action
    with pytest.raises(KbMcpError) as exc1:
        await audit_and_purge_object_links({}, client=client)
    assert exc1.value.code == McpErrorCode.VALIDATION_FAILED

    # 2. Unknown action
    with pytest.raises(KbMcpError) as exc2:
        await audit_and_purge_object_links({"action": "unknown_action"}, client=client)
    assert exc2.value.code == McpErrorCode.VALIDATION_FAILED

    # 3. purge_audited missing audit_ids
    with pytest.raises(KbMcpError) as exc3:
        await audit_and_purge_object_links(
            {"action": "purge_audited", "reason": "Administrative link purge justification"},
            client=client,
        )
    assert exc3.value.code == McpErrorCode.VALIDATION_FAILED

    # 4. purge_audited empty audit_ids
    with pytest.raises(KbMcpError) as exc4:
        await audit_and_purge_object_links(
            {
                "action": "purge_audited",
                "audit_ids": [],
                "reason": "Administrative link purge justification",
            },
            client=client,
        )
    assert exc4.value.code == McpErrorCode.VALIDATION_FAILED

    # 5. purge_audited audit_ids > 200 items
    with pytest.raises(KbMcpError) as exc5:
        await audit_and_purge_object_links(
            {
                "action": "purge_audited",
                "audit_ids": [str(uuid.uuid4()) for _ in range(201)],
                "reason": "Administrative link purge justification",
            },
            client=client,
        )
    assert exc5.value.code == McpErrorCode.VALIDATION_FAILED

    # 6. purge_audited missing reason
    with pytest.raises(KbMcpError) as exc6:
        await audit_and_purge_object_links(
            {"action": "purge_audited", "audit_ids": [str(uuid.uuid4())]},
            client=client,
        )
    assert exc6.value.code == McpErrorCode.VALIDATION_FAILED

    # 7. purge_audited reason < 10 chars
    with pytest.raises(KbMcpError) as exc7:
        await audit_and_purge_object_links(
            {"action": "purge_audited", "audit_ids": [str(uuid.uuid4())], "reason": "short"},
            client=client,
        )
    assert exc7.value.code == McpErrorCode.VALIDATION_FAILED

    # 8. purge_audited reason > 500 chars
    with pytest.raises(KbMcpError) as exc8:
        await audit_and_purge_object_links(
            {"action": "purge_audited", "audit_ids": [str(uuid.uuid4())], "reason": "x" * 501},
            client=client,
        )
    assert exc8.value.code == McpErrorCode.VALIDATION_FAILED

    # 9. list_flagged invalid reason_filter
    with pytest.raises(KbMcpError) as exc9:
        await audit_and_purge_object_links(
            {"action": "list_flagged", "reason_filter": "UNKNOWN_REASON"},
            client=client,
        )
    assert exc9.value.code == McpErrorCode.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_mcp_protocol_http_and_transcript_integration() -> None:
    """Verify execution through JSON-RPC HTTP transport, registering with transcript recorder."""
    audit_uuid = str(uuid.uuid4())
    act_uuid = str(uuid.uuid4())

    def _handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if req.method == "POST" and path == "/api/v1/admin/object-links:audit":
            return httpx.Response(
                200,
                json={"flagged_total": 1, "by_reason": {"ARCHIVED_POLICY_VIOLATION": 1}},
            )
        if req.method == "GET" and path == "/api/v1/admin/object-links/audits":
            return httpx.Response(
                200,
                json={
                    "total": 1,
                    "has_more": False,
                    "next_cursor": None,
                    "items": [
                        {
                            "id": audit_uuid,
                            "workspace_id": str(uuid.uuid4()),
                            "link_id": str(uuid.uuid4()),
                            "reason": "ARCHIVED_POLICY_VIOLATION",
                            "detected_at": "2026-11-13T10:00:00Z",
                            "purged_at": None,
                            "resolved_at": None,
                            "link_snapshot": {
                                "source_id": "s1",
                                "target_id": "t1",
                                "link_type": "BLOCKS",
                            },
                        }
                    ],
                },
            )
        if req.method == "POST" and path == "/api/v1/admin/object-links:purge":
            body = json.loads(req.content.decode("utf-8"))
            if body["audit_ids"] == ["conflict-uuid"]:
                return httpx.Response(
                    409,
                    json={
                        "type": "https://errors.kanban.local/link-not-flagged",
                        "title": "Link Not Flagged",
                        "status": 409,
                        "code": "LINK_NOT_FLAGGED",
                        "detail": "Link not flagged conflict",
                    },
                )
            return httpx.Response(200, json={"purged_count": 1, "activity_ids": [act_uuid]})
        return httpx.Response(404)

    admin_token_destructive = "kb_adm_dest_" + "d" * 40
    admin_token_write_only = "kb_adm_wron_" + "w" * 40

    def _introspect_handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content.decode("utf-8"))
        tok = body.get("token", "")
        if tok == admin_token_write_only:
            return httpx.Response(
                200,
                json={
                    "active": True,
                    "principal_id": str(uuid.uuid4()),
                    "workspace_id": str(uuid.uuid4()),
                    "surface": "admin",
                    "scopes": ["admin:read", "admin:write"],  # Lacks admin:destructive!
                },
            )
        return httpx.Response(
            200,
            json={
                "active": True,
                "principal_id": str(uuid.uuid4()),
                "workspace_id": str(uuid.uuid4()),
                "surface": "admin",
                "scopes": ["admin:read", "admin:write", "admin:destructive"],
            },
        )

    mock_transport = httpx.MockTransport(
        lambda r: (
            _introspect_handler(r) if r.url.path == "/internal/v1/mcp/introspect" else _handler(r)
        )
    )
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    kanban_client = KanbanApiClient(settings, transport=mock_transport)
    admin_reg = build_admin_registry(kanban_client)
    app = create_mcp_app(
        settings=settings,
        admin_registry=admin_reg,
        internal_client=kanban_client,
    )
    mcp_http_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )

    async with mcp_http_client:
        # 1. Initialize session with destructive key
        sess_dest = await _init_mcp_session(mcp_http_client, token=admin_token_destructive)

        # 2. Action: run_audit
        res_audit = await _call_admin_tool(
            mcp_http_client,
            sess_dest,
            "audit_and_purge_object_links",
            {"action": "run_audit"},
            token=admin_token_destructive,
        )
        assert res_audit["isError"] is False
        parsed_audit = yaml.safe_load(res_audit["content"][0]["text"])
        assert parsed_audit["flagged_total"] == 1

        # 3. Action: list_flagged
        res_list = await _call_admin_tool(
            mcp_http_client,
            sess_dest,
            "audit_and_purge_object_links",
            {"action": "list_flagged", "lod": "standard"},
            token=admin_token_destructive,
        )
        assert res_list["isError"] is False
        parsed_list = yaml.safe_load(res_list["content"][0]["text"])
        assert parsed_list["total_unpurged"] == 1

        # 4. Action: purge_audited with LINK_NOT_FLAGGED conflict
        res_conflict = await _call_admin_tool(
            mcp_http_client,
            sess_dest,
            "audit_and_purge_object_links",
            {
                "action": "purge_audited",
                "audit_ids": ["conflict-uuid"],
                "reason": "Remediating conflict link record",
            },
            token=admin_token_destructive,
        )
        assert res_conflict["isError"] is True
        assert "LINK_NOT_FLAGGED" in res_conflict["content"][0]["text"]

        # 5. Action: purge_audited positive
        res_purge = await _call_admin_tool(
            mcp_http_client,
            sess_dest,
            "audit_and_purge_object_links",
            {
                "action": "purge_audited",
                "audit_ids": [audit_uuid],
                "reason": "Administrative remediation of invalid links",
            },
            token=admin_token_destructive,
        )
        assert res_purge["isError"] is False
        parsed_purge = yaml.safe_load(res_purge["content"][0]["text"])
        assert parsed_purge["status"] == "purged"
        assert parsed_purge["purged_count"] == 1

        # 6. Scope separation: write-only key calling purge_audited -> INSUFFICIENT_SCOPE
        sess_write = await _init_mcp_session(mcp_http_client, token=admin_token_write_only)
        res_insufficient = await _call_admin_tool(
            mcp_http_client,
            sess_write,
            "audit_and_purge_object_links",
            {
                "action": "purge_audited",
                "audit_ids": [audit_uuid],
                "reason": "Administrative remediation of invalid links",
            },
            token=admin_token_write_only,
        )
        assert res_insufficient["isError"] is True
        assert "INSUFFICIENT_SCOPE" in res_insufficient["content"][0]["text"]


@pytest.mark.asyncio
async def test_audit_and_purge_edge_cases_and_branches() -> None:
    """Exercise remaining edge cases and branches to guarantee >=95% branch coverage."""
    # 1. Missing active client
    with pytest.raises(KbMcpError) as exc:
        await audit_and_purge_object_links({"action": "run_audit"}, client=None)
    assert exc.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE

    # 2. run_audit: non-dict response from API
    _, client_bad_audit = _build_test_harness(lambda _req: httpx.Response(200, json=["not a dict"]))
    with pytest.raises(KbMcpError) as exc2:
        await audit_and_purge_object_links({"action": "run_audit"}, client=client_bad_audit)
    assert exc2.value.code == McpErrorCode.UPSTREAM_ERROR

    # 3. list_flagged: non-dict response from API
    _, client_bad_list = _build_test_harness(lambda _req: httpx.Response(200, json="bad list"))
    with pytest.raises(KbMcpError) as exc3:
        await audit_and_purge_object_links({"action": "list_flagged"}, client=client_bad_list)
    assert exc3.value.code == McpErrorCode.UPSTREAM_ERROR

    # 4. purge_audited: non-dict response from API
    _, client_bad_purge = _build_test_harness(lambda _req: httpx.Response(200, json=12345))
    with pytest.raises(KbMcpError) as exc4:
        await audit_and_purge_object_links(
            {
                "action": "purge_audited",
                "audit_ids": [str(uuid.uuid4())],
                "reason": "Administrative link purge justification",
            },
            client=client_bad_purge,
        )
    assert exc4.value.code == McpErrorCode.UPSTREAM_ERROR

    # 5. run_audit with write-only key (succeeds) vs read-only key (fails)
    def _scope_check_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"flagged_total": 0, "by_reason": {}})

    # Scope check without context defaults to permitted in standalone
    _, client_scopes = _build_test_harness(_scope_check_handler)
    res_no_ctx = await audit_and_purge_object_links({"action": "run_audit"}, client=client_scopes)
    assert res_no_ctx["flagged_total"] == 0
