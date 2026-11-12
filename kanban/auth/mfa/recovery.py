# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Hashed one-time backup recovery codes service and helpers (KB-P2-05a)."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from kanban.security.keys import derive_subkey

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "CROCKFORD_ALPHABET",
    "RECOVERY_CODE_COUNT",
    "RECOVERY_CODE_LEN",
    "RecoveryCodeService",
    "generate_recovery_codes",
    "hash_recovery_code",
    "normalize_recovery_code",
]

CROCKFORD_ALPHABET: Final[str] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
RECOVERY_CODE_LEN: Final[int] = 10
RECOVERY_CODE_COUNT: Final[int] = 10
_CROCKFORD_TRANS = str.maketrans("iIlLoO", "111100")


def normalize_recovery_code(code: str) -> str:
    """Normalize a Crockford Base32 recovery code.

    Strips hyphens and whitespace, normalizes lookalike characters
    (i/l -> 1, o -> 0), converts to uppercase, and verifies length 10.
    """
    cleaned = re.sub(r"[\s\-]+", "", code).translate(_CROCKFORD_TRANS).upper()
    if len(cleaned) != RECOVERY_CODE_LEN or not all(c in CROCKFORD_ALPHABET for c in cleaned):
        msg = f"Invalid recovery code format: {code!r}"
        raise ValueError(msg)
    return cleaned


def hash_recovery_code(code: str, auth_pepper: bytes) -> bytes:
    """Compute HMAC-SHA256 digest of normalized recovery code using subkey."""
    normalized = normalize_recovery_code(code)
    subkey = derive_subkey(auth_pepper, "mfa/recovery")
    return hmac.new(subkey, normalized.encode("ascii"), hashlib.sha256).digest()


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Generate cryptographically random Crockford Base32 recovery codes.

    Each code provides 50 bits of entropy (10 characters) formatted as XXXXX-XXXXX.
    """
    codes: list[str] = []
    seen: set[str] = set()
    while len(codes) < count:
        raw = "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(RECOVERY_CODE_LEN))
        if raw in seen:
            continue
        seen.add(raw)
        half = RECOVERY_CODE_LEN // 2
        formatted = f"{raw[:half]}-{raw[half:]}"
        codes.append(formatted)
    return codes


class RecoveryCodeService:
    """Service for generating, storing, and consuming hashed recovery codes."""

    def __init__(self, auth_pepper: bytes) -> None:
        """Initialize service with auth pepper for key derivation."""
        self._auth_pepper = auth_pepper

    async def regenerate_codes(
        self,
        session: AsyncSession,
        principal_id: uuid.UUID,
    ) -> list[str]:
        """Generate and persist 10 new recovery codes, replacing all prior codes."""
        raw_codes = generate_recovery_codes(count=RECOVERY_CODE_COUNT)
        hmacs = [hash_recovery_code(c, self._auth_pepper) for c in raw_codes]

        await session.execute(
            text("SELECT kb_auth.recovery_codes_replace(:p_id, :p_hmacs)"),
            {"p_id": principal_id, "p_hmacs": hmacs},
        )
        return raw_codes

    async def consume_code(
        self,
        session: AsyncSession,
        principal_id: uuid.UUID,
        code: str,
    ) -> int:
        """Attempt to consume a single-use recovery code.

        Returns remaining unused code count (>= 0), or -1 if invalid or already consumed.
        """
        try:
            code_hmac = hash_recovery_code(code, self._auth_pepper)
        except ValueError:
            return -1

        res = await session.execute(
            text("SELECT kb_auth.recovery_code_consume(:p_id, :p_hmac)"),
            {"p_id": principal_id, "p_hmac": code_hmac},
        )
        return int(res.scalar_one())
