"""Spoof-resistant client IP resolution with trusted proxy traversal (S2.4, S3.3).

Exposes resolve_client_ip for resolving peer identifiers from ASGI scopes while
protecting against X-Forwarded-For header spoofing and IPv6 subnet rotation attacks.
"""

from __future__ import annotations

import ipaddress
import os
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def _parse_trusted_networks(
    trusted: Sequence[IPv4Network | IPv6Network | str] | str | None,
) -> tuple[IPv4Network | IPv6Network, ...]:
    """Parse trusted proxy CIDR entries from sequence, string, or environment."""
    if trusted is None:
        raw_env = os.environ.get("KANBAN_TRUSTED_PROXIES") or os.environ.get(
            "KB_TRUSTED_PROXIES", ""
        )
        if not raw_env.strip():
            return ()
        entries = [item.strip() for item in raw_env.replace(" ", ",").split(",") if item.strip()]
    elif isinstance(trusted, str):
        entries = [item.strip() for item in trusted.replace(" ", ",").split(",") if item.strip()]
    else:
        parsed: list[IPv4Network | IPv6Network] = []
        for item in trusted:
            if isinstance(item, (IPv4Network, IPv6Network)):
                parsed.append(item)
            elif item.strip():
                parsed.append(ipaddress.ip_network(item.strip(), strict=False))
        return tuple(parsed)

    parsed_list: list[IPv4Network | IPv6Network] = []
    for entry in entries:
        try:
            parsed_list.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return tuple(parsed_list)


def _is_trusted(
    ip: IPv4Address | IPv6Address,
    trusted_networks: Sequence[IPv4Network | IPv6Network],
) -> bool:
    """Determine whether an IP address falls within configured trusted proxy CIDRs."""
    return any(ip in net for net in trusted_networks)


def _format_ip(ip: IPv4Address | IPv6Address) -> str:
    """Format IP address normalizing IPv4-mapped IPv6 and bucketing IPv6 by /64."""
    if isinstance(ip, IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        network = IPv6Network(f"{ip}/64", strict=False)
        return f"{network.network_address}/64"
    return str(ip)


def _extract_direct_peer(scope: Mapping[str, Any]) -> IPv4Address | IPv6Address | str:
    """Extract and normalize the direct peer IP from the ASGI connection scope."""
    client_info = scope.get("client")
    direct_peer_str: str = ""
    if client_info and len(client_info) > 0 and client_info[0]:
        direct_peer_str = str(client_info[0]).strip().strip("[]")

    if not direct_peer_str:
        return ipaddress.ip_address("127.0.0.1")

    try:
        ip = ipaddress.ip_address(direct_peer_str)
    except ValueError:
        return direct_peer_str
    if isinstance(ip, IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _extract_xff_header(scope: Mapping[str, Any]) -> str | None:
    """Extract decoded X-Forwarded-For header string from ASGI headers if present."""
    headers: Sequence[tuple[bytes, bytes]] = scope.get("headers", ())
    for key, value in headers:
        if key.lower() == b"x-forwarded-for":
            try:
                decoded = value.decode("utf-8").strip()
            except UnicodeDecodeError:
                return None
            return decoded or None
    return None


def _resolve_from_xff(
    xff_str: str,
    trusted_nets: Sequence[IPv4Network | IPv6Network],
    direct_ip: IPv4Address | IPv6Address,
) -> IPv4Address | IPv6Address:
    """Walk X-Forwarded-For entries right-to-left and return the client address."""
    entries = [elem.strip().strip("[]") for elem in xff_str.split(",") if elem.strip()]
    if not entries:
        return direct_ip

    leftmost: IPv4Address | IPv6Address | None = None
    for entry in reversed(entries):
        try:
            candidate = ipaddress.ip_address(entry)
        except ValueError:
            return direct_ip

        if isinstance(candidate, IPv6Address) and candidate.ipv4_mapped is not None:
            candidate = candidate.ipv4_mapped

        leftmost = candidate
        if not _is_trusted(candidate, trusted_nets):
            return candidate

    return leftmost or direct_ip


def resolve_client_ip(
    scope: Mapping[str, Any],
    trusted_proxies: Sequence[IPv4Network | IPv6Network | str] | str | None = None,
) -> str:
    """Resolve spoof-resistant client IP address from ASGI connection scope.

    Uses scope['client'][0] as the direct peer. X-Forwarded-For headers are inspected
    only if the direct peer is inside trusted_proxies (or KANBAN_TRUSTED_PROXIES).
    Walks X-Forwarded-For right-to-left and returns the first untrusted address.
    Malformed entries immediately fall back to the direct peer. IPv4-mapped IPv6
    addresses are normalized to IPv4. IPv6 clients are bucketed by their /64 prefix.
    """
    peer = _extract_direct_peer(scope)
    if isinstance(peer, str):
        return peer

    trusted_nets = _parse_trusted_networks(trusted_proxies)
    if not trusted_nets or not _is_trusted(peer, trusted_nets):
        return _format_ip(peer)

    xff_str = _extract_xff_header(scope)
    if not xff_str:
        return _format_ip(peer)

    client_ip = _resolve_from_xff(xff_str, trusted_nets, peer)
    return _format_ip(client_ip)
