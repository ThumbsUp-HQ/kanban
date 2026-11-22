"""DNS-resolve-then-pin SSRF protection for external media proxy (S5.4, S10.2).

Delegates core IP verification, unwrapping, and host resolution to shared
kanban.security.ssrf while preserving MEDIA_HOST_BLOCKED error codes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kanban.security.ssrf import (
    _BLOCKED_NETWORKS,
    _NAT64_PREFIX,
    AsyncHostResolver,
    DefaultAsyncHostResolver,
    _unwrap_ip,
    is_public_global_ip,
)
from kanban.security.ssrf import (
    resolve_and_select_pinned_ip as _shared_resolve_and_select_pinned_ip,
)

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address

__all__ = [
    "_BLOCKED_NETWORKS",
    "_NAT64_PREFIX",
    "AsyncHostResolver",
    "DefaultAsyncHostResolver",
    "_unwrap_ip",
    "is_public_global_ip",
    "resolve_and_select_pinned_ip",
]


async def resolve_and_select_pinned_ip(
    host: str,
    resolver: AsyncHostResolver | None = None,
) -> IPv4Address | IPv6Address:
    """Resolve host once with DNS timeout and enforce all returned IPs are public global.

    Preserves MEDIA_HOST_BLOCKED error code for media proxy backwards compatibility.
    """
    return await _shared_resolve_and_select_pinned_ip(
        host,
        resolver,
        error_code="MEDIA_HOST_BLOCKED",
        error_title="Media Host Blocked",
    )
