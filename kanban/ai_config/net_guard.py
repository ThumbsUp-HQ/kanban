# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Network security guards for AI endpoints: resolve-then-check SSRF defense."""

from __future__ import annotations

import asyncio
import ipaddress
import urllib.parse
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence
    from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network

__all__ = [
    "HARD_DENIED_NETWORKS",
    "IPV6_ULA_NETWORKS",
    "LOOPBACK_NETWORKS",
    "PRIVATE_LAN_NETWORKS",
    "PRIVATE_LAN_TLDS",
    "RFC1918_NETWORKS",
    "EgressDeniedError",
    "Resolver",
    "is_hard_denied",
    "is_local_base_url",
    "is_local_or_private_ip",
    "is_private_lan_hostname",
    "resolve_and_pin",
]

_GETADDRINFO_TUPLE_LEN: int = 5

# Hard-denied network ranges protecting cloud metadata, link-local, and multicast
HARD_DENIED_NETWORKS: tuple[IPv4Network | IPv6Network, ...] = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("fd00:ec2::254/128"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("ff00::/8"),
    ipaddress.ip_network("::ffff:169.254.0.0/112"),
    ipaddress.ip_network("::ffff:100.64.0.0/106"),
)

RFC1918_NETWORKS: tuple[IPv4Network, ...] = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)

IPV6_ULA_NETWORKS: tuple[IPv6Network, ...] = (ipaddress.IPv6Network("fc00::/7"),)

LOOPBACK_NETWORKS: tuple[IPv4Network | IPv6Network, ...] = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
)

PRIVATE_LAN_NETWORKS: tuple[IPv4Network | IPv6Network, ...] = (
    *LOOPBACK_NETWORKS,
    *RFC1918_NETWORKS,
    *IPV6_ULA_NETWORKS,
)

_LOOPBACK_HOSTS: frozenset[str] = frozenset(
    {"127.0.0.1", "::1", "[::1]", "localhost", "localhost.localdomain"}
)

PRIVATE_LAN_TLDS: tuple[str, ...] = (
    ".local",
    ".lan",
    ".internal",
    ".home",
    ".home.arpa",
    ".corp",
    ".intranet",
    ".private",
    ".test",
)

type Resolver = Callable[[str, int], Awaitable[Sequence[Any]]]


class EgressDeniedError(Exception):
    """Raised when network egress is denied due to SSRF protection or CIDR policy."""

    def __init__(self, message: str, code: str = "EGRESS_DENIED") -> None:
        """Initialize egress denial with diagnostic error code."""
        super().__init__(message)
        self.message: str = message
        self.code: str = code


def is_hard_denied(ip: IPv4Address | IPv6Address) -> bool:
    """Check if an IP address belongs to any unconditionally denied metadata/link-local network."""
    for network in HARD_DENIED_NETWORKS:
        if ip in network:
            return True

    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        mapped = ip.ipv4_mapped
        for network in HARD_DENIED_NETWORKS:
            if mapped in network:
                return True

    return False


def is_local_or_private_ip(ip: IPv4Address | IPv6Address) -> bool:
    """Check if an IP address belongs to loopback, RFC1918, or IPv6 ULA without hard denial."""
    if is_hard_denied(ip):
        return False

    for network in PRIVATE_LAN_NETWORKS:
        if ip in network:
            return True

    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        mapped = ip.ipv4_mapped
        for network in PRIVATE_LAN_NETWORKS:
            if mapped in network:
                return True

    return False


def is_private_lan_hostname(host: str) -> bool:
    """Check if a hostname represents loopback, single-label name, or private LAN domain."""
    cleaned = host.strip("[]").lower()
    if not cleaned:
        return False
    if cleaned in _LOOPBACK_HOSTS:
        return True
    if any(cleaned.endswith(tld) for tld in PRIVATE_LAN_TLDS):
        return True
    return "." not in cleaned


