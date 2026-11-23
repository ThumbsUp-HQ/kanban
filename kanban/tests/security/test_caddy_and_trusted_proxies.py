"""Tests for Caddyfile hardening, runner mTLS listener, and trusted proxy traversal."""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from starlette.datastructures import Headers

from kanban.security.headers import (
    _format_ip,
    _get_raw_trusted_proxies,
    _has_forwarded_https_proto,
    _is_host_allowed,
    _is_https_request,
    _normalize_host_idna,
    _parse_trusted_networks,
    resolve_client_ip,
)

if TYPE_CHECKING:
    import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CADDYFILE_PATH = REPO_ROOT / "deploy" / "caddy" / "Caddyfile"
COMPOSE_PATH = REPO_ROOT / "deploy" / "compose" / "docker-compose.yml"


# ============================================================================
# Caddyfile Edge Hardening & Dedicated :8444 Runner mTLS Tests
# ============================================================================


def test_caddyfile_blocks_internal_routes_with_404() -> None:
    """Action 1: Verify /internal/* and /api/v1/internal/* are blocked with 404 at edge."""
    assert CADDYFILE_PATH.is_file(), f"Missing Caddyfile at {CADDYFILE_PATH}"
    content = CADDYFILE_PATH.read_text(encoding="utf-8")

    # Verify named matcher and response
    matcher_pattern = re.compile(
        r"@internal_routes\s+path\s+/internal/\*\s+/api/v1/internal/\*",
        re.MULTILINE,
    )
    assert matcher_pattern.search(content), "Missing @internal_routes matcher for /internal/*"

    respond_pattern = re.compile(r"respond\s+@internal_routes\s+404", re.MULTILINE)
    assert respond_pattern.search(content), "Missing respond @internal_routes 404 directive"


def test_caddyfile_strips_spoofable_headers_on_public_listener() -> None:
    """Action 1: Verify client-supplied internal and cert headers are stripped."""
    content = CADDYFILE_PATH.read_text(encoding="utf-8")

    spoofed_headers = [
        "-X-Client-Cert-Pem",
        "-X-Client-Cert-Der-B64",
        "-X-Client-Cert-CN",
        "-X-SSL-Client-Cert",
        "-X-KB-Service-Principal",
        "-X-KB-Internal-Auth",
        "-X-KB-Internal-Timestamp",
        "-X-KB-Internal-Signature",
    ]

    for header in spoofed_headers:
        assert f"header_up {header}" in content, (
            f"Missing header_up {header} directive in public reverse_proxy"
        )


def test_caddyfile_dedicated_8444_runner_mtls_listener() -> None:
    """Action 2: Verify dedicated :8444 runner mTLS block requiring client auth."""
    content = CADDYFILE_PATH.read_text(encoding="utf-8")

    # Match :8444 listener block
    assert ":8444 {" in content, "Missing :8444 site block in Caddyfile"

    # Verify TLS client authentication required
    assert "mode require" in content, "Missing mode require in client_auth"

    # Verify route restriction: forwards /api/v1/agent-runners/ws (KAN-324)
    assert "@runner_ws path /api/v1/agent-runners/ws /api/v1/agent-runners/ws/*" in content

    # Verify reverse_proxy to kanban-api:8000 with client cert headers
    assert "reverse_proxy kanban-api:8000" in content
    assert "header_up X-Client-Cert-Pem {http.request.tls.client.certificate_pem}" in content
    assert "header_up X-Client-Cert-Der-B64 {http.request.tls.client.certificate_der_base64}" in (
        content
    )

    # Verify fallthrough 404 for non-runner routes on :8444
    mtls_block = content.split(":8444 {")[1]
    assert "respond 404" in mtls_block, "Missing respond 404 fallback on :8444 listener"


# ============================================================================
# Docker Compose & Network Configuration Tests
# ============================================================================


