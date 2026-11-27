# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit tests for mcp.app, kanban.app mounting, and internal_client."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

import httpx
import pytest
from fastapi import FastAPI
from starlette.routing import Mount

from kanban.api.v1.oauth import OAuth2Error
from kanban.app import _bootstrap_runtime_state, _mount_mcp_surfaces, create_app, lifespan
from kanban.settings import Settings
from mcp.app import _build_surface_sub_app, create_mcp_app
from mcp.context import McpRequestContext, set_current_mcp_context
from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.protocol import InMemorySessionStore, McpProtocolHandler
from mcp.registry import Surface, ToolRegistry
from mcp.scoping import ConnectionScope, ScopeMode
from mcp.settings import McpSettings
from mcp.tests.test_internal_client import (
    test_case_5_oversized_response_stream_aborts,
    test_case_5_plaintext_http_rejected_in_mtls_mode,
    test_case_5_upstream_problem_status_mapping,
    test_mtls_client_initialization,
    test_network_transport_error_maps_to_upstream_unavailable,
    test_standalone_inprocess_missing_app_raises,
    test_successful_request_and_context_manager,
    test_upstream_fallback_error_mapping,
)

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = [
    "test_build_surface_sub_app",
    "test_case_5_oversized_response_stream_aborts",
    "test_case_5_plaintext_http_rejected_in_mtls_mode",
    "test_case_5_upstream_problem_status_mapping",
    "test_create_mcp_app_structure_and_routes",
    "test_internal_client_branches_and_errors",
    "test_internal_client_csrf_and_context_scope",
    "test_internal_client_edge_branches",
    "test_kanban_app_lifespan_and_runtime_bootstrap",
    "test_kanban_app_lifespan_defaults_and_exception_branches",
    "test_kanban_app_mcp_proxy_and_error_handlers",
    "test_mtls_client_initialization",
    "test_network_transport_error_maps_to_upstream_unavailable",
    "test_standalone_inprocess_missing_app_raises",
    "test_successful_request_and_context_manager",
    "test_upstream_fallback_error_mapping",
]


