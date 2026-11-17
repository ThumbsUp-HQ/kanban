# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Session token generation, HMAC cookie signing, and verification (KB-P2-02)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Final

from kanban.security.keys import derive_subkey

__all__ = [
    "FALLBACK_SESSION_COOKIE_NAME",
    "MAX_COOKIE_LEN",
    "SESSION_COOKIE_NAME",
    "TOKEN_BYTES_LEN",
    "attach_session_and_csrf_cookies",
    "build_clear_cookie_header",
    "build_clear_fallback_cookie_header",
    "build_set_cookie_header",
    "build_set_fallback_cookie_header",
    "encode_session_cookie",
    "extract_session_cookie",
    "generate_session_token",
    "hash_session_token",
    "is_plain_http",
    "parse_session_cookie",
]

SESSION_COOKIE_NAME: Final[str] = "__Host-kb_session"
FALLBACK_SESSION_COOKIE_NAME: Final[str] = "kb_session"
MAX_COOKIE_LEN: Final[int] = 128
MIN_SIGNED_COOKIE_LEN: Final[int] = 80
TOKEN_BYTES_LEN: Final[int] = 32
SIG_BYTES_LEN: Final[int] = 32


def generate_session_token() -> bytes:
    """Generate 32 cryptographically random bytes for an opaque session token."""
    return secrets.token_bytes(TOKEN_BYTES_LEN)


def hash_session_token(token: bytes) -> bytes:
    """Compute SHA-256 digest of session token for safe persistence."""
    return hashlib.sha256(token).digest()


def encode_session_cookie(token: bytes, session_hmac_key: bytes) -> str:
    """Sign token with HMAC-SHA256 and return dot-delimited URL-safe base64 string."""
    if len(token) != TOKEN_BYTES_LEN:
        msg = f"Token must be {TOKEN_BYTES_LEN} bytes, got {len(token)}"
        raise ValueError(msg)

    cookie_key = derive_subkey(session_hmac_key, "session/cookie")
    signature = hmac.new(cookie_key, token, hashlib.sha256).digest()

    b64_token = base64.urlsafe_b64encode(token).rstrip(b"=").decode("ascii")
    b64_sig = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{b64_token}.{b64_sig}"


def parse_session_cookie(cookie_val: str, session_hmac_key: bytes) -> bytes | None:
    """Parse and verify signed session cookie without querying database.

    Enforces:
    1. Maximum length constraint (<= 128 chars).
    2. Dot-separated format (token.sig).
    3. Exact byte length requirements (32-byte token, 32-byte signature).
    4. Constant-time HMAC verification.
    """
    if not cookie_val or len(cookie_val) > MAX_COOKIE_LEN:
        return None

    parts = cookie_val.split(".")
    if len(parts) != 2:  # noqa: PLR2004
        return None

    b64_token, b64_sig = parts

    try:
        token_padding = "=" * (-len(b64_token) % 4)
        token = base64.urlsafe_b64decode(b64_token + token_padding)

        sig_padding = "=" * (-len(b64_sig) % 4)
        given_sig = base64.urlsafe_b64decode(b64_sig + sig_padding)
    except (ValueError, binascii.Error):
        return None

    if len(token) != TOKEN_BYTES_LEN or len(given_sig) != SIG_BYTES_LEN:
        return None

    cookie_key = derive_subkey(session_hmac_key, "session/cookie")
    expected_sig = hmac.new(cookie_key, token, hashlib.sha256).digest()

    if not hmac.compare_digest(expected_sig, given_sig):
        return None

    return token


def extract_session_cookie(cookie_header: str | None) -> str | None:
    """Extract single __Host-kb_session cookie from raw Cookie header string.

    Rejects:
    - Requests without __Host-kb_session (unless a full signed kb_session fallback is present)
    - Requests carrying duplicate __Host-kb_session cookies (ambiguity defense)
    - Requests carrying unsigned/short non-Host variants (kb_session, __Secure-kb_session)
    """
    if not cookie_header:
        return None

    found_values: list[str] = []
    fallback_values: list[str] = []
    # Split on semicolon to get individual cookie declarations
    for item in cookie_header.split(";"):
        stripped = item.strip()
        if not stripped or "=" not in stripped:
            continue
        key, val = stripped.split("=", 1)
        key = key.strip()
        clean_val = val.strip()
        if key == SESSION_COOKIE_NAME:
            found_values.append(clean_val)
        elif key == FALLBACK_SESSION_COOKIE_NAME:
            fallback_values.append(clean_val)

    # Ambiguity check: duplicate __Host-kb_session cookies must fail closed
    if len(found_values) > 1:
        return None
    if len(found_values) == 1:
        return found_values[0]

    if len(fallback_values) == 1:
        candidate = fallback_values[0]
        if "." in candidate and MIN_SIGNED_COOKIE_LEN <= len(candidate) <= MAX_COOKIE_LEN:
            return candidate

    return None


