"""Unit tests for security headers middleware, CSP, and standalone.

Validates CSP manifest-src, HSTS, host punycode, and standalone cleartext blocking.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi import FastAPI, Response
from starlette.datastructures import Headers

from deploy.standalone.entrypoint import build_uvicorn_command
from kanban.app import create_app
from kanban.security.headers import (
    CSP_POLICY,
    SecurityHeadersMiddleware,
    _extract_host,
    _has_forwarded_https_proto,
    _is_host_allowed,
    _is_https_request,
    _normalize_host_idna,
    _parse_trusted_networks,
)
from kanban.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path

    from starlette.types import Message, Receive, Scope, Send


@pytest.fixture
def dummy_dist(tmp_path: Path) -> Path:
    """Fixture providing minimal dist directory with index.html."""
    dist_dir = tmp_path / "web_dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    return dist_dir


@pytest.mark.asyncio
async def test_security_headers_present_and_manifest_src(dummy_dist: Path) -> None:
    """Test all responses carry canonical CSP with manifest-src 'self' and hardening headers."""
    assert "manifest-src 'self';" in CSP_POLICY

    settings = Settings(web_dist=dummy_dist, deployment_mode="production")
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        endpoints_to_test = [
            "/api/v1/health",
            "/api/unknown",
            "/sse",
            "/mcp/agent",
        ]
        for ep in endpoints_to_test:
            resp = await client.get(ep)
            csp = resp.headers.get("content-security-policy")
            assert csp == CSP_POLICY
            assert "manifest-src 'self';" in (csp or "")
            assert "img-src 'self' blob: data:;" in (csp or "")
            assert resp.headers.get("x-content-type-options") == "nosniff"
            assert resp.headers.get("referrer-policy") == "no-referrer"
            assert resp.headers.get("x-frame-options") == "DENY"
            assert resp.headers.get("cross-origin-opener-policy") == "same-origin"
            assert resp.headers.get("cross-origin-resource-policy") == "same-origin"
            assert (
                resp.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=()"
            )
            assert (
                resp.headers.get("strict-transport-security")
                == "max-age=63072000; includeSubDomains"
            )


@pytest.mark.asyncio
async def test_hsts_behavior_production_vs_standalone(dummy_dist: Path) -> None:
    """Test HSTS is present in production mode and strictly omitted in standalone mode."""
    prod_app = create_app(Settings(web_dist=dummy_dist, deployment_mode="production"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=prod_app), base_url="http://localhost"
    ) as prod_client:
        r_prod = await prod_client.get("/api/v1/health")
        assert "strict-transport-security" in r_prod.headers

    standalone_app = create_app(Settings(web_dist=dummy_dist, deployment_mode="standalone"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=standalone_app), base_url="http://localhost"
    ) as standalone_client:
        r_standalone = await standalone_client.get("/api/v1/health")
        assert "strict-transport-security" not in r_standalone.headers


@pytest.mark.asyncio
async def test_inner_app_headers_replaced_never_duplicated() -> None:
    """Test inner application headers are overwritten by security middleware."""
    inner_app = FastAPI()

    @inner_app.get("/custom")
    def custom_endpoint() -> Response:
        resp = Response(content="ok", media_type="text/plain")
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["X-Content-Type-Options"] = "sniff-allowed"
        resp.headers["Content-Security-Policy"] = "default-src 'self'"
        return resp

    settings = Settings(deployment_mode="production")
    inner_app.add_middleware(SecurityHeadersMiddleware, settings=settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=inner_app), base_url="http://localhost"
    ) as client:
        resp = await client.get("/custom")
        assert resp.status_code == 200
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("content-security-policy") == "default-src 'self'"


@pytest.mark.asyncio
async def test_standalone_cleartext_blocking_and_allowed_hosts(dummy_dist: Path) -> None:
    """Test standalone cleartext HTTP blocking logic and allowed host overrides."""
    settings = Settings(
        web_dist=dummy_dist,
        deployment_mode="standalone",
        block_cleartext_http=True,
        standalone_cleartext_hosts=frozenset({"localhost", "127.0.0.1"}),
    )
    app = create_app(settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        # Localhost allowed
        r_allowed = await client.get("/api/v1/health", headers={"Host": "localhost:8080"})
        assert r_allowed.status_code == 200

        # Disallowed external host blocked with 403 problem json
        r_blocked = await client.get("/api/v1/health", headers={"Host": "public.example.com:8080"})
        assert r_blocked.status_code == 403
        data = r_blocked.json()
        assert data["title"] == "CLEARTEXT_HTTP_BLOCKED"

        # Missing host header returns 400
        r_no_host = await client.get("/api/v1/health", headers={"Host": ""})
        assert r_no_host.status_code == 400


@pytest.mark.asyncio
async def test_non_http_scope_passthrough() -> None:
    """Test non-http scope (lifespan) passes through middleware cleanly."""
    called = False

    async def dummy_app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal called
        called = True

    settings = Settings(deployment_mode="production")
    mw = SecurityHeadersMiddleware(dummy_app, settings=settings)

    scope: Scope = {"type": "lifespan"}

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(_msg: Message) -> None:
        pass

    await mw(scope, receive, send)
    assert called is True


def test_host_extraction_ipv6_and_ports() -> None:
    """Test _extract_host with IPv4, ports, and IPv6 brackets."""
    assert _extract_host("localhost:8080") == "localhost"
    assert _extract_host("example.com") == "example.com"
    assert _extract_host("[::1]:8080") == "[::1]"
    assert _extract_host("[2001:db8::1]") == "[2001:db8::1]"
    assert _extract_host("[malformed-ipv6:8080") == "[malformed-ipv6"


@pytest.mark.asyncio
async def test_standalone_https_passes_cleartext_block(dummy_dist: Path) -> None:
    """Test HTTPS request bypasses standalone cleartext blocking."""
    settings = Settings(
        web_dist=dummy_dist,
        deployment_mode="standalone",
        block_cleartext_http=True,
        standalone_cleartext_hosts=frozenset({"localhost"}),
    )
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        # Request with X-Forwarded-Proto: https passes even for non-whitelisted host
        r_fwd = await client.get(
            "/api/v1/health",
            headers={"Host": "public.example.com:8080", "X-Forwarded-Proto": "https"},
        )
        assert r_fwd.status_code == 200


def test_forwarded_https_proto_parsing() -> None:
    """Test RFC 7239 Forwarded header parsing."""
    assert _has_forwarded_https_proto("for=192.0.2.1;proto=https;by=203.0.113.43") is True
    assert _has_forwarded_https_proto('for=192.0.2.1;proto="https"') is True
    assert _has_forwarded_https_proto("for=192.0.2.1;proto=http") is False
    assert _has_forwarded_https_proto("for=192.0.2.1") is False


def test_is_https_request_helpers() -> None:
    """Test _is_https_request with scheme and various forwarding headers."""
    headers_https = Headers({"x-forwarded-proto": "https"})
    assert _is_https_request({"type": "http", "scheme": "http"}, headers_https) is True

    headers_scheme = Headers({"x-forwarded-scheme": "https"})
    assert _is_https_request({"type": "http", "scheme": "http"}, headers_scheme) is True

    headers_fwd = Headers({"forwarded": "proto=https"})
    assert _is_https_request({"type": "http", "scheme": "http"}, headers_fwd) is True

    headers_direct = Headers()
    assert _is_https_request({"type": "http", "scheme": "https"}, headers_direct) is True
    assert _is_https_request({"type": "http", "scheme": "http"}, headers_direct) is False


def test_idna_punycode_normalization_and_allowed_hosts() -> None:
    """Test IDNA punycode candidates generation and allowed check."""
    hosts = _normalize_host_idna("👍kanban.hackedyour.info")
    assert any("xn--" in h for h in hosts)

    allowed = frozenset({"xn--kanban-2e54e.hackedyour.info"})
    assert _is_host_allowed("👍kanban.hackedyour.info", allowed) is True
    assert _is_host_allowed("other.example.com", allowed) is False


def test_parse_trusted_networks() -> None:
    """Test _parse_trusted_networks parsing valid and invalid network strings."""
    nets = _parse_trusted_networks("127.0.0.1, 10.0.0.0/8, 192.168.1.0/24, invalid-ip")
    assert len(nets) == 3


def test_uvicorn_command_building(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test build_uvicorn_command with environment overrides."""
    monkeypatch.delenv("KB_FORWARDED_ALLOW_IPS", raising=False)
    monkeypatch.delenv("KB_TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("KANBAN_TRUSTED_PROXIES", raising=False)
    cmd = build_uvicorn_command()
    assert '--forwarded-allow-ips=""' in cmd
