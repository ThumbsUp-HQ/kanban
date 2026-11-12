"""Unit tests for spoof-resistant client IP resolution (S2.4, S3.3, KB-P2-18)."""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

from kanban.security.client_ip import _format_ip, resolve_client_ip
from kanban.security.ratelimit.base import RateLimitPolicy, make_key


def _make_scope(
    client_ip: str | None = None,
    client_port: int = 12345,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict[str, Any]:
    """Construct an ASGI scope mapping for testing."""
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/api/test",
        "headers": headers or [],
    }
    if client_ip is not None:
        scope["client"] = (client_ip, client_port)
    return scope


def test_case_04_xff_spoof_and_trusted_traversal() -> None:
    """Test Case 4: XFF spoof protection, trusted proxy traversal, and malformed fallback."""
    trusted_nets = [ipaddress.ip_network("10.0.0.0/8")]

    # 1. Untrusted peer 203.0.113.9 sends X-Forwarded-For: 127.0.0.1 -> resolved 203.0.113.9
    scope_untrusted = _make_scope(
        client_ip="203.0.113.9",
        headers=[(b"x-forwarded-for", b"127.0.0.1")],
    )
    assert resolve_client_ip(scope_untrusted, trusted_nets) == "203.0.113.9"

    # 2. Trusted proxy 10.0.0.2 with XFF: 198.51.100.7, 10.0.0.3 -> 198.51.100.7
    scope_trusted = _make_scope(
        client_ip="10.0.0.2",
        headers=[(b"x-forwarded-for", b"198.51.100.7, 10.0.0.3")],
    )
    assert resolve_client_ip(scope_trusted, trusted_nets) == "198.51.100.7"

    # 3. Garbage X-Forwarded-For: ', ,%00' -> falls back to direct peer
    scope_garbage = _make_scope(
        client_ip="10.0.0.2",
        headers=[(b"x-forwarded-for", b", ,%00")],
    )
    assert resolve_client_ip(scope_garbage, trusted_nets) == "10.0.0.2"


def test_case_05_ipv6_rotation_subnet_bucketing() -> None:
    """Test Case 5: 30 addresses inside one /64 prefix resolve to identical bucket keys."""
    policy = RateLimitPolicy(name="ipv6_test", limit=50, window_seconds=60)
    session_key = b"k" * 32

    # Generate 30 different host addresses inside 2001:db8:abcd:0012::/64
    addresses = [f"2001:db8:abcd:12::{i:x}" for i in range(1, 31)]

    resolved_ips: set[str] = set()
    bucket_keys: set[bytes] = set()

    for addr in addresses:
        scope = _make_scope(client_ip=addr)
        resolved = resolve_client_ip(scope)
        resolved_ips.add(resolved)
        key = make_key(policy, resolved, session_hmac_key=session_key)
        bucket_keys.add(key)

    # All 30 distinct addresses in the same /64 prefix MUST resolve identically
    assert len(resolved_ips) == 1
    assert len(bucket_keys) == 1
    expected_net = "2001:db8:abcd:12::/64"
    assert next(iter(resolved_ips)) == expected_net


def test_ipv4_mapped_ipv6_normalization() -> None:
    """Verify IPv4-mapped IPv6 addresses are cleanly normalized to IPv4 strings."""
    scope = _make_scope(client_ip="::ffff:192.0.2.1")
    assert resolve_client_ip(scope) == "192.0.2.1"


