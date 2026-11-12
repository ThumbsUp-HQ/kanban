"""Sliding-window rate limiting service and policy definitions (S2.2, S2.4).

This package provides sliding-window rate limiting with PostgreSQL-backed and
Valkey-backed implementations, keyed via HMAC-SHA256 digests over pseudonymous
identifiers, and enforced on FastAPI routes via the rate_limited decorator.

Predefined Security Policies:
- AUTH_LOGIN_ACCOUNT: 5 hits per 900s (15 minutes). Prevents targeted credential
  guessing against individual accounts.
- AUTH_LOGIN_IP: 20 hits per 900s (15 minutes). Prevents distributed credential
  stuffing from a single IP address or subnet.
- AUTH_MFA_VERIFY: 5 hits per 300s (5 minutes). Mitigates brute-force attacks on
  TOTP codes and recovery keys.
- SETUP_CLAIM_IP: 10 hits per 3600s (1 hour). Prevents automated enumeration
  of initial setup and server-claim tokens.
- MEDIA_PROXY_PRINCIPAL: 120 hits per 60s (1 minute). Limits SSRF proxying and
  bandwidth consumption from external markdown image fetches.
- ATTACHMENT_UPLOAD_PRINCIPAL: 30 hits per 60s (1 minute). Throttles file upload
  bursts and storage exhaustion.
"""

from __future__ import annotations

from kanban.security.ratelimit.base import (
    RateLimitDecision,
    RateLimiter,
    RateLimitPolicy,
    make_key,
)
from kanban.security.ratelimit.decorator import (
    build_rate_limiter,
    rate_limited,
)
from kanban.security.ratelimit.pg import PgRateLimiter
from kanban.security.ratelimit.valkey import (
    SLIDING_WINDOW_LUA,
    ValkeyCommands,
    ValkeyRateLimiter,
)

AUTH_LOGIN_ACCOUNT = RateLimitPolicy(
    name="auth_login_account",
    limit=5,
    window_seconds=900,
    fail_mode="closed",
)

AUTH_LOGIN_IP = RateLimitPolicy(
    name="auth_login_ip",
    limit=20,
    window_seconds=900,
    fail_mode="closed",
)

AUTH_MFA_VERIFY = RateLimitPolicy(
    name="auth_mfa_verify",
    limit=5,
    window_seconds=300,
    fail_mode="closed",
)

SETUP_CLAIM_IP = RateLimitPolicy(
    name="setup_claim_ip",
    limit=10,
    window_seconds=3600,
    fail_mode="closed",
)

MEDIA_PROXY_PRINCIPAL = RateLimitPolicy(
    name="media_proxy_principal",
    limit=120,
    window_seconds=60,
    fail_mode="closed",
)

ATTACHMENT_UPLOAD_PRINCIPAL = RateLimitPolicy(
    name="attachment_upload_principal",
    limit=30,
    window_seconds=60,
    fail_mode="closed",
)

__all__ = [
    "ATTACHMENT_UPLOAD_PRINCIPAL",
    "AUTH_LOGIN_ACCOUNT",
    "AUTH_LOGIN_IP",
    "AUTH_MFA_VERIFY",
    "MEDIA_PROXY_PRINCIPAL",
    "SETUP_CLAIM_IP",
    "SLIDING_WINDOW_LUA",
    "PgRateLimiter",
    "RateLimitDecision",
    "RateLimitPolicy",
    "RateLimiter",
    "ValkeyCommands",
    "ValkeyRateLimiter",
    "build_rate_limiter",
    "make_key",
    "rate_limited",
]
