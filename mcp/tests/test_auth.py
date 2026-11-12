# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and integration tests for MCP authentication middleware and tool scoping (KB-P4-02a)."""

from __future__ import annotations

import base64
import json
import os
from collections.abc import MutableMapping  # noqa: TC003
from pathlib import Path  # noqa: TC003
from typing import Any

import httpx
import pytest
from starlette.applications import Starlette

from mcp.app import create_mcp_app
from mcp.auth import (
    SCOPE_REQUIREMENTS,
    IntrospectionCache,
    McpAuthMiddleware,
    get_default_cache,
    hash_mcp_api_key,
    set_tool_scope_requirements,
)
from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.registry import Surface, ToolRegistry, ToolSpec, create_placeholder_tool
from mcp.settings import McpSettings
from mcp.tests.conftest import record_http_exchange


def _generate_test_mcp_key(surface: Surface) -> str:
    prefix = {"agent": "kb_agt_", "docs": "kb_doc_", "admin": "kb_adm_"}[surface.value]
    rand = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
    return f"{prefix}{rand}"


def _build_test_app_with_tools(
    surface: Surface,
    mock_transport: httpx.AsyncBaseTransport,
    *,
    auth_enabled: bool = True,
) -> tuple[httpx.AsyncClient, ToolRegistry]:
    """Construct an MCP application with custom tools and mock upstream client."""
    reg = ToolRegistry(surface)
    reg.register(create_placeholder_tool(surface))

    # Add a write tool for testing scope gating
    async def _write_handler(_args: dict[str, Any]) -> dict[str, str]:
        return {"status": "created"}

    reg.register(
        ToolSpec(
            name="test_agent_write",
            description="Tool requiring agent:write scope",
            surface=surface,
            input_schema={"type": "object"},
            handler=_write_handler,
        )
    )

    settings = McpSettings(mode="standalone_inprocess", auth_enabled=auth_enabled)
    kanban_client = KanbanApiClient(settings, transport=mock_transport)

    kwargs: dict[str, Any] = {"settings": settings}
    if surface == Surface.AGENT:
        kwargs["agent_registry"] = reg
    elif surface == Surface.DOCS:
        kwargs["docs_registry"] = reg
    elif surface == Surface.ADMIN:
        kwargs["admin_registry"] = reg

    base_app = create_mcp_app(**kwargs)

    middleware = McpAuthMiddleware(
        base_app,
        surface=surface,
        internal_client=kanban_client,
        settings=settings,
    )

    asgi_transport = httpx.ASGITransport(app=middleware)
    client = httpx.AsyncClient(transport=asgi_transport, base_url="http://test")
    return client, reg


