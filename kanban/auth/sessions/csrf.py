# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Session-bound double-submit CSRF token generation and validation middleware (KB-P2-02)."""

from __future__ import annotations

import base64
import binascii
import hmac
import os
import secrets
import uuid
from typing import TYPE_CHECKING, Final

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from kanban.api.problems import Problem
from kanban.api.request_id import get_request_id
from kanban.security.keys import derive_subkey

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = [
    "CSRF_COOKIE_NAME",
    "CSRF_EXEMPT_PATHS",
    "CSRF_HEADER_NAME",
    "PRE_SESSION_ID",
    "CsrfMiddleware",
    "build_clear_csrf_cookie_header",
    "build_set_csrf_cookie_header",
    "extract_csrf_cookie",
    "generate_csrf_token",
    "validate_csrf_token",
]

CSRF_COOKIE_NAME: Final[str] = "__Host-kb_csrf"
CSRF_HEADER_NAME: Final[str] = "X-CSRF-Token"
PRE_SESSION_ID: Final[uuid.UUID] = uuid.UUID(int=0)
NONCE_BYTES_LEN: Final[int] = 16
SIG_BYTES_LEN: Final[int] = 32

# Explicit list of endpoints exempt from CSRF validation
CSRF_EXEMPT_PATHS: Final[tuple[str, ...]] = (
    # Health check endpoints: read-only/monitoring with no session state
    "/api/v1/healthz",
    "/health",
    # Initial session endpoint: safe GET/discovery endpoint used to obtain pre-session CSRF token
    "/api/v1/auth/session",
)


def generate_csrf_token(session_id: uuid.UUID, session_hmac_key: bytes) -> str:
    """Generate session-bound HMAC CSRF token with a fresh 16-byte random nonce."""
    nonce = secrets.token_bytes(NONCE_BYTES_LEN)
    csrf_key = derive_subkey(session_hmac_key, "session/csrf")
    msg = session_id.bytes + nonce
    signature = hmac.new(csrf_key, msg, "sha256").digest()

    b64_nonce = base64.urlsafe_b64encode(nonce).rstrip(b"=").decode("ascii")
    b64_sig = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{b64_nonce}.{b64_sig}"


def validate_csrf_token(token: str, session_id: uuid.UUID, session_hmac_key: bytes) -> bool:
    """Verify cryptographic authenticity of session-bound CSRF token."""
    if not token or "." not in token:
        return False

    parts = token.split(".")
    if len(parts) != 2:  # noqa: PLR2004
        return False

    b64_nonce, b64_sig = parts
    try:
        nonce_pad = "=" * (-len(b64_nonce) % 4)
        nonce = base64.urlsafe_b64decode(b64_nonce + nonce_pad)

        sig_pad = "=" * (-len(b64_sig) % 4)
        given_sig = base64.urlsafe_b64decode(b64_sig + sig_pad)
    except (ValueError, binascii.Error):
        return False

    if len(nonce) != NONCE_BYTES_LEN or len(given_sig) != SIG_BYTES_LEN:
        return False

    csrf_key = derive_subkey(session_hmac_key, "session/csrf")
    expected_sig = hmac.new(csrf_key, session_id.bytes + nonce, "sha256").digest()

    return hmac.compare_digest(expected_sig, given_sig)


def extract_csrf_cookie(request: Request) -> str | None:
    """Extract single __Host-kb_csrf cookie from request."""
    return request.cookies.get(CSRF_COOKIE_NAME)


def build_set_csrf_cookie_header(csrf_token: str) -> str:
    """Format Set-Cookie header for __Host-kb_csrf (Strict SameSite, non-HttpOnly for SPA)."""
    return f"{CSRF_COOKIE_NAME}={csrf_token}; Path=/; Secure; SameSite=Strict"


def build_clear_csrf_cookie_header() -> str:
    """Format Set-Cookie header to clear __Host-kb_csrf."""
    return f"{CSRF_COOKIE_NAME}=; Path=/; Secure; SameSite=Strict; Max-Age=0"


