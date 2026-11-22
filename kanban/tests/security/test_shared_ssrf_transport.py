# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for shared DNS-pinned SSRF protection and socket transport (S2.1, S10.2)."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from ipaddress import IPv4Address, IPv6Address
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from kanban.api.problems import ProblemException
from kanban.security.ssrf import (
    DefaultAsyncHostResolver,
    DefaultPinnedConnectionTransport,
    PinnedConnectionTransport,
    _unwrap_ip,
    is_public_global_ip,
    resolve_and_select_pinned_ip,
    validate_not_redirect,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class MockSpyResolver:
    """Configurable test resolver returning predefined sequences of IP addresses."""

    def __init__(self, records: Sequence[IPv4Address | IPv6Address] | None = None) -> None:
        """Initialize spy with optional records."""
        self.records = list(records) if records is not None else []
        self.resolved_hosts: list[str] = []

    async def resolve(self, host: str) -> Sequence[IPv4Address | IPv6Address]:
        """Record query and return canned records."""
        self.resolved_hosts.append(host)
        return self.records


def test_is_public_global_ip_accepts_valid_public_ips() -> None:
    """Verify is_public_global_ip returns True for routable global IPv4/IPv6 addresses."""
    valid_ips = [
        "93.184.216.34",
        "8.8.8.8",
        "1.1.1.1",
        "140.82.121.3",
        "2606:4700:4700::1111",
        "2001:4860:4860::8888",
        ipaddress.ip_address("93.184.216.34"),
        ipaddress.ip_address("2606:4700:4700::1111"),
    ]
    for ip in valid_ips:
        assert is_public_global_ip(ip) is True, f"Expected {ip} to be public"


def test_is_public_global_ip_rejects_internal_and_dangerous_ranges() -> None:
    """Verify is_public_global_ip rejects loopback, RFC1918, CGNAT, IMDS, ULA and multicast."""
    blocked_ips = [
        "127.0.0.1",
        "127.0.1.1",
        "0.0.0.0",  # noqa: S104
        "10.0.0.1",
        "10.254.254.254",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.0.1",
        "192.168.1.100",
        "169.254.169.254",  # AWS/GCP IMDS
        "169.254.1.1",
        "100.64.0.1",  # CGNAT
        "100.127.255.254",
        "192.0.2.1",  # TEST-NET-1
        "198.51.100.1",  # TEST-NET-2
        "203.0.113.1",  # TEST-NET-3
        "224.0.0.1",  # Multicast
        "240.0.0.1",  # Reserved
        "255.255.255.255",
        "::1",  # IPv6 loopback
        "::",
        "fe80::1",  # IPv6 link-local
        "fc00::1",  # IPv6 ULA
        "fd12:3456:789a::1",
        "fec0::1",  # IPv6 site-local
        "ff02::1",  # IPv6 multicast
        "2001:db8::1",  # IPv6 documentation
        "invalid-ip-string",
        "999.999.999.999",
    ]
    for ip in blocked_ips:
        assert is_public_global_ip(ip) is False, f"Expected {ip} to be blocked"


def test_unwrap_ip_handles_mapped_and_nat64() -> None:
    """Verify IPv4-mapped IPv6 and NAT64 addresses unwrap to internal IPv4."""
    # IPv4-mapped loopback
    mapped_loopback = ipaddress.ip_address("::ffff:127.0.0.1")
    assert is_public_global_ip(mapped_loopback) is False
    assert _unwrap_ip(mapped_loopback) == ipaddress.IPv4Address("127.0.0.1")

    # IPv4-mapped RFC1918
    mapped_private = ipaddress.ip_address("::ffff:192.168.1.1")
    assert is_public_global_ip(mapped_private) is False
    assert _unwrap_ip(mapped_private) == ipaddress.IPv4Address("192.168.1.1")

    # NAT64 embedded private (64:ff9b::a00:1 -> 10.0.0.1)
    nat64_private = ipaddress.ip_address("64:ff9b::a00:1")
    assert is_public_global_ip(nat64_private) is False
    assert _unwrap_ip(nat64_private) == ipaddress.IPv4Address("10.0.0.1")

    # NAT64 embedded IMDS (64:ff9b::a9fe:a9fe -> 169.254.169.254)
    nat64_imds = ipaddress.ip_address("64:ff9b::a9fe:a9fe")
    assert is_public_global_ip(nat64_imds) is False
    assert _unwrap_ip(nat64_imds) == ipaddress.IPv4Address("169.254.169.254")

    # NAT64 embedded public IP (64:ff9b::5db8:d822 -> 93.184.216.34)
    nat64_public = ipaddress.ip_address("64:ff9b::5db8:d822")
    assert is_public_global_ip(nat64_public) is True
    assert _unwrap_ip(nat64_public) == ipaddress.IPv4Address("93.184.216.34")


@pytest.mark.asyncio
async def test_resolve_and_select_pinned_ip_success() -> None:
    """Verify successful DNS resolution returns first validated public IP."""
    public_ips = [
        ipaddress.ip_address("93.184.216.34"),
        ipaddress.ip_address("2606:4700:4700::1111"),
    ]
    resolver = MockSpyResolver(records=public_ips)

    pinned = await resolve_and_select_pinned_ip("example.com", resolver=resolver)
    assert pinned == public_ips[0]
    assert resolver.resolved_hosts == ["example.com"]


@pytest.mark.asyncio
async def test_resolve_and_select_pinned_ip_zero_records() -> None:
    """Verify resolution returning empty sequence raises ProblemException."""
    resolver = MockSpyResolver(records=[])

    with pytest.raises(ProblemException) as exc:
        await resolve_and_select_pinned_ip("empty.example.com", resolver=resolver)
    assert exc.value.status == 403
    assert exc.value.code == "SSRF_HOST_BLOCKED"


@pytest.mark.asyncio
async def test_resolve_and_select_pinned_ip_rejects_mixed_records() -> None:
    """Verify DNS rebinding / mixed response with ANY non-public IP fails closed."""
    mixed_ips = [
        ipaddress.ip_address("93.184.216.34"),
        ipaddress.ip_address("127.0.0.1"),  # Malicious rebinding candidate
    ]
    resolver = MockSpyResolver(records=mixed_ips)

    with pytest.raises(ProblemException) as exc:
        await resolve_and_select_pinned_ip("rebind.example.com", resolver=resolver)
    assert exc.value.status == 403
    assert "blocked non-public IP" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_resolve_and_select_pinned_ip_timeout() -> None:
    """Verify slow DNS resolution exceeding timeout raises ProblemException."""

    class SlowResolver:
        async def resolve(self, _host: str) -> Sequence[IPv4Address | IPv6Address]:
            await asyncio.sleep(0.5)
            return [ipaddress.ip_address("93.184.216.34")]

    with pytest.raises(ProblemException) as exc:
        await resolve_and_select_pinned_ip(
            "slow.example.com", resolver=SlowResolver(), timeout=0.05
        )
    assert exc.value.status == 403
    assert "timed out" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_default_async_host_resolver_success_and_error() -> None:
    """Verify DefaultAsyncHostResolver deduplicates and maps socket errors."""
    resolver = DefaultAsyncHostResolver(
        port=443, error_code="SSRF_HOST_BLOCKED", error_title="SSRF Blocked"
    )

    mock_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ]
    with patch("asyncio.get_running_loop") as mock_loop_fn:
        mock_loop = AsyncMock()
        mock_loop.getaddrinfo = AsyncMock(return_value=mock_addrinfo)
        mock_loop_fn.return_value = mock_loop

        ips = await resolver.resolve("example.com")
        assert len(ips) == 1
        assert str(ips[0]) == "93.184.216.34"

    with patch("asyncio.get_running_loop") as mock_loop_fn:
        mock_loop = AsyncMock()
        mock_loop.getaddrinfo = AsyncMock(side_effect=socket.gaierror("Name not known"))
        mock_loop_fn.return_value = mock_loop

        with pytest.raises(ProblemException) as exc:
            await resolver.resolve("nonexistent.example.com")
        assert exc.value.status == 403
        assert exc.value.code == "SSRF_HOST_BLOCKED"


