"""Unit tests for KAN-18 coverage on auth and protocol edge cases."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from starlette.datastructures import Headers as StarletteHeaders

from mcp.app import create_mcp_app
from mcp.auth import McpAuthContext, McpAuthMiddleware
from mcp.internal_client import KanbanApiClient
from mcp.protocol import InMemorySessionStore, McpProtocolHandler
from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.scoping import ConnectionScope, ScopeMode
from mcp.settings import McpSettings

if TYPE_CHECKING:
    from starlette.types import Message, Scope


@pytest.mark.asyncio
async def test_auth_resolve_surface_and_origin() -> None:
    """Test _resolve_surface and KANBAN_PUBLIC_ORIGIN handling."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    base_app = create_mcp_app(settings)
    dynamic_mw = McpAuthMiddleware(base_app, surface=None, settings=settings)

    well_known_scope: Scope = {
        "type": "http",
        "path": "/.well-known/oauth-protected-resource",
    }
    assert dynamic_mw._resolve_surface(well_known_scope) is None  # noqa: SLF001

    old_origin = os.environ.get("KANBAN_PUBLIC_ORIGIN")
    try:
        os.environ["KANBAN_PUBLIC_ORIGIN"] = "https://public.kanban.test"
        resp_env = dynamic_mw._unauthorized_response(Surface.AGENT)  # noqa: SLF001
        auth_hdr = resp_env.headers["www-authenticate"]
        assert "https://public.kanban.test" in auth_hdr
    finally:
        if old_origin is not None:
            os.environ["KANBAN_PUBLIC_ORIGIN"] = old_origin
        else:
            os.environ.pop("KANBAN_PUBLIC_ORIGIN", None)


@pytest.mark.asyncio
async def test_auth_unauthorized_custom_headers_and_scope() -> None:
    """Test custom forwarded headers and connection scope in unauthorized response."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    base_app = create_mcp_app(settings)
    dynamic_mw = McpAuthMiddleware(base_app, surface=None, settings=settings)

    fwd_headers = StarletteHeaders(
        headers={"x-forwarded-host": "mcp.example.com", "x-forwarded-proto": "https"}
    )
    resp_fwd = dynamic_mw._unauthorized_response(  # noqa: SLF001
        Surface.DOCS, headers=fwd_headers
    )
    assert "https://mcp.example.com" in resp_fwd.headers["www-authenticate"]

    resp_none = dynamic_mw._unauthorized_response(Surface.ADMIN, headers=None)  # noqa: SLF001
    assert resp_none.status_code == 401

    conn_scope = ConnectionScope(ScopeMode.PROJECT, workspace_slug="kanban", project_key="KANBA")
    resp_scope = dynamic_mw._unauthorized_response(  # noqa: SLF001
        Surface.DOCS, req_scope=conn_scope
    )
    assert "/w/kanban/p/KANBA" in resp_scope.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_auth_cidr_checks_allowed_and_denied() -> None:
    """Test CIDR client IP matching and invalid IP formats."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    base_app = create_mcp_app(settings)

    async def mock_cidr_transport(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "active": True,
                "principal_id": "018f-0000",
                "workspace_id": "018f-0001",
                "surface": "agent",
                "scopes": ["agent:read"],
                "allowed_cidrs": ["10.0.0.0/8"],
            },
        )

    mw_cidr = McpAuthMiddleware(
        base_app,
        surface=Surface.AGENT,
        internal_client=KanbanApiClient(
            settings, transport=httpx.MockTransport(mock_cidr_transport)
        ),
        settings=settings,
    )

    async def mock_receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    sent_status: list[int] = []

    async def record_send(msg: Message) -> None:
        if msg.get("type") == "http.response.start":
            sent_status.append(int(msg["status"]))

    # 1. Allowed IP
    scope_allowed: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/agent",
        "headers": [(b"authorization", b"Bearer kb_agt_cidr_key_123456789012345")],
        "client": ("10.1.2.3", 54321),
    }
    await mw_cidr(scope_allowed, mock_receive, record_send)
    assert len(sent_status) > 0
    assert sent_status[0] in (200, 400, 404)

    # 2. Invalid IP format
    bad_status: list[int] = []

    async def record_bad_send(msg: Message) -> None:
        if msg.get("type") == "http.response.start":
            bad_status.append(int(msg["status"]))

    scope_bad: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/agent",
        "headers": [
            (b"authorization", b"Bearer kb_agt_cidr_key_123456789012345"),
            (b"x-forwarded-for", b"not-an-ip"),
        ],
    }
    await mw_cidr(scope_bad, mock_receive, record_bad_send)
    assert len(bad_status) > 0
    assert bad_status[0] == 403

    # 3. Denied IP
    denied_status: list[int] = []

    async def record_denied_send(msg: Message) -> None:
        if msg.get("type") == "http.response.start":
            denied_status.append(int(msg["status"]))

    scope_denied: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/agent",
        "headers": [
            (b"authorization", b"Bearer kb_agt_cidr_key_123456789012345"),
            (b"x-forwarded-for", b"192.168.1.100"),
        ],
    }
    await mw_cidr(scope_denied, mock_receive, record_denied_send)
    assert len(denied_status) > 0
    assert denied_status[0] == 403


