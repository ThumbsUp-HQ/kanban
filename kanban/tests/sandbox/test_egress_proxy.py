# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, TC002, ANN401, D103, SLF001, S106, B007, RUF059, TRY003, EM101
"""Tests for TokenInjectingEgressProxy security bounds, policies, and token zeroing (KB-P5-14)."""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from kanban.sandbox.egress_proxy import EgressProxyPolicy, TokenInjectingEgressProxy


def _create_backend_app() -> tuple[Starlette, dict[str, Any]]:
    captured_data: dict[str, Any] = {
        "headers": {},
        "requests": [],
    }

    async def get_issue(request: Request) -> JSONResponse:
        captured_data["headers"] = dict(request.headers)
        captured_data["requests"].append(request.url.path)
        return JSONResponse({"id": "issue-123", "key": "KAN-10", "title": "Test Issue"})

    async def get_large(request: Request) -> Response:
        del request
        # 1 MiB response to test 512 KiB cap
        return Response(content=b"A" * (1024 * 1024), media_type="text/plain")

    routes = [
        Route("/api/v1/issues/KAN-10", get_issue),
        Route("/api/v1/issues/KAN-10/large", get_large),
        Route("/api/v1/issues", get_issue, methods=["POST"]),
        Route("/api/v1/admin/ai/providers", get_issue),
    ]
    return Starlette(routes=routes), captured_data


