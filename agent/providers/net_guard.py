# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Network security guards for LLM providers: resolve-then-check SSRF defense."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.providers.errors import EgressDenied
from kanban.ai_config.net_guard import (
    HARD_DENIED_NETWORKS,
    EgressDeniedError,
    Resolver,
    _extract_ip,
    is_hard_denied,
)
from kanban.ai_config.net_guard import (
    resolve_and_pin as _core_resolve_and_pin,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network

__all__ = [
    "HARD_DENIED_NETWORKS",
    "Resolver",
    "_extract_ip",
    "is_hard_denied",
    "resolve_and_pin",
]


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
    try:
        return await _core_resolve_and_pin(host, port, allowed_cidrs, resolver=resolver)
    except EgressDeniedError as err:
        raise EgressDenied(err.message, code=err.code) from err
