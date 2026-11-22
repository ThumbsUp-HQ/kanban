# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Shared DNS-pinned SSRF protection and socket transport (S2.1, S5.4, S10.2).

Provides:
- is_public_global_ip: Strict verification rejecting RFC1918, loopback, CGNAT,
  cloud metadata (169.254.169.254), IPv6 ULA, IPv4-mapped, and NAT64 (64:ff9b::/96).
- resolve_and_select_pinned_ip: Async DNS resolution with 2.0s timeout and
  all-record verification preventing DNS-rebinding attacks.
- PinnedConnectionTransport: Direct IP TLS transport preserving SNI.
- validate_not_redirect: HTTP 300..399 status validation preventing redirect bypasses.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

from kanban.api.problems import ProblemException

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

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

_HTTP_REDIRECT_MIN: Final[int] = 300
_HTTP_REDIRECT_MAX: Final[int] = 399


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

    def __init__(
        self,
        port: int = 443,
        error_code: str = "MEDIA_HOST_BLOCKED",
        error_title: str = "Media Host Blocked",
    ) -> None:
        """Initialize default resolver with target port and error code."""
        self._port = port
        self._error_code = error_code
        self._error_title = error_title

    async def resolve(self, host: str) -> Sequence[IPv4Address | IPv6Address]:
        """Resolve host into distinct IPv4 and IPv6 addresses."""
        loop = asyncio.get_running_loop()
        try:
            addr_info = await loop.getaddrinfo(
                host,
                self._port,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as err:
            msg = f"DNS resolution failed for host '{host}': {err}"
            raise ProblemException(
                code=self._error_code,
                status=403,
                title=self._error_title,
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


async def _execute_resolution(
    active_resolver: object,
    host: str,
    timeout: float,  # noqa: ASYNC109
) -> list[IPv4Address | IPv6Address]:
    """Execute host resolution with timeout and return list of IP address objects."""
    if hasattr(active_resolver, "resolve"):
        raw_res = active_resolver.resolve(host)
    elif callable(active_resolver):
        raw_res = active_resolver(host)
    else:
        msg = f"Invalid DNS resolver: {active_resolver!r}"
        raise TypeError(msg)

    if asyncio.iscoroutine(raw_res) or hasattr(raw_res, "__await__"):
        async with asyncio.timeout(timeout):
            raw_records = await raw_res
    else:
        raw_records = raw_res

    records: list[IPv4Address | IPv6Address] = []
    for r in raw_records:
        if isinstance(r, (IPv4Address, IPv6Address)):
            records.append(r)
        else:
            records.append(ipaddress.ip_address(str(r)))
    return records


async def resolve_and_select_pinned_ip(
    host: str,
    resolver: (
        AsyncHostResolver
        | Callable[
            [str],
            Sequence[str | IPv4Address | IPv6Address]
            | Awaitable[Sequence[str | IPv4Address | IPv6Address]],
        ]
        | None
    ) = None,
    *,
    timeout: float = 2.0,  # noqa: ASYNC109
    error_code: str = "SSRF_HOST_BLOCKED",
    error_title: str = "SSRF Host Blocked",
) -> IPv4Address | IPv6Address:
    """Resolve host once with DNS timeout and enforce all returned IPs are public global.

    Rejects immediately if zero records are returned, resolution times out (2.0s),
    or ANY returned record fails is_public_global_ip (preventing mixed responses).
    Returns the first verified IP address for pinned socket connection.
    """
    active_resolver = resolver or DefaultAsyncHostResolver()
    try:
        records = await _execute_resolution(active_resolver, host, timeout)
    except TimeoutError as err:
        msg = f"DNS resolution timed out for host '{host}'"
        raise SSRFBlockedError(
            code=error_code,
            status=403,
            title=error_title,
            detail=msg,
        ) from err
    except ProblemException:
        raise
    except Exception as err:
        msg = f"DNS resolution failed for host '{host}': {err}"
        raise SSRFBlockedError(
            code=error_code,
            status=403,
            title=error_title,
            detail=msg,
        ) from err

    if not records:
        msg = f"DNS resolution returned zero records for host '{host}'"
        raise SSRFBlockedError(
            code=error_code,
            status=403,
            title=error_title,
            detail=msg,
        )

    for rec in records:
        if not is_public_global_ip(rec):
            msg = (
                f"External host '{host}' resolved to blocked non-public "
                f"IP address '{rec}' (SSRF guard)"
            )
            raise SSRFBlockedError(
                code=error_code,
                status=403,
                title=error_title,
                detail=msg,
            )

    return records[0]


@runtime_checkable
class PinnedConnectionTransport(Protocol):
    """Protocol for opening a direct IP TLS connection to an external host."""

    async def open_connection(
        self,
        ip: str,
        port: int,
        server_hostname: str,
        connect_timeout: float,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Open TLS connection directly to ip literal verifying server_hostname."""
        ...


class DefaultPinnedConnectionTransport:
    """Default transport establishing TLS socket directly to pinned IP."""

    async def open_connection(
        self,
        ip: str,
        port: int,
        server_hostname: str,
        connect_timeout: float,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Connect TCP to pinned IP with TLS verification against server_hostname."""
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        ssl_ctx.check_hostname = True
        return await asyncio.wait_for(
            asyncio.open_connection(
                host=ip,
                port=port,
                ssl=ssl_ctx,
                server_hostname=server_hostname,
            ),
            timeout=connect_timeout,
        )


class SSRFBlockedError(ProblemException):
    """Raised when an egress target host or redirect violates SSRF egress policy."""

    def __init__(
        self,
        detail: str,
        code: str = "SSRF_HOST_BLOCKED",
        status: int = 403,
        title: str = "SSRF Blocked",
    ) -> None:
        """Initialize SSRFBlockedError with status, code, and detail."""
        super().__init__(status=status, code=code, title=title, detail=detail)


def validate_not_redirect(
    status_code: int,
    original_host: str = "",
    *,
    error_code: str = "REDIRECT_BLOCKED",
    error_title: str = "Redirect Blocked",
) -> None:
    """Raise ProblemException if status code indicates an HTTP redirect (300..399)."""
    if _HTTP_REDIRECT_MIN <= status_code <= _HTTP_REDIRECT_MAX:
        host_msg = f"Upstream host '{original_host}'" if original_host else "Upstream host"
        msg = f"{host_msg} attempted redirect with status {status_code}"
        raise SSRFBlockedError(
            code=error_code,
            status=502,
            title=error_title,
            detail=msg,
        )