def test_validate_not_redirect() -> None:
    """Verify validate_not_redirect raises for 300..399 and passes non-redirects."""
    # Non-redirects should pass without exception
    validate_not_redirect(200, "example.com")
    validate_not_redirect(404, "example.com")
    validate_not_redirect(500, "example.com")

    # 3xx redirects must raise
    for code in (301, 302, 303, 307, 308):
        with pytest.raises(ProblemException) as exc:
            validate_not_redirect(code, "redirect.example.com")
        assert exc.value.status == 502
        assert exc.value.code == "REDIRECT_BLOCKED"
        assert f"status {code}" in str(exc.value.detail)


def test_pinned_connection_transport_protocol() -> None:
    """Verify DefaultPinnedConnectionTransport conforms to PinnedConnectionTransport protocol."""
    transport = DefaultPinnedConnectionTransport()
    assert isinstance(transport, PinnedConnectionTransport)


@pytest.mark.asyncio
async def test_resolve_and_select_pinned_ip_with_callable_and_invalid_resolver() -> None:
    """Verify callable resolvers, invalid resolvers, and problem passthrough."""
    # 1. Callable returning strings
    resolved = await resolve_and_select_pinned_ip(
        "example.com", resolver=lambda _h: ["93.184.216.34"]
    )
    assert str(resolved) == "93.184.216.34"

    # 2. Invalid resolver type
    with pytest.raises(ProblemException) as exc:
        await resolve_and_select_pinned_ip("example.com", resolver=123)  # type: ignore[arg-type]
    assert exc.value.status == 403

    # 3. ProblemException re-raised as-is
    class ProblemResolver:
        async def resolve(self, _h: str) -> Sequence[IPv4Address]:
            msg = "Custom detail"
            raise ProblemException(code="CUSTOM_CODE", status=400, title="Custom", detail=msg)

    with pytest.raises(ProblemException) as exc2:
        await resolve_and_select_pinned_ip("example.com", resolver=ProblemResolver())
    assert exc2.value.code == "CUSTOM_CODE"
    assert exc2.value.status == 400


@pytest.mark.asyncio
async def test_default_pinned_connection_transport_open_connection() -> None:
    """Verify DefaultPinnedConnectionTransport delegates to asyncio.open_connection."""
    transport = DefaultPinnedConnectionTransport()
    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open:
        mock_open.return_value = (AsyncMock(), AsyncMock())
        res = await transport.open_connection(
            ip="93.184.216.34",
            port=443,
            server_hostname="example.com",
            connect_timeout=5.0,
        )
        assert len(res) == 2
        mock_open.assert_awaited_once()
