"""Unit tests for security headers middleware and standalone cleartext blocking."""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Response
from starlette.types import Message, Receive, Scope, Send

from deploy.standalone.entrypoint import build_uvicorn_command
from kanban.app import create_app
from kanban.security.headers import CSP_POLICY, SecurityHeadersMiddleware
from kanban.settings import Settings


@pytest.fixture
def dummy_dist(tmp_path: Path) -> Path:
    """Fixture providing minimal dist directory with index.html."""
    dist_dir = tmp_path / "web_dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    return dist_dir


@pytest.mark.asyncio
async def test_security_headers_present_on_all_responses(dummy_dist: Path) -> None:
    """Test all responses (200, 404, 501) carry canonical CSP and hardening headers."""
    settings = Settings(web_dist=dummy_dist, deployment_mode="production")
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        endpoints_to_test = [
            "/api/v1/health",  # 200
            "/api/unknown",  # 404
            "/sse",  # 501
            "/mcp/agent",  # 501
        ]
        for ep in endpoints_to_test:
            resp = await client.get(ep)
            csp = resp.headers.get("content-security-policy")
            assert csp == CSP_POLICY
            assert "img-src 'self' blob: data:;" in (csp or "")
            assert "data:image/" not in (csp or "")
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
    # Production
    prod_app = create_app(Settings(web_dist=dummy_dist, deployment_mode="production"))
    prod_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=prod_app), base_url="http://localhost"
    )
    async with prod_client:
        r_prod = await prod_client.get("/api/v1/health")
        assert "strict-transport-security" in r_prod.headers

    # Standalone
    standalone_app = create_app(Settings(web_dist=dummy_dist, deployment_mode="standalone"))
    standalone_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=standalone_app), base_url="http://localhost"
    )
    async with standalone_client:
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
        return resp

    settings = Settings(deployment_mode="production")
    inner_app.add_middleware(SecurityHeadersMiddleware, settings=settings)

    transport = httpx.ASGITransport(app=inner_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.get("/custom")
        assert resp.status_code == 200
        # Exactly one DENY, no duplicate headers
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("x-content-type-options") == "nosniff"


@pytest.mark.asyncio
async def test_standalone_allows_cleartext_http_by_default(dummy_dist: Path) -> None:
    """Test standalone mode allows cleartext HTTP on any host by default (availability first)."""
    settings = Settings(
        web_dist=dummy_dist,
        deployment_mode="standalone",
    )
    assert settings.block_cleartext_http is False
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        for host in (
            "localhost:8080",
            "192.168.1.101:8921",
            "k.hackedyour.info",
            "xn--kanban-2e54e.hackedyour.info:8080",
        ):
            resp = await client.get("/api/v1/health", headers={"Host": host})
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_standalone_cleartext_host_blocking(
    dummy_dist: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test standalone mode blocks non-loopback IPs when KB_BLOCK_CLEARTEXT_HTTP is set."""
    monkeypatch.setenv("KB_BLOCK_CLEARTEXT_HTTP", "true")
    settings = Settings(
        web_dist=dummy_dist,
        deployment_mode="standalone",
        standalone_cleartext_hosts=frozenset({"localhost", "127.0.0.1", "[::1]"}),
    )
    assert settings.block_cleartext_http is True
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        # Allowed loopback hosts
        for host in ("localhost:8080", "127.0.0.1:8080", "[::1]:8080", "localhost"):
            resp = await client.get("/api/v1/health", headers={"Host": host})
            assert resp.status_code == 200

        # Blocked external IP
        resp_blocked = await client.get("/api/v1/health", headers={"Host": "192.168.1.20:8080"})
        assert resp_blocked.status_code == 403
        assert resp_blocked.headers.get("content-type") == "application/problem+json"
        body = resp_blocked.json()
        assert body["title"] == "CLEARTEXT_HTTP_BLOCKED"
        assert "Put a TLS reverse proxy in front" in body["detail"]

    # Explicitly allowed via KB_STANDALONE_CLEARTEXT_HOSTS
    custom_settings = Settings(
        web_dist=dummy_dist,
        deployment_mode="standalone",
        block_cleartext_http=True,
        standalone_cleartext_hosts=frozenset({"localhost", "192.168.1.20"}),
    )
    app_custom = create_app(custom_settings)
    transport_custom = httpx.ASGITransport(app=app_custom)
    async with httpx.AsyncClient(transport=transport_custom, base_url="http://localhost") as client:
        resp_allowed = await client.get("/api/v1/health", headers={"Host": "192.168.1.20:8080"})
        assert resp_allowed.status_code == 200

    # Production mode never blocks regardless of Host header
    prod_app = create_app(Settings(web_dist=dummy_dist, deployment_mode="production"))
    transport_prod = httpx.ASGITransport(app=prod_app)
    async with httpx.AsyncClient(transport=transport_prod, base_url="http://localhost") as client:
        resp_prod = await client.get("/api/v1/health", headers={"Host": "192.168.1.20:8080"})
        assert resp_prod.status_code == 200


@pytest.mark.asyncio
async def test_standalone_missing_host_header(dummy_dist: Path) -> None:
    """Test standalone mode returns 400 when Host header is missing and cleartext block is on."""
    settings = Settings(
        web_dist=dummy_dist,
        deployment_mode="standalone",
        block_cleartext_http=True,
    )
    app = create_app(settings)

    # Use pure ASGI scope without host header in headers list
    async def app_caller() -> int:
        response_status = 0

        async def receive() -> Message:
            return {"type": "http.request", "body": b""}

        async def send(message: Message) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                val = message["status"]
                assert isinstance(val, int)
                response_status = val

        scope: Scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/health",
            "scheme": "http",
            "headers": [],  # No host header
        }
        await app(scope, receive, send)
        return response_status

    status = await app_caller()
    assert status == 400


@pytest.mark.asyncio
async def test_non_http_scope_passes_through(dummy_dist: Path) -> None:
    """Test non-http scope passes through SecurityHeadersMiddleware unchanged."""
    settings = Settings(web_dist=dummy_dist, deployment_mode="production")
    inner_called = False

    async def dummy_receive() -> Message:
        return {"type": "lifespan.startup"}

    async def dummy_send(_message: Message) -> None:
        pass

    async def dummy_inner(_s: Scope, _r: Receive, _snd: Send) -> None:
        nonlocal inner_called
        inner_called = True

    mw = SecurityHeadersMiddleware(dummy_inner, settings=settings)
    scope: Scope = {"type": "lifespan"}
    await mw(scope, dummy_receive, dummy_send)
    assert inner_called is True


@pytest.mark.asyncio
async def test_standalone_reverse_proxy_https_allowed(dummy_dist: Path) -> None:
    """Test standalone mode permits external host access when terminated via HTTPS reverse proxy."""
    settings = Settings(
        web_dist=dummy_dist,
        deployment_mode="standalone",
        block_cleartext_http=True,
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        ext_host = "xn--kanban-2e54e.hackedyour.info:8080"

        # Baseline: Plain cleartext HTTP to external host is blocked
        resp_blocked = await client.get("/api/v1/health", headers={"Host": ext_host})
        assert resp_blocked.status_code == 403
        assert resp_blocked.json()["title"] == "CLEARTEXT_HTTP_BLOCKED"

        # X-Forwarded-Proto: https allows external host
        resp_xfp = await client.get(
            "/api/v1/health",
            headers={"Host": ext_host, "X-Forwarded-Proto": "https"},
        )
        assert resp_xfp.status_code == 200

        # X-Forwarded-Proto with proxy chain containing https
        resp_chain = await client.get(
            "/api/v1/health",
            headers={"Host": ext_host, "X-Forwarded-Proto": "https, http"},
        )
        assert resp_chain.status_code == 200

        # X-Forwarded-Scheme: https
        resp_xfs = await client.get(
            "/api/v1/health",
            headers={"Host": ext_host, "X-Forwarded-Scheme": "https"},
        )
        assert resp_xfs.status_code == 200

        # RFC 7239 Forwarded: proto=https
        resp_fwd = await client.get(
            "/api/v1/health",
            headers={"Host": ext_host, "Forwarded": "proto=https"},
        )
        assert resp_fwd.status_code == 200

        # RFC 7239 Forwarded: complex with quoted proto
        resp_fwd_complex = await client.get(
            "/api/v1/health",
            headers={"Host": ext_host, "Forwarded": 'for=192.0.2.60;proto="https";by=203.0.113.43'},
        )
        assert resp_fwd_complex.status_code == 200

        # X-Forwarded-Proto: http is still blocked
        resp_http = await client.get(
            "/api/v1/health",
            headers={"Host": ext_host, "X-Forwarded-Proto": "http"},
        )
        assert resp_http.status_code == 403
        assert resp_http.json()["title"] == "CLEARTEXT_HTTP_BLOCKED"


@pytest.mark.asyncio
async def test_standalone_reverse_proxy_scope_scheme_https(dummy_dist: Path) -> None:
    """Test ASGI scope with scheme='https' passes directly without cleartext block."""
    settings = Settings(web_dist=dummy_dist, deployment_mode="standalone")
    app = create_app(settings)

    response_status = 0

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        nonlocal response_status
        if message["type"] == "http.response.start":
            val = message["status"]
            assert isinstance(val, int)
            response_status = val

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/api/v1/health",
        "raw_path": b"/api/v1/health",
        "query_string": b"",
        "scheme": "https",
        "headers": [(b"host", b"xn--kanban-2e54e.hackedyour.info:8080")],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8080),
    }
    await app(scope, receive, send)
    assert response_status == 200


@pytest.mark.asyncio
async def test_standalone_idn_punycode_host_matching(dummy_dist: Path) -> None:
    """Test IDN / Punycode host equivalence against standalone_cleartext_hosts."""
    punycode_host = "xn--kanban-2e54e.hackedyour.info"
    unicode_host = "👍kanban.hackedyour.info"

    # Case 1: Configured with Punycode host
    settings_puny = Settings(
        web_dist=dummy_dist,
        deployment_mode="standalone",
        block_cleartext_http=True,
        standalone_cleartext_hosts=frozenset({"localhost", punycode_host}),
    )
    app_puny = create_app(settings_puny)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_puny), base_url="http://localhost"
    ) as client:
        # Both punycode and unicode Host headers must be accepted
        r1 = await client.get("/api/v1/health", headers={"Host": f"{punycode_host}:8080"})
        assert r1.status_code == 200

        r2 = await client.get(
            "/api/v1/health", headers=[(b"host", f"{unicode_host}:8080".encode())]
        )
        assert r2.status_code == 200

        # Unconfigured host is blocked
        r_blocked = await client.get(
            "/api/v1/health", headers={"Host": "other.hackedyour.info:8080"}
        )
        assert r_blocked.status_code == 403

    # Case 2: Configured with Unicode host
    settings_uni = Settings(
        web_dist=dummy_dist,
        deployment_mode="standalone",
        block_cleartext_http=True,
        standalone_cleartext_hosts=frozenset({"localhost", unicode_host}),
    )
    app_uni = create_app(settings_uni)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_uni), base_url="http://localhost"
    ) as client:
        # Both punycode and unicode Host headers must be accepted
        r3 = await client.get("/api/v1/health", headers={"Host": f"{punycode_host}:8080"})
        assert r3.status_code == 200

        r4 = await client.get(
            "/api/v1/health", headers=[(b"host", f"{unicode_host}:8080".encode())]
        )
        assert r4.status_code == 200


def test_build_uvicorn_command_forwarded_allow_ips(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test build_uvicorn_command forwarded_allow_ips non-wildcard defaults and env vars."""
    # Default is safe non-wildcard ('--forwarded-allow-ips=""')
    monkeypatch.delenv("KB_FORWARDED_ALLOW_IPS", raising=False)
    monkeypatch.delenv("KB_TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("KANBAN_TRUSTED_PROXIES", raising=False)
    cmd = build_uvicorn_command()
    assert '--forwarded-allow-ips=""' in cmd

    # Explicit override
    monkeypatch.setenv("KB_FORWARDED_ALLOW_IPS", "127.0.0.1,10.0.0.1")
    cmd_custom = build_uvicorn_command()
    assert "--forwarded-allow-ips=127.0.0.1,10.0.0.1" in cmd_custom

    # Respects KB_TRUSTED_PROXIES when KB_FORWARDED_ALLOW_IPS is not set
    monkeypatch.delenv("KB_FORWARDED_ALLOW_IPS", raising=False)
    monkeypatch.setenv("KB_TRUSTED_PROXIES", "10.0.0.0/8")
    cmd_trusted = build_uvicorn_command()
    assert "--forwarded-allow-ips=10.0.0.0/8" in cmd_trusted