def test_env_var_trusted_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify KANBAN_TRUSTED_PROXIES environment variable parsing."""
    monkeypatch.setenv("KANBAN_TRUSTED_PROXIES", "10.0.0.0/8, 172.16.0.0/12")
    scope = _make_scope(
        client_ip="172.16.5.1",
        headers=[(b"x-forwarded-for", b"203.0.113.45")],
    )
    assert resolve_client_ip(scope) == "203.0.113.45"


def test_empty_or_malformed_scope_handling() -> None:
    """Verify defensive handling of missing client info or unparseable peer addresses."""
    # Scope without client field defaults to loopback
    empty_scope: dict[str, Any] = {"type": "http", "headers": []}
    assert resolve_client_ip(empty_scope) == "127.0.0.1"

    # Malformed non-IP string returned as-is
    malformed_scope = _make_scope(client_ip="unix:/run/app.sock")
    assert resolve_client_ip(malformed_scope) == "unix:/run/app.sock"


def test_trusted_proxy_string_and_sequence_formats() -> None:
    """Verify trusted_proxies parameter as single string and mixed sequences."""
    # Single string format with space separator
    scope = _make_scope(client_ip="10.0.0.1", headers=[(b"x-forwarded-for", b"203.0.113.1")])
    assert resolve_client_ip(scope, "10.0.0.0/8 192.168.0.0/16") == "203.0.113.1"

    # Sequence of strings
    assert resolve_client_ip(scope, ["10.0.0.0/8", ""]) == "203.0.113.1"


def test_env_var_with_invalid_entries_and_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify robust handling of empty env var and invalid CIDRs in environment."""
    monkeypatch.setenv("KANBAN_TRUSTED_PROXIES", "   ")
    scope = _make_scope(client_ip="10.0.0.1", headers=[(b"x-forwarded-for", b"203.0.113.1")])
    assert resolve_client_ip(scope) == "10.0.0.1"

    # Invalid CIDR string skipped gracefully
    monkeypatch.setenv("KANBAN_TRUSTED_PROXIES", "not_a_cidr, 10.0.0.0/8")
    assert resolve_client_ip(scope) == "203.0.113.1"


def test_xff_edge_cases() -> None:
    """Verify trusted peer with missing, non-utf8, whitespace, all-comma, and all-trusted XFF."""
    trusted = [ipaddress.ip_network("10.0.0.0/8")]

    # 1. Trusted peer without XFF header
    s_no_xff = _make_scope(client_ip="10.0.0.1", headers=[])
    assert resolve_client_ip(s_no_xff, trusted) == "10.0.0.1"

    # 2. Trusted peer with non-UTF-8 header
    s_non_utf8 = _make_scope(client_ip="10.0.0.1", headers=[(b"x-forwarded-for", b"\xff\xfe")])
    assert resolve_client_ip(s_non_utf8, trusted) == "10.0.0.1"

    # 3. Trusted peer with whitespace-only XFF
    s_ws = _make_scope(client_ip="10.0.0.1", headers=[(b"x-forwarded-for", b"   ")])
    assert resolve_client_ip(s_ws, trusted) == "10.0.0.1"

    # 4. Trusted peer with comma-only XFF
    s_commas = _make_scope(client_ip="10.0.0.1", headers=[(b"x-forwarded-for", b",, , ")])
    assert resolve_client_ip(s_commas, trusted) == "10.0.0.1"

    # 5. XFF with IPv4-mapped IPv6 candidate
    s_mapped = _make_scope(
        client_ip="10.0.0.1",
        headers=[(b"x-forwarded-for", b"::ffff:198.51.100.22")],
    )
    assert resolve_client_ip(s_mapped, trusted) == "198.51.100.22"

    # 6. All proxies trusted in XFF -> returns leftmost address
    s_all_trusted = _make_scope(
        client_ip="10.0.0.1",
        headers=[(b"x-forwarded-for", b"10.0.0.5, 10.0.0.4")],
    )
    assert resolve_client_ip(s_all_trusted, trusted) == "10.0.0.5"


def test_format_ip_and_header_scanning() -> None:
    """Verify _format_ip with mapped IPv6 and multi-header scanning in resolve_client_ip."""
    # IPv4-mapped IPv6
    mapped = ipaddress.ip_address("::ffff:198.51.100.99")
    assert _format_ip(mapped) == "198.51.100.99"

    # Multi-header scanning before finding x-forwarded-for
    trusted = [ipaddress.ip_network("10.0.0.0/8")]
    scope = _make_scope(
        client_ip="10.0.0.1",
        headers=[
            (b"host", b"localhost"),
            (b"authorization", b"Bearer test"),
            (b"x-forwarded-for", b"198.51.100.12"),
        ],
    )
    assert resolve_client_ip(scope, trusted) == "198.51.100.12"