@pytest.mark.asyncio
async def test_protocol_ephemeral_tool_mapping_and_errors() -> None:
    """Test protocol dispatch for ephemeral docs search and error handling."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    registry = ToolRegistry(Surface.DOCS)

    async def mock_search_handler(_args: dict[str, Any]) -> str:
        return "search results ok"

    registry.register(
        ToolSpec(
            name="search",
            surface=Surface.DOCS,
            description="Docs search tool",
            input_schema={"type": "object"},
            handler=mock_search_handler,
        )
    )

    auth_read_doc = McpAuthContext(
        token="kb_eph_read_doc_token",  # noqa: S106
        token_sha256=b"1",
        surface=Surface.DOCS,
        scopes=frozenset(),
        token_kind="ephemeral",  # noqa: S106
        allowed_tools=frozenset(["read_doc"]),
    )

    async def mock_introspect_ok(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"active": True, "token": "kb_eph_read_doc_token"})

    handler = McpProtocolHandler(
        surface=Surface.DOCS,
        registry=registry,
        session_store=InMemorySessionStore(),
        settings=settings,
        internal_client=KanbanApiClient(
            settings, transport=httpx.MockTransport(mock_introspect_ok)
        ),
    )

    # 1. Ephemeral read_doc tool mapping
    res = await handler._dispatch_method(  # noqa: SLF001
        "tools/call",
        req_id=1,
        params={"name": "search", "arguments": {}},
        auth_context=auth_read_doc,
    )
    assert res.status_code == 200

    # 2. Upstream unavailable
    async def mock_explode(_req: httpx.Request) -> httpx.Response:
        err_msg = "Network down"
        raise httpx.ConnectError(err_msg)

    handler_err = McpProtocolHandler(
        surface=Surface.DOCS,
        registry=registry,
        session_store=InMemorySessionStore(),
        settings=settings,
        internal_client=KanbanApiClient(settings, transport=httpx.MockTransport(mock_explode)),
    )
    res_err = await handler_err._dispatch_method(  # noqa: SLF001
        "tools/call",
        req_id=2,
        params={"name": "search", "arguments": {}},
        auth_context=auth_read_doc,
    )
    assert res_err.status_code == 200
    assert "UPSTREAM_UNAVAILABLE" in bytes(res_err.body).decode()

    # 3. Ephemeral token expired
    async def mock_expired(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"active": False, "reason": "TOKEN_EXPIRED_OR_REVOKED"})

    handler_exp = McpProtocolHandler(
        surface=Surface.DOCS,
        registry=registry,
        session_store=InMemorySessionStore(),
        settings=settings,
        internal_client=KanbanApiClient(settings, transport=httpx.MockTransport(mock_expired)),
    )
    res_exp = await handler_exp._dispatch_method(  # noqa: SLF001
        "tools/call",
        req_id=3,
        params={"name": "search", "arguments": {}},
        auth_context=auth_read_doc,
    )
    assert res_exp.status_code == 200
    assert "TOKEN_EXPIRED_OR_REVOKED" in bytes(res_exp.body).decode()

    # 4. Unknown reason -> UNAUTHENTICATED
    async def mock_unknown(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"active": False, "reason": "UNKNOWN_REASON"})

    handler_unk = McpProtocolHandler(
        surface=Surface.DOCS,
        registry=registry,
        session_store=InMemorySessionStore(),
        settings=settings,
        internal_client=KanbanApiClient(settings, transport=httpx.MockTransport(mock_unknown)),
    )
    res_unk = await handler_unk._dispatch_method(  # noqa: SLF001
        "tools/call",
        req_id=4,
        params={"name": "search", "arguments": {}},
        auth_context=auth_read_doc,
    )
    assert res_unk.status_code == 200
    assert "UNAUTHENTICATED" in bytes(res_unk.body).decode()

    # 5. Upstream EPHEMERAL_TOOL_FORBIDDEN
    async def mock_forbid(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"active": False, "reason": "EPHEMERAL_TOOL_FORBIDDEN"})

    handler_forbid = McpProtocolHandler(
        surface=Surface.DOCS,
        registry=registry,
        session_store=InMemorySessionStore(),
        settings=settings,
        internal_client=KanbanApiClient(settings, transport=httpx.MockTransport(mock_forbid)),
    )
    res_forbid = await handler_forbid._dispatch_method(  # noqa: SLF001
        "tools/call",
        req_id=5,
        params={"name": "search", "arguments": {}},
        auth_context=auth_read_doc,
    )
    assert res_forbid.status_code == 200
    assert "EPHEMERAL_TOOL_FORBIDDEN" in bytes(res_forbid.body).decode()
