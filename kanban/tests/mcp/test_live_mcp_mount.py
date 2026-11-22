# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Forensic unit and integration tests for live MCP mounts on the app server (KANBA-179)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest

from kanban.app import create_app
from kanban.settings import Settings
from mcp.app import create_mcp_app
from mcp.internal_client import KanbanApiClient
from mcp.registry import Surface, ToolRegistry, ToolSpec
from mcp.settings import McpSettings

if TYPE_CHECKING:
    from pathlib import Path

    from starlette.types import ASGIApp


@pytest.fixture
def app_with_static(tmp_path: Path) -> ASGIApp:
    """Create Kanban application instance with dummy web dist."""
    dist_dir = tmp_path / "web_dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("<!doctype html><html><body>Test</body></html>", encoding="utf-8")
    settings = Settings(web_dist=dist_dir, deployment_mode="production")
    return create_app(settings)


@pytest.mark.asyncio
async def test_rfc9728_protected_resource_metadata_endpoints(
    app_with_static: ASGIApp,
) -> None:
    """Test RFC 9728 protected-resource metadata is properly routed on live app server."""
    transport = httpx.ASGITransport(app=app_with_static)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # 1. Agent surface metadata
        resp_agent = await client.get("/.well-known/oauth-protected-resource/mcp/agent")
        assert resp_agent.status_code == 200
        data_agent = resp_agent.json()
        assert data_agent["resource"] == "http://localhost/mcp/agent"
        assert data_agent["authorization_servers"] == ["http://localhost"]
        assert data_agent["scopes_supported"] == ["agent:read", "agent:write"]
        assert data_agent["bearer_methods_supported"] == ["header"]

        # 2. Docs surface metadata
        resp_docs = await client.get("/.well-known/oauth-protected-resource/mcp/docs")
        assert resp_docs.status_code == 200
        data_docs = resp_docs.json()
        assert data_docs["resource"] == "http://localhost/mcp/docs"
        assert data_docs["scopes_supported"] == ["docs:read", "docs:write"]

        # 3. Admin surface metadata
        resp_admin = await client.get("/.well-known/oauth-protected-resource/mcp/admin")
        assert resp_admin.status_code == 200
        data_admin = resp_admin.json()
        assert data_admin["resource"] == "http://localhost/mcp/admin"
        assert data_admin["scopes_supported"] == [
            "admin:read",
            "admin:write",
            "admin:destructive",
        ]

        # 4. Scoped metadata: workspace and project suffixes
        resp_scoped = await client.get(
            "/.well-known/oauth-protected-resource/mcp/agent/w/demo-workspace/p/DEMO-PRJ"
        )
        assert resp_scoped.status_code == 200
        data_scoped = resp_scoped.json()
        assert data_scoped["resource"] == "http://localhost/mcp/agent/w/demo-workspace/p/DEMO-PRJ"

        # 5. Unknown surface returns 404
        resp_unknown = await client.get("/.well-known/oauth-protected-resource/mcp/unknown-surface")
        assert resp_unknown.status_code == 404


@pytest.mark.asyncio
async def test_mcp_surfaces_unauthenticated_401(
    app_with_static: ASGIApp,
) -> None:
    """Test unauthenticated requests to live /mcp/* return 401 with WWW-Authenticate header."""
    transport = httpx.ASGITransport(app=app_with_static)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        for surface in ("agent", "docs", "admin"):
            resp = await client.post(f"/mcp/{surface}", json={})
            assert resp.status_code == 401
            www_auth = resp.headers.get("www-authenticate", "")
            assert 'Bearer realm="kanban-mcp"' in www_auth
            assert (
                f'resource_metadata="https://127.0.0.1:8443/.well-known/oauth-protected-resource/mcp/{surface}"'
                in www_auth
            )

        # Verify reverse-proxy Host header without X-Forwarded-Host resolves public domain
        resp_proxy = await client.post(
            "/mcp/agent/w/kanban",
            json={},
            headers={"Host": "k.hackedyour.info", "X-Forwarded-Proto": "https"},
        )
        assert resp_proxy.status_code == 401
        assert (
            'resource_metadata="https://k.hackedyour.info/.well-known/oauth-protected-resource/mcp/agent/w/kanban"'
            in resp_proxy.headers.get("www-authenticate", "")
        )


