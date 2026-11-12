# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Server-side sessions, HMAC cookies, rotation, timeouts, and CSRF (KB-P2-02)."""

from kanban.auth.sessions.cookies import (
    MAX_COOKIE_LEN,
    SESSION_COOKIE_NAME,
    TOKEN_BYTES_LEN,
    build_clear_cookie_header,
    build_set_cookie_header,
    encode_session_cookie,
    extract_session_cookie,
    generate_session_token,
    hash_session_token,
    parse_session_cookie,
)
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_EXEMPT_PATHS,
    CSRF_HEADER_NAME,
    PRE_SESSION_ID,
    CsrfMiddleware,
    build_clear_csrf_cookie_header,
    build_set_csrf_cookie_header,
    extract_csrf_cookie,
    generate_csrf_token,
    validate_csrf_token,
)
from kanban.auth.sessions.resolver import (
    SessionCookieResolver,
    require_full_session,
)
from kanban.auth.sessions.service import (
    DEFAULT_AAL2_FRESH_SECONDS,
    DEFAULT_ABSOLUTE_SECONDS,
    DEFAULT_IDLE_SECONDS,
    MAX_POLICY_SECONDS,
    MIN_POLICY_SECONDS,
    IssuedSession,
    SessionPolicy,
    SessionService,
)

__all__ = [
    "CSRF_COOKIE_NAME",
    "CSRF_EXEMPT_PATHS",
    "CSRF_HEADER_NAME",
    "DEFAULT_AAL2_FRESH_SECONDS",
    "DEFAULT_ABSOLUTE_SECONDS",
    "DEFAULT_IDLE_SECONDS",
    "MAX_COOKIE_LEN",
    "MAX_POLICY_SECONDS",
    "MIN_POLICY_SECONDS",
    "PRE_SESSION_ID",
    "SESSION_COOKIE_NAME",
    "TOKEN_BYTES_LEN",
    "CsrfMiddleware",
    "IssuedSession",
    "SessionCookieResolver",
    "SessionPolicy",
    "SessionService",
    "build_clear_cookie_header",
    "build_clear_csrf_cookie_header",
    "build_set_cookie_header",
    "build_set_csrf_cookie_header",
    "encode_session_cookie",
    "extract_csrf_cookie",
    "extract_session_cookie",
    "generate_csrf_token",
    "generate_session_token",
    "hash_session_token",
    "parse_session_cookie",
    "require_full_session",
    "validate_csrf_token",
]
