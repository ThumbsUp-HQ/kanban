# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: TC002, ANN401
"""Tests for ScriptDepthGuardMiddleware recursion prevention (KB-P5-14, S13.3)."""

from __future__ import annotations

from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import Receive, Scope, Send

from kanban.api.middleware.script_depth import ScriptDepthGuardMiddleware


def _create_test_app() -> Starlette:
    async def get_issue(request: Request) -> JSONResponse:
        return JSONResponse(
            {"key": request.path_params["key"], "depth": request.state.script_depth}
        )

    async def execute_cf(request: Request) -> JSONResponse:
        del request
        return JSONResponse({"executed": True})

    async def transition(request: Request) -> JSONResponse:
        del request
        return JSONResponse({"transitioned": True})

    async def mcp_surface(request: Request) -> JSONResponse:
        return JSONResponse({"surface": request.path_params["surface"]})

    async def get_custom_fields(request: Request) -> JSONResponse:
        depth = request.state.script_depth
        return JSONResponse({"cached_only": depth >= 1, "depth": depth})

    routes = [
        Route("/api/v1/issues/{key}", get_issue),
        Route("/api/v1/issues/{key}/custom-fields/{cf}/execute", execute_cf, methods=["POST"]),
        Route("/api/v1/issues/{key}/transitions", transition, methods=["POST"]),
        Route("/mcp/{surface}", mcp_surface),
        Route("/api/v1/issues/{key}/custom-fields", get_custom_fields),
    ]

    return Starlette(
        routes=routes,
        middleware=[Middleware(ScriptDepthGuardMiddleware)],
    )


def test_depth_header_absent_allows_access() -> None:
    """Absent depth header sets script_depth=0 and allows all endpoints."""
    client = TestClient(_create_test_app())
    res = client.get("/api/v1/issues/KAN-1")
    assert res.status_code == 200
    assert res.json()["depth"] == 0

    res_post = client.post("/api/v1/issues/KAN-1/custom-fields/cf-1/execute")
    assert res_post.status_code == 200
    assert res_post.json()["executed"] is True


def test_depth_header_zero_allows_access() -> None:
    """Depth header 0 sets script_depth=0 and allows execution."""
    client = TestClient(_create_test_app())
    res = client.post(
        "/api/v1/issues/KAN-1/custom-fields/cf-1/execute",
        headers={"X-Kanban-Script-Depth": "0"},
    )
    assert res.status_code == 200
    assert res.json()["executed"] is True


def test_depth_header_one_blocks_execute() -> None:
    """Depth header >= 1 blocks custom field execution with 409 SCRIPT_RECURSION_BLOCKED."""
    client = TestClient(_create_test_app())
    res = client.post(
        "/api/v1/issues/KAN-1/custom-fields/cf-1/execute",
        headers={"X-Kanban-Script-Depth": "1"},
    )
    assert res.status_code == 409
    body = res.json()
    assert body["code"] == "SCRIPT_RECURSION_BLOCKED"
    assert "depth '1'" in body["detail"]


def test_depth_header_blocks_transitions() -> None:
    """Depth header >= 1 blocks workflow state transitions."""
    client = TestClient(_create_test_app())
    res = client.post(
        "/api/v1/issues/KAN-1/transitions",
        headers={"X-Kanban-Script-Depth": "2"},
    )
    assert res.status_code == 409
    body = res.json()
    assert body["code"] == "SCRIPT_RECURSION_BLOCKED"


def test_depth_header_blocks_mcp() -> None:
    """Depth header >= 1 blocks MCP access."""
    client = TestClient(_create_test_app())
    res = client.get(
        "/mcp/agent",
        headers={"X-Kanban-Script-Depth": "1"},
    )
    assert res.status_code == 409
    assert res.json()["code"] == "SCRIPT_RECURSION_BLOCKED"


def test_depth_header_non_digit_fails_closed() -> None:
    """Non-digit depth header fails closed as blocked."""
    client = TestClient(_create_test_app())
    res = client.get(
        "/mcp/admin",
        headers={"X-Kanban-Script-Depth": "evil_inject"},
    )
    assert res.status_code == 409
    assert res.json()["code"] == "SCRIPT_RECURSION_BLOCKED"


def test_depth_header_cached_custom_fields() -> None:
    """GET custom-fields exposes script_depth to return cached values when depth >= 1."""
    client = TestClient(_create_test_app())
    res = client.get(
        "/api/v1/issues/KAN-1/custom-fields",
        headers={"X-Kanban-Script-Depth": "1"},
    )
    assert res.status_code == 200
    assert res.json()["cached_only"] is True
    assert res.json()["depth"] == 1


@pytest.mark.asyncio
async def test_non_http_scope_passthrough() -> None:
    """Lifespan or websocket scopes pass through unchanged."""
    called = False

    async def dummy_app(scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive, send
        nonlocal called
        called = True

    async def dummy_receive() -> dict[str, Any]:
        return {}

    async def dummy_send(message: Any) -> None:
        del message

    mw = ScriptDepthGuardMiddleware(dummy_app)
    await mw({"type": "lifespan"}, dummy_receive, dummy_send)
    assert called is True


@pytest.mark.asyncio
async def test_non_ascii_header_and_missing_state_scope() -> None:
    """Non-ASCII byte in X-Kanban-Script-Depth header and scope without state handled cleanly."""
    called = False

    async def dummy_app(scope: Scope, receive: Receive, send: Send) -> None:
        del receive, send
        nonlocal called
        called = True
        assert scope["state"]["script_depth"] == 1

    async def dummy_receive() -> dict[str, Any]:
        return {}

    async def dummy_send(message: Any) -> None:
        del message

    mw = ScriptDepthGuardMiddleware(dummy_app)
    # Scope without "state" key, and raw header with invalid non-ascii bytes
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/issues/KAN-1",
        "headers": [(b"x-kanban-script-depth", b"\xff\xfe\xfd")],
    }
    await mw(scope, dummy_receive, dummy_send)
    assert called is True