def build_set_cookie_header(
    cookie_val: str,
    expires_at: datetime | None = None,
    *,
    max_age: int | None = None,
    persistent: bool = True,
) -> str:
    """Format Set-Cookie header for __Host-kb_session."""
    parts = [
        f"{SESSION_COOKIE_NAME}={cookie_val}",
        "Path=/",
        "HttpOnly",
        "Secure",
        "SameSite=Lax",
    ]
    if persistent:
        if expires_at is not None:
            utc_dt = expires_at.astimezone(UTC)
            expires_str = utc_dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
            parts.append(f"Expires={expires_str}")
            if max_age is None:
                calc_max_age = max(0, int((utc_dt - datetime.now(UTC)).total_seconds()))
                parts.append(f"Max-Age={calc_max_age}")
            else:
                parts.append(f"Max-Age={max_age}")
        elif max_age is not None:
            parts.append(f"Max-Age={max_age}")
            from datetime import timedelta  # noqa: PLC0415

            utc_dt = datetime.now(UTC) + timedelta(seconds=max_age)
            expires_str = utc_dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
            parts.append(f"Expires={expires_str}")

    return "; ".join(parts)


def build_set_fallback_cookie_header(
    cookie_val: str,
    expires_at: datetime | None = None,
    *,
    max_age: int | None = None,
    persistent: bool = True,
) -> str:
    """Format Set-Cookie header for non-Host kb_session over plain HTTP local dev."""
    parts = [
        f"{FALLBACK_SESSION_COOKIE_NAME}={cookie_val}",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
    ]
    if persistent:
        if expires_at is not None:
            utc_dt = expires_at.astimezone(UTC)
            expires_str = utc_dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
            parts.append(f"Expires={expires_str}")
            if max_age is None:
                calc_max_age = max(0, int((utc_dt - datetime.now(UTC)).total_seconds()))
                parts.append(f"Max-Age={calc_max_age}")
            else:
                parts.append(f"Max-Age={max_age}")
        elif max_age is not None:
            parts.append(f"Max-Age={max_age}")
            from datetime import timedelta  # noqa: PLC0415

            utc_dt = datetime.now(UTC) + timedelta(seconds=max_age)
            expires_str = utc_dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
            parts.append(f"Expires={expires_str}")

    return "; ".join(parts)


def is_plain_http(request: object | None) -> bool:
    """Detect whether request arrives over plain HTTP (direct or reverse proxy)."""
    if request is None:
        return False
    headers = getattr(request, "headers", None)
    if headers:
        fwd_proto = (headers.get("x-forwarded-proto") or "").lower().strip()
        if fwd_proto:
            return fwd_proto == "http"
        fwd = (headers.get("forwarded") or "").lower()
        if "proto=http" in fwd:
            return True
        if "proto=https" in fwd:
            return False
    url = getattr(request, "url", None)
    return bool(url and getattr(url, "scheme", "").lower() == "http")


def attach_session_and_csrf_cookies(
    response: object,
    request: object | None,
    issued: object,
    csrf_token: str | None = None,
    *,
    persistent: bool | None = None,
) -> None:
    """Unified helper to attach __Host- and fallback session & CSRF cookies to responses."""
    from kanban.auth.sessions.csrf import (  # noqa: PLC0415
        build_set_csrf_cookie_header,
        build_set_fallback_csrf_cookie_header,
    )

    is_persist = persistent if persistent is not None else getattr(issued, "is_persistent", True)
    cookie_val = getattr(issued, "cookie_val", str(issued))
    token_csrf = csrf_token or getattr(issued, "csrf_token", None)
    expires_at = getattr(issued, "absolute_expires_at", None) if is_persist else None

    sess_hdr = build_set_cookie_header(cookie_val, expires_at=expires_at, persistent=is_persist)

    def _add(hdr: str) -> None:
        if hasattr(response, "raw_headers"):
            response.raw_headers.append((b"set-cookie", hdr.encode("latin-1")))
        elif hasattr(response, "headers"):
            response.headers.append("Set-Cookie", hdr)

    _add(sess_hdr)
    if token_csrf:
        _add(build_set_csrf_cookie_header(token_csrf))

    if is_plain_http(request):
        fb_sess_hdr = build_set_fallback_cookie_header(
            cookie_val, expires_at=expires_at, persistent=is_persist
        )
        _add(fb_sess_hdr)
        if token_csrf:
            _add(build_set_fallback_csrf_cookie_header(token_csrf))


def build_clear_cookie_header() -> str:
    """Format Set-Cookie header to clear __Host-kb_session."""
    return f"{SESSION_COOKIE_NAME}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0"


def build_clear_fallback_cookie_header() -> str:
    """Format Set-Cookie header to clear non-Host kb_session."""
    return f"{FALLBACK_SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