def test_docker_compose_trusted_proxies_and_runner_mtls_port() -> None:
    """Action 3: Verify KB_TRUSTED_PROXIES and port 8444 in deploy/compose/docker-compose.yml."""
    assert COMPOSE_PATH.is_file(), f"Missing docker-compose.yml at {COMPOSE_PATH}"
    compose_data = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))

    services = compose_data["services"]
    networks = compose_data["networks"]

    # 1. Verify reverse-proxy publishes 8444 for runner mTLS
    assert "reverse-proxy" in services
    proxy_ports = services["reverse-proxy"]["ports"]
    assert "8444:8444" in proxy_ports

    # 2. Verify kanban-api configures KB_TRUSTED_PROXIES for internal Caddy network
    assert "kanban-api" in services
    api_env = services["kanban-api"]["environment"]
    trusted_proxies_cfg = api_env.get("KB_TRUSTED_PROXIES", "")
    assert "172.28.0.0/16" in trusted_proxies_cfg

    # 3. Verify app_net is internal and specifies subnet 172.28.0.0/16
    assert "app_net" in networks
    assert networks["app_net"].get("internal") is True
    ipam_config = networks["app_net"]["ipam"]["config"]
    subnets = [cfg.get("subnet") for cfg in ipam_config]
    assert "172.28.0.0/16" in subnets


# ============================================================================
# Spoof-Resistant resolve_client_ip Tests (kanban.security.headers)
# ============================================================================


def test_resolve_client_ip_untrusted_peer_ignores_spoofed_headers() -> None:
    """Verify that an untrusted direct peer cannot spoof X-Forwarded-For or X-Real-IP."""
    trusted = "10.0.0.0/8"
    untrusted_peer_ip = "203.0.113.9"

    scope: dict[str, Any] = {
        "type": "http",
        "client": (untrusted_peer_ip, 54321),
        "headers": [
            (b"x-forwarded-for", b"198.51.100.7, 10.0.0.2"),
            (b"x-real-ip", b"198.51.100.8"),
        ],
    }

    # Must ignore all headers and return untrusted direct peer IP
    resolved = resolve_client_ip(scope, trusted)
    assert resolved == untrusted_peer_ip


def test_resolve_client_ip_trusted_peer_traverses_xff() -> None:
    """Verify right-to-left traversal of X-Forwarded-For through trusted proxies."""
    trusted = "10.0.0.0/8, 172.28.0.0/16"
    proxy_peer_ip = "172.28.0.2"

    scope: dict[str, Any] = {
        "type": "http",
        "client": (proxy_peer_ip, 45123),
        "headers": [
            (b"x-forwarded-for", b"198.51.100.12, 10.0.0.5"),
        ],
    }

    # Direct peer 172.28.0.2 is trusted; intermediate 10.0.0.5 is trusted; client is 198.51.100.12
    resolved = resolve_client_ip(scope, trusted)
    assert resolved == "198.51.100.12"


def test_resolve_client_ip_trusted_peer_uses_x_real_ip_when_xff_absent() -> None:
    """Action 3: Verify X-Real-IP is trusted when immediate peer is within trusted_proxies."""
    trusted = ["172.28.0.0/16"]
    proxy_peer_ip = "172.28.0.10"

    scope: dict[str, Any] = {
        "type": "http",
        "client": (proxy_peer_ip, 45123),
        "headers": [
            (b"x-real-ip", b"203.0.113.45"),
        ],
    }

    resolved = resolve_client_ip(scope, trusted)
    assert resolved == "203.0.113.45"


def test_resolve_client_ip_xff_takes_precedence_over_x_real_ip() -> None:
    """Verify X-Forwarded-For takes precedence when both XFF and X-Real-IP are present."""
    trusted = "172.28.0.0/16"
    proxy_peer_ip = "172.28.0.10"

    scope: dict[str, Any] = {
        "type": "http",
        "client": (proxy_peer_ip, 45123),
        "headers": [
            (b"x-forwarded-for", b"198.51.100.77"),
            (b"x-real-ip", b"203.0.113.45"),
        ],
    }

    resolved = resolve_client_ip(scope, trusted)
    assert resolved == "198.51.100.77"


def test_resolve_client_ip_malformed_xff_falls_back_to_direct_peer() -> None:
    """Verify that malformed IP strings in X-Forwarded-For safely fall back to peer."""
    trusted = "10.0.0.0/8"
    proxy_peer_ip = "10.0.0.2"

    scope: dict[str, Any] = {
        "type": "http",
        "client": (proxy_peer_ip, 45123),
        "headers": [
            (b"x-forwarded-for", b"not-a-valid-ip, 10.0.0.3"),
        ],
    }

    resolved = resolve_client_ip(scope, trusted)
    assert resolved == proxy_peer_ip


