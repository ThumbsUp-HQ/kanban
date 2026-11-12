"""Unit tests for ASGI RequestIdMiddleware, request ID validation, and log filter (S3.4)."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from kanban.api.request_id import (
    RequestIdFilter,
    RequestIdMiddleware,
    get_request_id,
)
from kanban.app import create_app
from kanban.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, MutableMapping
    from pathlib import Path

    from starlette.types import Receive, Scope, Send

_HEX_32_REGEX = re.compile(r"^[0-9a-f]{32}$")


@pytest.fixture
def api_settings(tmp_path: Path) -> Settings:
    """Fixture providing isolated settings with dummy web_dist directory."""
    dist_dir = tmp_path / "web_dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("<!doctype html><html><body>Test</body></html>", encoding="utf-8")
    return Settings(
        web_dist=dist_dir,
        deployment_mode="production",
    )


def test_get_request_id_fallback() -> None:
    """Test get_request_id generates a fallback 32-hex ID when contextvar is empty."""
    val = get_request_id()
    assert isinstance(val, str)
    assert _HEX_32_REGEX.match(val)


def test_request_id_log_filter() -> None:
    """Test RequestIdFilter injects request_id attribute into log records."""
    log_filter = RequestIdFilter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )
    result = log_filter.filter(record)
    assert result is True
    assert hasattr(record, "request_id")
    assert isinstance(record.request_id, str)
    assert len(record.request_id) >= 8


@pytest.mark.asyncio
async def test_case_1_healthz_generates_32_hex_id(api_settings: Settings) -> None:
    """Test Case 1: GET /api/v1/healthz returns 200 with generated 32-hex X-Request-ID."""
    app = create_app(api_settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        req_id = response.headers.get("x-request-id")
        assert req_id is not None
        assert _HEX_32_REGEX.match(req_id)

        # Test compatibility alias /api/v1/health
        alias_response = await client.get("/api/v1/health")
        assert alias_response.status_code == 200
        assert alias_response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_case_7_security_request_id_log_injection(api_settings: Settings) -> None:
    """Test Case 7: Malformed or hostile inbound X-Request-ID headers are replaced."""
    app = create_app(api_settings)

    hostile_inbound_raw = [
        b"abc\r\nX-Evil: 1",
        b"a" * 65,
        b"short",
        "ä-unicode-id-12".encode(),
        b"invalid spaces in id",
        b"req#with@symbols!",
        b"\xff\xfe\xfd",
    ]

    def _make_send(
        messages: list[MutableMapping[str, Any]],
    ) -> Callable[[MutableMapping[str, Any]], Awaitable[None]]:
        async def _send(msg: MutableMapping[str, Any]) -> None:
            messages.append(msg)

        return _send

    for bad_raw in hostile_inbound_raw:
        sent_messages: list[MutableMapping[str, Any]] = []

        async def dummy_receive() -> dict[str, Any]:
            return {"type": "http.request"}

        dummy_send = _make_send(sent_messages)

        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/healthz",
            "raw_path": b"/api/v1/healthz",
            "query_string": b"",
            "headers": [(b"x-request-id", bad_raw)],
            "client": ("127.0.0.1", 12345),
            "server": ("localhost", 80),
        }

        middleware = RequestIdMiddleware(app)
        await middleware(scope, dummy_receive, dummy_send)

        # Check response headers from http.response.start
        start_msg = next(m for m in sent_messages if m["type"] == "http.response.start")
        headers_dict = {k.lower(): v.decode("ascii") for k, v in start_msg["headers"]}
        outbound_id = headers_dict.get(b"x-request-id")
        assert outbound_id is not None
        assert outbound_id.encode("ascii") != bad_raw
        assert _HEX_32_REGEX.match(outbound_id)

    # Valid inbound ID is preserved and echoed unchanged via httpx
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        valid_id = "req-0123456789"
        valid_res = await client.get("/api/v1/healthz", headers={"X-Request-ID": valid_id})
        assert valid_res.status_code == 200
        assert valid_res.headers.get("x-request-id") == valid_id


@pytest.mark.asyncio
async def test_non_http_scope_passthrough() -> None:
    """Test RequestIdMiddleware passes non-http scopes through cleanly."""
    called = False

    async def dummy_app(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal called
        called = True
        del scope, receive, send

    middleware = RequestIdMiddleware(dummy_app)
    scope: Scope = {"type": "lifespan"}

    async def dummy_receive() -> dict[str, object]:
        return {}

    async def dummy_send(msg: object) -> None:
        del msg

    await middleware(scope, dummy_receive, dummy_send)
    assert called is True
