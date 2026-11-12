"""DNS-resolve-then-pin SSRF protection for external media proxy (S5.4, S10.2)."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
from typing import TYPE_CHECKING, Protocol

from kanban.api.problems import ProblemException

if TYPE_CHECKING:
    from collections.abc import Sequence

_NAT64_PREFIX: IPv6Network = ipaddress.IPv6Network("64:ff9b::/96")

_BLOCKED_NETWORKS: tuple[IPv4Network | IPv6Network, ...] = (
    # IPv4 loopback & unspecified
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("0.0.0.0/8"),
    # RFC 1918 private
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    # Link-local / Cloud metadata (AWS/GCP IMDS 169.254.169.254)
    ipaddress.ip_network("169.254.0.0/16"),
    # Carrier-Grade NAT (CGNAT)
    ipaddress.ip_network("100.64.0.0/10"),
    # Benchmarking & Documentation
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    # Broadcast & Multicast
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    # IPv6 loopback & unspecified
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/128"),
    # IPv6 link-local
    ipaddress.ip_network("fe80::/10"),
    # IPv6 Unique Local (ULA) & Site-Local
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fec0::/10"),
    # IPv6 multicast & documentation
    ipaddress.ip_network("ff00::/8"),
    ipaddress.ip_network("2001:db8::/32"),
)


def _unwrap_ip(ip: IPv4Address | IPv6Address) -> IPv4Address | IPv6Address:
    """Unwrap IPv4-mapped IPv6 or NAT64-embedded IPv4 address."""
    if isinstance(ip, IPv6Address):
        if ip.ipv4_mapped is not None:
            return ip.ipv4_mapped
        if ip in _NAT64_PREFIX:
            return ipaddress.IPv4Address(ip.packed[-4:])
    return ip


def is_public_global_ip(addr: str | IPv4Address | IPv6Address) -> bool:
    """Return True if IP address is a publicly routable global unicast address.

    Rejects loopback, RFC 1918 private, link-local/metadata, CGNAT, IPv6 ULA,
    multicast, broadcast, documentation, and unwrapped IPv4-mapped or NAT64 addresses.
    """
    if isinstance(addr, str):
        cleaned = addr.strip().strip("[]")
        try:
            raw_ip = ipaddress.ip_address(cleaned)
        except ValueError:
            return False
    else:
        raw_ip = addr

    ip = _unwrap_ip(raw_ip)

    if not ip.is_global:
        return False

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_reserved
    ):
        return False

    return not any(ip in net for net in _BLOCKED_NETWORKS)


class AsyncHostResolver(Protocol):
    """Protocol for asynchronous DNS host resolution."""

    async def resolve(self, host: str) -> Sequence[IPv4Address | IPv6Address]:
        """Resolve host returning sequence of distinct IP addresses."""
        ...


class DefaultAsyncHostResolver:
    """Production DNS resolver delegating to asyncio.get_running_loop().getaddrinfo."""

    async def resolve(self, host: str) -> Sequence[IPv4Address | IPv6Address]:
        """Resolve host into distinct IPv4 and IPv6 addresses."""
        loop = asyncio.get_running_loop()
        try:
            addr_info = await loop.getaddrinfo(
                host,
                443,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as err:
            msg = f"DNS resolution failed for host '{host}': {err}"
            raise ProblemException(
                code="MEDIA_HOST_BLOCKED",
                status=403,
                title="Media Host Blocked",
                detail=msg,
            ) from err

        ips: list[IPv4Address | IPv6Address] = []
        seen: set[str] = set()
        for _family, _socktype, _proto, _canonname, sockaddr in addr_info:
            raw_ip = str(sockaddr[0])
            if raw_ip not in seen:
                seen.add(raw_ip)
                ips.append(ipaddress.ip_address(raw_ip))
        return ips


async def resolve_and_select_pinned_ip(
    host: str,
    resolver: AsyncHostResolver | None = None,
) -> IPv4Address | IPv6Address:
    """Resolve host once with DNS timeout and enforce all returned IPs are public global.

    Rejects immediately if zero records are returned, resolution times out (2.0s),
    or ANY returned record fails is_public_global_ip (preventing mixed responses).
    Returns the first verified IP address for pinned socket connection.
    """
    active_resolver = resolver or DefaultAsyncHostResolver()
    try:
        records = await asyncio.wait_for(active_resolver.resolve(host), timeout=2.0)
    except TimeoutError as err:
        msg = f"DNS resolution timed out for media host '{host}'"
        raise ProblemException(
            code="MEDIA_HOST_BLOCKED",
            status=403,
            title="Media Host Blocked",
            detail=msg,
        ) from err

    if not records:
        msg = f"DNS resolution returned zero records for media host '{host}'"
        raise ProblemException(
            code="MEDIA_HOST_BLOCKED",
            status=403,
            title="Media Host Blocked",
            detail=msg,
        )

    for rec in records:
        if not is_public_global_ip(rec):
            msg = (
                f"External media host '{host}' resolved to blocked non-public "
                f"IP address '{rec}' (SSRF guard)"
            )
            raise ProblemException(
                code="MEDIA_HOST_BLOCKED",
                status=403,
                title="Media Host Blocked",
                detail=msg,
            )

    return records[0]