def test_resolve_client_ip_malformed_x_real_ip_falls_back_to_direct_peer() -> None:
    """Verify that malformed IP strings in X-Real-IP safely fall back to direct peer."""
    trusted = "10.0.0.0/8"
    proxy_peer_ip = "10.0.0.2"

    scope: dict[str, Any] = {
        "type": "http",
        "client": (proxy_peer_ip, 45123),
        "headers": [
            (b"x-real-ip", b"invalid-ip-string"),
        ],
    }

    resolved = resolve_client_ip(scope, trusted)
    assert resolved == proxy_peer_ip


def test_resolve_client_ip_ipv4_mapped_ipv6_normalization() -> None:
    """Verify that IPv4-mapped IPv6 addresses are normalized to pure IPv4."""
    trusted = "10.0.0.0/8"
    proxy_peer_ip = "10.0.0.2"

    # 1. In X-Forwarded-For
    scope_xff: dict[str, Any] = {
        "type": "http",
        "client": (proxy_peer_ip, 45123),
        "headers": [(b"x-forwarded-for", b"::ffff:198.51.100.22")],
    }
    assert resolve_client_ip(scope_xff, trusted) == "198.51.100.22"

    # 2. In X-Real-IP
    scope_real_ip: dict[str, Any] = {
        "type": "http",
        "client": (proxy_peer_ip, 45123),
        "headers": [(b"x-real-ip", b"::ffff:198.51.100.33")],
    }
    assert resolve_client_ip(scope_real_ip, trusted) == "198.51.100.33"

    # 3. In direct peer
    scope_peer: dict[str, Any] = {
        "type": "http",
        "client": ("::ffff:198.51.100.44", 45123),
        "headers": [],
    }
    assert resolve_client_ip(scope_peer, trusted) == "198.51.100.44"


def test_resolve_client_ip_ipv6_subnet_bucketing() -> None:
    """Verify that IPv6 addresses are bucketed into their /64 subnet."""
    trusted = "10.0.0.0/8"
    proxy_peer_ip = "10.0.0.2"

    scope_real_ip: dict[str, Any] = {
        "type": "http",
        "client": (proxy_peer_ip, 45123),
        "headers": [(b"x-real-ip", b"2001:0db8:85a3:0000:0000:8a2e:0370:7334")],
    }
    assert resolve_client_ip(scope_real_ip, trusted) == "2001:db8:85a3::/64"


