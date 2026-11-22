# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and integration tests for MCP capability_mask and CIDR validation.

Validates KB-SEC-05 Actions 2 and 3:
1. Tool dispatch rejection when caller's CredentialBoundary.capability_mask masks out
   required capabilities (EDIT, TRANSITION, DELETE, COMMENT, LINK).
2. tools/list filtering when capability_mask is narrowed to read-only.
3. Spoof-resistant trusted proxy client IP validation for allowed_cidrs (rejecting
   spoofed X-Forwarded-For from untrusted peers, accepting traversed IP from trusted peers).
"""

from __future__ import annotations

import base64
import os
import uuid
from typing import Any

import httpx
import pytest

from mcp.app import create_mcp_app
from mcp.auth import McpAuthContext, McpAuthMiddleware
from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.protocol import InMemorySessionStore, McpProtocolHandler
from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.scoping import (
    Capability,
    CredentialBoundary,
    enforce_credential_boundary_on_tool_call,
    get_required_tool_capability,
)
from mcp.settings import McpSettings

_DUMMY_SCHEMA: dict[str, Any] = {"type": "object"}


def _generate_test_key(surface: Surface) -> str:
    prefix = {"agent": "kb_agt_", "docs": "kb_doc_", "admin": "kb_adm_"}[surface.value]
    rand = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
    return f"{prefix}{rand}"


def test_get_required_tool_capability_mapping() -> None:
    """Verify tool names correctly map to required Capability bit flags."""
    assert get_required_tool_capability("search_tickets") == Capability.VIEW
    assert get_required_tool_capability("read_ticket") == Capability.VIEW
    assert get_required_tool_capability("search") == Capability.VIEW
    assert get_required_tool_capability("read_doc") == Capability.VIEW

    assert get_required_tool_capability("create_ticket") == Capability.EDIT
    assert get_required_tool_capability("update_ticket") == Capability.EDIT
    assert get_required_tool_capability("create") == Capability.EDIT
    assert get_required_tool_capability("update") == Capability.EDIT

    assert get_required_tool_capability("begin_work") == Capability.TRANSITION
    assert get_required_tool_capability("transition_ticket") == Capability.TRANSITION
    assert get_required_tool_capability("complete_work") == Capability.TRANSITION

    assert get_required_tool_capability("destructive_lifecycle") == Capability.DELETE

    assert get_required_tool_capability("add_comment") == Capability.COMMENT
    assert get_required_tool_capability("link_objects") == Capability.LINK

    # Admin actions mapping
    assert get_required_tool_capability("admin", "delete_principal") == Capability.DELETE
    assert get_required_tool_capability("admin", "rebuild_era") == Capability.ADMIN
    assert get_required_tool_capability("admin", "configure_workspace") == Capability.ADMIN


def test_enforce_credential_boundary_capability_mask_violations() -> None:
    """Verify tool call capability enforcement rejects masked capabilities."""
    # 1. Caller with VIEW only (1) attempting create_ticket (EDIT = 4)
    boundary_view_only = CredentialBoundary(
        scope_tier="workspace",
        surface="agent",
        capability_mask=int(Capability.VIEW),
    )

    with pytest.raises(KbMcpError) as exc_view:
        enforce_credential_boundary_on_tool_call(
            "create_ticket",
            {"summary": "Test"},
            boundary_view_only,
        )
    err = exc_view.value
    assert err.code == McpErrorCode.INSUFFICIENT_SCOPE
    assert "requires capability EDIT (4)" in err.message
    assert err.extra is not None
    assert err.extra.get("required_capability") == "EDIT"
    assert err.extra.get("required_bit") == 4
    assert err.extra.get("capability_mask") == 1

    # 2. Caller with VIEW | EDIT (5) attempting transition_ticket (TRANSITION = 8)
    boundary_view_edit = CredentialBoundary(
        scope_tier="workspace",
        surface="agent",
        capability_mask=int(Capability.VIEW | Capability.EDIT),
    )
    with pytest.raises(KbMcpError) as exc_trans:
        enforce_credential_boundary_on_tool_call(
            "transition_ticket",
            {"identifier": "KAN-1", "state": "In Progress"},
            boundary_view_edit,
        )
    assert exc_trans.value.code == McpErrorCode.INSUFFICIENT_SCOPE
    assert exc_trans.value.extra is not None
    assert exc_trans.value.extra.get("required_capability") == "TRANSITION"

    # 3. Caller attempting add_comment (COMMENT = 16) without COMMENT capability
    with pytest.raises(KbMcpError) as exc_comment:
        enforce_credential_boundary_on_tool_call(
            "add_comment",
            {"identifier": "KAN-1", "comment": "Note"},
            boundary_view_edit,
        )
    assert exc_comment.value.code == McpErrorCode.INSUFFICIENT_SCOPE
    assert exc_comment.value.extra is not None
    assert exc_comment.value.extra.get("required_capability") == "COMMENT"

    # 4. Caller attempting link_objects (LINK = 32) without LINK capability
    with pytest.raises(KbMcpError) as exc_link:
        enforce_credential_boundary_on_tool_call(
            "link_objects",
            {"source": "KAN-1", "target": "KAN-2"},
            boundary_view_edit,
        )
    assert exc_link.value.code == McpErrorCode.INSUFFICIENT_SCOPE
    assert exc_link.value.extra is not None
    assert exc_link.value.extra.get("required_capability") == "LINK"

    # 5. Caller attempting destructive_lifecycle (DELETE = 128) without DELETE capability
    boundary_admin_no_delete = CredentialBoundary(
        scope_tier="workspace",
        surface="admin",
        capability_mask=int(Capability.ALL & ~Capability.DELETE),
    )
    with pytest.raises(KbMcpError) as exc_del:
        enforce_credential_boundary_on_tool_call(
            "destructive_lifecycle",
            {"target": "doc", "id": str(uuid.uuid4())},
            boundary_admin_no_delete,
        )
    assert exc_del.value.code == McpErrorCode.INSUFFICIENT_SCOPE
    assert exc_del.value.extra is not None
    assert exc_del.value.extra.get("required_capability") == "DELETE"

    # 6. Caller with proper capabilities succeeds without exception
    boundary_full = CredentialBoundary(
        scope_tier="workspace",
        surface="agent",
        capability_mask=int(Capability.ALL),
    )
    enforce_credential_boundary_on_tool_call("create_ticket", {"summary": "Ok"}, boundary_full)
    enforce_credential_boundary_on_tool_call(
        "transition_ticket", {"identifier": "KAN-1"}, boundary_full
    )
    enforce_credential_boundary_on_tool_call("add_comment", {"identifier": "KAN-1"}, boundary_full)


def test_enforce_credential_boundary_workspace_and_project_allowlists() -> None:
    """Verify workspace and project allowlists are enforced at tool dispatch."""
    ws_allowed = uuid.uuid4()
    ws_denied = uuid.uuid4()
    proj_allowed = uuid.uuid4()
    proj_denied = uuid.uuid4()

    boundary = CredentialBoundary(
        scope_tier="workspace",
        surface="agent",
        workspace_allowlist=frozenset({ws_allowed}),
        project_allowlist=frozenset({proj_allowed}),
        capability_mask=255,
    )

    # 1. Allowed workspace argument succeeds
    enforce_credential_boundary_on_tool_call(
        "search_tickets", {"workspace": str(ws_allowed)}, boundary
    )

    # 2. Denied workspace argument rejected
    with pytest.raises(KbMcpError) as exc_ws:
        enforce_credential_boundary_on_tool_call(
            "search_tickets", {"workspace": str(ws_denied)}, boundary
        )
    assert exc_ws.value.code == McpErrorCode.KEY_SCOPE_VIOLATION
    assert str(ws_denied) in exc_ws.value.message

    # 3. Allowed project argument succeeds
    enforce_credential_boundary_on_tool_call(
        "search_tickets", {"project": str(proj_allowed)}, boundary
    )

    # 4. Denied project argument rejected
    with pytest.raises(KbMcpError) as exc_proj:
        enforce_credential_boundary_on_tool_call(
            "search_tickets", {"project": str(proj_denied)}, boundary
        )
    assert exc_proj.value.code == McpErrorCode.KEY_SCOPE_VIOLATION
    assert str(proj_denied) in exc_proj.value.message

    # 5. Non-ephemeral allowed_tools narrowing
    boundary_narrowed = CredentialBoundary(
        scope_tier="workspace",
        surface="agent",
        allowed_tools=frozenset({"search_tickets", "read_ticket"}),
    )
    with pytest.raises(KbMcpError) as exc_narrowed:
        enforce_credential_boundary_on_tool_call(
            "create_ticket", {"summary": "Denied"}, boundary_narrowed
        )
    assert exc_narrowed.value.code == McpErrorCode.INSUFFICIENT_SCOPE
    assert "Tool narrowing is active" in str(exc_narrowed.value.hint)

    # 6. CredentialBoundary method coverage
    assert boundary.allows_workspace(None) is True
    assert boundary.allows_project(None) is True
    boundary_global = CredentialBoundary(scope_tier="global")
    assert boundary_global.allows_workspace(uuid.uuid4()) is True
    assert boundary_global.allows_project(uuid.uuid4()) is True

    boundary_cidr = CredentialBoundary(allowed_cidrs=("10.0.0.0/8",))
    assert boundary_cidr.allows_ip("10.1.2.3") is True
    assert boundary_cidr.allows_ip("192.168.1.1") is False
    assert boundary_cidr.allows_ip("invalid-ip") is False
    assert boundary_cidr.allows_ip(None) is True


@pytest.mark.asyncio
async def test_mcp_protocol_tools_call_capability_mask_rejection() -> None:
    """Verify McpProtocolHandler rejects tool call in JSON-RPC when capability is masked out."""
    reg = ToolRegistry(Surface.AGENT)

    async def _dummy_create(_args: dict[str, Any]) -> dict[str, str]:
        return {"status": "created"}

    reg.register(
        ToolSpec(
            name="create_ticket",
            description="Create ticket",
            surface=Surface.AGENT,
            input_schema=_DUMMY_SCHEMA,
            handler=_dummy_create,
        )
    )

    store = InMemorySessionStore()
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    handler = McpProtocolHandler(Surface.AGENT, reg, store, settings)

    # Caller with VIEW only (capability_mask = 1)
    boundary = CredentialBoundary(
        scope_tier="workspace",
        surface="agent",
        capability_mask=int(Capability.VIEW),
    )
    auth_ctx = McpAuthContext(
        token="kb_agt_testtoken",  # noqa: S106
        token_sha256=b"fake-digest",
        principal_id="user-1",
        surface=Surface.AGENT,
        scopes=frozenset(["agent:read", "agent:write"]),
        capability_mask=int(Capability.VIEW),
        credential_boundary=boundary,
    )

    resp = await handler._handle_tools_call(  # noqa: SLF001
        101,
        {"name": "create_ticket", "arguments": {"summary": "Test Summary"}},
        auth_context=auth_ctx,
    )
    assert resp.status_code == 200
    assert isinstance(resp.body, bytes)
    data = resp.body.decode("utf-8")
    assert "isError" in data
    assert "EDIT" in data
    assert "INSUFFICIENT_SCOPE" in data


@pytest.mark.asyncio
async def test_mcp_protocol_tools_list_capability_mask_filtering() -> None:
    """Verify protocol handler filters mutating tools out of tools/list for read-only tokens."""
    reg = ToolRegistry(Surface.AGENT)

    async def _dummy_read(_args: dict[str, Any]) -> dict[str, str]:
        return {"status": "ok"}

    async def _dummy_write(_args: dict[str, Any]) -> dict[str, str]:
        return {"status": "ok"}

    reg.register(
        ToolSpec(
            name="read_ticket",
            description="Read ticket",
            surface=Surface.AGENT,
            input_schema=_DUMMY_SCHEMA,
            handler=_dummy_read,
        )
    )
    reg.register(
        ToolSpec(
            name="create_ticket",
            description="Create ticket",
            surface=Surface.AGENT,
            input_schema=_DUMMY_SCHEMA,
            handler=_dummy_write,
        )
    )

    store = InMemorySessionStore()
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    handler = McpProtocolHandler(Surface.AGENT, reg, store, settings)

    # 1. Read-only caller (VIEW = 1) sees only read_ticket
    boundary_ro = CredentialBoundary(
        scope_tier="workspace",
        surface="agent",
        capability_mask=int(Capability.VIEW),
    )
    auth_ro = McpAuthContext(
        token="kb_agt_ro",  # noqa: S106
        token_sha256=b"ro-digest",
        principal_id="user-1",
        surface=Surface.AGENT,
        scopes=frozenset(["agent:read"]),
        capability_mask=int(Capability.VIEW),
        credential_boundary=boundary_ro,
    )

    resp_ro = handler._handle_tools_list(1, auth_context=auth_ro)  # noqa: SLF001
    assert isinstance(resp_ro.body, bytes)
    data_ro = resp_ro.body.decode("utf-8")
    assert "read_ticket" in data_ro
    assert "create_ticket" not in data_ro

    # 2. Read-write caller (VIEW | EDIT = 5) sees both tools
    boundary_rw = CredentialBoundary(
        scope_tier="workspace",
        surface="agent",
        capability_mask=int(Capability.VIEW | Capability.EDIT),
    )
    auth_rw = McpAuthContext(
        token="kb_agt_rw",  # noqa: S106
        token_sha256=b"rw-digest",
        principal_id="user-1",
        surface=Surface.AGENT,
        scopes=frozenset(["agent:read", "agent:write"]),
        capability_mask=int(Capability.VIEW | Capability.EDIT),
        credential_boundary=boundary_rw,
    )

    resp_rw = handler._handle_tools_list(2, auth_context=auth_rw)  # noqa: SLF001
    assert isinstance(resp_rw.body, bytes)
    data_rw = resp_rw.body.decode("utf-8")
    assert "read_ticket" in data_rw
    assert "create_ticket" in data_rw


@pytest.mark.asyncio
async def test_trusted_proxy_client_ip_cidr_validation() -> None:
    """Verify spoofed X-Forwarded-For is rejected unless peer is a trusted proxy."""
    token = _generate_test_key(Surface.AGENT)

    def mock_introspect(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "active": True,
                "principal_id": "018f-0000",
                "workspace_id": "018f-0001",
                "surface": "agent",
                "scopes": ["agent:read", "agent:write"],
                "scope_tier": "personal_user",
                "allowed_cidrs": ["192.168.1.0/24"],
            },
        )

    mock_transport = httpx.MockTransport(mock_introspect)

    reg = ToolRegistry(Surface.AGENT)

    async def _write_handler(_args: dict[str, Any]) -> dict[str, str]:
        return {"status": "created"}

    reg.register(
        ToolSpec(
            name="test_agent_write",
            description="Test tool",
            surface=Surface.AGENT,
            input_schema=_DUMMY_SCHEMA,
            handler=_write_handler,
        )
    )

    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    kanban_client = KanbanApiClient(settings, transport=mock_transport)

    base_app = create_mcp_app(
        settings,
        agent_registry=reg,
        kanban_app=None,
    )
    app = McpAuthMiddleware(
        base_app,
        surface=Surface.AGENT,
        internal_client=kanban_client,
        settings=settings,
    )

    # 1. Direct request from untrusted peer attempting to spoof X-Forwarded-For
    transport_untrusted = httpx.ASGITransport(
        app=app,
        client=("203.0.113.9", 54321),  # Untrusted external client
    )
    async with httpx.AsyncClient(
        transport=transport_untrusted, base_url="http://test"
    ) as client_untrusted:
        spoofed_resp = await client_untrusted.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Forwarded-For": "192.168.1.50",
            },
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
        # MUST BE REJECTED (403) because 203.0.113.9 is not in trusted_proxies, so XFF is ignored!
        assert spoofed_resp.status_code == 403
        data = spoofed_resp.json()
        assert data["error"] == "KEY_CIDR_DENIED"
        assert "203.0.113.9" in data["message"]

    # 2. Request through trusted proxy (127.0.0.1) with valid upstream IP in allowed CIDR
    transport_trusted = httpx.ASGITransport(
        app=app,
        client=("127.0.0.1", 54321),  # Local trusted proxy
    )
    async with httpx.AsyncClient(
        transport=transport_trusted, base_url="http://test"
    ) as client_trusted:
        valid_resp = await client_trusted.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Forwarded-For": "192.168.1.50",
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert valid_resp.status_code == 200

        # 3. Request through trusted proxy with upstream IP outside allowed CIDR
        invalid_resp = await client_trusted.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Forwarded-For": "10.0.0.99",
            },
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        assert invalid_resp.status_code == 403
        assert invalid_resp.json()["error"] == "KEY_CIDR_DENIED"
