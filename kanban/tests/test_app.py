"""Unit tests for the canonical Kanban ASGI application factory."""

import inspect
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.requests import Request
from starlette.routing import Mount
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from kanban.api.v1.oauth import OAuth2Error
from kanban.app import (
    _bootstrap_runtime_state,
    _mount_mcp_surfaces,
    create_app,
    lifespan,
)
from kanban.settings import Settings

if TYPE_CHECKING:
    from starlette.types import Receive, Scope, Send


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

        # Non-GET method on unknown API path with valid CSRF tokens
        sess_resp = await client.get("/api/v1/auth/session")
        csrf_token = sess_resp.json()["csrf_token"]
        post_resp = await client.post(
            "/api/v2/nonexistent",
            headers={"X-CSRF-Token": csrf_token},
            cookies={"__Host-kb_csrf": csrf_token},
        )
        assert post_resp.status_code == 404
        assert post_resp.headers.get("content-type") == "application/problem+json"


@pytest.mark.asyncio
async def test_sse_unauthenticated_401(test_settings: Settings) -> None:
    """Test GET /sse returns 401 Unauthorized problem JSON when unauthenticated."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.get("/sse")
        assert response.status_code == 401
        assert response.headers.get("content-type") == "application/problem+json"
        data = response.json()
        assert data["title"] == "Unauthorized"
        assert data["status"] == 401


@pytest.mark.asyncio
async def test_mcp_surfaces_live_auth_challenge(test_settings: Settings) -> None:
    """Test /mcp/* routes are live and return 401 challenge with WWW-Authenticate metadata."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        for path in ("/mcp/agent", "/mcp/docs", "/mcp/admin"):
            response = await client.get(path)
            assert response.status_code == 401
            assert "www-authenticate" in response.headers
            assert "resource_metadata=" in response.headers["www-authenticate"]


def test_websocket_close_4401(test_settings: Settings) -> None:
    """Test unauthenticated WebSocket connection to /ws is closed with 4401."""
    app = create_app(test_settings)
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect("/ws"):
        pass
    assert exc_info.value.code == 4401


@pytest.mark.asyncio
async def test_openapi_and_docs_routing(test_settings: Settings) -> None:
    """Test OpenAPI schema, docs at /api/docs & /api/redoc, and SPA at /docs."""
    app = create_app(test_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        openapi_resp = await client.get("/api/openapi.json")
        assert openapi_resp.status_code == 200
        assert "openapi" in openapi_resp.json()

        # Workspace /docs falls back to SPA index.html (200) rather than Swagger UI
        docs_resp = await client.get("/docs")
        assert "Swagger UI" not in docs_resp.text

        # Interactive API documentation served at /api/docs and /api/redoc
        api_docs_resp = await client.get("/api/docs")
        assert api_docs_resp.status_code == 200
        assert "Swagger UI" in api_docs_resp.text

        redoc_resp = await client.get("/api/redoc")
        assert redoc_resp.status_code == 200
        assert "ReDoc" in redoc_resp.text


@pytest.mark.asyncio
async def test_app_lifespan_and_bootstrap_coverage(test_settings: Settings) -> None:
    """Test application lifespan context and bootstrap state coverage."""
    app = create_app(test_settings)

    # Lifespan startup with realtime hub, owned engine, and background jobs enabled
    mock_hub = AsyncMock()
    mock_session_target = MagicMock()
    mock_owned_engine = AsyncMock()
    app.state.realtime_hub = mock_hub
    app.state.enable_background_jobs = True
    app.state.session_factory = mock_session_target
    app.state.key_material = MagicMock()

    with (
        patch("kanban.app._bootstrap_runtime_state", return_value=mock_owned_engine),
        patch("kanban.app.mint_setup_token_if_uninitialized", new_callable=AsyncMock),
    ):
        async with lifespan(app):
            assert app.state.job_scheduler is not None
            mock_hub.start.assert_awaited_once()

    mock_hub.drain.assert_awaited_once()
    mock_owned_engine.dispose.assert_awaited_once()

    # Lifespan default (hub=None, should_run=False, owned_engine=None)
    app_default = create_app(test_settings)
    async with lifespan(app_default):
        pass

    # Lifespan setup token check failure branch
    app_mint_err = create_app(test_settings)
    app_mint_err.state.session_factory = mock_session_target
    with patch(
        "kanban.app.mint_setup_token_if_uninitialized",
        side_effect=RuntimeError("Mint fail"),
    ):
        async with lifespan(app_mint_err):
            pass

    # Bootstrap with no database URL returns None
    app_no_db = create_app(test_settings)
    assert _bootstrap_runtime_state(app_no_db) is None

    # Bootstrap with pre-set session_factory returns None
    app_no_db.state.session_factory = object()
    assert _bootstrap_runtime_state(app_no_db) is None

    # Bootstrap with simulated database_url and pre-set providers
    app_with_db = create_app(test_settings)
    app_with_db.state.settings = MagicMock(
        database_url="postgresql+asyncpg://user:pass@localhost/db"
    )
    app_with_db.state.kek_provider = object()
    app_with_db.state.session_service = object()
    app_with_db.state.principal_resolver = object()
    mock_km = MagicMock()
    mock_km.master_kek_kid = "kid1"
    mock_km.master_kek = b"0" * 32
    mock_km.session_hmac_key = b"1" * 32
    mock_engine = AsyncMock()

    with (
        patch("kanban.app.create_async_engine", return_value=mock_engine),
        patch("kanban.app.load_key_material", return_value=mock_km),
        patch("kanban.app.RLSSessionFactory"),
    ):
        res = _bootstrap_runtime_state(app_with_db)
        assert res is mock_engine
        assert app_with_db.state.engine is mock_engine

    # Bootstrap error handling branch
    app_fail = create_app(test_settings)
    app_fail.state.settings = MagicMock(database_url="postgresql+asyncpg://user:pass@localhost/db")
    with patch("kanban.app.create_async_engine", side_effect=RuntimeError("Engine fail")):
        assert _bootstrap_runtime_state(app_fail) is None

    # MCP surface mounting error handling branch
    app_err = create_app(test_settings)
    app_err.state.mcp_app = None
    with patch("importlib.import_module", side_effect=ImportError("No module")):
        _mount_mcp_surfaces(app_err)


@pytest.mark.asyncio
async def test_oauth2_error_handler_and_endpoints(test_settings: Settings) -> None:
    """Test OAuth2Error handler, favicon, and oauth-protected-resource endpoints."""
    app = create_app(test_settings)
    handler = app.exception_handlers.get(OAuth2Error)
    assert handler is not None

    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/oauth/token",
        "headers": [],
    }
    req = Request(scope)
    raw_resp = handler(
        req, OAuth2Error(error="invalid_grant", description="Invalid authorization code")
    )
    resp = await raw_resp if inspect.isawaitable(raw_resp) else raw_resp
    assert resp.status_code == 400
    expected_body = b'{"error":"invalid_grant","error_description":"Invalid authorization code"}'
    assert resp.body == expected_body

    # Test favicon and oauth-protected-resource endpoints via HTTP client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        fav_resp = await client.get("/favicon.ico")
        assert fav_resp.status_code == 200
        assert fav_resp.headers["content-type"] == "image/svg+xml"
        assert fav_resp.headers["cache-control"] == "public, max-age=86400"

        oauth_meta_resp = await client.get("/.well-known/oauth-protected-resource")
        assert oauth_meta_resp.status_code == 200
        oauth_sub_resp = await client.get("/.well-known/oauth-protected-resource/mcp/agent")
        assert oauth_sub_resp.status_code == 200


@pytest.mark.asyncio
async def test_mcp_proxy_app_branches(test_settings: Settings) -> None:
    """Test _McpProxyApp HTTP path root_path prefixing and non-HTTP scope delegation."""
    app = create_app(test_settings)
    mock_mcp = AsyncMock()
    app.state.mcp_app = mock_mcp

    # Access the mounted MCP proxy app
    routes = [r for r in app.routes if isinstance(r, Mount) and r.path == "/mcp"]
    assert routes, "MCP route must be mounted at /mcp"
    mcp_proxy = routes[0].app

    dummy_receive: Receive = AsyncMock()
    dummy_send: Send = AsyncMock()

    # HTTP scope with root_path not in path
    http_scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/agent",
        "root_path": "/mcp",
        "headers": [],
    }
    await mcp_proxy(http_scope, dummy_receive, dummy_send)
    assert mock_mcp.await_count == 1

    # Non-HTTP scope (e.g. websocket)
    ws_scope: Scope = {
        "type": "websocket",
        "path": "/ws",
        "headers": [],
    }
    await mcp_proxy(ws_scope, dummy_receive, dummy_send)
    assert mock_mcp.await_count == 2


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