class CsrfMiddleware(BaseHTTPMiddleware):
    """ASGI middleware enforcing session-bound double-submit CSRF and browser metadata defenses."""

    def __init__(
        self,
        app: ASGIApp,
        session_hmac_key: bytes | None = None,
    ) -> None:
        """Initialize middleware with key material for token verification."""
        super().__init__(app)
        self._session_hmac_key = session_hmac_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Fast-path bypass for non-HTTP, safe methods, and exempt paths for streaming."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        path = scope.get("path", "")
        if (
            method in ("GET", "HEAD", "OPTIONS", "TRACE")
            or not path.startswith("/api/")
            or path in CSRF_EXEMPT_PATHS
        ):
            await self.app(scope, receive, send)
            return

        await super().__call__(scope, receive, send)

    def _get_key(self, request: Request) -> bytes:
        """Resolve session HMAC key from instance attribute or request app state."""
        if self._session_hmac_key is not None:
            return self._session_hmac_key
        km = getattr(request.app.state, "key_material", None)
        if km is not None:
            return km.session_hmac_key  # type: ignore[no-any-return]
        return b"\x00" * 32

    def _validate_metadata(self, request: Request) -> str | None:
        """Validate browser security headers (Sec-Fetch-Site and Origin)."""
        sec_fetch_site = request.headers.get("sec-fetch-site")
        if sec_fetch_site and sec_fetch_site.strip().lower() not in ("same-origin", "none"):
            return "Sec-Fetch-Site not same-origin or none"

        origin = request.headers.get("origin")
        if origin:
            public_origin = os.environ.get("KANBAN_PUBLIC_ORIGIN")
            if public_origin:
                if origin.strip().rstrip("/") != public_origin.strip().rstrip("/"):
                    return "Origin does not match configured public origin"
            else:
                host = request.headers.get("host")
                if host:
                    expected_origin = f"{request.url.scheme}://{host}"
                    if origin.strip().rstrip("/") != expected_origin.strip().rstrip("/"):
                        return "Origin does not match request host"
        return None

    async def _resolve_session_id(self, request: Request) -> uuid.UUID:
        """Resolve active session ID or return unauthenticated PRE_SESSION_ID."""
        session_id = getattr(request.state, "session_id", None)
        if session_id is None:
            resolver = getattr(request.app.state, "principal_resolver", None)
            if resolver is not None:
                principal_ctx = await resolver.resolve(request)
                if principal_ctx is not None and principal_ctx.session_id is not None:
                    session_id = principal_ctx.session_id

        if session_id is None:
            principal_ctx = getattr(request.state, "principal", None)
            if principal_ctx is not None and principal_ctx.session_id is not None:
                session_id = principal_ctx.session_id
            else:
                session_id = PRE_SESSION_ID
        return session_id

    def _validate_double_submit(self, request: Request, session_id: uuid.UUID) -> str | None:
        """Validate header/cookie presence, match, and cryptographic signature."""
        header_token = request.headers.get(CSRF_HEADER_NAME)
        cookie_token = extract_csrf_cookie(request)

        if not header_token or not cookie_token:
            return "Missing CSRF token header or cookie"

        if not hmac.compare_digest(header_token, cookie_token):
            return "CSRF header does not match cookie"

        hmac_key = self._get_key(request)
        if not validate_csrf_token(header_token, session_id, hmac_key):
            return "Invalid CSRF token signature for current session"

        return None

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Inspect request and validate CSRF tokens on unsafe methods."""
        # Safe methods are always permitted
        if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
            return await call_next(request)

        # Non-API paths and exempt paths are out of scope
        path = request.url.path
        if not path.startswith("/api/") or path in CSRF_EXEMPT_PATHS:
            return await call_next(request)

        # Defense-in-depth: Sec-Fetch-Site and Origin verification
        meta_err = self._validate_metadata(request)
        if meta_err is not None:
            return self._csrf_rejected_response(meta_err)

        # Double-submit token check against resolved session id
        session_id = await self._resolve_session_id(request)
        token_err = self._validate_double_submit(request, session_id)
        if token_err is not None:
            return self._csrf_rejected_response(token_err)

        return await call_next(request)

    def _csrf_rejected_response(self, detail: str) -> JSONResponse:
        """Construct standard RFC 7807 403 problem response for CSRF failure."""
        problem = Problem(
            type="https://kanban.hackedyour.info/problems/csrf-rejected",
            title="CSRF validation failed",
            status=403,
            detail=detail,
            code="CSRF_REJECTED",
            request_id=get_request_id(),
        )
        return JSONResponse(
            status_code=403,
            content=problem.model_dump(exclude_none=True),
            media_type="application/problem+json",
        )
