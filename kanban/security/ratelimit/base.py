"""Base interfaces, data structures, policy validation, and key hashing (S2.4)."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from typing import Literal, Protocol

_POLICY_NAME_REGEX = re.compile(r"^[a-z0-9_.]{3,48}$")
_MIN_LIMIT = 1
_MAX_LIMIT = 100000
_MIN_WINDOW_SECONDS = 1
_MAX_WINDOW_SECONDS = 86400
_VALID_FAIL_MODES = ("closed", "open")


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """Configuration contract for sliding-window rate limits.

    Validates bounds on name format, request limit, window duration, and fail mode.
    """

    name: str
    limit: int
    window_seconds: int
    fail_mode: Literal["closed", "open"] = "closed"

    def __post_init__(self) -> None:
        """Validate policy fields against specification boundaries."""
        if not _POLICY_NAME_REGEX.match(self.name):
            msg = f"Invalid policy name: {self.name!r}. Must match regex '^[a-z0-9_.]{{3,48}}$'."
            raise ValueError(msg)

        if not (_MIN_LIMIT <= self.limit <= _MAX_LIMIT):
            msg = (
                f"Invalid limit: {self.limit}. "
                f"Must be an integer between {_MIN_LIMIT} and {_MAX_LIMIT}."
            )
            raise ValueError(msg)

        if not (_MIN_WINDOW_SECONDS <= self.window_seconds <= _MAX_WINDOW_SECONDS):
            msg = (
                f"Invalid window_seconds: {self.window_seconds}. "
                f"Must be an integer between {_MIN_WINDOW_SECONDS} and {_MAX_WINDOW_SECONDS}."
            )
            raise ValueError(msg)

        if self.fail_mode not in _VALID_FAIL_MODES:
            msg = f"Invalid fail_mode: {self.fail_mode!r}. Must be one of {_VALID_FAIL_MODES}."
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Outcome of a rate limit counter inspection."""

    allowed: bool
    remaining: int
    retry_after_seconds: int


class RateLimiter(Protocol):
    """Protocol for sliding-window rate limiter backends."""

    async def hit(self, policy: RateLimitPolicy, key: bytes) -> RateLimitDecision:
        """Record a hit against a rate limit bucket and return decision."""
        ...

    async def reset(self, policy: RateLimitPolicy, key: bytes) -> None:
        """Clear rate limit counter state for the specified key."""
        ...


def make_key(
    policy: RateLimitPolicy,
    *parts: str,
    session_hmac_key: bytes | None = None,
) -> bytes:
    """Compute pseudonymous HMAC-SHA256 key for a rate limit bucket.

    Derives a dedicated subkey using derive_subkey(session_hmac_key, 'ratelimit/key')
    over the delimiter-separated policy name and identifier strings.
    Raw client identifiers (IPs, emails, usernames) are never stored or logged.
    """
    from kanban.security.keys import derive_subkey  # noqa: PLC0415

    root_key = session_hmac_key
    if root_key is None:
        try:
            from kanban.security.keys import KeyMaterialError, load_key_material  # noqa: PLC0415

            root_key = load_key_material().session_hmac_key
        except (KeyMaterialError, KeyError, ValueError, OSError, RuntimeError):
            # Fallback for environments or tests without a complete keyring file
            env_val = os.environ.get("KANBAN_SESSION_HMAC_KEY") or os.environ.get(
                "KB_SESSION_HMAC_KEY"
            )
            if env_val:
                from kanban.security.keys import _decode_b64url_key  # noqa: PLC0415

                root_key = _decode_b64url_key(env_val, "SESSION_HMAC_KEY")
            else:
                msg = (
                    "session_hmac_key must be provided either explicitly, via "
                    "load_key_material(), or in KANBAN_SESSION_HMAC_KEY."
                )
                raise ValueError(msg) from None

    subkey = derive_subkey(root_key, "ratelimit/key")
    payload = (policy.name + "\x1f" + "\x1f".join(parts)).encode("utf-8")
    return hmac.new(subkey, payload, hashlib.sha256).digest()