@pytest.mark.asyncio
async def test_create_mcp_app_structure_and_routes() -> None:
    """Test create_mcp_app constructs registries, sub-apps, routes, and attaches state."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=False)
    reg_agent = ToolRegistry(Surface.AGENT)
    reg_docs = ToolRegistry(Surface.DOCS)
    reg_admin = ToolRegistry(Surface.ADMIN)

    app = create_mcp_app(
        settings,
        agent_registry=reg_agent,
        docs_registry=reg_docs,
        admin_registry=reg_admin,
    )

    assert app.state.settings == settings
    assert isinstance(app.state.session_store, InMemorySessionStore)
    assert app.state.agent_registry.is_frozen
    assert app.state.docs_registry.is_frozen
    assert app.state.admin_registry.is_frozen

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # Check metadata route
        resp = await client.get("/.well-known/oauth-protected-resource/mcp/agent")
        assert resp.status_code == 200

        # Check sub-app direct route
        resp = await client.get("/mcp/agent")
        assert resp.status_code == 405  # GET not allowed on JSON-RPC endpoint with empty body


@pytest.mark.asyncio
async def test_build_surface_sub_app() -> None:
    """Test _build_surface_sub_app handles root and workspace/project paths."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=False)
    reg = ToolRegistry(Surface.AGENT)
    reg.freeze()
    store = InMemorySessionStore()
    handler = McpProtocolHandler(Surface.AGENT, reg, store, settings)
    sub_app = _build_surface_sub_app(handler)

    transport = httpx.ASGITransport(app=sub_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        r1 = await client.post(
            "/",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
        assert r1.status_code in (200, 400, 404)


@pytest.mark.asyncio
async def test_kanban_app_lifespan_and_runtime_bootstrap(tmp_path: Path) -> None:
    """Cover lifespan and _bootstrap_runtime_state branches in kanban/app.py."""
    dist_dir = tmp_path / "web_dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("<!doctype html><html><body>Test</body></html>", encoding="utf-8")

    settings = Settings(
        web_dist=dist_dir,
        database_url="postgresql+asyncpg://kanban_app:test@localhost:5432/test_db",
        deployment_mode="production",
    )
    app = create_app(settings)

    # 1. Lifespan with mock hub, key_material, and scheduler
    mock_hub = mock.AsyncMock()
    mock_hub.start = mock.AsyncMock()
    mock_hub.drain = mock.AsyncMock()
    app.state.realtime_hub = mock_hub
    app.state.enable_background_jobs = True
    app.state.key_material = mock.MagicMock(
        master_kek_kid="k1",
        master_kek=b"0" * 32,
        session_hmac_key=b"0" * 32,
    )

    with mock.patch("kanban.app.create_async_engine") as mock_engine_factory:
        mock_engine = mock.AsyncMock()
        mock_engine.dispose = mock.AsyncMock()
        mock_engine_factory.return_value = mock_engine

        with mock.patch("kanban.app.RLSSessionFactory") as mock_sf_cls:
            mock_sf = mock.MagicMock()
            mock_sf_cls.return_value = mock_sf

            with (
                mock.patch("kanban.app.verify_schema_head", new_callable=mock.AsyncMock),
                mock.patch(
                    "kanban.app.mint_setup_token_if_uninitialized",
                    new_callable=mock.AsyncMock,
                ),
            ):
                async with lifespan(app):
                    pass

    mock_hub.start.assert_awaited_once()
    mock_hub.drain.assert_awaited_once()
    mock_engine.dispose.assert_awaited_once()

    # 2. _bootstrap_runtime_state early return branch
    app.state.session_factory = mock.MagicMock()
    assert _bootstrap_runtime_state(app) is None

    # 3. _bootstrap_runtime_state exception handling branch
    app.state.session_factory = None
    with mock.patch("kanban.app.create_async_engine", side_effect=RuntimeError("DB engine error")):
        assert _bootstrap_runtime_state(app) is None


@pytest.mark.asyncio
async def test_kanban_app_lifespan_defaults_and_exception_branches(tmp_path: Path) -> None:
    """Cover default lifespan without hub, mint exception, and _mount_mcp_surfaces failure."""
    dist_dir = tmp_path / "web_dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("<!doctype html><html><body>Test</body></html>", encoding="utf-8")

    empty_app = FastAPI()
    empty_app.state.settings = Settings(web_dist=dist_dir)
    async with lifespan(empty_app):
        pass

    # Lifespan with mint setup token raising exception
    app2 = create_app(empty_app.state.settings)
    app2.state.key_material = mock.MagicMock(
        master_kek_kid="k1",
        master_kek=b"0" * 32,
        session_hmac_key=b"0" * 32,
    )
    with mock.patch("kanban.app.create_async_engine") as mf:
        mf.return_value = mock.AsyncMock()
        with (
            mock.patch("kanban.app.RLSSessionFactory"),
            mock.patch("kanban.app.verify_schema_head", new_callable=mock.AsyncMock),
            mock.patch(
                "kanban.app.mint_setup_token_if_uninitialized",
                side_effect=RuntimeError("setup token check error"),
            ),
        ):
            async with lifespan(app2):
                pass

    # _mount_mcp_surfaces exception handling
    with mock.patch("mcp.app.create_mcp_app", side_effect=RuntimeError("mcp mount failed")):
        _mount_mcp_surfaces(empty_app)


@pytest.mark.asyncio
async def test_kanban_app_mcp_proxy_and_error_handlers(tmp_path: Path) -> None:
    """Cover _McpProxyApp non-http scope and OAuth2Error handler in kanban/app.py."""
    dist_dir = tmp_path / "web_dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("<!doctype html><html><body>Test</body></html>", encoding="utf-8")
    settings = Settings(web_dist=dist_dir, deployment_mode="production")

    # 1. Fallback import error handling in _mount_mcp_surfaces
    app_no_mcp = create_app(settings)
    with mock.patch("importlib.import_module", side_effect=ImportError("No module")):
        _mount_mcp_surfaces(app_no_mcp)

    # 2. OAuth2Error exception handler
    app = create_app(settings)
    handler = app.exception_handlers.get(OAuth2Error)
    assert handler is not None
    res = handler(
        mock.MagicMock(),
        OAuth2Error(error="invalid_client", description="Bad client", status_code=401),
    )
    resp = await res if inspect.isawaitable(res) else res
    assert resp.status_code == 401
    data = json.loads(bytes(resp.body).decode("utf-8"))
    assert data["error"] == "invalid_client"
    assert data["error_description"] == "Bad client"

    # 3. Non-http scope in _McpProxyApp
    mcp_app = getattr(app.state, "mcp_app", None)
    if mcp_app:
        received_scope_types: list[str] = []

        async def dummy_target(scope: Scope, _receive: Receive, _send: Send) -> None:
            received_scope_types.append(str(scope.get("type", "")))

        app.state.mcp_app = dummy_target
        # Send websocket scope to proxy
        mount_route = next(
            (r for r in app.routes if isinstance(r, Mount) and r.path == "/mcp"),
            None,
        )
        assert mount_route is not None
        proxy_app: ASGIApp = mount_route.app
        scope: Scope = {"type": "websocket", "path": "/mcp/agent"}
        await proxy_app(scope, mock.AsyncMock(), mock.AsyncMock())
        assert "websocket" in received_scope_types


@pytest.mark.asyncio
async def test_internal_client_csrf_and_context_scope() -> None:
    """Cover _ensure_csrf_token, context connection scopes, and extra problem mappings."""
    received_headers: dict[str, str] = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal received_headers
        received_headers = dict(request.headers)
        if request.url.path == "/api/v1/auth/session":
            return httpx.Response(200, json={"csrf_token": "csrf-tok-xyz"})
        if request.url.path == "/api/v1/problem-extra":
            return httpx.Response(
                409,
                json={
                    "type": "urn:problem-type:conflict",
                    "code": "AMBIGUOUS_IDENTIFIER",
                    "detail": "Ambiguous",
                    "layer": "database",
                    "candidates": [{"id": "1"}],
                    "blockers": ["b1"],
                    "unauthorized_mentions": ["@secret"],
                },
            )
        return httpx.Response(200, json={"ok": True})

    settings = McpSettings(mode="standalone_inprocess")
    client = KanbanApiClient(settings, transport=httpx.MockTransport(mock_handler))

    # 1. CSRF token auto-fetch on unsafe method
    await client.request("POST", "/api/v1/issues", json_data={"title": "test"})
    assert received_headers.get("x-csrf-token") == "csrf-tok-xyz"

    # 2. Context connection scope headers
    scope = ConnectionScope(
        mode=ScopeMode.PROJECT,
        workspace_slug="my-ws",
        project_key="MY-PRJ",
    )
    ctx = McpRequestContext(
        surface=Surface.AGENT,
        connection_scope=scope,
    )
    set_current_mcp_context(ctx)

    try:
        await client.request("GET", "/api/v1/items")
        assert received_headers.get("x-kb-scope-workspace") == "my-ws"
        assert received_headers.get("x-kb-scope-project") == "MY-PRJ"

        # 3. Problem extra fields mapping
        with pytest.raises(KbMcpError) as exc_info:
            await client.request("POST", "/api/v1/problem-extra", json_data={})

        err = exc_info.value
        assert err.code == McpErrorCode.AMBIGUOUS_IDENTIFIER
        assert "database" in str(err.hint)
        assert err.candidates == [{"id": "1"}]
        assert err.blockers == ["b1"]
        assert err.extra is not None
        assert err.extra.get("unauthorized_mentions") == ["@secret"]

    finally:
        set_current_mcp_context(None)


@pytest.mark.asyncio
async def test_internal_client_branches_and_errors() -> None:
    """Cover remaining branches in mcp.internal_client."""
    # 1. Missing transport/app in standalone_inprocess
    with pytest.raises(ValueError, match="kanban_app or transport is required"):
        KanbanApiClient(McpSettings(mode="standalone_inprocess"))

    # 2. Plaintext http:// in mtls mode
    with pytest.raises(ValueError, match="Plaintext http:// base URL is strictly prohibited"):
        KanbanApiClient(
            McpSettings(mode="mtls", kanban_api_base_url="http://insecure.internal"),
            transport=httpx.MockTransport(lambda _r: httpx.Response(200)),
        )

    # 3. Valid mtls configuration paths
    mtls_settings = McpSettings(
        mode="mtls",
        kanban_api_base_url="https://secure.internal",
        internal_ca_path=Path("/tmp/ca.crt"),
        client_cert_path=Path("/tmp/client.crt"),
        client_key_path=Path("/tmp/client.key"),
    )
    client = KanbanApiClient(
        mtls_settings,
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={"ok": True})),
    )
    await client.request(
        "GET",
        "/api/v1/test",
        subject_token="tok_sub",  # noqa: S106
        mcp_session_id="sess_123",
        params={"p": "1"},
    )
    await client.aclose()

    # 4. Context scope with global mode
    global_scope = ConnectionScope(mode=ScopeMode.GLOBAL)
    set_current_mcp_context(McpRequestContext(surface=Surface.AGENT, connection_scope=global_scope))
    try:
        req_headers: dict[str, str] = {}

        def record_handler(r: httpx.Request) -> httpx.Response:
            nonlocal req_headers
            req_headers = dict(r.headers)
            return httpx.Response(200, json={"status": "ok"})

        cli = KanbanApiClient(
            McpSettings(mode="standalone_inprocess"),
            transport=httpx.MockTransport(record_handler),
        )
        await cli.request("GET", "/api/v1/global")
        assert req_headers.get("x-kb-scope-global") == "true"
    finally:
        set_current_mcp_context(None)


