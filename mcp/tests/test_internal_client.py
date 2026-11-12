# Copyright 2026 Kanban Platform Contributors
"""Tests for internal KanbanApiClient mTLS, timeouts, and error mapping."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest

from mcp.errors import KbMcpError, McpErrorCode
from mcp.internal_client import KanbanApiClient
from mcp.settings import McpSettings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


@pytest.mark.asyncio
async def test_case_5_upstream_problem_status_mapping() -> None:
    """Test Case 5: MockTransport status codes 404, 409, 412, 422, 429, 503 map to McpErrorCode."""
    scenarios: list[tuple[int, dict[str, Any], McpErrorCode]] = [
        (404, {"title": "Issue Not Found", "detail": "Issue 42 not found"}, McpErrorCode.NOT_FOUND),
        (
            409,
            {"type": "urn:problem-type:etag-mismatch", "detail": "Stale version"},
            McpErrorCode.CONFLICT_ETAG,
        ),
        (
            409,
            {"type": "urn:problem-type:conflict", "detail": "Key duplicate"},
            McpErrorCode.VALIDATION_FAILED,
        ),
        (412, {"detail": "Precondition failed"}, McpErrorCode.CONFLICT_ETAG),
        (422, {"detail": "Validation error"}, McpErrorCode.VALIDATION_FAILED),
        (429, {"detail": "Too many requests"}, McpErrorCode.RATE_LIMITED),
        (503, {"detail": "Service unavailable"}, McpErrorCode.UPSTREAM_UNAVAILABLE),
    ]

    for status_code, problem_json, expected_code in scenarios:
        captured_headers: dict[str, str] = {}

        def _handler(
            request: httpx.Request,
            *,
            code: int = status_code,
            prob: dict[str, Any] = problem_json,
        ) -> httpx.Response:
            nonlocal captured_headers
            captured_headers = dict(request.headers)
            return httpx.Response(
                code,
                headers={"content-type": "application/problem+json"},
                json=prob,
            )

        transport = httpx.MockTransport(_handler)
        settings = McpSettings(mode="standalone_inprocess")
        client = KanbanApiClient(settings, transport=transport)

        with pytest.raises(KbMcpError) as exc_info:
            await client.request(
                "GET",
                "/api/test",
                subject_token="kb_usr_12345",  # noqa: S106
                mcp_session_id="sess_abcde",
            )

        assert exc_info.value.code == expected_code
        assert exc_info.value.message == problem_json["detail"]
        assert captured_headers.get("x-kb-subject-token") == "kb_usr_12345"
        assert captured_headers.get("x-kb-mcp-session") == "sess_abcde"
        await client.aclose()


@pytest.mark.asyncio
async def test_case_5_plaintext_http_rejected_in_mtls_mode() -> None:
    """Test Case 5: Plaintext http:// base URL in mode='mtls' raises ValueError."""
    settings = McpSettings(
        mode="mtls",
        kanban_api_base_url="http://insecure-api.local",
    )
    with pytest.raises(ValueError, match="Plaintext http:// base URL is strictly prohibited"):
        KanbanApiClient(settings)


@pytest.mark.asyncio
async def test_standalone_inprocess_missing_app_raises() -> None:
    """Verify standalone_inprocess mode raises ValueError if no app or transport given."""
    settings = McpSettings(mode="standalone_inprocess")
    with pytest.raises(ValueError, match="kanban_app or transport is required"):
        KanbanApiClient(settings, kanban_app=None, transport=None)


@pytest.mark.asyncio
async def test_case_5_oversized_response_stream_aborts() -> None:
    """Test Case 5: Response body exceeding 8 MiB raises UPSTREAM_ERROR."""
    # 9 MiB streaming response
    chunk_size = 1024 * 1024  # 1 MiB
    total_chunks = 9

    async def _stream_generator() -> AsyncIterator[bytes]:
        for _ in range(total_chunks):
            yield b"a" * chunk_size

    def _stream_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_stream_generator())

    transport = httpx.MockTransport(_stream_handler)
    settings = McpSettings(mode="standalone_inprocess", response_body_limit_bytes=8 * 1024 * 1024)
    client = KanbanApiClient(settings, transport=transport)

    with pytest.raises(KbMcpError) as exc_info:
        await client.request("GET", "/api/big-stream")

    assert exc_info.value.code == McpErrorCode.UPSTREAM_ERROR
    assert "exceeds limit" in exc_info.value.message
    await client.aclose()


