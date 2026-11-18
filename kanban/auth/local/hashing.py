# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Argon2id password hashing and constant-work verification with HMAC-SHA256 pepper (KB-P2-04)."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import os
import secrets
import threading
import unicodedata
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable

import anyio
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from kanban.api.problems import ProblemException
from kanban.security.keys import KeyMaterialError, _decode_b64url_key, load_key_material

__all__ = [
    "DUMMY_HASH",
    "MAX_PASSWORD_BYTES",
    "MIN_PASSWORD_BYTES",
    "get_argon2_semaphore",
    "get_auth_pepper",
    "hash_password",
    "hash_password_sync",
    "needs_rehash",
    "reset_argon2_semaphore",
    "verify",
    "verify_password",
    "verify_password_sync",
]

DEFAULT_ARGON2_CONCURRENCY: Final[int] = 4
DEFAULT_ARGON2_TIMEOUT_SECONDS: Final[float] = 2.0
MIN_PASSWORD_BYTES: Final[int] = 8
MAX_PASSWORD_BYTES: Final[int] = 1024


def _get_hasher() -> PasswordHasher:
    """Create PasswordHasher configured to standard platform parameters."""
    return PasswordHasher(
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        salt_len=16,
        type=Type.ID,
    )


# Precompute dummy hash once at module load with identical parameters
_dummy_secret = secrets.token_bytes(32)
_DUMMY_INPUT: Final[str] = base64.b64encode(_dummy_secret).decode("ascii")
_DUMMY_INPUT_FAIL: Final[str] = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
DUMMY_HASH: Final[str] = _get_hasher().hash(_DUMMY_INPUT)


class _SemaphoreState:
    """Internal thread-safe semaphore holder bound to running event loops."""

    lock: threading.Lock = threading.Lock()
    instance: asyncio.Semaphore | None = None
    loop: asyncio.AbstractEventLoop | None = None


def get_auth_pepper() -> bytes:
    """Retrieve auth pepper key material from runtime keyring or environment."""
    try:
        return load_key_material().auth_pepper
    except (KeyMaterialError, KeyError, ValueError, OSError, RuntimeError):
        raw = os.environ.get("KANBAN_AUTH_PEPPER") or os.environ.get("KB_AUTH_PEPPER")
        if raw:
            return _decode_b64url_key(raw, "KANBAN_AUTH_PEPPER")
        msg = "Authentication pepper (KB_AUTH_PEPPER / KANBAN_AUTH_PEPPER) not configured"
        raise ValueError(msg) from None


def get_argon2_semaphore(concurrency: int | None = None) -> asyncio.Semaphore:
    """Return an asyncio Semaphore scoped to the current event loop and configured concurrency."""
    loop = asyncio.get_running_loop()
    limit = (
        concurrency
        if concurrency is not None
        else int(os.environ.get("KANBAN_ARGON2_CONCURRENCY", str(DEFAULT_ARGON2_CONCURRENCY)))
    )
    with _SemaphoreState.lock:
        if _SemaphoreState.instance is None or _SemaphoreState.loop is not loop:
            _SemaphoreState.instance = asyncio.Semaphore(limit)
            _SemaphoreState.loop = loop
        return _SemaphoreState.instance


def reset_argon2_semaphore() -> None:
    """Reset the module-level semaphore (test isolation helper)."""
    with _SemaphoreState.lock:
        _SemaphoreState.instance = None
        _SemaphoreState.loop = None


async def _run_with_concurrency_limit[T](
    fn: Callable[..., T],
    *args: object,
    timeout_seconds: float = DEFAULT_ARGON2_TIMEOUT_SECONDS,
) -> T:
    """Acquire semaphore permit with bounded timeout and execute CPU-intensive task in thread."""
    sem = get_argon2_semaphore()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=timeout_seconds)
    except TimeoutError as exc:
        raise ProblemException(
            code="AUTH_BUSY",
            status=503,
            title="Authentication Service Busy",
            detail="Authentication capacity exceeded; please retry shortly",
            headers={"Retry-After": "2"},
        ) from exc

    try:
        return await anyio.to_thread.run_sync(fn, *args)
    finally:
        sem.release()


def _normalize_and_pepper(password: str, pepper: bytes) -> str:
    """NFKC normalize, validate UTF-8 length (8..1024), and compute HMAC-SHA256 peppered base64."""
    norm = unicodedata.normalize("NFKC", password)
    pw_bytes = norm.encode("utf-8")
    if not (MIN_PASSWORD_BYTES <= len(pw_bytes) <= MAX_PASSWORD_BYTES):
        msg = (
            f"Password length must be between {MIN_PASSWORD_BYTES} and "
            f"{MAX_PASSWORD_BYTES} UTF-8 bytes (got {len(pw_bytes)})"
        )
        raise ValueError(msg)
    mac = hmac.new(pepper, pw_bytes, hashlib.sha256).digest()
    return base64.b64encode(mac).decode("ascii")


def hash_password_sync(password: str, pepper: bytes | None = None) -> str:
    """Compute Argon2id hash synchronously over NFKC-normalized HMAC-peppered password."""
    active_pepper = pepper if pepper is not None else get_auth_pepper()
    b64_mac = _normalize_and_pepper(password, active_pepper)
    return _get_hasher().hash(b64_mac)


async def hash_password(
    password: str,
    pepper: bytes | None = None,
    *,
    timeout_seconds: float = DEFAULT_ARGON2_TIMEOUT_SECONDS,
) -> str:
    """Compute Argon2id hash under concurrency semaphore and anyio thread."""
    return await _run_with_concurrency_limit(
        hash_password_sync,
        password,
        pepper,
        timeout_seconds=timeout_seconds,
    )


def verify_password_sync(
    stored_hash: str,
    password: str,
    pepper: bytes | None = None,
) -> bool:
    """Verify password synchronously against stored hash with constant-work miss path."""
    active_pepper = pepper if pepper is not None else get_auth_pepper()
    ph = _get_hasher()

    norm = unicodedata.normalize("NFKC", password)
    pw_bytes = norm.encode("utf-8")
    is_len_valid = MIN_PASSWORD_BYTES <= len(pw_bytes) <= MAX_PASSWORD_BYTES

    if not is_len_valid or stored_hash == DUMMY_HASH:
        # Constant-work miss path: perform exactly 1 Argon2 verification
        with contextlib.suppress(VerifyMismatchError, VerificationError):
            ph.verify(DUMMY_HASH, _DUMMY_INPUT_FAIL)
        return False

    try:
        mac = hmac.new(active_pepper, pw_bytes, hashlib.sha256).digest()
        b64_mac = base64.b64encode(mac).decode("ascii")
        return bool(ph.verify(stored_hash, b64_mac))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


async def verify_password(
    stored_hash: str,
    password: str,
    pepper: bytes | None = None,
    *,
    timeout_seconds: float = DEFAULT_ARGON2_TIMEOUT_SECONDS,
) -> bool:
    """Verify password under concurrency semaphore and anyio thread."""
    return await _run_with_concurrency_limit(
        verify_password_sync,
        stored_hash,
        password,
        pepper,
        timeout_seconds=timeout_seconds,
    )


verify = verify_password


def needs_rehash(stored_hash: str) -> bool:
    """Check if stored hash needs upgrading to current hasher parameters."""
    return _get_hasher().check_needs_rehash(stored_hash)