async def _raw_unix_request(
    socket_path: Path,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """Execute raw HTTP request over Unix stream socket."""
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    req_lines = [f"{method} {path} HTTP/1.1", "Host: test-socket"]
    if headers:
        for k, v in headers.items():
            req_lines.append(f"{k}: {v}")
    req_lines.append("\r\n")
    req_data = "\r\n".join(req_lines).encode("ascii")
    if body:
        req_data += body

    writer.write(req_data)
    await writer.drain()

    # Read response
    status_line = await reader.readline()
    status_str = status_line.decode("ascii", errors="replace").strip()
    status_code = int(status_str.split(" ")[1])

    resp_headers: dict[str, str] = {}
    content_len = None
    while True:
        line = await reader.readline()
        if not line or line in (b"\r\n", b"\n"):
            break
        h_str = line.decode("ascii", errors="replace").strip()
        if ":" in h_str:
            k, v = h_str.split(":", 1)
            resp_headers[k.strip().lower()] = v.strip()
            if k.strip().lower() == "content-length":
                content_len = int(v.strip())

    resp_body = b""
    if content_len is not None:
        resp_body = await reader.readexactly(content_len)
    else:
        resp_body = await reader.read()

    writer.close()
    await writer.wait_closed()
    return status_code, resp_headers, resp_body


@pytest.fixture
def short_tmp_dir() -> Any:
    path = Path(f"/tmp/ks_{uuid.uuid4().hex[:8]}")
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.mark.asyncio
async def test_proxy_positive_flow_and_header_scrubbing(short_tmp_dir: Path) -> None:
    """Test valid allowlisted GET scrubs client auth and injects bearer token and script depth."""
    backend_app, captured = _create_backend_app()
    secret_token = "kb_sec_super_secret_token_12345"
    policy = EgressProxyPolicy(
        egress_allowlist=["/api/v1/issues/KAN-10"],
        max_requests=10,
        timeout_ms=10000,
    )

    proxy = TokenInjectingEgressProxy(
        token=secret_token,
        policy=policy,
        app=backend_app,
        base_dir=short_tmp_dir,
    )

    async with proxy:
        assert proxy.socket_path.exists()
        # Verify permissions 0600 on socket
        assert (proxy.socket_path.stat().st_mode & 0o777) == 0o600

        # Send request with hostile spoofed headers
        status, headers, body = await _raw_unix_request(
            proxy.socket_path,
            "GET",
            "/api/v1/issues/KAN-10",
            headers={
                "Authorization": "Bearer attacker_token",
                "Cookie": "session=attacker_session",
                "X-Forwarded-For": "evil.corp",
                "X-Kanban-Script-Depth": "99",
            },
        )
        assert status == 200
        data = json.loads(body.decode("utf-8"))
        assert data["key"] == "KAN-10"

        # Verify backend received injected headers, not attacker headers
        injected = captured["headers"]
        assert injected["authorization"] == f"Bearer {secret_token}"
        assert injected["x-kanban-script-depth"] == "1"
        assert "cookie" not in injected
        assert "x-forwarded-for" not in injected

    # Verify zero token memory after exit
    assert not any(proxy._token_buf)
    assert not proxy.socket_path.exists()
    assert not proxy.runtime_dir.exists()


@pytest.mark.asyncio
async def test_proxy_policy_method_not_allowed(short_tmp_dir: Path) -> None:
    """Methods other than GET return 405 PROXY_METHOD_NOT_ALLOWED."""
    backend_app, _ = _create_backend_app()
    policy = EgressProxyPolicy(egress_allowlist=["/api/v1/issues*"])

    async with TokenInjectingEgressProxy(
        token="test_tok",
        policy=policy,
        app=backend_app,
        base_dir=short_tmp_dir,
    ) as proxy:
        for m in ("POST", "PUT", "DELETE", "PATCH"):
            status, _, body = await _raw_unix_request(proxy.socket_path, m, "/api/v1/issues")
            assert status == 405
            prob = json.loads(body.decode("utf-8"))
            assert prob["code"] == "PROXY_METHOD_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_proxy_policy_route_not_allowlisted(short_tmp_dir: Path) -> None:
    """Non-allowlisted routes and path traversal attempts return 403 PROXY_ROUTE_NOT_ALLOWLISTED."""
    backend_app, _ = _create_backend_app()
    policy = EgressProxyPolicy(egress_allowlist=["/api/v1/issues/KAN-10"])

    async with TokenInjectingEgressProxy(
        token="test_tok",
        policy=policy,
        app=backend_app,
        base_dir=short_tmp_dir,
    ) as proxy:
        # Route not in allowlist
        status, _, body = await _raw_unix_request(
            proxy.socket_path, "GET", "/api/v1/admin/ai/providers"
        )
        assert status == 403
        assert json.loads(body)["code"] == "PROXY_ROUTE_NOT_ALLOWLISTED"

        # Path traversal with ..
        status2, _, body2 = await _raw_unix_request(
            proxy.socket_path, "GET", "/api/v1/issues/KAN-10/../../admin/ai/providers"
        )
        assert status2 == 403
        assert json.loads(body2)["code"] == "PROXY_ROUTE_NOT_ALLOWLISTED"

        # Path traversal with %2e%2e
        status3, _, body3 = await _raw_unix_request(
            proxy.socket_path, "GET", "/api/v1/issues/KAN-10/%2e%2e/%2e%2e/admin/ai/providers"
        )
        assert status3 == 403
        assert json.loads(body3)["code"] == "PROXY_ROUTE_NOT_ALLOWLISTED"


@pytest.mark.asyncio
async def test_proxy_max_requests_budget(short_tmp_dir: Path) -> None:
    """11th request when max_requests=10 returns 429 PROXY_MAX_REQUESTS_EXCEEDED."""
    backend_app, _ = _create_backend_app()
    policy = EgressProxyPolicy(egress_allowlist=["/api/v1/issues/KAN-10"], max_requests=10)

    async with TokenInjectingEgressProxy(
        token="test_tok",
        policy=policy,
        app=backend_app,
        base_dir=short_tmp_dir,
    ) as proxy:
        for i in range(10):
            st, _, _ = await _raw_unix_request(proxy.socket_path, "GET", "/api/v1/issues/KAN-10")
            assert st == 200

        # 11th request fails
        st11, _, body11 = await _raw_unix_request(proxy.socket_path, "GET", "/api/v1/issues/KAN-10")
        assert st11 == 429
        assert json.loads(body11)["code"] == "PROXY_MAX_REQUESTS_EXCEEDED"


@pytest.mark.asyncio
async def test_proxy_token_expiry(short_tmp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Request after expiration returns 401 PROXY_TOKEN_EXPIRED."""
    backend_app, _ = _create_backend_app()
    policy = EgressProxyPolicy(egress_allowlist=["/api/v1/issues/KAN-10"], timeout_ms=5000)

    proxy = TokenInjectingEgressProxy(
        token="test_tok",
        policy=policy,
        app=backend_app,
        base_dir=short_tmp_dir,
    )

    async with proxy:
        # Fast-forward monotonic clock past token expiry
        real_monotonic = time.monotonic
        monkeypatch.setattr(time, "monotonic", lambda: real_monotonic() + 16.0)

        st, _, body = await _raw_unix_request(proxy.socket_path, "GET", "/api/v1/issues/KAN-10")
        assert st == 401
        assert json.loads(body)["code"] == "PROXY_TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_proxy_caps_response_body_at_512kib(short_tmp_dir: Path) -> None:
    """Response payload streaming is capped at 512 KiB."""
    backend_app, _ = _create_backend_app()
    policy = EgressProxyPolicy(egress_allowlist=["/api/v1/issues/KAN-10/large"])

    async with TokenInjectingEgressProxy(
        token="test_tok",
        policy=policy,
        app=backend_app,
        base_dir=short_tmp_dir,
    ) as proxy:
        st, _, body = await _raw_unix_request(
            proxy.socket_path, "GET", "/api/v1/issues/KAN-10/large"
        )
        assert st == 200
        assert len(body) == 524288  # exactly 512 KiB


@pytest.mark.asyncio
async def test_proxy_path_traversal_and_malformed_targets(short_tmp_dir: Path) -> None:
    """Path traversal, authority URLs, invalid characters and unallowlisted routes fail with 403."""
    backend_app, _ = _create_backend_app()
    policy = EgressProxyPolicy(
        egress_allowlist=["/api/v1/issues/KAN-10", "/api/v1/issues/KAN-10/*"]
    )

    async with TokenInjectingEgressProxy(
        token="test_tok",
        policy=policy,
        app=backend_app,
        base_dir=short_tmp_dir,
    ) as proxy:
        # 1. Backslash in path
        st1, _, _ = await _raw_unix_request(proxy.socket_path, "GET", "/api/v1/issues\\evil")
        assert st1 == 403

        # 2. Authority URL
        st2, _, _ = await _raw_unix_request(
            proxy.socket_path, "GET", "http://evil.com/api/v1/issues/KAN-10"
        )
        assert st2 == 403

        # 3. Path traversal .. and %2e
        st3, _, _ = await _raw_unix_request(
            proxy.socket_path, "GET", "/api/v1/issues/KAN-10/../../admin"
        )
        assert st3 == 403

        st4, _, _ = await _raw_unix_request(proxy.socket_path, "GET", "/api/v1/issues/%2e%2e/admin")
        assert st4 == 403

        # 4. Route not under /api/v1/
        st5, _, _ = await _raw_unix_request(proxy.socket_path, "GET", "/api/v2/issues/KAN-10")
        assert st5 == 403

        # 5. Route with query string (valid)
        st6, _, _ = await _raw_unix_request(
            proxy.socket_path, "GET", "/api/v1/issues/KAN-10?fields=summary"
        )
        assert st6 == 200


@pytest.mark.asyncio
async def test_proxy_malformed_and_empty_requests(short_tmp_dir: Path) -> None:
    """Empty connection or malformed request line returns 400 Bad Request."""
    backend_app, _ = _create_backend_app()
    policy = EgressProxyPolicy(egress_allowlist=["/api/v1/issues/KAN-10"])

    async with TokenInjectingEgressProxy(
        token="test_tok",
        policy=policy,
        app=backend_app,
        base_dir=short_tmp_dir,
    ) as proxy:
        # 1. Empty connection
        reader, writer = await asyncio.open_unix_connection(str(proxy.socket_path))
        writer.close()
        await writer.wait_closed()

        # 2. Malformed HTTP request line (single token)
        reader, writer = await asyncio.open_unix_connection(str(proxy.socket_path))
        writer.write(b"MALFORMED_LINE\r\n\r\n")
        await writer.drain()
        resp_data = await reader.read(4096)
        writer.close()
        await writer.wait_closed()
        assert b"400" in resp_data


@pytest.mark.asyncio
async def test_proxy_zero_token_direct(short_tmp_dir: Path) -> None:
    """Directly calling zero_token renders get_active_token None."""
    backend_app, _ = _create_backend_app()
    proxy = TokenInjectingEgressProxy(
        token="super_secret",
        policy=EgressProxyPolicy(),
        app=backend_app,
        base_dir=short_tmp_dir,
    )
    assert proxy._get_active_token() == "super_secret"
    proxy.zero_token()
    assert proxy._get_active_token() is None


@pytest.mark.asyncio
async def test_proxy_backend_internal_error_handling(short_tmp_dir: Path) -> None:
    """Proxy catches backend app exceptions and returns 500 PROXY_INTERNAL_ERROR."""

    async def broken_app(scope: Any, receive: Any, send: Any) -> None:
        del scope, receive, send
        raise RuntimeError("Fatal ASGI internal error")

    policy = EgressProxyPolicy(egress_allowlist=["/api/v1/issues/KAN-10"])
    async with TokenInjectingEgressProxy(
        token="test_tok",
        policy=policy,
        app=broken_app,
        base_dir=short_tmp_dir,
    ) as proxy:
        st, _, body = await _raw_unix_request(proxy.socket_path, "GET", "/api/v1/issues/KAN-10")
        assert st == 500
        assert json.loads(body)["code"] == "PROXY_INTERNAL_ERROR"


@pytest.mark.asyncio
async def test_proxy_without_app(short_tmp_dir: Path) -> None:
    """Proxy initialized without ASGI app creates standard AsyncClient."""
    proxy = TokenInjectingEgressProxy(
        token="tok",
        policy=EgressProxyPolicy(),
        base_dir=short_tmp_dir,
    )
    await proxy.start()
    assert proxy.socket_path.exists()
    await proxy.stop()
    assert not proxy.socket_path.exists()


@pytest.mark.asyncio
async def test_proxy_coverage_branches(short_tmp_dir: Path) -> None:
    """Cover edge cases: base_dir None, request_count, existing socket unlink, _http_client None, normalization mismatch."""
    # 1. base_dir is None
    proxy_default = TokenInjectingEgressProxy(
        token="tok",
        policy=EgressProxyPolicy(),
        base_dir=None,
    )
    assert proxy_default.runtime_dir.parent.name == "sandbox"
    assert proxy_default.request_count == 0

    # 2. Existing socket unlink on start
    existing_sock_dir = short_tmp_dir / "existing"
    existing_sock_dir.mkdir(parents=True, exist_ok=True)
    fake_sock = existing_sock_dir / "proxy.sock"
    fake_sock.touch()
    assert fake_sock.exists()

    proxy_existing = TokenInjectingEgressProxy(
        token="tok",
        policy=EgressProxyPolicy(),
        base_dir=short_tmp_dir,
        invocation_id=uuid.UUID(hex="00000000000000000000000000000001"),
    )
    proxy_existing.runtime_dir = existing_sock_dir
    proxy_existing.socket_path = fake_sock
    await proxy_existing.start()
    await proxy_existing.stop()

    # 3. _http_client is None when processing request -> 503 UPSTREAM_UNAVAILABLE
    backend_app, _ = _create_backend_app()
    proxy_no_client = TokenInjectingEgressProxy(
        token="tok",
        policy=EgressProxyPolicy(egress_allowlist=["/api/v1/issues/KAN-10"]),
        app=backend_app,
        base_dir=short_tmp_dir,
    )
    async with proxy_no_client:
        proxy_no_client._http_client = None
        st, _, body = await _raw_unix_request(
            proxy_no_client.socket_path, "GET", "/api/v1/issues/KAN-10"
        )
        assert st == 503
        assert json.loads(body)["code"] == "UPSTREAM_UNAVAILABLE"

    # 4. Path normalization mismatch
    async with TokenInjectingEgressProxy(
        token="tok",
        policy=EgressProxyPolicy(egress_allowlist=["/api/v1/*"]),
        app=backend_app,
        base_dir=short_tmp_dir,
    ) as proxy_norm:
        st, _, _ = await _raw_unix_request(proxy_norm.socket_path, "GET", "/api/v1/issues//KAN-10")
        assert st == 403


@pytest.mark.parametrize(
    "target",
    [
        "/api/v1/issues/a%2Fadmin",
        "/api/v1/issues/a%2fadmin",
        "/api/v1/issues/a%00b",
        "/api/v1/issues/a%5cb",
        "/api/v1/issues/a%5Cb",
        "/api/v1/issues/%2e%2e/admin",
        "/api/v1/issues/a%252Fb",
        "/api/v1/issues/a\\b",
        "/api/v1/issues/a/b/c",
        "/api/v1/issues/",
    ],
)
def test_validate_path_rejects_encoded_and_spanning(target: str) -> None:
    proxy = TokenInjectingEgressProxy(
        token="t" * 24,
        policy=EgressProxyPolicy(egress_allowlist=["/api/v1/issues/*"]),
    )
    ok, _, _ = proxy._validate_path(target)
    assert ok is False
    proxy.zero_token()


def test_validate_path_segment_aware_allows_single_segment() -> None:
    proxy = TokenInjectingEgressProxy(
        token="t" * 24,
        policy=EgressProxyPolicy(egress_allowlist=["/api/v1/issues/*"]),
    )
    ok, _, target = proxy._validate_path("/api/v1/issues/KAN-10?x=1")
    assert ok is True
    assert target == "/api/v1/issues/KAN-10?x=1"
    proxy.zero_token()


def test_validate_path_rejects_decoded_control_chars() -> None:
    proxy = TokenInjectingEgressProxy(
        token="t" * 24,
        policy=EgressProxyPolicy(egress_allowlist=["/api/v1/issues/*"]),
    )
    ok, _, _ = proxy._validate_path("/api/v1/issues/a%0Ab")
    assert ok is False
    proxy.zero_token()


async def _send_raw(socket_path: Path, data: bytes) -> bytes:
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    writer.write(data)
    await writer.drain()
    out = await reader.read(65536)
    writer.close()
    await writer.wait_closed()
    return out


@pytest.mark.asyncio
async def test_proxy_rejects_oversized_request_line(short_tmp_dir: Path) -> None:
    backend_app, _ = _create_backend_app()
    policy = EgressProxyPolicy(egress_allowlist=["/api/v1/issues/KAN-10"], timeout_ms=10000)
    async with TokenInjectingEgressProxy(
        token="kb_sec_tok_1234567890abcdef", policy=policy, app=backend_app, base_dir=short_tmp_dir
    ) as proxy:
        out = await _send_raw(proxy.socket_path, b"GET /" + b"a" * 5000 + b" HTTP/1.1\r\n\r\n")
    assert b" 414 " in out.split(b"\r\n", 1)[0]


@pytest.mark.asyncio
async def test_proxy_rejects_too_many_headers(short_tmp_dir: Path) -> None:
    backend_app, _ = _create_backend_app()
    policy = EgressProxyPolicy(egress_allowlist=["/api/v1/issues/KAN-10"], timeout_ms=10000)
    headers = b"".join(b"X-H%d: v\r\n" % i for i in range(100))
    async with TokenInjectingEgressProxy(
        token="kb_sec_tok_1234567890abcdef", policy=policy, app=backend_app, base_dir=short_tmp_dir
    ) as proxy:
        out = await _send_raw(
            proxy.socket_path, b"GET /api/v1/issues/KAN-10 HTTP/1.1\r\n" + headers + b"\r\n"
        )
    assert b" 431 " in out.split(b"\r\n", 1)[0]


@pytest.mark.asyncio
async def test_proxy_rejects_oversized_header_bytes(short_tmp_dir: Path) -> None:
    backend_app, _ = _create_backend_app()
    policy = EgressProxyPolicy(egress_allowlist=["/api/v1/issues/KAN-10"], timeout_ms=10000)
    headers = b"".join(b"X-H%d: %s\r\n" % (i, b"v" * 3000) for i in range(8))
    async with TokenInjectingEgressProxy(
        token="kb_sec_tok_1234567890abcdef", policy=policy, app=backend_app, base_dir=short_tmp_dir
    ) as proxy:
        out = await _send_raw(
            proxy.socket_path, b"GET /api/v1/issues/KAN-10 HTTP/1.1\r\n" + headers + b"\r\n"
        )
    assert b" 431 " in out.split(b"\r\n", 1)[0]


@pytest.mark.asyncio
async def test_proxy_stalled_client_times_out(short_tmp_dir: Path) -> None:
    backend_app, _ = _create_backend_app()
    policy = EgressProxyPolicy(egress_allowlist=["/api/v1/issues/KAN-10"], timeout_ms=100)
    async with TokenInjectingEgressProxy(
        token="kb_sec_tok_1234567890abcdef", policy=policy, app=backend_app, base_dir=short_tmp_dir
    ) as proxy:
        # Send request line and never finish headers: handler must be cut off.
        out = await _send_raw(proxy.socket_path, b"GET /api/v1/issues/KAN-10 HTTP/1.1\r\n")
    assert b" 408 " in out.split(b"\r\n", 1)[0]


@pytest.mark.asyncio
async def test_proxy_500_does_not_echo_exception(short_tmp_dir: Path) -> None:
    async def boom(*_args: Any) -> None:
        raise RuntimeError("SECRET_INTERNAL_DETAIL")

    policy = EgressProxyPolicy(egress_allowlist=["/api/v1/issues/KAN-10"], timeout_ms=10000)
    async with TokenInjectingEgressProxy(
        token="kb_sec_tok_1234567890abcdef", policy=policy, app=boom, base_dir=short_tmp_dir
    ) as proxy:
        status, _, body = await _raw_unix_request(proxy.socket_path, "GET", "/api/v1/issues/KAN-10")
    assert status == 500
    assert b"SECRET_INTERNAL_DETAIL" not in body