@pytest.mark.asyncio
async def test_successful_request_and_context_manager() -> None:
    """Verify successful response parsing and async context manager support."""

    def _ok_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/json":
            return httpx.Response(200, json={"status": "ok", "items": [1, 2, 3]})
        if request.url.path == "/api/empty":
            return httpx.Response(204)
        return httpx.Response(200, text="plain string text")

    transport = httpx.MockTransport(_ok_handler)
    settings = McpSettings(mode="standalone_inprocess")

    async with KanbanApiClient(settings, transport=transport) as client:
        # JSON response
        data = await client.request("GET", "/api/json")
        assert data == {"status": "ok", "items": [1, 2, 3]}

        # Empty 204
        empty = await client.request("GET", "/api/empty")
        assert empty is None

        # Text response
        text_resp = await client.request("GET", "/api/text")
        assert text_resp == "plain string text"


@pytest.mark.asyncio
async def test_network_transport_error_maps_to_upstream_unavailable() -> None:
    """Verify httpx.TransportError maps to McpErrorCode.UPSTREAM_UNAVAILABLE."""

    def _failing_handler(_request: httpx.Request) -> httpx.Response:
        msg = "Connection refused by upstream daemon"
        raise httpx.ConnectError(msg)

    transport = httpx.MockTransport(_failing_handler)
    settings = McpSettings(mode="standalone_inprocess")
    client = KanbanApiClient(settings, transport=transport)

    with pytest.raises(KbMcpError) as exc_info:
        await client.request("GET", "/api/down")

    assert exc_info.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE
    assert "Upstream communication failure" in exc_info.value.message
    await client.aclose()


@pytest.mark.asyncio
async def test_mtls_client_initialization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify mTLS client initializes correctly with certs and ca."""
    ca_file = tmp_path / "ca.crt"
    ca_file.write_text("dummy ca", encoding="utf-8")
    cert_file = tmp_path / "client.crt"
    cert_file.write_text("dummy cert", encoding="utf-8")
    key_file = tmp_path / "client.key"
    key_file.write_text("dummy key", encoding="utf-8")

    captured_kwargs: dict[str, Any] = {}

    class MockAsyncClient:
        def __init__(self, **kwargs: object) -> None:
            nonlocal captured_kwargs
            captured_kwargs = kwargs

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    settings = McpSettings(
        mode="mtls",
        kanban_api_base_url="https://127.0.0.1:8443",
        internal_ca_path=ca_file,
        client_cert_path=cert_file,
        client_key_path=key_file,
    )
    client = KanbanApiClient(settings)
    assert client.settings.mode == "mtls"
    assert captured_kwargs["http2"] is True
    assert captured_kwargs["verify"] == str(ca_file)
    assert captured_kwargs["cert"] == (str(cert_file), str(key_file))
    assert captured_kwargs["base_url"] == "https://127.0.0.1:8443"
    await client.aclose()

    # Verify initialization with defaults (verify=True, cert=None)
    monkeypatch.undo()
    real_settings = McpSettings(
        mode="mtls",
        kanban_api_base_url="https://127.0.0.1:8443",
    )
    real_client = KanbanApiClient(real_settings)
    assert real_client.settings.mode == "mtls"
    await real_client.aclose()


@pytest.mark.asyncio
async def test_upstream_fallback_error_mapping() -> None:
    """Verify non-standard HTTP 400 and unparseable body fallback to UPSTREAM_ERROR."""

    def _bad_body_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/not-json":
            return httpx.Response(404, content=b"Raw text 404")
        if request.url.path == "/api/empty-503":
            return httpx.Response(503, content=b"")
        if request.url.path == "/api/json-list":
            return httpx.Response(400, content=b"[1, 2, 3]")
        return httpx.Response(400, content=b"{not valid json")

    transport = httpx.MockTransport(_bad_body_handler)
    settings = McpSettings(mode="standalone_inprocess")
    async with KanbanApiClient(settings, transport=transport) as client:
        # Non-JSON 404
        with pytest.raises(KbMcpError) as exc_404:
            await client.request("GET", "/api/not-json")
        assert exc_404.value.code == McpErrorCode.NOT_FOUND
        assert "404" in exc_404.value.message

        # Empty 503
        with pytest.raises(KbMcpError) as exc_503:
            await client.request("GET", "/api/empty-503")
        assert exc_503.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE
        assert "503" in exc_503.value.message

        # JSON list 400
        with pytest.raises(KbMcpError) as exc_list:
            await client.request("GET", "/api/json-list")
        assert exc_list.value.code == McpErrorCode.UPSTREAM_ERROR

        # Fallback 400
        with pytest.raises(KbMcpError) as exc_400:
            await client.request("GET", "/api/fallback-400")
        assert exc_400.value.code == McpErrorCode.UPSTREAM_ERROR
        assert "400" in exc_400.value.message

    # Also verify transport in mtls mode
    mtls_settings = McpSettings(
        mode="mtls",
        kanban_api_base_url="https://api.internal:8443",
    )
    async with KanbanApiClient(mtls_settings, transport=transport) as mtls_client:
        with pytest.raises(KbMcpError) as exc_mtls:
            await mtls_client.request("GET", "/api/empty-503")
        assert exc_mtls.value.code == McpErrorCode.UPSTREAM_UNAVAILABLE
