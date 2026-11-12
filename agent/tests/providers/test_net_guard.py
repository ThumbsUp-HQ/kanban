# Copyright 2026 Kanban Platform Contributors
"""Unit tests for agent network guard: resolve-then-check SSRF defense."""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from agent.providers.errors import EgressDenied, ProviderPolicyError
from agent.providers.net_guard import (
    HARD_DENIED_NETWORKS,
    _extract_ip,
    is_hard_denied,
    resolve_and_pin,
)

if TYPE_CHECKING:
    from ipaddress import IPv4Network, IPv6Network

DEFAULT_ALLOWED_CIDRS: list[IPv4Network | IPv6Network] = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
]


class TestHardDeniedNetworks:
    """Tests for hard-denied network detection."""

    @pytest.mark.parametrize(
        "ip_str",
        [
            "169.254.169.254",
            "169.254.0.1",
            "169.254.255.255",
            "0.0.0.0",  # noqa: S104  # Testing IP validation pattern
            "0.1.2.3",
            "224.0.0.1",
            "239.255.255.250",
            "::",
            "fe80::1",
            "fe80::ffff",
            "fd00:ec2::254",
            "ff02::1",
            "::ffff:169.254.169.254",
            "::ffff:169.254.1.1",
        ],
    )
    def test_denied_ips_are_flagged(self, ip_str: str) -> None:
        """Verify hard-denied metadata and link-local IPs are flagged."""
        ip = ipaddress.ip_address(ip_str)
        assert is_hard_denied(ip) is True

    @pytest.mark.parametrize(
        "ip_str",
        [
            "127.0.0.1",
            "10.0.0.1",
            "172.16.0.1",
            "192.168.1.1",
            "8.8.8.8",
            "1.1.1.1",
            "::1",
            "fc00::1",
            "2001:db8::1",
            "::ffff:127.0.0.1",
            "::ffff:10.0.0.1",
        ],
    )
    def test_safe_ips_are_not_flagged(self, ip_str: str) -> None:
        """Verify non-metadata IPs are not flagged by is_hard_denied."""
        ip = ipaddress.ip_address(ip_str)
        assert is_hard_denied(ip) is False

    def test_all_expected_ranges_present(self) -> None:
        """Verify all mandated networks exist in HARD_DENIED_NETWORKS."""
        expected = {
            ipaddress.ip_network("169.254.0.0/16"),
            ipaddress.ip_network("fe80::/10"),
            ipaddress.ip_network("fd00:ec2::254/128"),
            ipaddress.ip_network("0.0.0.0/8"),
            ipaddress.ip_network("::/128"),
            ipaddress.ip_network("224.0.0.0/4"),
            ipaddress.ip_network("ff00::/8"),
            ipaddress.ip_network("::ffff:169.254.0.0/112"),
        }
        assert expected.issubset(set(HARD_DENIED_NETWORKS))


class TestExtractIP:
    """Tests for internal IP extraction from resolver entries."""

    def test_extract_from_ip_objects(self) -> None:
        """Extract IP from pre-parsed IPv4 and IPv6 address objects."""
        v4 = ipaddress.ip_address("127.0.0.1")
        v6 = ipaddress.ip_address("::1")
        assert _extract_ip(v4) == v4
        assert _extract_ip(v6) == v6

    def test_extract_from_string(self) -> None:
        """Extract IP from string address representation."""
        assert _extract_ip("192.168.1.1") == ipaddress.ip_address("192.168.1.1")

    def test_extract_from_getaddrinfo_tuple(self) -> None:
        """Extract IP from 5-tuple returned by getaddrinfo."""
        gai_tuple = (2, 1, 6, "", ("127.0.0.1", 11434))
        assert _extract_ip(gai_tuple) == ipaddress.ip_address("127.0.0.1")

    def test_extract_from_invalid_entry_raises(self) -> None:
        """Invalid resolver entry types raise ValueError."""
        with pytest.raises(ValueError, match="Unable to parse IP address"):
            _extract_ip(12345)
        # Empty sockaddr tuple
        with pytest.raises(ValueError, match="Unable to parse IP address"):
            _extract_ip((2, 1, 6, "", ()))


