"""Security headers middleware and Content-Security-Policy definition.

Implements the hardened production HTTP response headers mandated by Section 5.4,
including the strict Content-Security-Policy, anti-framing, nosniff, and
standalone cleartext loopback protections, as well as spoof-resistant client IP
resolution with trusted proxy traversal.
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import os
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network
from typing import TYPE_CHECKING, Any, Final

from starlette.datastructures import Headers

from kanban.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from kanban.settings import Settings

CSP_POLICY: Final[str] = (
    "default-src 'none'; "
    "manifest-src 'self'; "
    "script-src 'self'; "
    "worker-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' blob: data:; "
    "font-src 'self'; "
    "connect-src 'self' wss:; "
    "media-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "require-trusted-types-for 'script'; "
    "trusted-types kanban-sanitizer dompurify;"
)

_SECURITY_HEADER_NAMES: Final[frozenset[bytes]] = frozenset(
    {
        b"content-security-policy",
        b"x-content-type-options",
        b"referrer-policy",
        b"x-frame-options",
        b"cross-origin-opener-policy",
        b"cross-origin-resource-policy",
        b"permissions-policy",
        b"strict-transport-security",
    }
)


def _extract_host(host_header: str) -> str:
    """Extract lowercase host without port, preserving IPv6 brackets."""
    host = host_header.strip().lower()
    if host.startswith("["):
        closing = host.find("]")
        if closing != -1:
            return host[: closing + 1]
    if ":" in host:
        return host.rsplit(":", 1)[0]
    return host


def _has_forwarded_https_proto(forwarded: str) -> bool:
    """Check RFC 7239 Forwarded header for proto=https."""
    for element in forwarded.split(","):
        for param in element.split(";"):
            key, sep, val = param.strip().partition("=")
            if sep and key.strip().lower() == "proto" and val.strip().strip('"').lower() == "https":
                return True
    return False


def _is_https_request(scope: Scope, headers: Headers) -> bool:
    """Determine whether request was received over HTTPS (direct or reverse proxy)."""
    if scope.get("scheme", "").lower() == "https":
        return True

    xf_proto = headers.get("x-forwarded-proto")
    if xf_proto and any(p.strip().lower() == "https" for p in xf_proto.split(",")):
        return True

    xf_scheme = headers.get("x-forwarded-scheme")
    if xf_scheme and any(s.strip().lower() == "https" for s in xf_scheme.split(",")):
        return True

    forwarded = headers.get("forwarded")
    return bool(forwarded and _has_forwarded_https_proto(forwarded))


def _normalize_host_idna(host_name: str) -> set[str]:
    """Generate canonical ASCII Punycode and Unicode representations of a host name."""
    seeds = {host_name}
    # Handle UTF-8 host header bytes decoded as latin-1 by ASGI/Starlette
    with contextlib.suppress(UnicodeError):
        seeds.add(host_name.encode("latin-1").decode("utf-8"))

    candidates = set(seeds)
    for seed in seeds:
        with contextlib.suppress(UnicodeError):
            idna_ascii = seed.encode("idna").decode("ascii")
            candidates.add(idna_ascii)
            candidates.add(idna_ascii.encode("ascii").decode("idna"))
    return candidates


def _is_host_allowed(host_name: str, allowed_hosts: frozenset[str] | set[str]) -> bool:
    """Check if host matches allowed cleartext hosts under IDN / Punycode normalization."""
    candidates = _normalize_host_idna(host_name)
    if any(h in allowed_hosts for h in candidates):
        return True

    for allowed in allowed_hosts:
        with contextlib.suppress(UnicodeError):
            if allowed.encode("idna").decode("ascii") in candidates:
                return True

    return False


def _get_raw_trusted_proxies() -> str:
    """Retrieve raw trusted proxies string from environment or application settings."""
    raw_env = os.environ.get("KB_TRUSTED_PROXIES") or os.environ.get("KANBAN_TRUSTED_PROXIES", "")
    if not raw_env.strip():
        try:
            raw_env = get_settings().trusted_proxies
        except (RuntimeError, ValueError):
            return ""
    return raw_env


def _parse_trusted_networks(
    trusted: Sequence[IPv4Network | IPv6Network | str] | str | None,
) -> tuple[IPv4Network | IPv6Network, ...]:
    """Parse trusted proxy CIDR entries from sequence, string, or environment."""
    if trusted is None:
        raw_str = _get_raw_trusted_proxies()
        entries: Sequence[IPv4Network | IPv6Network | str] = [
            item.strip() for item in raw_str.replace(" ", ",").split(",") if item.strip()
        ]
    elif isinstance(trusted, str):
        entries = [item.strip() for item in trusted.replace(" ", ",").split(",") if item.strip()]
    else:
        entries = trusted

    parsed_list: list[IPv4Network | IPv6Network] = []
    for item in entries:
        if isinstance(item, (IPv4Network, IPv6Network)):
            parsed_list.append(item)
            continue
        token = item.strip()
        if not token:
            continue
        try:
            parsed_list.append(ipaddress.ip_network(token, strict=False))
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
    if hasattr(scope, "scope"):
        scope = scope.scope
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


def _extract_header_val(scope: Mapping[str, Any], header_name_bytes: bytes) -> str | None:
    """Extract decoded header string from ASGI headers if present."""
    headers: Sequence[tuple[bytes, bytes]] = scope.get("headers", ())
    for key, value in headers:
        if key.lower() == header_name_bytes:
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
    """Walk X-Forwarded-For entries right-to-left and return first untrusted address."""
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


def _resolve_from_real_ip(
    real_ip_str: str,
    direct_ip: IPv4Address | IPv6Address,
) -> IPv4Address | IPv6Address:
    """Parse X-Real-IP candidate returning normalized address or direct peer fallback."""
    candidate_str = real_ip_str.strip().strip("[]")
    try:
        candidate = ipaddress.ip_address(candidate_str)
    except ValueError:
        return direct_ip
    else:
        if isinstance(candidate, IPv6Address) and candidate.ipv4_mapped is not None:
            return candidate.ipv4_mapped
        return candidate


def resolve_client_ip(
    scope: Mapping[str, Any],
    trusted_proxies: Sequence[IPv4Network | IPv6Network | str] | str | None = None,
) -> str:
    """Resolve spoof-resistant client IP address from ASGI connection scope.

    Uses scope['client'][0] as the direct peer. X-Forwarded-For and X-Real-IP headers
    are inspected ONLY if the direct peer is inside trusted_proxies (or KB_TRUSTED_PROXIES /
    KANBAN_TRUSTED_PROXIES).
    Untrusted peers have their direct peer IP returned immediately, ignoring all spoofed headers.
    When the direct peer is trusted, X-Forwarded-For is traversed right-to-left. If absent,
    X-Real-IP is inspected. Malformed entries immediately fall back to the direct peer.
    IPv4-mapped IPv6 addresses are normalized to IPv4. IPv6 clients are bucketed by /64 prefix.
    """
    if hasattr(scope, "scope"):
        scope = scope.scope
    peer = _extract_direct_peer(scope)
    if isinstance(peer, str):
        return peer

    trusted_nets = _parse_trusted_networks(trusted_proxies)
    if not trusted_nets or not _is_trusted(peer, trusted_nets):
        return _format_ip(peer)

    # 1. Check X-Forwarded-For
    xff_str = _extract_header_val(scope, b"x-forwarded-for")
    if xff_str:
        candidate = _resolve_from_xff(xff_str, trusted_nets, peer)
        if candidate != peer or not _is_trusted(candidate, trusted_nets):
            return _format_ip(candidate)

    # 2. Fall back to X-Real-IP if X-Forwarded-For is absent
    x_real_ip = _extract_header_val(scope, b"x-real-ip")
    if x_real_ip:
        candidate = _resolve_from_real_ip(x_real_ip, peer)
        return _format_ip(candidate)

    return _format_ip(peer)


class SecurityHeadersMiddleware:
    """Pure ASGI middleware enforcing hardening headers and standalone Host rules."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        """Initialize middleware with inner ASGI application and settings."""
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process incoming ASGI HTTP request and enforce security headers."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check standalone cleartext block only when explicitly enabled via KB_BLOCK_CLEARTEXT_HTTP
        if self.settings.deployment_mode == "standalone" and self.settings.block_cleartext_http:
            headers = Headers(scope=scope)
            if not _is_https_request(scope, headers):
                host_header = headers.get("host")
                if not host_header:
                    await self._send_problem(
                        send,
                        status=400,
                        title="Bad Request",
                        detail="Host header is required",
                    )
                    return

                host_name = _extract_host(host_header)
                if not _is_host_allowed(host_name, self.settings.standalone_cleartext_hosts):
                    await self._send_problem(
                        send,
                        status=403,
                        title="CLEARTEXT_HTTP_BLOCKED",
                        detail=(
                            "Standalone mode serves cleartext HTTP only to localhost. "
                            "Put a TLS reverse proxy in front or add the host to "
                            "KB_STANDALONE_CLEARTEXT_HOSTS."
                        ),
                    )
                    return

        # Wrap send to inject security headers
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = self._inject_security_headers(message.get("headers", []))
            await send(message)

        await self.app(scope, receive, send_wrapper)

    def _inject_security_headers(
        self, existing_headers: list[tuple[bytes, bytes]]
    ) -> list[tuple[bytes, bytes]]:
        """Construct canonical security headers while preserving route-specific CSP."""
        custom_csp: bytes | None = None
        raw_headers: list[tuple[bytes, bytes]] = []
        for name, value in existing_headers:
            if name.lower() == b"content-security-policy":
                custom_csp = value
            elif name.lower() not in _SECURITY_HEADER_NAMES:
                raw_headers.append((name, value))

        csp_val = custom_csp if custom_csp is not None else CSP_POLICY.encode("latin1")
        raw_headers.append((b"content-security-policy", csp_val))
        raw_headers.append((b"x-content-type-options", b"nosniff"))
        raw_headers.append((b"referrer-policy", b"no-referrer"))
        raw_headers.append((b"x-frame-options", b"DENY"))
        raw_headers.append((b"cross-origin-opener-policy", b"same-origin"))
        raw_headers.append((b"cross-origin-resource-policy", b"same-origin"))
        raw_headers.append((b"permissions-policy", b"camera=(), microphone=(), geolocation=()"))

        if self.settings.deployment_mode == "production":
            hsts_value = f"max-age={self.settings.hsts_max_age}; includeSubDomains".encode("latin1")
            raw_headers.append((b"strict-transport-security", hsts_value))

        return raw_headers

    async def _send_problem(
        self,
        send: Send,
        status: int,
        title: str,
        detail: str,
    ) -> None:
        body = json.dumps(
            {
                "type": "about:blank",
                "title": title,
                "status": status,
                "detail": detail,
            }
        ).encode("utf-8")

        raw_headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"application/problem+json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"content-security-policy", CSP_POLICY.encode("latin1")),
            (b"x-content-type-options", b"nosniff"),
            (b"referrer-policy", b"no-referrer"),
            (b"x-frame-options", b"DENY"),
            (b"cross-origin-opener-policy", b"same-origin"),
            (b"cross-origin-resource-policy", b"same-origin"),
            (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
        ]

        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": raw_headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
            }
        )