def test_resolve_client_ip_environment_variable_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that KB_TRUSTED_PROXIES and KANBAN_TRUSTED_PROXIES are parsed from env."""
    proxy_peer_ip = "172.28.0.5"
    client_ip = "203.0.113.88"

    scope: dict[str, Any] = {
        "type": "http",
        "client": (proxy_peer_ip, 50000),
        "headers": [(b"x-real-ip", client_ip.encode("ascii"))],
    }

    # 1. With KB_TRUSTED_PROXIES
    monkeypatch.setenv("KB_TRUSTED_PROXIES", "172.28.0.0/16")
    monkeypatch.delenv("KANBAN_TRUSTED_PROXIES", raising=False)
    assert resolve_client_ip(scope) == client_ip

    # 2. With KANBAN_TRUSTED_PROXIES fallback
    monkeypatch.delenv("KB_TRUSTED_PROXIES", raising=False)
    monkeypatch.setenv("KANBAN_TRUSTED_PROXIES", "172.28.0.0/16")
    assert resolve_client_ip(scope) == client_ip

    # 3. Without any trusted proxies env var -> untrusted peer, returns direct peer
    monkeypatch.delenv("KB_TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("KANBAN_TRUSTED_PROXIES", raising=False)
    assert resolve_client_ip(scope) == proxy_peer_ip


def test_resolve_client_ip_edge_scopes() -> None:
    """Verify edge cases: missing client info, unix domain sockets, and Request wrappers."""
    # Empty scope defaults to 127.0.0.1
    assert resolve_client_ip({}) == "127.0.0.1"

    # Unix domain socket returned as-is
    unix_scope: dict[str, Any] = {
        "type": "http",
        "client": ("unix:/run/app.sock", 0),
    }
    assert resolve_client_ip(unix_scope) == "unix:/run/app.sock"

    # Object with .scope attribute (like starlette.requests.Request)
    class DummyRequest:
        def __init__(self, inner_scope: dict[str, Any]) -> None:
            self.scope = inner_scope

    dummy = DummyRequest(
        {
            "type": "http",
            "client": ("10.0.0.2", 12345),
            "headers": [(b"x-real-ip", b"198.51.100.99")],
        }
    )
    assert resolve_client_ip(dummy, "10.0.0.0/8") == "198.51.100.99"  # type: ignore[arg-type]


def test_resolve_client_ip_typed_networks_and_empty_xff() -> None:
    """Verify Sequence[IPv4Network] argument and empty X-Forwarded-For fallback."""
    net = ipaddress.ip_network("10.0.0.0/8")
    scope: dict[str, Any] = {
        "type": "http",
        "client": ("10.0.0.2", 12345),
        "headers": [(b"x-forwarded-for", b"   ")],
    }
    assert resolve_client_ip(scope, [net]) == "10.0.0.2"


def test_resolve_client_ip_all_trusted_returns_leftmost() -> None:
    """Verify that when all XFF addresses are trusted, leftmost address is returned."""
    trusted = "10.0.0.0/8, 172.28.0.0/16"
    proxy_peer_ip = "172.28.0.2"

    scope: dict[str, Any] = {
        "type": "http",
        "client": (proxy_peer_ip, 45123),
        "headers": [
            (b"x-forwarded-for", b"10.0.0.5, 10.0.0.2"),
        ],
    }

    assert resolve_client_ip(scope, trusted) == "10.0.0.5"


def test_resolve_client_ip_non_utf8_header_bytes() -> None:
    """Verify that non-UTF-8 header bytes are safely handled without crash."""
    trusted = "10.0.0.0/8"
    proxy_peer_ip = "10.0.0.2"

    scope: dict[str, Any] = {
        "type": "http",
        "client": (proxy_peer_ip, 45123),
        "headers": [
            (b"x-forwarded-for", b"\xff\xfe\xfd"),
            (b"x-real-ip", b"\x80\x81"),
        ],
    }

    assert resolve_client_ip(scope, trusted) == proxy_peer_ip


def test_headers_helpers_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify helper branch coverage in kanban.security.headers."""
    # 1. Forwarded proto check
    assert _has_forwarded_https_proto("for=192.0.2.1;proto=https;by=203.0.113.1")
    assert not _has_forwarded_https_proto("for=192.0.2.1;proto=http;by=203.0.113.1")
    assert not _has_forwarded_https_proto("garbage_header_without_equals")

    # 2. _is_https_request with scheme and forwarded headers
    scope_https = {"scheme": "https"}
    assert _is_https_request(scope_https, Headers({}))

    scope_http = {"scheme": "http"}
    h_scheme = Headers({"x-forwarded-scheme": "https"})
    assert _is_https_request(scope_http, h_scheme)

    h_forwarded = Headers({"forwarded": "proto=https"})
    assert _is_https_request(scope_http, h_forwarded)

    # 3. Host IDNA normalization
    candidates = _normalize_host_idna("xn--bcher-kva.example")
    assert "xn--bcher-kva.example" in candidates

    # 4. Host allowed checking with Punycode conversion
    assert _is_host_allowed("localhost", frozenset({"localhost"}))
    assert not _is_host_allowed("evil.corp", frozenset({"localhost"}))
    assert _is_host_allowed("xn--bcher-kva.example", frozenset({"bücher.example"}))

    # 5. _parse_trusted_networks with sequence of networks and invalid tokens
    nets = _parse_trusted_networks(
        [
            ipaddress.ip_network("10.0.0.0/8"),
            "172.28.0.0/16",
            "   ",
            "invalid_cidr_token",
        ]
    )
    assert len(nets) == 2

    # 6. _format_ip with mapped IPv6
    mapped_ip = ipaddress.ip_address("::ffff:192.0.2.1")
    assert _format_ip(mapped_ip) == "192.0.2.1"

    # 7. _get_raw_trusted_proxies exception handling
    monkeypatch.delenv("KB_TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("KANBAN_TRUSTED_PROXIES", raising=False)
    monkeypatch.setattr(
        "kanban.security.headers.get_settings",
        lambda: (_ for _ in ()).throw(RuntimeError("settings unavailable")),
    )
    assert _get_raw_trusted_proxies() == ""