class TestResolveAndPin:
    """Tests for resolve_and_pin SSRF defense logic."""

    @pytest.mark.asyncio
    async def test_case_4_allows_loopback_and_rfc1918(self) -> None:
        """Case 4: resolve-then-check allows loopback and RFC1918 within configured CIDR list."""
        # Literal loopback
        pinned_v4 = await resolve_and_pin("127.0.0.1", 11434, DEFAULT_ALLOWED_CIDRS)
        assert pinned_v4 == ipaddress.ip_address("127.0.0.1")

        # Literal IPv6 loopback
        pinned_v6 = await resolve_and_pin("::1", 11434, DEFAULT_ALLOWED_CIDRS)
        assert pinned_v6 == ipaddress.ip_address("::1")

        # Literal RFC1918 addresses
        for addr in ("10.0.1.5", "172.16.50.1", "192.168.1.100"):
            res = await resolve_and_pin(addr, 11434, DEFAULT_ALLOWED_CIDRS)
            assert res == ipaddress.ip_address(addr)

        # Hostname resolving to loopback via resolver
        async def mock_resolver(_host: str, _port: int) -> list[str]:
            return ["127.0.0.1"]

        resolved = await resolve_and_pin(
            "localhost", 11434, DEFAULT_ALLOWED_CIDRS, resolver=mock_resolver
        )
        assert resolved == ipaddress.ip_address("127.0.0.1")

    @pytest.mark.asyncio
    async def test_case_5_rejects_metadata_even_if_operator_allowed(self) -> None:
        """Case 5: rejects 169.254.169.254 with OLLAMA_METADATA_DENIED even if in allowed CIDRs."""
        # Operator mistakenly allowed 169.254.0.0/16
        mistaken_cidrs = [*DEFAULT_ALLOWED_CIDRS, ipaddress.ip_network("169.254.0.0/16")]

        # Test literal IP
        with pytest.raises(EgressDenied) as exc_info:
            await resolve_and_pin("169.254.169.254", 11434, mistaken_cidrs)

        assert exc_info.value.code == "OLLAMA_METADATA_DENIED"
        assert issubclass(EgressDenied, ProviderPolicyError)

        # Test via hostname resolution
        async def mock_resolver(_host: str, _port: int) -> list[str]:
            return ["169.254.169.254"]

        with pytest.raises(EgressDenied) as exc_info2:
            await resolve_and_pin(
                "metadata.internal", 11434, mistaken_cidrs, resolver=mock_resolver
            )

        assert exc_info2.value.code == "OLLAMA_METADATA_DENIED"

    @pytest.mark.asyncio
    async def test_case_6_multi_record_rejects_if_any_ip_is_denied(self) -> None:
        """Case 6: resolve-then-check denies multi-record with any metadata IP."""

        async def mock_multi_resolver(_host: str, _port: int) -> list[str]:
            return ["127.0.0.1", "169.254.169.254"]

        with pytest.raises(EgressDenied) as exc_info:
            await resolve_and_pin(
                "rebinding.attacker.local",
                11434,
                DEFAULT_ALLOWED_CIDRS,
                resolver=mock_multi_resolver,
            )

        assert exc_info.value.code == "OLLAMA_METADATA_DENIED"

    @pytest.mark.asyncio
    async def test_literal_outside_allowed_cidrs(self) -> None:
        """Literal public IP not in allowed CIDRs raises OLLAMA_CIDR_DENIED."""
        with pytest.raises(EgressDenied) as exc_info:
            await resolve_and_pin("8.8.8.8", 11434, DEFAULT_ALLOWED_CIDRS)

        assert exc_info.value.code == "OLLAMA_CIDR_DENIED"

    @pytest.mark.asyncio
    async def test_multi_record_outside_allowed_cidrs(self) -> None:
        """Hostname resolving to a safe IP and an unapproved public IP is denied."""

        async def mock_resolver(_host: str, _port: int) -> list[str]:
            return ["127.0.0.1", "8.8.8.8"]

        with pytest.raises(EgressDenied) as exc_info:
            await resolve_and_pin(
                "split.local", 11434, DEFAULT_ALLOWED_CIDRS, resolver=mock_resolver
            )

        assert exc_info.value.code == "OLLAMA_CIDR_DENIED"

    @pytest.mark.asyncio
    async def test_empty_dns_resolution_raises(self) -> None:
        """Empty address record from DNS raises OLLAMA_CIDR_DENIED."""

        async def mock_empty_resolver(_host: str, _port: int) -> list[str]:
            return []

        with pytest.raises(EgressDenied) as exc_info:
            await resolve_and_pin(
                "nowhere.local", 11434, DEFAULT_ALLOWED_CIDRS, resolver=mock_empty_resolver
            )

        assert exc_info.value.code == "OLLAMA_CIDR_DENIED"

    @pytest.mark.asyncio
    async def test_default_loop_getaddrinfo_resolution(self) -> None:
        """Default resolver uses loop.getaddrinfo when resolver is None."""
        fake_records = [(2, 1, 6, "", ("127.0.0.1", 11434))]
        with patch("asyncio.get_running_loop") as mock_get_loop:
            mock_loop = AsyncMock()
            mock_loop.getaddrinfo.return_value = fake_records
            mock_get_loop.return_value = mock_loop

            resolved = await resolve_and_pin("ollama.local", 11434, DEFAULT_ALLOWED_CIDRS)
            assert resolved == ipaddress.ip_address("127.0.0.1")
            mock_loop.getaddrinfo.assert_awaited_once_with("ollama.local", 11434)

    @pytest.mark.asyncio
    async def test_ipv4_mapped_ipv6_allowed(self) -> None:
        """IPv4-mapped IPv6 address matching allowed CIDR passes."""
        mapped = ipaddress.IPv6Address("::ffff:127.0.0.1")

        async def mock_resolver(_host: str, _port: int) -> list[ipaddress.IPv6Address]:
            return [mapped]

        resolved = await resolve_and_pin(
            "mapped.local", 11434, DEFAULT_ALLOWED_CIDRS, resolver=mock_resolver
        )
        assert resolved == mapped

    @pytest.mark.asyncio
    async def test_ipv4_mapped_ipv6_disallowed(self) -> None:
        """IPv4-mapped IPv6 address NOT matching allowed CIDR fails."""
        mapped = ipaddress.IPv6Address("::ffff:8.8.8.8")

        async def mock_resolver(_host: str, _port: int) -> list[ipaddress.IPv6Address]:
            return [mapped]

        with pytest.raises(EgressDenied) as exc_info:
            await resolve_and_pin(
                "mapped-denied.local", 11434, DEFAULT_ALLOWED_CIDRS, resolver=mock_resolver
            )
        assert exc_info.value.code == "OLLAMA_CIDR_DENIED"
