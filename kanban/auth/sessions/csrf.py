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
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from kanban.api.problems import Problem
from kanban.api.request_id import get_request_id
from kanban.auth.sessions.cookies import (
    build_clear_cookie_header,
    build_clear_fallback_cookie_header,
    extract_session_cookie,
    is_plain_http,
)
from kanban.security.keys import derive_subkey
from kanban.settings import get_settings

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = [
    "CSRF_COOKIE_NAME",
    "CSRF_EXEMPT_PATHS",
    "CSRF_HEADER_NAME",
    "FALLBACK_CSRF_COOKIE_NAME",
    "PRE_SESSION_ID",
    "CsrfMiddleware",
    "build_clear_csrf_cookie_header",
    "build_clear_fallback_csrf_cookie_header",
    "build_set_csrf_cookie_header",
    "build_set_fallback_csrf_cookie_header",
    "extract_csrf_cookie",
    "generate_csrf_token",
    "validate_csrf_token",
]

CSRF_COOKIE_NAME: Final[str] = "__Host-kb_csrf"
FALLBACK_CSRF_COOKIE_NAME: Final[str] = "kb_csrf"
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
    # OAuth 2.1 client/token machine endpoints
    "/oauth/register",
    "/oauth/token",
    "/oauth/revoke",
    "/oauth/device/authorize",
    "/oauth/authorize/decision",
    # Internal MCP introspection
    "/internal/v1/mcp/introspect",
    "/internal/mcp/introspect",
    # Headless machine endpoints
    "/api/v1/agent-runners/enroll",
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
    """Extract __Host-kb_csrf (or plain-HTTP kb_csrf fallback) cookie from request."""
    host_cookie = request.cookies.get(CSRF_COOKIE_NAME)
    if host_cookie:
        return host_cookie
    fallback_cookie = request.cookies.get(FALLBACK_CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if header_token and fallback_cookie and hmac.compare_digest(header_token, fallback_cookie):
        return fallback_cookie
    return fallback_cookie


def build_set_csrf_cookie_header(csrf_token: str) -> str:
    """Format Set-Cookie header for __Host-kb_csrf (Strict SameSite, non-HttpOnly for SPA)."""
    return f"{CSRF_COOKIE_NAME}={csrf_token}; Path=/; Secure; SameSite=Strict"


def build_set_fallback_csrf_cookie_header(csrf_token: str) -> str:
    """Format Set-Cookie header for non-Host kb_csrf over plain HTTP local dev."""
    return f"{FALLBACK_CSRF_COOKIE_NAME}={csrf_token}; Path=/; SameSite=Strict"


def build_clear_csrf_cookie_header() -> str:
    """Format Set-Cookie header to clear __Host-kb_csrf."""
    return f"{CSRF_COOKIE_NAME}=; Path=/; Secure; SameSite=Strict; Max-Age=0"


def build_clear_fallback_csrf_cookie_header() -> str:
    """Format Set-Cookie header to clear non-Host kb_csrf."""
    return f"{FALLBACK_CSRF_COOKIE_NAME}=; Path=/; SameSite=Strict; Max-Age=0"


def _resolve_public_origin() -> str | None:
    """Retrieve public origin from environment or application settings."""
    public_origin = os.environ.get("KANBAN_PUBLIC_ORIGIN") or os.environ.get("KB_PUBLIC_ORIGIN")
    if not public_origin:
        try:
            public_origin = get_settings().public_origin
        except RuntimeError:
            return None
    return public_origin.strip().rstrip("/") if public_origin else None


def _get_allowed_origins(request: Request, public_origin: str | None) -> set[str]:
    """Build allowed origin strings from configured public origin and host header."""
    allowed: set[str] = set()
    if public_origin:
        allowed.add(public_origin)
        try:
            parsed = urlsplit(public_origin)
            if parsed.scheme and parsed.netloc:
                allowed.add(f"{parsed.scheme}://{parsed.netloc}".rstrip("/"))
        except Exception:  # noqa: BLE001, S110
            pass
    host = request.headers.get("host")
    if host:
        clean_host = host.strip()
        allowed.add(f"{request.url.scheme}://{clean_host}")
        allowed.add(f"https://{clean_host}")
        allowed.add(f"http://{clean_host}")
    return allowed


def _check_origin_header(
    origin: str, allowed_origins: set[str], public_origin: str | None
) -> str | None:
    """Validate Origin header against allowed origins."""
    clean_origin = origin.strip().rstrip("/")
    if not allowed_origins or clean_origin not in allowed_origins:
        if public_origin:
            return "Origin does not match configured public origin"
        return "Origin does not match request host"
    return None


def _check_referer_header(
    referer: str, allowed_origins: set[str], public_origin: str | None
) -> str | None:
    """Validate Referer header when Origin is omitted."""
    try:
        parsed_ref = urlsplit(referer.strip())
        if parsed_ref.scheme not in ("http", "https") or not parsed_ref.netloc:
            return "Referer header is malformed"
        ref_origin = f"{parsed_ref.scheme}://{parsed_ref.netloc}".rstrip("/")
    except ValueError:
        return "Referer header is malformed"

    if not allowed_origins or ref_origin not in allowed_origins:
        if public_origin:
            return "Referer does not match configured public origin"
        return "Referer does not match request host"
    return None


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
        """Validate browser security headers (Sec-Fetch-Site, Origin, and Referer)."""
        sec_fetch_site = request.headers.get("sec-fetch-site")
        if sec_fetch_site and sec_fetch_site.strip().lower() not in ("same-origin", "none"):
            return "Sec-Fetch-Site not same-origin or none"

        public_origin = _resolve_public_origin()
        allowed_origins = _get_allowed_origins(request, public_origin)

        origin = request.headers.get("origin")
        if origin:
            return _check_origin_header(origin, allowed_origins, public_origin)

        referer = request.headers.get("referer")
        if referer:
            return _check_referer_header(referer, allowed_origins, public_origin)

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
            if (
                session_id != PRE_SESSION_ID
                and request.url.path in ("/api/v1/setup/claim", "/api/v1/auth/local/login")
                and validate_csrf_token(header_token, PRE_SESSION_ID, hmac_key)
            ):
                return None
            return "Invalid CSRF token signature for current session"

        return None

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Inspect request and validate CSRF tokens on unsafe methods."""
        # Safe methods are always permitted
        if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
            return await call_next(request)

        # Internal service or token-authenticated requests bypass ambient cookie CSRF
        if request.headers.get("x-kb-subject-token") or request.headers.get("x-kb-internal-auth"):
            return await call_next(request)

        # Non-API paths and exempt paths are out of scope
        path = request.url.path
        if not path.startswith("/api/") or path in CSRF_EXEMPT_PATHS:
            return await call_next(request)

        # Double-submit token check against resolved session id
        session_id = await self._resolve_session_id(request)
        cookie_header = request.headers.get("cookie")
        has_session_cookie = bool(extract_session_cookie(cookie_header))
        is_dead_session = has_session_cookie and session_id == PRE_SESSION_ID

        # Defense-in-depth: Sec-Fetch-Site and Origin verification
        meta_err = self._validate_metadata(request)
        if meta_err is not None:
            return self._csrf_rejected_response(
                meta_err, request=request, is_dead_session=is_dead_session
            )

        token_err = self._validate_double_submit(request, session_id)
        if token_err is not None:
            return self._csrf_rejected_response(
                token_err, request=request, is_dead_session=is_dead_session
            )

        response = await call_next(request)
        if is_dead_session:
            response.raw_headers.append(
                (b"set-cookie", build_clear_cookie_header().encode("latin-1"))
            )
            if is_plain_http(request):
                response.raw_headers.append(
                    (b"set-cookie", build_clear_fallback_cookie_header().encode("latin-1"))
                )
        return response

    def _csrf_rejected_response(
        self,
        detail: str,
        *,
        request: Request | None = None,
        is_dead_session: bool = False,
    ) -> JSONResponse:
        """Construct standard RFC 7807 403 problem response for CSRF failure."""
        problem = Problem(
            type="https://kanban.hackedyour.info/problems/csrf-rejected",
            title="CSRF validation failed",
            status=403,
            detail=detail,
            code="CSRF_REJECTED",
            request_id=get_request_id(),
        )
        resp = JSONResponse(
            status_code=403,
            content=problem.model_dump(exclude_none=True),
            media_type="application/problem+json",
        )
        if request is not None and is_dead_session:
            # Clear stale session cookies (Max-Age=0) and reissue valid pre-session CSRF cookie
            resp.raw_headers.append((b"set-cookie", build_clear_cookie_header().encode("latin-1")))
            if is_plain_http(request):
                resp.raw_headers.append(
                    (b"set-cookie", build_clear_fallback_cookie_header().encode("latin-1"))
                )
            fresh_csrf = generate_csrf_token(PRE_SESSION_ID, self._get_key(request))
            resp.raw_headers.append(
                (b"set-cookie", build_set_csrf_cookie_header(fresh_csrf).encode("latin-1"))
            )
            if is_plain_http(request):
                resp.raw_headers.append(
                    (
                        b"set-cookie",
                        build_set_fallback_csrf_cookie_header(fresh_csrf).encode("latin-1"),
                    )
                )
        return resp