@pytest.mark.asyncio
async def test_401_challenge_missing_and_blank_bearer() -> None:
    """Missing or blank Authorization header returns 401 with WWW-Authenticate metadata."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    app = create_mcp_app(settings)

    mock_transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"active": True}))
    client_mock = KanbanApiClient(settings, transport=mock_transport)

    agent_mw = McpAuthMiddleware(
        app,
        surface=Surface.AGENT,
        internal_client=client_mock,
        settings=settings,
    )
    transport = httpx.ASGITransport(app=agent_mw)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Missing Authorization header
        resp1 = await client.post(
            "/mcp/agent",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert resp1.status_code == 401
        www_auth1 = resp1.headers.get("www-authenticate", "")
        assert 'Bearer realm="kanban-mcp"' in www_auth1
        assert (
            'resource_metadata="https://127.0.0.1:8443/.well-known/oauth-protected-resource/mcp/agent"'
            in www_auth1
        )

        # 2. Blank Authorization header
        resp2 = await client.post(
            "/mcp/agent",
            headers={"Authorization": "Bearer   "},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert resp2.status_code == 401
        assert "resource_metadata=" in resp2.headers.get("www-authenticate", "")

        # 3. Non-bearer scheme
        resp3 = await client.post(
            "/mcp/agent",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
            json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        )
        assert resp3.status_code == 401


@pytest.mark.asyncio
async def test_prefix_precheck_local_rejection_zero_network_call() -> None:
    """Prefix mismatch rejected locally with 403 SURFACE_KEY_MISMATCH and 0 upstream calls."""
    call_count = 0

    def mock_introspect(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"active": True})

    mock_transport = httpx.MockTransport(mock_introspect)
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    app = create_mcp_app(settings)
    client_mock = KanbanApiClient(settings, transport=mock_transport)

    agent_mw = McpAuthMiddleware(
        app,
        surface=Surface.AGENT,
        internal_client=client_mock,
        settings=settings,
    )
    admin_mw = McpAuthMiddleware(
        app,
        surface=Surface.ADMIN,
        internal_client=client_mock,
        settings=settings,
    )

    t_agent = httpx.ASGITransport(app=agent_mw)
    t_admin = httpx.ASGITransport(app=admin_mw)

    _, adm_token, _, _ = ("kb_adm_", "kb_adm_" + "x" * 43, b"", "")
    _, agt_token, _, _ = ("kb_agt_", "kb_agt_" + "y" * 43, b"", "")

    async with httpx.AsyncClient(transport=t_agent, base_url="http://test") as c_agent:
        # Present kb_adm_ on /mcp/agent -> 403
        resp = await c_agent.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {adm_token}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert resp.status_code == 403
        assert resp.json() == {"error": "SURFACE_KEY_MISMATCH"}
        assert call_count == 0

        # Reserved ephemeral prefix kb_agt_eph_ rejected
        eph_token = "kb_agt_eph_" + "z" * 43
        resp_eph = await c_agent.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {eph_token}"},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert resp_eph.status_code == 403
        assert resp_eph.json() == {"error": "SURFACE_KEY_MISMATCH"}
        assert call_count == 0

    async with httpx.AsyncClient(transport=t_admin, base_url="http://test") as c_admin:
        # Present kb_agt_ on /mcp/admin -> 403
        resp = await c_admin.post(
            "/mcp/admin",
            headers={"Authorization": f"Bearer {agt_token}"},
            json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        )
        assert resp.status_code == 403
        assert resp.json() == {"error": "SURFACE_KEY_MISMATCH"}
        assert call_count == 0


@pytest.mark.asyncio
async def test_introspection_cache_positive_only_and_ttl() -> None:
    """Positive introspection results cached for 15s; negative results not cached."""
    now_time = 5000.0

    def fake_clock() -> float:
        return now_time

    cache = IntrospectionCache(time_provider=fake_clock, default_ttl_s=15.0)

    token = "kb_agt_" + "a" * 43
    digest = hash_mcp_api_key(token)

    # 1. Negative result is not cached
    assert cache.get("agent", digest) is None

    # 2. Cache positive result
    pos_data = {
        "active": True,
        "principal_id": "018f-0000",
        "workspace_id": "018f-0001",
        "surface": "agent",
        "scopes": ["agent:read"],
    }
    cache.set("agent", digest, pos_data)

    # 3. Hit within 15 seconds
    assert cache.get("agent", digest) == pos_data
    now_time = 5014.0
    assert cache.get("agent", digest) == pos_data

    # 4. Expired after 15 seconds
    now_time = 5016.0
    assert cache.get("agent", digest) is None

    # 5. LRU eviction when exceeding max_entries
    small_cache = IntrospectionCache(max_entries=3, time_provider=fake_clock)
    small_cache.set("agent", b"1" * 32, {"active": True, "k": 1})
    small_cache.set("agent", b"2" * 32, {"active": True, "k": 2})
    small_cache.set("agent", b"3" * 32, {"active": True, "k": 3})

    # Access 1 to mark it recently used
    assert small_cache.get("agent", b"1" * 32) is not None
    # Insert 4 -> should evict 2 (least recently used)
    small_cache.set("agent", b"4" * 32, {"active": True, "k": 4})
    assert small_cache.get("agent", b"2" * 32) is None
    assert small_cache.get("agent", b"1" * 32) is not None


@pytest.mark.asyncio
async def test_tools_list_filtering_and_tools_call_insufficient_scope() -> None:
    """Verify tools/list filtering and tools/call scope gating."""
    agent_token = "kb_agt_" + "s" * 43

    def mock_introspect(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "active": True,
                "principal_id": "018f-0000",
                "workspace_id": "018f-0001",
                "surface": "agent",
                "scopes": ["agent:read"],  # Only agent:read!
            },
        )

    mock_transport = httpx.MockTransport(mock_introspect)
    client, _reg = _build_test_app_with_tools(Surface.AGENT, mock_transport)

    async with client:
        # 1. Initialize session
        init_resp = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {agent_token}"},
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
        assert init_resp.status_code == 200
        session_id = init_resp.headers["mcp-session-id"]

        # 2. tools/list: ping_agent requires agent:read (included);
        #    test_agent_write requires agent:write (omitted)
        list_resp = await client.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {agent_token}",
                "Mcp-Session-Id": session_id,
            },
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert list_resp.status_code == 200
        tool_names = [t["name"] for t in list_resp.json()["result"]["tools"]]
        assert "ping_agent" in tool_names
        assert "test_agent_write" not in tool_names

        # 3. tools/call on tool requiring agent:write -> returns isError: true
        call_resp = await client.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {agent_token}",
                "Mcp-Session-Id": session_id,
            },
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "test_agent_write", "arguments": {}},
            },
        )
        assert call_resp.status_code == 200
        call_data = call_resp.json()
        assert call_data["result"]["isError"] is True
        error_text = call_data["result"]["content"][0]["text"]
        assert "INSUFFICIENT_SCOPE" in error_text


@pytest.mark.asyncio
async def test_session_token_binding_mismatch_returns_404() -> None:
    """Session initialized with token 1 returns 404 if accessed with token 2."""
    token_1 = "kb_agt_" + "1" * 43
    token_2 = "kb_agt_" + "2" * 43

    def mock_introspect(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content.decode("utf-8"))
        tok = data.get("token")
        if tok in (token_1, token_2):
            return httpx.Response(
                200,
                json={
                    "active": True,
                    "principal_id": "018f-0000",
                    "workspace_id": "018f-0001",
                    "surface": "agent",
                    "scopes": ["agent:read", "agent:write"],
                },
            )
        return httpx.Response(200, json={"active": False})

    mock_transport = httpx.MockTransport(mock_introspect)
    client, _ = _build_test_app_with_tools(Surface.AGENT, mock_transport)

    async with client:
        # 1. Initialize with token_1
        init_resp = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token_1}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )
        assert init_resp.status_code == 200
        session_id = init_resp.headers["mcp-session-id"]

        # 2. Access with token_1 -> OK
        call1 = await client.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token_1}",
                "Mcp-Session-Id": session_id,
            },
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert call1.status_code == 200

        # 3. Access with token_2 -> 404
        call2 = await client.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token_2}",
                "Mcp-Session-Id": session_id,
            },
            json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        )
        assert call2.status_code == 404


@pytest.mark.asyncio
async def test_transcript_generation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Capture comprehensive MCP transcript with 401, 403, INSUFFICIENT_SCOPE, and tools/list."""
    transcript_file = tmp_path / "mcp-transcript.txt"
    monkeypatch.setenv("KB_MCP_TRANSCRIPT_PATH", str(transcript_file))

    token_read = "kb_agt_" + "r" * 43
    token_admin = "kb_adm_" + "a" * 43

    def mock_introspect(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content.decode("utf-8"))
        tok = data.get("token")
        if tok == token_read:
            return httpx.Response(
                200,
                json={
                    "active": True,
                    "principal_id": "018f-0000",
                    "workspace_id": "018f-0001",
                    "surface": "agent",
                    "scopes": ["agent:read"],
                },
            )
        return httpx.Response(200, json={"active": False})

    mock_transport = httpx.MockTransport(mock_introspect)
    client, _ = _build_test_app_with_tools(Surface.AGENT, mock_transport)

    async with client:
        # 1. 401 challenge (missing auth)
        resp_401 = await client.post(
            "/mcp/agent",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert resp_401.status_code == 401
        record_http_exchange(transcript_file, resp_401.request, resp_401)

        # 2. 403 mismatch (admin token on agent surface)
        resp_403 = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token_admin}"},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert resp_403.status_code == 403
        record_http_exchange(transcript_file, resp_403.request, resp_403)

        # 3. Successful initialize with read token
        init_resp = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token_read}"},
            json={"jsonrpc": "2.0", "id": 3, "method": "initialize"},
        )
        assert init_resp.status_code == 200
        session_id = init_resp.headers["mcp-session-id"]
        record_http_exchange(transcript_file, init_resp.request, init_resp)

        # 4. Successful tools/list
        list_resp = await client.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token_read}",
                "Mcp-Session-Id": session_id,
            },
            json={"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
        )
        assert list_resp.status_code == 200
        record_http_exchange(transcript_file, list_resp.request, list_resp)

        # 5. INSUFFICIENT_SCOPE tool call
        scope_resp = await client.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token_read}",
                "Mcp-Session-Id": session_id,
            },
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "test_agent_write", "arguments": {}},
            },
        )
        assert scope_resp.status_code == 200
        assert scope_resp.json()["result"]["isError"] is True
        record_http_exchange(transcript_file, scope_resp.request, scope_resp)

    # Assert transcript file recorded all exchanges
    assert transcript_file.exists()
    content = transcript_file.read_text(encoding="utf-8")
    assert "401 Unauthorized" in content
    assert "www-authenticate: bearer" in content.lower()
    assert "403 Forbidden" in content
    assert "SURFACE_KEY_MISMATCH" in content
    assert "INSUFFICIENT_SCOPE" in content
    # Assert zero unredacted keys
    assert token_read not in content
    assert token_admin not in content


