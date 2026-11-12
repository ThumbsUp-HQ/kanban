"""Unit tests for the canonical Kanban ASGI application factory."""

from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from kanban.app import create_app
from kanban.settings import Settings


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Fixture providing isolated settings with dummy web_dist directory."""
    dist_dir = tmp_path / "web_dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("<!doctype html><html><body>Test</body></html>", encoding="utf-8")
    return Settings(
        web_dist=dist_dir,
        deployment_mode="production",
    )


@pytest.mark.asyncio
async def test_health_check_endpoint(test_settings: Settings) -> None:
    """Test GET /api/v1/health returns 200 with status ok."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_api_not_found_problem_json(test_settings: Settings) -> None:
    """Test unknown /api/* endpoints return RFC 9457 Problem Details 404."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # Subpath
        response = await client.get("/api/nope")
        assert response.status_code == 404
        assert response.headers.get("content-type") == "application/problem+json"
        data = response.json()
        assert data["type"] == "about:blank"
        assert data["title"] == "Not Found"
        assert data["status"] == 404

        # Non-GET method on unknown API path
        post_resp = await client.post("/api/v2/nonexistent")
        assert post_resp.status_code == 404
        assert post_resp.headers.get("content-type") == "application/problem+json"


@pytest.mark.asyncio
async def test_sse_placeholder_501(test_settings: Settings) -> None:
    """Test GET /sse returns 501 Not Implemented problem JSON."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get("/sse")
        assert response.status_code == 501
        assert response.headers.get("content-type") == "application/problem+json"
        data = response.json()
        assert data["title"] == "Not Implemented"
        assert data["status"] == 501


@pytest.mark.asyncio
async def test_mcp_placeholders_501(test_settings: Settings) -> None:
    """Test /mcp/* routes return 501 Not Implemented without importing mcp module."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        for path in ("/mcp/agent", "/mcp/docs", "/mcp/admin", "/mcp/admin/tools"):
            response = await client.get(path)
            assert response.status_code == 501
            assert response.headers.get("content-type") == "application/problem+json"
            assert response.json()["status"] == 501


def test_websocket_close_1008(test_settings: Settings) -> None:
    """Test WebSocket connection to /ws is closed with policy violation code 1008."""
    app = create_app(test_settings)
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect("/ws"):
        pass
    assert exc_info.value.code == 1008


@pytest.mark.asyncio
async def test_openapi_available_but_docs_disabled(test_settings: Settings) -> None:
    """Test OpenAPI schema is available at /api/openapi.json while Swagger/Redoc are disabled."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        openapi_resp = await client.get("/api/openapi.json")
        assert openapi_resp.status_code == 200
        assert "openapi" in openapi_resp.json()

        # Swagger and Redoc should not match API routes and fall back or 404
        docs_resp = await client.get("/docs")
        # /docs falls back to SPA index.html (200) rather than Swagger UI
        assert "Swagger UI" not in docs_resp.text


def test_default_settings_and_hosts_parsing() -> None:
    """Test default settings initialization and standalone_cleartext_hosts validator formats."""
    # Default factory invocation without settings
    app = create_app()
    assert app is not None

    # Test standalone_cleartext_hosts with comma-separated string
    s_str = Settings(standalone_cleartext_hosts="example.org, custom.internal")  # type: ignore[arg-type]
    assert "example.org" in s_str.standalone_cleartext_hosts
    assert "custom.internal" in s_str.standalone_cleartext_hosts
    assert "localhost" in s_str.standalone_cleartext_hosts

    # Test standalone_cleartext_hosts with None
    s_none = Settings(standalone_cleartext_hosts=None)  # type: ignore[arg-type]
    assert "localhost" in s_none.standalone_cleartext_hosts

    # Test standalone_cleartext_hosts with unsupported type fallback
    s_fallback = Settings(standalone_cleartext_hosts=12345)  # type: ignore[arg-type]
    assert "localhost" in s_fallback.standalone_cleartext_hosts
