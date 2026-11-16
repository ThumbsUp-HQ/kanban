"""Security headers middleware and Content-Security-Policy definition.

Implements the hardened production HTTP response headers mandated by Section 5.4,
including the strict Content-Security-Policy, anti-framing, nosniff, and
standalone cleartext loopback protections.
"""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING, Final

from starlette.datastructures import Headers

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from kanban.settings import Settings

CSP_POLICY: Final[str] = (
    "default-src 'none'; "
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

        # Check standalone cleartext block
        if self.settings.deployment_mode == "standalone":
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