@pytest.mark.asyncio
async def test_live_mcp_authenticated_session_and_tools(tmp_path: Path) -> None:
    """Test authenticated session initialize and tools/list on live app server."""
    dist_dir = tmp_path / "web_dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("<!doctype html><html><body>Test</body></html>", encoding="utf-8")
    settings = Settings(web_dist=dist_dir, deployment_mode="production")

    token = "kb_agt_live_mount_test_token"

    def mock_introspect(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content.decode("utf-8"))
        assert data["token"] == token
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

    mcp_settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    mock_client = KanbanApiClient(mcp_settings, transport=httpx.MockTransport(mock_introspect))

    reg = ToolRegistry(Surface.AGENT)
    reg.register(
        ToolSpec(
            name="test_live_ping",
            description="Live mounted tool",
            surface=Surface.AGENT,
            input_schema={"type": "object"},
            handler=lambda _a: {"ok": True},
        )
    )

    custom_mcp_app = create_mcp_app(
        mcp_settings,
        internal_client=mock_client,
        agent_registry=reg,
    )

    app = create_app(settings)
    app.state.mcp_app = custom_mcp_app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # 1. Initialize with Bearer token
        init_resp = await client.post(
            "/mcp/agent",
            headers={"Authorization": f"Bearer {token}"},
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
        assert session_id is not None

        # 2. tools/list
        tools_resp = await client.post(
            "/mcp/agent",
            headers={
                "Authorization": f"Bearer {token}",
                "Mcp-Session-Id": session_id,
            },
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert tools_resp.status_code == 200
        tool_names = [t["name"] for t in tools_resp.json()["result"]["tools"]]
        assert "test_live_ping" in tool_names


@pytest.mark.asyncio
async def test_live_mcp_bearer_token_whitespace_tolerance(tmp_path: Path) -> None:
    """Test whitespace in Authorization: Bearer <token> is tolerated on live app mount."""
    dist_dir = tmp_path / "web_dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("<!doctype html><html><body>Test</body></html>", encoding="utf-8")
    settings = Settings(web_dist=dist_dir, deployment_mode="production")

    token = "kb_agt_whitespace_test_token"

    def mock_introspect(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content.decode("utf-8"))
        assert data["token"] == token
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

    mcp_settings = McpSettings(mode="standalone_inprocess", auth_enabled=True)
    mock_client = KanbanApiClient(mcp_settings, transport=httpx.MockTransport(mock_introspect))

    custom_mcp_app = create_mcp_app(
        mcp_settings,
        internal_client=mock_client,
    )

    app = create_app(settings)
    app.state.mcp_app = custom_mcp_app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # Extra spaces and tabs around Bearer and token
        for auth_val in (
            f"   Bearer    {token}   ",
            f"Bearer\t{token}",
            f"  Bearer  \t  {token} ",
        ):
            resp = await client.post(
                "/mcp/agent",
                headers={"Authorization": auth_val},
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
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_in_process_client_security_headers_and_loopback() -> None:
    """Test KanbanApiClient in standalone_inprocess mode connects to http://localhost."""
    received_requests: list[httpx.Request] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        received_requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(mock_handler)
    settings = McpSettings(mode="standalone_inprocess")
    client = KanbanApiClient(settings, transport=transport)

    await client.request("GET", "/api/v1/health")

    assert len(received_requests) == 1
    req = received_requests[0]
    assert req.url.host == "localhost"
    assert req.headers.get("x-kb-service-principal") is None
    assert "p=mcp-gateway,v2=" in req.headers.get("x-kb-internal-auth", "")