def is_local_base_url(url: str | None) -> bool:
    """Check if a base URL targets loopback, RFC1918, ULA, or private LAN host."""
    if url is None:
        return False
    trimmed = url.strip()
    if not trimmed:
        return False
    parsed = urllib.parse.urlsplit(trimmed)
    host = (parsed.hostname or "").strip("[]").lower()
    if not host:
        return False
    if host in _LOOPBACK_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return is_local_or_private_ip(ip)
    except ValueError:
        return is_private_lan_hostname(host)


def _is_in_allowed_cidrs(
    ip: IPv4Address | IPv6Address,
    allowed_cidrs: Sequence[IPv4Network | IPv6Network],
) -> bool:
    for cidr in allowed_cidrs:
        if ip in cidr:
            return True

    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        mapped = ip.ipv4_mapped
        for cidr in allowed_cidrs:
            if mapped in cidr:
                return True

    return False


def _extract_ip(entry: object) -> IPv4Address | IPv6Address:
    if isinstance(entry, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        return entry
    if isinstance(entry, str):
        return ipaddress.ip_address(entry)
    if isinstance(entry, (tuple, list)) and len(entry) >= _GETADDRINFO_TUPLE_LEN:
        sockaddr = entry[4]
        if isinstance(sockaddr, (tuple, list)) and len(sockaddr) >= 1:
            return ipaddress.ip_address(str(sockaddr[0]))
    msg = f"Unable to parse IP address from resolver record: {entry!r}"
    raise ValueError(msg)


def _check_literal_ip(
    host: str,
    allowed_cidrs: Sequence[IPv4Network | IPv6Network] | None,
) -> IPv4Address | IPv6Address | None:
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        return None

    if is_hard_denied(literal_ip):
        msg = f"Host '{host}' resolves to hard-denied metadata or link-local network"
        raise EgressDeniedError(msg, code="OLLAMA_METADATA_DENIED")
    if allowed_cidrs is not None and not _is_in_allowed_cidrs(literal_ip, allowed_cidrs):
        msg = f"Host '{host}' is outside allowed CIDRs"
        raise EgressDeniedError(msg, code="OLLAMA_CIDR_DENIED")

    return literal_ip


async def _resolve_ips(
    host: str,
    port: int,
    resolver: Resolver | None,
) -> list[IPv4Address | IPv6Address]:
    if resolver is not None:
        raw_results = await resolver(host, port)
    else:
        loop = asyncio.get_running_loop()
        raw_results = await loop.getaddrinfo(host, port)

    if not raw_results:
        msg = f"DNS resolution for '{host}' returned zero addresses"
        raise EgressDeniedError(msg, code="OLLAMA_CIDR_DENIED")

    return [_extract_ip(item) for item in raw_results]


async def resolve_and_pin(
    host: str,
    port: int,
    allowed_cidrs: Sequence[IPv4Network | IPv6Network] | None = None,
    *,
    resolver: Resolver | None = None,
) -> IPv4Address | IPv6Address:
    """Resolve host and verify all resolved addresses against allowed and denied CIDRs.

    Raises EgressDeniedError with code 'OLLAMA_METADATA_DENIED' if any address matches
    cloud metadata or link-local ranges, or 'OLLAMA_CIDR_DENIED' if any address
    falls outside the allowed CIDR list.
    """
    literal = _check_literal_ip(host, allowed_cidrs)
    if literal is not None:
        return literal

    parsed_ips = await _resolve_ips(host, port, resolver)

    # Multi-record rebinding defense: EVERY resolved address must be tested
    for ip in parsed_ips:
        if is_hard_denied(ip):
            msg = f"DNS resolution for '{host}' contains hard-denied metadata IP '{ip}'"
            raise EgressDeniedError(msg, code="OLLAMA_METADATA_DENIED")

    if allowed_cidrs is not None:
        for ip in parsed_ips:
            if not _is_in_allowed_cidrs(ip, allowed_cidrs):
                msg = (
                    f"DNS resolution for '{host}' contains unapproved IP '{ip}' "
                    "outside allowed CIDRs"
                )
                raise EgressDeniedError(msg, code="OLLAMA_CIDR_DENIED")

    return parsed_ips[0]
