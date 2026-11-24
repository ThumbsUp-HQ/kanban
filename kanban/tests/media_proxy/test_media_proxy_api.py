"""Unit tests for media proxy API endpoint, HMAC gating, and rate limiting (S5.4, S10.2)."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.app import create_app
from kanban.media_proxy.client import (
    MAX_PROXY_BYTES,
    DefaultPinnedConnectionTransport,
    PinnedTlsMediaClient,
    _parse_status_code,
    _validate_content_type_and_length,
    _verify_magic_signature,
)
from kanban.media_proxy.placeholder import (
    AIR_GAP_PLACEHOLDER_PNG,
    AIR_GAP_STATUS_HEADER,
    DefaultAirGapChecker,
)
from kanban.media_proxy.service import MediaProxyService
from kanban.media_proxy.signing import (
    _validate_host,
    sign_media_proxy_url,
    validate_external_image_url,
    verify_media_proxy_url,
)
from kanban.security.keys import KeyMaterial
from kanban.security.ratelimit.valkey import ValkeyRateLimiter
from kanban.tests.security.fakes import FakeValkey

if TYPE_CHECKING:
    from collections.abc import Sequence
    from ipaddress import IPv4Address, IPv6Address


class _TestPrincipalResolver:
    """Configurable principal resolver for testing authenticated routes."""

    def __init__(self, principal: PrincipalContext | None = None) -> None:
        self.principal = principal

    async def resolve(self, _request: object) -> PrincipalContext | None:
        return self.principal


class _MockResolver:
    """Mock DNS resolver returning static or custom IP addresses."""

    def __init__(self, records: Sequence[IPv4Address | IPv6Address] | None = None) -> None:
        self.records = records if records is not None else [ipaddress.ip_address("93.184.216.34")]
        self.call_count = 0

    async def resolve(self, _host: str) -> Sequence[IPv4Address | IPv6Address]:
        self.call_count += 1
        return self.records


class _MockSocketTransport:
    """Mock socket transport recording outbound requests and returning configured HTTP responses."""

    def __init__(self, response_bytes: bytes) -> None:
        self.response_bytes = response_bytes
        self.written_bytes = bytearray()
        self.connect_count = 0

    async def open_connection(
        self,
        ip: str,
        port: int,
        server_hostname: str,
        connect_timeout: float,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        del ip, port, server_hostname, connect_timeout
        self.connect_count += 1
        reader = asyncio.StreamReader()
        reader.feed_data(self.response_bytes)
        reader.feed_eof()

        writer_mock = MagicMock()

        def _record_write(data: bytes) -> None:
            self.written_bytes.extend(data)

        writer_mock.write = MagicMock(side_effect=_record_write)
        writer_mock.close = MagicMock()
        writer_mock.drain = MagicMock()

        async def _async_drain() -> None:
            pass

        async def _async_wait_closed() -> None:
            pass

        writer_mock.drain = _async_drain
        writer_mock.wait_closed = _async_wait_closed
        return reader, writer_mock


class _MockAirGapChecker:
    """Mock air gap checker toggling air-gap mode."""

    def __init__(self, *, enabled: bool) -> None:
        self.enabled = enabled

    def is_air_gap_enabled(self, _workspace_id: uuid.UUID | None = None) -> bool:
        return self.enabled


@pytest.fixture
def test_keys() -> KeyMaterial:
    """Provide static test KeyMaterial with 32-byte keys."""
    return KeyMaterial(
        master_kek=b"K" * 32,
        auth_pepper=b"P" * 32,
        session_hmac_key=b"S" * 32,
        master_kek_kid="test-kek-1",
    )


@pytest.fixture
def auth_principal() -> PrincipalContext:
    """Provide standard authenticated PrincipalContext."""
    return PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("session",),
    )


@pytest.mark.asyncio
async def test_case_1_positive_cookieless_proxy(
    test_keys: KeyMaterial,
    auth_principal: PrincipalContext,
) -> None:
    """Test Case 1: Positive cookieless proxying and header sanitization (S5.4, S10.2)."""
    valid_png_body = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    upstream_http = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: image/png; charset=utf-8\r\n"
        b"Content-Length: " + str(len(valid_png_body)).encode("ascii") + b"\r\n"
        b"Set-Cookie: track=malicious_tracker\r\n"
        b"Server: Apache/2.4.41\r\n"
        b'ETag: "12345"\r\n'
        b"\r\n" + valid_png_body
    )
    transport = _MockSocketTransport(upstream_http)
    resolver = _MockResolver()
    client = PinnedTlsMediaClient(transport=transport)
    service = MediaProxyService(
        resolver=resolver, client=client, air_gap_checker=_MockAirGapChecker(enabled=False)
    )

    app = create_app()
    app.state.key_material = test_keys
    app.state.principal_resolver = _TestPrincipalResolver(auth_principal)
    app.state.media_proxy_service = service
    app.state.rate_limiter = ValkeyRateLimiter(FakeValkey())

    raw_url = "https://img.example.com/diagram.png"
    signed_path = sign_media_proxy_url(raw_url, test_keys)

    asgi_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=asgi_transport,
        base_url="http://testserver",
        cookies={"client_session": "secret_cookie"},
        headers={
            "Authorization": "Bearer token",
            "Referer": "https://secret.kanban.internal",
            "X-Forwarded-For": "203.0.113.195",
        },
    ) as http_client:
        response = await http_client.get(signed_path)

    assert response.status_code == 200
    assert response.content == valid_png_body
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-length"] == str(len(valid_png_body))
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "set-cookie" not in response.headers
    assert "server" not in response.headers
    assert "etag" not in response.headers

    # Verify upstream received ZERO client cookies, auth, or tracking headers
    req_bytes = bytes(transport.written_bytes)
    assert b"secret_cookie" not in req_bytes
    assert b"Cookie:" not in req_bytes
    assert b"Authorization:" not in req_bytes
    assert b"Referer:" not in req_bytes
    assert b"X-Forwarded-For:" not in req_bytes


@pytest.mark.asyncio
async def test_case_2_hmac_gate_defense(
    test_keys: KeyMaterial,
    auth_principal: PrincipalContext,
) -> None:
    """Test Case 2: HMAC signature gating and zero DNS resolution on failure (S5.4, S10.2)."""
    resolver = _MockResolver()
    transport = _MockSocketTransport(b"")
    service = MediaProxyService(resolver=resolver, client=PinnedTlsMediaClient(transport=transport))

    app = create_app()
    app.state.key_material = test_keys
    app.state.principal_resolver = _TestPrincipalResolver(auth_principal)
    app.state.media_proxy_service = service
    app.state.rate_limiter = ValkeyRateLimiter(FakeValkey())

    asgi_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        # A: Missing signature
        res_a = await client.get("/api/v1/media-proxy?u=https://img.example.com/a.png&sig=")
        assert res_a.status_code == 403
        assert res_a.json()["code"] == "INVALID_SIGNATURE"
        assert resolver.call_count == 0

        # B: Bit-flipped signature (flip penultimate char inside the 32-byte digest)
        valid_path = sign_media_proxy_url("https://img.example.com/a.png", test_keys)
        tampered_path = valid_path[:-2] + ("AA" if valid_path[-2:] != "AA" else "zz")
        res_b = await client.get(tampered_path)
        assert res_b.status_code == 403
        assert res_b.json()["code"] == "INVALID_SIGNATURE"
        assert resolver.call_count == 0

        # C: Valid signature for URL A presented for URL B
        sig_a = valid_path.split("sig=")[1]
        res_c = await client.get(f"/api/v1/media-proxy?u=https://img.example.com/b.png&sig={sig_a}")
        assert res_c.status_code == 403
        assert res_c.json()["code"] == "INVALID_SIGNATURE"
        assert resolver.call_count == 0


@pytest.mark.asyncio
async def test_case_5_zero_redirects(
    test_keys: KeyMaterial,
    auth_principal: PrincipalContext,
) -> None:
    """Test Case 5: Immediate 502 MEDIA_REDIRECT_BLOCKED on 3xx responses (S5.4, S10.2)."""
    for code in (301, 302, 307, 308):
        redirect_http = (
            f"HTTP/1.1 {code} Found\r\n"
            "Location: http://169.254.169.254/latest/meta-data/\r\n"
            "Content-Length: 0\r\n"
            "\r\n"
        ).encode("ascii")
        transport = _MockSocketTransport(redirect_http)
        resolver = _MockResolver()
        service = MediaProxyService(
            resolver=resolver, client=PinnedTlsMediaClient(transport=transport)
        )

        app = create_app()
        app.state.key_material = test_keys
        app.state.principal_resolver = _TestPrincipalResolver(auth_principal)
        app.state.media_proxy_service = service
        app.state.rate_limiter = ValkeyRateLimiter(FakeValkey())

        signed_path = sign_media_proxy_url("https://img.example.com/test.png", test_keys)
        asgi_transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=asgi_transport, base_url="http://testserver"
        ) as client:
            res = await client.get(signed_path)

        assert res.status_code == 502
        assert res.json()["code"] == "MEDIA_REDIRECT_BLOCKED"
        # Zero second connection attempts
        assert transport.connect_count == 1


def test_case_6_url_and_port_scanning() -> None:
    """Test Case 6: Reject invalid schemes, credentials, ports, and fragments (S5.4)."""
    # Plain HTTP disallowed
    with pytest.raises(ProblemException) as exc1:
        validate_external_image_url("http://img.example.com/a.png")
    assert exc1.value.code == "INVALID_MEDIA_URL"
    assert exc1.value.status == 400

    # Disallowed port
    with pytest.raises(ProblemException) as exc2:
        validate_external_image_url("https://img.example.com:8443/a.png")
    assert exc2.value.code == "INVALID_MEDIA_URL"
    assert exc2.value.status == 400

    # Userinfo disallowed
    with pytest.raises(ProblemException) as exc3:
        validate_external_image_url("https://user:pass@img.example.com/a.png")
    assert exc3.value.code == "INVALID_MEDIA_URL"
    assert exc3.value.status == 400

    # Fragment disallowed
    with pytest.raises(ProblemException) as exc4:
        validate_external_image_url("https://img.example.com/a.png#fragment")
    assert exc4.value.code == "INVALID_MEDIA_URL"
    assert exc4.value.status == 400


@pytest.mark.asyncio
async def test_case_7_mime_and_magic_mismatch(
    test_keys: KeyMaterial,
    auth_principal: PrincipalContext,
) -> None:
    """Test Case 7: Raster MIME restriction and magic signature verification (S5.4, S10.2)."""
    # Disallowed MIME type (image/svg+xml)
    svg_http = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: image/svg+xml\r\n"
        b"Content-Length: 20\r\n\r\n"
        b"<svg><rect/></svg>"
    )
    transport_svg = _MockSocketTransport(svg_http)
    service_svg = MediaProxyService(
        resolver=_MockResolver(), client=PinnedTlsMediaClient(transport=transport_svg)
    )

    app = create_app()
    app.state.key_material = test_keys
    app.state.principal_resolver = _TestPrincipalResolver(auth_principal)
    app.state.media_proxy_service = service_svg
    app.state.rate_limiter = ValkeyRateLimiter(FakeValkey())

    signed_svg = sign_media_proxy_url("https://img.example.com/badge.svg", test_keys)
    asgi_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        res_svg = await client.get(signed_svg)

    assert res_svg.status_code == 415
    assert res_svg.json()["code"] == "MEDIA_TYPE_DISALLOWED"

    # Declared image/png with HTML body
    html_http = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: image/png\r\n"
        b"Content-Length: 23\r\n\r\n"
        b"<html><script>1</script>"
    )
    transport_html = _MockSocketTransport(html_http)
    service_html = MediaProxyService(
        resolver=_MockResolver(), client=PinnedTlsMediaClient(transport=transport_html)
    )
    app.state.media_proxy_service = service_html

    signed_html = sign_media_proxy_url("https://img.example.com/exploit.png", test_keys)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        res_html = await client.get(signed_html)

    assert res_html.status_code == 502
    assert res_html.json()["code"] == "MEDIA_SIGNATURE_MISMATCH"


@pytest.mark.asyncio
async def test_case_8_boundary_10mib_cap(
    test_keys: KeyMaterial,
    auth_principal: PrincipalContext,
) -> None:
    """Test Case 8: Maximum payload limit 10 MiB enforcement (S5.4, S10.2)."""
    # Exceeding Content-Length header
    too_large_cl_http = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: image/png\r\n"
        b"Content-Length: " + str(MAX_PROXY_BYTES + 1).encode("ascii") + b"\r\n\r\n"
        b"\x89PNG\r\n\x1a\n"
    )
    transport_cl = _MockSocketTransport(too_large_cl_http)
    service_cl = MediaProxyService(
        resolver=_MockResolver(), client=PinnedTlsMediaClient(transport=transport_cl)
    )

    app = create_app()
    app.state.key_material = test_keys
    app.state.principal_resolver = _TestPrincipalResolver(auth_principal)
    app.state.media_proxy_service = service_cl
    app.state.rate_limiter = ValkeyRateLimiter(FakeValkey())

    signed_path = sign_media_proxy_url("https://img.example.com/huge.png", test_keys)
    asgi_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        res_cl = await client.get(signed_path)

    assert res_cl.status_code == 502
    assert res_cl.json()["code"] == "MEDIA_TOO_LARGE"


@pytest.mark.asyncio
async def test_case_9_air_gap_mode_and_rate_limit(
    test_keys: KeyMaterial,
    auth_principal: PrincipalContext,
) -> None:
    """Test Case 9: Air-gap mode, 401 unauthenticated, and 429 rate limit (S5.4, S10.2)."""
    resolver = _MockResolver()
    transport = _MockSocketTransport(b"")
    service = MediaProxyService(
        resolver=resolver,
        client=PinnedTlsMediaClient(transport=transport),
        air_gap_checker=_MockAirGapChecker(enabled=True),
    )

    fake_valkey = FakeValkey()
    rate_limiter = ValkeyRateLimiter(fake_valkey)

    app = create_app()
    app.state.key_material = test_keys
    app.state.principal_resolver = _TestPrincipalResolver(auth_principal)
    app.state.media_proxy_service = service
    app.state.rate_limiter = rate_limiter

    signed_path = sign_media_proxy_url("https://img.example.com/diagram.png", test_keys)
    asgi_transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        # Step 1: Air-gap short-circuit returns 200 with zero DNS or TCP calls
        res_air = await client.get(signed_path)
        assert res_air.status_code == 200
        assert res_air.headers["x-kanban-media-status"] == AIR_GAP_STATUS_HEADER
        assert res_air.content == AIR_GAP_PLACEHOLDER_PNG
        assert resolver.call_count == 0
        assert transport.connect_count == 0

        # Step 2: Unauthenticated request returns 401 AUTHENTICATION_REQUIRED
        app.state.principal_resolver = _TestPrincipalResolver(None)
        res_unauth = await client.get(signed_path)
        assert res_unauth.status_code == 401
        assert res_unauth.json()["code"] == "AUTHENTICATION_REQUIRED"

        # Restore auth for rate limit testing
        app.state.principal_resolver = _TestPrincipalResolver(auth_principal)

        # Step 3: MEDIA_PROXY_PRINCIPAL threshold (120 requests per 60s)
        # We already made 1 request (res_air). Let's make 119 more successful requests.
        for _ in range(119):
            res = await client.get(signed_path)
            assert res.status_code == 200

        # 121st request breaches the limit -> 429 RATE_LIMITED
        res_429 = await client.get(signed_path)
        assert res_429.status_code == 429
        assert res_429.json()["code"] == "RATE_LIMITED"
        assert "retry-after" in res_429.headers


@pytest.mark.asyncio
async def test_generate_contract_sample_artifact(
    test_keys: KeyMaterial,
    auth_principal: PrincipalContext,
) -> None:
    """Generate docs/qa/KANBA-66/contract-sample.json containing required wire responses."""
    # Capture 200 Proxied Image
    valid_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    up_200 = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: image/png\r\n"
        b"Content-Length: " + str(len(valid_png)).encode("ascii") + b"\r\n\r\n" + valid_png
    )
    svc_200 = MediaProxyService(
        resolver=_MockResolver(),
        client=PinnedTlsMediaClient(transport=_MockSocketTransport(up_200)),
        air_gap_checker=_MockAirGapChecker(enabled=False),
    )

    app = create_app()
    app.state.key_material = test_keys
    app.state.principal_resolver = _TestPrincipalResolver(auth_principal)
    app.state.media_proxy_service = svc_200
    app.state.rate_limiter = ValkeyRateLimiter(FakeValkey())

    signed_url = sign_media_proxy_url("https://img.example.com/asset.png", test_keys)
    asgi_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        r_200 = await client.get(signed_url)

        # 200 Air-Gap Placeholder
        app.state.media_proxy_service = MediaProxyService(
            resolver=_MockResolver(),
            client=PinnedTlsMediaClient(transport=_MockSocketTransport(b"")),
            air_gap_checker=_MockAirGapChecker(enabled=True),
        )
        r_airgap = await client.get(signed_url)

        # 403 INVALID_SIGNATURE
        r_403_sig = await client.get(
            "/api/v1/media-proxy?u=https://img.example.com/asset.png&sig=bad"
        )

        # 403 MEDIA_HOST_BLOCKED
        app.state.media_proxy_service = MediaProxyService(
            resolver=_MockResolver(records=[ipaddress.ip_address("169.254.169.254")]),
            client=PinnedTlsMediaClient(transport=_MockSocketTransport(b"")),
            air_gap_checker=_MockAirGapChecker(enabled=False),
        )
        r_403_host = await client.get(signed_url)

        # 502 MEDIA_REDIRECT_BLOCKED
        redir_http = b"HTTP/1.1 302 Found\r\nLocation: https://evil.example.com/\r\n\r\n"
        app.state.media_proxy_service = MediaProxyService(
            resolver=_MockResolver(),
            client=PinnedTlsMediaClient(transport=_MockSocketTransport(redir_http)),
            air_gap_checker=_MockAirGapChecker(enabled=False),
        )
        r_502_redir = await client.get(signed_url)

        # 502 MEDIA_TOO_LARGE
        too_large_http = (
            b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: 10485761\r\n\r\n"
        )
        app.state.media_proxy_service = MediaProxyService(
            resolver=_MockResolver(),
            client=PinnedTlsMediaClient(transport=_MockSocketTransport(too_large_http)),
            air_gap_checker=_MockAirGapChecker(enabled=False),
        )
        r_502_large = await client.get(signed_url)

    contract_data = {
        "description": "Captured HTTP contract samples for KANBA-66 (KB-P2-16) Media Proxy API",
        "route": "GET /api/v1/media-proxy",
        "responses": {
            "200_PROXIED_IMAGE": {
                "status_code": r_200.status_code,
                "headers": dict(r_200.headers),
                "body_bytes_length": len(r_200.content),
            },
            "200_AIR_GAP_PLACEHOLDER": {
                "status_code": r_airgap.status_code,
                "headers": dict(r_airgap.headers),
                "body_bytes_length": len(r_airgap.content),
            },
            "403_INVALID_SIGNATURE": {
                "status_code": r_403_sig.status_code,
                "payload": r_403_sig.json(),
            },
            "403_MEDIA_HOST_BLOCKED": {
                "status_code": r_403_host.status_code,
                "payload": r_403_host.json(),
            },
            "502_MEDIA_REDIRECT_BLOCKED": {
                "status_code": r_502_redir.status_code,
                "payload": r_502_redir.json(),
            },
            "502_MEDIA_TOO_LARGE": {
                "status_code": r_502_large.status_code,
                "payload": r_502_large.json(),
            },
        },
    }

    proof_dir = Path("docs/qa/KANBA-66")
    proof_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
    contract_file = proof_dir / "contract-sample.json"
    contract_file.write_text(json.dumps(contract_data, indent=2), encoding="utf-8")


def test_magic_signature_verification() -> None:
    """Verify raster magic signature matching across all supported formats."""
    # PNG
    assert _verify_magic_signature("image/png", b"\x89PNG\r\n\x1a\n\x00") is True
    assert _verify_magic_signature("image/png", b"NOTPNG\x00\x00") is False

    # JPEG
    assert _verify_magic_signature("image/jpeg", b"\xff\xd8\xff\xe0\x00\x10") is True
    assert _verify_magic_signature("image/jpeg", b"\x00\x00\x00\x00") is False

    # GIF
    assert _verify_magic_signature("image/gif", b"GIF87a\x01\x00") is True
    assert _verify_magic_signature("image/gif", b"GIF89a\x01\x00") is True
    assert _verify_magic_signature("image/gif", b"GIF88a\x01\x00") is False

    # WebP
    assert _verify_magic_signature("image/webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ") is True
    assert _verify_magic_signature("image/webp", b"RIFF\x00\x00\x00\x00NOTP") is False

    # AVIF
    assert _verify_magic_signature("image/avif", b"\x00\x00\x00\x1cftypavif\x00\x00") is True
    assert _verify_magic_signature("image/avif", b"\x00\x00\x00\x1cftypavis\x00\x00") is True
    assert _verify_magic_signature("image/avif", b"\x00\x00\x00\x1cftypmif1\x00\x00") is True
    assert _verify_magic_signature("image/avif", b"\x00\x00\x00\x1cftypother") is False

    # Too short or unknown
    assert _verify_magic_signature("image/png", b"\x89P") is False
    assert _verify_magic_signature("image/webp", b"RIFF") is False
    assert _verify_magic_signature("image/unknown", b"\x00\x00\x00\x00") is False


def test_status_code_parsing_failures() -> None:
    """Verify malformed, non-integer, and non-200 upstream status lines."""
    with pytest.raises(ProblemException) as exc1:
        _parse_status_code(b"", "host.example.com")
    assert exc1.value.code == "MEDIA_UPSTREAM_ERROR"

    with pytest.raises(ProblemException) as exc2:
        _parse_status_code(b"MALFORMED\r\n", "host.example.com")
    assert exc2.value.code == "MEDIA_UPSTREAM_ERROR"

    with pytest.raises(ProblemException) as exc3:
        _parse_status_code(b"HTTP/1.1 NOTINT OK\r\n", "host.example.com")
    assert exc3.value.code == "MEDIA_UPSTREAM_ERROR"

    with pytest.raises(ProblemException) as exc4:
        _parse_status_code(b"HTTP/1.1 404 Not Found\r\n", "host.example.com")
    assert exc4.value.code == "MEDIA_UPSTREAM_ERROR"


def test_header_validation_failures() -> None:
    """Verify invalid content-length and content-type parsing."""
    headers_ok = {"content-type": "image/png; charset=utf-8", "content-length": "invalid_num"}
    assert _validate_content_type_and_length(headers_ok) == "image/png"


@pytest.mark.asyncio
async def test_chunked_transfer_encoding(
    test_keys: KeyMaterial,
    auth_principal: PrincipalContext,
) -> None:
    """Verify chunked transfer encoding handling, trailers, and error conditions."""
    png_bytes = b"\x89PNG\r\n\x1a\n"
    # Format RFC 7230 chunked stream with trailing headers
    chunked_resp = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: image/png\r\n"
        b"Transfer-Encoding: chunked\r\n"
        b"\r\n"
        b"4\r\n"
        b"\x89PNG\r\n"
        b"4\r\n"
        b"\r\n\x1a\n\r\n"
        b"0\r\n"
        b"X-Trailer: trailer-value\r\n"
        b"\r\n"
    )
    transport = _MockSocketTransport(chunked_resp)
    service = MediaProxyService(
        resolver=_MockResolver(),
        client=PinnedTlsMediaClient(transport=transport),
        air_gap_checker=_MockAirGapChecker(enabled=False),
    )

    app = create_app()
    app.state.key_material = test_keys
    app.state.principal_resolver = _TestPrincipalResolver(auth_principal)
    app.state.media_proxy_service = service
    app.state.rate_limiter = ValkeyRateLimiter(FakeValkey())

    signed_url = sign_media_proxy_url("https://img.example.com/chunked.png", test_keys)
    asgi_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        res = await client.get(signed_url)

    assert res.status_code == 200
    assert res.content == png_bytes

    # Invalid chunk size hex
    bad_chunk_resp = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: image/png\r\n"
        b"Transfer-Encoding: chunked\r\n"
        b"\r\n"
        b"ZZ\r\n"
        b"invalid\r\n"
    )
    app.state.media_proxy_service = MediaProxyService(
        resolver=_MockResolver(),
        client=PinnedTlsMediaClient(transport=_MockSocketTransport(bad_chunk_resp)),
        air_gap_checker=_MockAirGapChecker(enabled=False),
    )
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        res_bad = await client.get(signed_url)
    assert res_bad.status_code == 502
    assert res_bad.json()["code"] == "MEDIA_UPSTREAM_ERROR"


@pytest.mark.asyncio
async def test_service_query_params_and_air_gap_checker(
    test_keys: KeyMaterial,
    auth_principal: PrincipalContext,
) -> None:
    """Verify service forwarding of query parameters and DefaultAirGapChecker evaluation."""
    png_bytes = b"\x89PNG\r\n\x1a\n"
    resp = b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: 8\r\n\r\n" + png_bytes
    transport = _MockSocketTransport(resp)
    service = MediaProxyService(
        resolver=_MockResolver(),
        client=PinnedTlsMediaClient(transport=transport),
        air_gap_checker=_MockAirGapChecker(enabled=False),
    )

    app = create_app()
    app.state.key_material = test_keys
    app.state.principal_resolver = _TestPrincipalResolver(auth_principal)
    app.state.media_proxy_service = service
    app.state.rate_limiter = ValkeyRateLimiter(FakeValkey())

    signed_url = sign_media_proxy_url("https://img.example.com/asset.png?v=2&w=200", test_keys)
    asgi_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        res = await client.get(signed_url)

    assert res.status_code == 200
    written = bytes(transport.written_bytes)
    assert b"GET /asset.png?v=2&w=200 HTTP/1.1" in written

    # DefaultAirGapChecker coverage
    with patch.dict(os.environ, {"KANBAN_AIR_GAP_MODE": "true"}):
        checker = DefaultAirGapChecker()
        assert checker.is_air_gap_enabled() is True

    with patch.dict(os.environ, {"KANBAN_AIR_GAP_MODE": "false"}):
        checker = DefaultAirGapChecker()
        assert checker.is_air_gap_enabled() is False

    mock_req = MagicMock()
    mock_req.app.state.is_air_gap_enabled = lambda _ws: True
    assert DefaultAirGapChecker(request=mock_req).is_air_gap_enabled() is True

    mock_req2 = MagicMock()
    mock_req2.app.state.is_air_gap_enabled = None
    mock_req2.app.state.settings = SimpleNamespace(air_gap_mode=True)
    assert DefaultAirGapChecker(request=mock_req2).is_air_gap_enabled() is True


def test_signing_boundary_checks(test_keys: KeyMaterial) -> None:
    """Verify signing URL boundaries, literal host rejections, and verify edge cases."""
    with pytest.raises(ProblemException) as exc_host1:
        _validate_host("")
    assert exc_host1.value.code == "INVALID_MEDIA_URL"

    with pytest.raises(ProblemException) as exc_host2:
        _validate_host("a" * 254)
    assert exc_host2.value.code == "INVALID_MEDIA_URL"

    with pytest.raises(ProblemException) as exc_host3:
        _validate_host("127.0.0.1")
    assert exc_host3.value.code == "INVALID_MEDIA_URL"

    with pytest.raises(ProblemException) as exc_url1:
        validate_external_image_url("")
    assert exc_url1.value.code == "INVALID_MEDIA_URL"

    with pytest.raises(ProblemException) as exc_url2:
        validate_external_image_url("https://" + ("a" * 2045) + ".example.com/p.png")
    assert exc_url2.value.code == "INVALID_MEDIA_URL"

    # verify_media_proxy_url edge cases
    assert verify_media_proxy_url("", "sig", test_keys) is False
    assert verify_media_proxy_url("https://example.com/a.png", "", test_keys) is False
    assert verify_media_proxy_url("https://example.com/a.png", "a" * 65, test_keys) is False
    assert verify_media_proxy_url("https://example.com/a.png", "bad!!!base64", test_keys) is False


@pytest.mark.asyncio
async def test_default_pinned_connection_transport() -> None:
    """Verify DefaultPinnedConnectionTransport calls asyncio.open_connection."""
    transport = DefaultPinnedConnectionTransport()
    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open:
        mock_open.return_value = (AsyncMock(), AsyncMock())
        reader, writer = await transport.open_connection(
            ip="93.184.216.34",
            port=443,
            server_hostname="img.example.com",
            connect_timeout=3.0,
        )
        assert reader is not None
        assert writer is not None
        assert mock_open.call_count == 1


class _OversizeReaderTransport:
    async def open_connection(
        self,
        ip: str,
        port: int,
        server_hostname: str,
        connect_timeout: float,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        del ip, port, server_hostname, connect_timeout
        reader = asyncio.StreamReader()
        header = b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\n\r\n"
        reader.feed_data(header + b"\x89PNG" + b"X" * (MAX_PROXY_BYTES + 10))
        reader.feed_eof()
        w = MagicMock()
        w.write = MagicMock()
        w.close = MagicMock()
        w.drain = AsyncMock()
        w.wait_closed = AsyncMock()
        return reader, w


class _ChunkedOversizeTransport:
    async def open_connection(
        self,
        ip: str,
        port: int,
        server_hostname: str,
        connect_timeout: float,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        del ip, port, server_hostname, connect_timeout
        reader = asyncio.StreamReader()
        chunk_hex = f"{MAX_PROXY_BYTES + 1:x}".encode("ascii")
        header = b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nTransfer-Encoding: chunked\r\n\r\n"
        payload = header + chunk_hex + b"\r\n" + b"Y" * (MAX_PROXY_BYTES + 1) + b"\r\n0\r\n\r\n"
        reader.feed_data(payload)
        reader.feed_eof()
        w = MagicMock()
        w.write = MagicMock()
        w.close = MagicMock()
        w.drain = AsyncMock()
        w.wait_closed = AsyncMock()
        return reader, w


class _HangingTransport:
    async def open_connection(
        self,
        ip: str,
        port: int,
        server_hostname: str,
        connect_timeout: float,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        del ip, port, server_hostname, connect_timeout
        await asyncio.sleep(10.0)
        return asyncio.StreamReader(), MagicMock()


@pytest.mark.asyncio
async def test_stream_limits_and_timeouts() -> None:
    """Verify streaming limit enforcement on fixed and chunked bodies and client timeout."""
    test_ip = ipaddress.ip_address("93.184.216.34")

    # Fixed body exceeding limit without Content-Length
    client_oversize = PinnedTlsMediaClient(transport=_OversizeReaderTransport())
    with pytest.raises(ProblemException) as exc1:
        await client_oversize.fetch_media(test_ip, "img.example.com", "/oversize.png")
    assert exc1.value.code == "MEDIA_TOO_LARGE"

    # Chunked body exceeding limit
    client_chunked = PinnedTlsMediaClient(transport=_ChunkedOversizeTransport())
    with pytest.raises(ProblemException) as exc2:
        await client_chunked.fetch_media(test_ip, "img.example.com", "/chunked_huge.png")
    assert exc2.value.code == "MEDIA_TOO_LARGE"

    # Total timeout in fetch_media
    client_hanging = PinnedTlsMediaClient(transport=_HangingTransport())
    with patch("kanban.media_proxy.client._TOTAL_TIMEOUT", 0.05), pytest.raises(TimeoutError):
        await client_hanging.fetch_media(test_ip, "img.example.com", "/timeout.png")


@pytest.mark.asyncio
async def test_api_loads_default_key_material(
    test_keys: KeyMaterial,
    auth_principal: PrincipalContext,
) -> None:
    """Verify endpoint falls back to load_key_material() when not present on app.state."""
    app = create_app()
    app.state.principal_resolver = _TestPrincipalResolver(auth_principal)
    app.state.rate_limiter = ValkeyRateLimiter(FakeValkey())
    b64_key = base64.urlsafe_b64encode(test_keys.session_hmac_key).decode("ascii")
    with (
        patch.dict(os.environ, {"KANBAN_SESSION_HMAC_KEY": b64_key}),
        patch("kanban.api.v1.media_proxy.load_key_material", return_value=test_keys) as mock_load,
    ):
        asgi_transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=asgi_transport, base_url="http://testserver"
        ) as client:
            res = await client.get("/api/v1/media-proxy?u=https://img.example.com/a.png&sig=bad")
        assert res.status_code == 403
        assert res.json()["code"] == "INVALID_SIGNATURE"
        assert mock_load.call_count == 1
