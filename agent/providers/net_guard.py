# Copyright 2026 Kanban Platform Contributors
"""Network security guards for LLM providers: resolve-then-check SSRF defense."""

from __future__ import annotations

import asyncio
import ipaddress
from typing import TYPE_CHECKING, Any

from agent.providers.errors import EgressDenied

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence
    from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network

__all__ = [
    "HARD_DENIED_NETWORKS",
    "Resolver",
    "is_hard_denied",
    "resolve_and_pin",
]

_GETADDRINFO_TUPLE_LEN: int = 5

# Hard-denied network ranges protecting cloud metadata, link-local, and multicast
HARD_DENIED_NETWORKS: tuple[IPv4Network | IPv6Network, ...] = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fd00:ec2::254/128"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("ff00::/8"),
    ipaddress.ip_network("::ffff:169.254.0.0/112"),
)

type Resolver = Callable[[str, int], Awaitable[Sequence[Any]]]


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
    allowed_cidrs: Sequence[IPv4Network | IPv6Network],
) -> IPv4Address | IPv6Address | None:
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        return None

    if is_hard_denied(literal_ip):
        msg = f"Host '{host}' resolves to hard-denied metadata or link-local network"
        raise EgressDenied(msg, code="OLLAMA_METADATA_DENIED")
    if not _is_in_allowed_cidrs(literal_ip, allowed_cidrs):
        msg = f"Host '{host}' is outside allowed CIDRs"
        raise EgressDenied(msg, code="OLLAMA_CIDR_DENIED")

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
        raise EgressDenied(msg, code="OLLAMA_CIDR_DENIED")

    return [_extract_ip(item) for item in raw_results]


async def resolve_and_pin(
    host: str,
    port: int,
    allowed_cidrs: Sequence[IPv4Network | IPv6Network],
    *,
    resolver: Resolver | None = None,
) -> IPv4Address | IPv6Address:
    """Resolve host and verify all resolved addresses against allowed and denied CIDRs.

    Raises EgressDenied with code 'OLLAMA_METADATA_DENIED' if any address matches
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
            raise EgressDenied(msg, code="OLLAMA_METADATA_DENIED")

    for ip in parsed_ips:
        if not _is_in_allowed_cidrs(ip, allowed_cidrs):
            msg = f"DNS resolution for '{host}' contains unapproved IP '{ip}' outside allowed CIDRs"
            raise EgressDenied(msg, code="OLLAMA_CIDR_DENIED")

    return parsed_ips[0]