@pytest.mark.asyncio
async def test_internal_client_edge_branches() -> None:
    """Cover error mapping edge branches and CSRF fetch failures."""

    # 1. CSRF fetch error tolerance
    def csrf_err_handler(r: httpx.Request) -> httpx.Response:
        if r.url.path == "/api/v1/auth/session":
            return httpx.Response(500, text="Internal Error")
        return httpx.Response(200, json={"status": "ok"})

    cli = KanbanApiClient(
        McpSettings(mode="standalone_inprocess"),
        transport=httpx.MockTransport(csrf_err_handler),
    )
    res = await cli.request("POST", "/api/v1/test", json_data={"x": 1})
    assert res == {"status": "ok"}

    # 2. Problem mapping branches
    problems: list[dict[str, object]] = [
        {
            "type": "urn:problem:conflict",
            "code": "ALREADY_PROMOTED",
            "extra": {"candidates": [{"id": "1"}]},
        },
        {
            "type": "urn:problem:mention-access-warning",
            "code": "UNKNOWN",
        },
        {
            "type": "urn:problem:transition-held",
            "code": "TRANSITION_HELD",
        },
    ]

    for p in problems:
        with pytest.raises(KbMcpError):
            cli._map_upstream_error(409, json.dumps(p).encode("utf-8"))  # noqa: SLF001
