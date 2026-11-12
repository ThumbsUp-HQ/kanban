# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for RFC 9728 protected-resource metadata endpoints (KB-P4-02b)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

from mcp.app import create_mcp_app
from mcp.metadata import build_protected_resource_metadata
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