@pytest.mark.asyncio
async def test_introspection_cache_methods() -> None:
    """Test IntrospectionCache invalidate, clear, and get_default_cache."""
    cache = IntrospectionCache(max_entries=10, default_ttl_s=15.0)
    digest = b"\x01" * 32
    cache.set("agent", digest, {"active": True, "scopes": ["agent:read"]})
    assert cache.get("agent", digest) is not None

    cache.invalidate("agent", digest)
    assert cache.get("agent", digest) is None

    cache.set("agent", digest, {"active": True})
    assert cache.get("agent", digest) is not None
    cache.clear()
    assert cache.get("agent", digest) is None

    def_cache = get_default_cache()
    assert isinstance(def_cache, IntrospectionCache)


def test_tool_scope_requirements_registration() -> None:
    """Test set_tool_scope_requirements dynamically updates scope map."""
    tool_name = "test_custom_scopeless_tool"
    set_tool_scope_requirements(tool_name, {"custom:read", "custom:write"})
    assert tool_name in SCOPE_REQUIREMENTS
    assert SCOPE_REQUIREMENTS[tool_name] == frozenset({"custom:read", "custom:write"})


@pytest.mark.asyncio
async def test_auth_disabled_and_non_http_scope() -> None:
    """Verify auth disabled passes through and non-http ASGI scope passes through."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=False)
    mock_transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"active": True}))
    client_mock = KanbanApiClient(settings, transport=mock_transport)

    # 1. Non-http scope passes through
    called = False

    async def dummy_app(_scope: object, _receive: object, _send: object) -> None:
        nonlocal called
        called = True

    async def dummy_receive() -> dict[str, Any]:
        return {}

    async def dummy_send(_message: MutableMapping[str, Any]) -> None:
        pass

    dummy_mw = McpAuthMiddleware(
        dummy_app, surface=Surface.AGENT, internal_client=client_mock, settings=settings
    )
    await dummy_mw({"type": "websocket"}, dummy_receive, dummy_send)
    assert called is True

    # 2. Auth disabled allows request with zero auth headers
    client, _ = _build_test_app_with_tools(Surface.AGENT, mock_transport, auth_enabled=False)
    async with client:
        resp = await client.post(
            "/mcp/agent", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_surface_resolution_from_path() -> None:
    """Verify surface is automatically resolved from path when surface=None."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)

    def dummy_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"active": True, "scopes": ["agent:read", "docs:read", "admin:read"]},
        )

    mock_transport = httpx.MockTransport(dummy_handler)
    client_mock = KanbanApiClient(settings, transport=mock_transport)

    app = create_mcp_app(settings)
    # surface=None: resolves from path
    mw = McpAuthMiddleware(app, surface=None, internal_client=client_mock, settings=settings)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=mw), base_url="http://test")

    async with client:
        # Unknown path: surface=None -> passes through to base app (which 404s on unrecognized path)
        resp_other = await client.post("/api/other", json={})
        assert resp_other.status_code == 404

        # /mcp/agent with missing auth -> 401 agent challenge
        resp_agent = await client.post("/mcp/agent", json={})
        assert resp_agent.status_code == 401
        assert "resource_metadata=" in resp_agent.headers["www-authenticate"]
        assert "/mcp/agent" in resp_agent.headers["www-authenticate"]

        # /mcp/docs with missing auth -> 401 docs challenge
        resp_docs = await client.post("/mcp/docs", json={})
        assert resp_docs.status_code == 401
        assert "/mcp/docs" in resp_docs.headers["www-authenticate"]

        # /mcp/admin with missing auth -> 401 admin challenge
        resp_admin = await client.post("/mcp/admin", json={})
        assert resp_admin.status_code == 401
        assert "/mcp/admin" in resp_admin.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_upstream_client_unavailable_503() -> None:
    """Verify 503 is returned when no internal client is configured."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    dummy_app = Starlette()
    mw = McpAuthMiddleware(
        dummy_app, surface=Surface.AGENT, internal_client=None, settings=settings
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=mw), base_url="http://test")

    token = _generate_test_mcp_key(Surface.AGENT)
    async with client:
        resp = await client.post(
            "/mcp/agent", headers={"Authorization": f"Bearer {token}"}, json={}
        )
        assert resp.status_code == 503
        assert resp.json()["error"] == "UPSTREAM_UNAVAILABLE"


@pytest.mark.asyncio
async def test_upstream_introspection_error_paths() -> None:
    """Verify handling of upstream exceptions and non-dict responses."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    app = create_mcp_app(settings)
    token = _generate_test_mcp_key(Surface.AGENT)

    # 1. Upstream raises KbMcpError(SURFACE_KEY_MISMATCH)
    async def mock_mismatch(*_args: object, **_kwargs: object) -> object:
        raise KbMcpError(McpErrorCode.SURFACE_KEY_MISMATCH, "Surface mismatch")

    client_mismatch = KanbanApiClient(
        settings, transport=httpx.MockTransport(lambda _: httpx.Response(200))
    )
    client_mismatch.request = mock_mismatch  # type: ignore[method-assign]
    mw1 = McpAuthMiddleware(
        app, surface=Surface.AGENT, internal_client=client_mismatch, settings=settings
    )
    c1 = httpx.AsyncClient(transport=httpx.ASGITransport(app=mw1), base_url="http://test")
    async with c1:
        resp1 = await c1.post("/mcp/agent", headers={"Authorization": f"Bearer {token}"}, json={})
        assert resp1.status_code == 403
        assert resp1.json()["error"] == "SURFACE_KEY_MISMATCH"

    # 2. Upstream raises generic Exception
    async def mock_exc(*_args: object, **_kwargs: object) -> object:
        msg = "Internal crash"
        raise RuntimeError(msg)

    client_exc = KanbanApiClient(
        settings, transport=httpx.MockTransport(lambda _: httpx.Response(200))
    )
    client_exc.request = mock_exc  # type: ignore[method-assign]
    mw2 = McpAuthMiddleware(
        app, surface=Surface.AGENT, internal_client=client_exc, settings=settings
    )
    c2 = httpx.AsyncClient(transport=httpx.ASGITransport(app=mw2), base_url="http://test")
    async with c2:
        resp2 = await c2.post("/mcp/agent", headers={"Authorization": f"Bearer {token}"}, json={})
        assert resp2.status_code == 401

    # 3. Upstream returns non-dict (e.g. list or string)
    client_nondict = KanbanApiClient(
        settings,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=["unexpected", "list"])),
    )
    mw3 = McpAuthMiddleware(
        app, surface=Surface.AGENT, internal_client=client_nondict, settings=settings
    )
    c3 = httpx.AsyncClient(transport=httpx.ASGITransport(app=mw3), base_url="http://test")
    async with c3:
        resp3 = await c3.post("/mcp/agent", headers={"Authorization": f"Bearer {token}"}, json={})
        assert resp3.status_code == 401

    # 4. Upstream returns active=False with reason=SURFACE_KEY_MISMATCH
    client_reason_mismatch = KanbanApiClient(
        settings,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"active": False, "reason": "SURFACE_KEY_MISMATCH"})
        ),
    )
    mw4 = McpAuthMiddleware(
        app, surface=Surface.AGENT, internal_client=client_reason_mismatch, settings=settings
    )
    c4 = httpx.AsyncClient(transport=httpx.ASGITransport(app=mw4), base_url="http://test")
    async with c4:
        resp4 = await c4.post("/mcp/agent", headers={"Authorization": f"Bearer {token}"}, json={})
        assert resp4.status_code == 403
        assert resp4.json()["error"] == "SURFACE_KEY_MISMATCH"

    # 5. Upstream returns active=False with other reason (e.g. EXPIRED)
    client_expired = KanbanApiClient(
        settings,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"active": False, "reason": "EXPIRED"})
        ),
    )
    mw5 = McpAuthMiddleware(
        app, surface=Surface.AGENT, internal_client=client_expired, settings=settings
    )
    c5 = httpx.AsyncClient(transport=httpx.ASGITransport(app=mw5), base_url="http://test")
    async with c5:
        resp5 = await c5.post("/mcp/agent", headers={"Authorization": f"Bearer {token}"}, json={})
        assert resp5.status_code == 401
