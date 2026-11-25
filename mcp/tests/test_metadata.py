# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for RFC 9728 protected-resource metadata endpoints (KB-P4-02b)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
from starlette.requests import Request

from mcp.app import create_mcp_app
from mcp.metadata import (
    build_protected_resource_metadata,
    resolve_public_base_url,
)
from mcp.settings import McpSettings

if TYPE_CHECKING:
    from starlette.types import ASGIApp


@pytest.fixture
def mcp_app() -> ASGIApp:
    """Create test MCP ASGI application."""
    settings = McpSettings(
        mode="standalone_inprocess",
        auth_enabled=False,
    )
    return create_mcp_app(settings=settings)


@pytest.mark.asyncio
async def test_protected_resource_metadata_surfaces(mcp_app: ASGIApp) -> None:
    """Test RFC 9728 metadata documents for all 3 surfaces (Test Case 7)."""
    transport = httpx.ASGITransport(app=mcp_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Agent surface
        resp_agent = await client.get("/.well-known/oauth-protected-resource/mcp/agent")
        assert resp_agent.status_code == 200
        data_agent = resp_agent.json()
        assert data_agent["resource"] == "http://testserver/mcp/agent"
        assert data_agent["authorization_servers"] == ["http://testserver"]
        assert data_agent["scopes_supported"] == ["agent:read", "agent:write"]
        assert data_agent["bearer_methods_supported"] == ["header"]

        # 2. Docs surface
        resp_docs = await client.get("/.well-known/oauth-protected-resource/mcp/docs")
        assert resp_docs.status_code == 200
        data_docs = resp_docs.json()
        assert data_docs["resource"] == "http://testserver/mcp/docs"
        assert data_docs["scopes_supported"] == ["docs:read", "docs:write"]
        assert data_docs["bearer_methods_supported"] == ["header"]

        # 3. Admin surface
        resp_admin = await client.get("/.well-known/oauth-protected-resource/mcp/admin")
        assert resp_admin.status_code == 200
        data_admin = resp_admin.json()
        assert data_admin["resource"] == "http://testserver/mcp/admin"
        assert data_admin["scopes_supported"] == ["admin:read", "admin:write", "admin:destructive"]
        assert data_admin["bearer_methods_supported"] == ["header"]

        # 4. Unknown surface -> 404
        resp_unknown = await client.get("/.well-known/oauth-protected-resource/mcp/invalid")
        assert resp_unknown.status_code == 404


def test_build_protected_resource_metadata_helper() -> None:
    """Test helper returns None for invalid surfaces."""
    assert build_protected_resource_metadata("unknown", "http://base") is None
    meta = build_protected_resource_metadata("agent", "http://base/", "http://issuer/")
    assert meta is not None
    assert meta["resource"] == "http://base/mcp/agent"
    assert meta["authorization_servers"] == ["http://issuer"]


@pytest.mark.asyncio
async def test_protected_resource_metadata_endpoint_scoped_paths(mcp_app: ASGIApp) -> None:
    """Test RFC 9728 discovery across bare, scoped /w/{ws}, and project paths (KAN-395)."""
    transport = httpx.ASGITransport(app=mcp_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Bare /.well-known/oauth-protected-resource
        resp_bare = await client.get("/.well-known/oauth-protected-resource")
        assert resp_bare.status_code == 200
        assert resp_bare.json()["resource"] == "http://testserver/mcp/agent"

        # /mcp
        resp_mcp = await client.get("/.well-known/oauth-protected-resource/mcp")
        assert resp_mcp.status_code == 200
        assert resp_mcp.json()["resource"] == "http://testserver/mcp/agent"

        # /mcp/w/engineering
        resp_ws = await client.get("/.well-known/oauth-protected-resource/mcp/w/engineering")
        assert resp_ws.status_code == 200
        assert resp_ws.json()["resource"] == "http://testserver/mcp/agent/w/engineering"

        # /mcp/w/engineering/p/ENG
        resp_proj = await client.get(
            "/.well-known/oauth-protected-resource/mcp/w/engineering/p/ENG"
        )
        assert resp_proj.status_code == 200
        assert resp_proj.json()["resource"] == "http://testserver/mcp/agent/w/engineering/p/ENG"

        # /mcp/docs/w/engineering/p/ENG
        resp_docs_proj = await client.get(
            "/.well-known/oauth-protected-resource/mcp/docs/w/engineering/p/ENG"
        )
        assert resp_docs_proj.status_code == 200
        assert resp_docs_proj.json()["resource"] == "http://testserver/mcp/docs/w/engineering/p/ENG"


def test_resolve_public_base_url_variations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test public base URL resolution across environment and proxy header matrix (KAN-395)."""
    # 1. KANBAN_PUBLIC_ORIGIN env var
    monkeypatch.setenv("KANBAN_PUBLIC_ORIGIN", "https://proxy.example.com/")
    assert resolve_public_base_url() == "https://proxy.example.com"
    monkeypatch.delenv("KANBAN_PUBLIC_ORIGIN", raising=False)

    # 2. X-Forwarded-Proto and X-Forwarded-Host with chained proxies
    req_fwd = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "server": ("127.0.0.1", 8080),
            "path": "/",
            "headers": [
                (b"x-forwarded-proto", b"https, http"),
                (b"x-forwarded-host", b"k.hackedyour.info, 127.0.0.1"),
            ],
        }
    )
    assert resolve_public_base_url(req_fwd) == "https://k.hackedyour.info"

    # 3. Only Host header
    req_host = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "server": ("127.0.0.1", 8080),
            "path": "/",
            "headers": [(b"host", b"app.local:8443")],
        }
    )
    assert resolve_public_base_url(req_host) == "https://app.local:8443"

    # 4. None fallback
    assert resolve_public_base_url(None) == "http://localhost:8000"
