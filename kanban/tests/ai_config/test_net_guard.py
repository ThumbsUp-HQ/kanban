# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for kanban.ai_config.net_guard: SSRF defenses and LAN classification."""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING

import pytest

from kanban.ai_config.net_guard import (
    EgressDeniedError,
    _extract_ip,
    is_hard_denied,
    is_local_base_url,
    is_local_or_private_ip,
    is_private_lan_hostname,
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


def test_hard_denied_networks_completeness() -> None:
    """Verify HARD_DENIED_NETWORKS covers cloud metadata, CGNAT, link-local, and multicast."""
    denied_ips = [
        "169.254.169.254",
        "fe80::1",
        "100.64.0.1",
        "0.0.0.0",  # noqa: S104
        "::",
        "224.0.0.1",
        "ff02::1",
        "fd00:ec2::254",
    ]
    for raw in denied_ips:
        ip = ipaddress.ip_address(raw)
        assert is_hard_denied(ip) is True

    # IPv4 mapped forms
    mapped_metadata = ipaddress.ip_address("::ffff:169.254.169.254")
    assert is_hard_denied(mapped_metadata) is True

    mapped_cgnat = ipaddress.ip_address("::ffff:100.64.0.1")
    assert is_hard_denied(mapped_cgnat) is True

    # Safe IP
    assert is_hard_denied(ipaddress.ip_address("192.168.1.1")) is False
    assert is_hard_denied(ipaddress.ip_address("8.8.8.8")) is False


def test_is_local_or_private_ip() -> None:
    """Verify is_local_or_private_ip identifies loopback, RFC1918, ULA."""
    # Loopback
    assert is_local_or_private_ip(ipaddress.ip_address("127.0.0.1")) is True
    assert is_local_or_private_ip(ipaddress.ip_address("::1")) is True

    # RFC1918
    assert is_local_or_private_ip(ipaddress.ip_address("10.0.0.1")) is True
    assert is_local_or_private_ip(ipaddress.ip_address("172.16.0.1")) is True
    assert is_local_or_private_ip(ipaddress.ip_address("192.168.1.100")) is True

    # IPv6 ULA
    assert is_local_or_private_ip(ipaddress.ip_address("fc00::1")) is True
    assert is_local_or_private_ip(ipaddress.ip_address("fd12:3456::1")) is True

    # IPv4-mapped private
    mapped_pvt = ipaddress.ip_address("::ffff:192.168.1.1")
    assert is_local_or_private_ip(mapped_pvt) is True

    # Public IP
    assert is_local_or_private_ip(ipaddress.ip_address("8.8.8.8")) is False
    assert is_local_or_private_ip(ipaddress.ip_address("1.1.1.1")) is False

    # Metadata / link-local hard denied
    assert is_local_or_private_ip(ipaddress.ip_address("169.254.169.254")) is False
    assert is_local_or_private_ip(ipaddress.ip_address("fe80::1")) is False
    assert is_local_or_private_ip(ipaddress.ip_address("100.64.0.1")) is False


def test_is_private_lan_hostname() -> None:
    """Verify is_private_lan_hostname identifies localhost, LAN TLDs, and single-label names."""
    assert is_private_lan_hostname("localhost") is True
    assert is_private_lan_hostname("localhost.localdomain") is True
    assert is_private_lan_hostname("127.0.0.1") is True
    assert is_private_lan_hostname("::1") is True

    # Private LAN domains
    assert is_private_lan_hostname("ollama.lan") is True
    assert is_private_lan_hostname("vllm.local") is True
    assert is_private_lan_hostname("ai.internal") is True
    assert is_private_lan_hostname("server.home") is True
    assert is_private_lan_hostname("gateway.home.arpa") is True
    assert is_private_lan_hostname("node.corp") is True
    assert is_private_lan_hostname("model.intranet") is True
    assert is_private_lan_hostname("host.private") is True
    assert is_private_lan_hostname("test-box.test") is True

    # Single-label names (docker / k8s service names)
    assert is_private_lan_hostname("ollama") is True
    assert is_private_lan_hostname("vllm-service") is True
    assert is_private_lan_hostname("inference") is True

    # Public internet hostnames
    assert is_private_lan_hostname("api.openai.com") is False
    assert is_private_lan_hostname("generativelanguage.googleapis.com") is False
    assert is_private_lan_hostname("example.com") is False
    assert is_private_lan_hostname("") is False


def test_is_local_base_url() -> None:
    """Verify is_local_base_url detects local and private LAN endpoints."""
    assert is_local_base_url(None) is False
    assert is_local_base_url("   ") is False

    # Local loopback & LAN
    assert is_local_base_url("http://127.0.0.1:11434") is True
    assert is_local_base_url("http://localhost:8000/v1") is True
    assert is_local_base_url("http://[::1]:8080") is True
    assert is_local_base_url("http://192.168.1.50:11434") is True
    assert is_local_base_url("http://10.0.0.5:8000/v1") is True
    assert is_local_base_url("http://172.16.1.1:11434") is True
    assert is_local_base_url("http://fc00::1:11434") is True
    assert is_local_base_url("http://ollama:11434") is True
    assert is_local_base_url("http://vllm.lan:8000/v1") is True

    # Public cloud
    assert is_local_base_url("https://api.openai.com/v1") is False
    assert is_local_base_url("https://generativelanguage.googleapis.com") is False
    assert is_local_base_url("https://8.8.8.8:8000") is False

    # Metadata SSRF
    assert is_local_base_url("http://169.254.169.254") is False
    assert is_local_base_url("http://100.64.0.1:8000") is False


@pytest.mark.asyncio
async def test_resolve_and_pin_literal_success() -> None:
    """Literal IP in allowed CIDR returns successfully."""
    ip = await resolve_and_pin("127.0.0.1", 11434, DEFAULT_ALLOWED_CIDRS)
    assert str(ip) == "127.0.0.1"


@pytest.mark.asyncio
async def test_resolve_and_pin_metadata_rejection() -> None:
    """Metadata IP is unconditionally rejected even if allowed_cidrs includes it."""
    mistaken = [*DEFAULT_ALLOWED_CIDRS, ipaddress.ip_network("169.254.0.0/16")]
    with pytest.raises(EgressDeniedError) as exc_info:
        await resolve_and_pin("169.254.169.254", 11434, mistaken)
    assert exc_info.value.code == "OLLAMA_METADATA_DENIED"


@pytest.mark.asyncio
async def test_resolve_and_pin_cgnat_rejection() -> None:
    """CGNAT 100.64.0.0/10 metadata range is unconditionally rejected."""
    mistaken = [*DEFAULT_ALLOWED_CIDRS, ipaddress.ip_network("100.64.0.0/10")]
    with pytest.raises(EgressDeniedError) as exc_info:
        await resolve_and_pin("100.64.0.1", 11434, mistaken)
    assert exc_info.value.code == "OLLAMA_METADATA_DENIED"


@pytest.mark.asyncio
async def test_resolve_and_pin_outside_allowed_cidrs() -> None:
    """Public IP outside allowed CIDR list raises OLLAMA_CIDR_DENIED."""
    with pytest.raises(EgressDeniedError) as exc_info:
        await resolve_and_pin("8.8.8.8", 11434, DEFAULT_ALLOWED_CIDRS)
    assert exc_info.value.code == "OLLAMA_CIDR_DENIED"


@pytest.mark.asyncio
async def test_resolve_and_pin_dns_resolver() -> None:
    """DNS resolution with mock resolver evaluates all records and prevents rebinding."""

    async def mock_resolver(_host: str, _port: int) -> list[str]:
        return ["127.0.0.1"]

    ip = await resolve_and_pin("ollama.local", 11434, DEFAULT_ALLOWED_CIDRS, resolver=mock_resolver)
    assert str(ip) == "127.0.0.1"

    # Multi-record rebinding attack
    async def mock_rebinding(_host: str, _port: int) -> list[str]:
        return ["127.0.0.1", "169.254.169.254"]

    with pytest.raises(EgressDeniedError) as exc_rebinding:
        await resolve_and_pin(
            "rebinding.local", 11434, DEFAULT_ALLOWED_CIDRS, resolver=mock_rebinding
        )
    assert exc_rebinding.value.code == "OLLAMA_METADATA_DENIED"

    # Empty DNS response
    async def mock_empty(_host: str, _port: int) -> list[str]:
        return []

    with pytest.raises(EgressDeniedError) as exc_empty:
        await resolve_and_pin("nowhere.local", 11434, DEFAULT_ALLOWED_CIDRS, resolver=mock_empty)
    assert exc_empty.value.code == "OLLAMA_CIDR_DENIED"


def test_extract_ip_helper() -> None:
    """Verify _extract_ip handles IP objects, strings, and getaddrinfo tuples."""
    ip4 = ipaddress.ip_address("127.0.0.1")
    assert _extract_ip(ip4) == ip4
    assert _extract_ip("192.168.1.1") == ipaddress.ip_address("192.168.1.1")

    # getaddrinfo tuple format: (family, type, proto, canonname, sockaddr)
    gai_tuple = (2, 1, 6, "", ("10.0.0.1", 80))
    assert _extract_ip(gai_tuple) == ipaddress.ip_address("10.0.0.1")

    with pytest.raises(ValueError, match="Unable to parse IP address"):
        _extract_ip(12345)
