# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""RFC 6238 TOTP authentication factor service and algorithm (KB-P2-05a)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import struct
import time
import urllib.parse
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from kanban.security.envelope import (
    EnvelopeDecryptError,
    EnvelopeInputError,
    SealedSecret,
    open_bound,
    seal_bound,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.security.envelope import KekProvider

logger = logging.getLogger(__name__)

TOTP_DIGITS: Final[int] = 6
TOTP_STEP_SECONDS: Final[int] = 30
PENDING_EXPIRY_SECONDS: Final[int] = 600

__all__ = [
    "PENDING_EXPIRY_SECONDS",
    "TOTP_DIGITS",
    "TOTP_STEP_SECONDS",
    "TotpService",
    "totp_at",
    "verify_totp",
]


def totp_at(secret: bytes, timestamp: int, digits: int = TOTP_DIGITS) -> str:
    """Compute RFC 6238 TOTP code for timestamp using HMAC-SHA1.

    Args:
        secret: 160-bit shared secret key material.
        timestamp: Unix epoch timestamp in seconds.
        digits: Number of digits in generated code (defaults to 6).

    """
    counter = timestamp // TOTP_STEP_SECONDS
    counter_bytes = struct.pack(">Q", counter)
    digest = hmac.new(secret, counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10**digits)).zfill(digits)


def verify_totp(
    secret: bytes,
    code: str,
    last_accepted_step: int,
    timestamp: int | None = None,
    window: int = 1,
) -> tuple[bool, int]:
    """Verify TOTP code against acceptance window with replay prevention.

    Returns (is_valid, accepted_step). If invalid, returns (False, 0).
    Rejects malformed formats (non-ASCII, non-digits, length != 6) without HMAC.
    """
    if len(code) != TOTP_DIGITS or not code.isascii() or not code.isdigit():
        return False, 0

    current_time = timestamp if timestamp is not None else int(time.time())
    current_step = current_time // TOTP_STEP_SECONDS

    for step in range(current_step - window, current_step + window + 1):
        if step <= last_accepted_step:
            continue
        expected_code = totp_at(secret, step * TOTP_STEP_SECONDS, digits=TOTP_DIGITS)
        if hmac.compare_digest(expected_code, code):
            return True, step

    return False, 0


class TotpService:
    """Service for TOTP factor enrollment, confirmation, verification, and revocation."""

    def __init__(self, kek: KekProvider) -> None:
        """Initialize service with root KEK provider."""
        self._kek = kek

    async def has_active_factor(
        self,
        session: AsyncSession,
        principal_id: uuid.UUID,
    ) -> bool:
        """Check if principal has an active TOTP factor or WebAuthn credentials."""
        res = await session.execute(
            text(
                "SELECT has_active_totp, webauthn_credential_count FROM kb_auth.mfa_status(:p_id)"
            ),
            {"p_id": principal_id},
        )
        row = res.mappings().first()
        if not row:
            return False
        return bool(row["has_active_totp"] or (row["webauthn_credential_count"] or 0) > 0)

    async def enroll(
        self,
        session: AsyncSession,
        principal_id: uuid.UUID,
        username: str,
        *,
        deny_if_active: bool = False,
    ) -> tuple[str, str]:
        """Enroll a new pending TOTP factor. Returns (otpauth_uri, secret_b32)."""
        if deny_if_active and await self.has_active_factor(session, principal_id):
            msg = "Cannot enroll or overwrite TOTP factor when MFA is already active"
            raise ValueError(msg)

        secret = secrets.token_bytes(20)
        secret_b32 = base64.b32encode(secret).decode("ascii")
        aad = b"kanban/totp/v1|" + principal_id.bytes
        sealed = seal_bound(secret, aad, self._kek)

        await session.execute(
            text("SELECT kb_auth.totp_enroll(:p_id, :p_blob, :p_wrapped, :p_kid)"),
            {
                "p_id": principal_id,
                "p_blob": sealed.encrypted_secret_blob,
                "p_wrapped": sealed.wrapped_dek,
                "p_kid": sealed.dek_kid,
            },
        )

        safe_username = urllib.parse.quote(username)
        uri = (
            f"otpauth://totp/Kanban:{safe_username}"
            f"?secret={secret_b32}&issuer=Kanban&algorithm=SHA1&digits=6&period=30"
        )
        return uri, secret_b32

    async def confirm(
        self,
        session: AsyncSession,
        principal_id: uuid.UUID,
        code: str,
        timestamp: int | None = None,
    ) -> bool:
        """Confirm a pending factor if code matches within window and factor < 600s."""
        res = await session.execute(
            text("SELECT * FROM kb_auth.totp_get_pending(:p_id)"),
            {"p_id": principal_id},
        )
        row = res.mappings().first()
        if not row:
            return False

        sealed = SealedSecret(
            encrypted_secret_blob=row["encrypted_secret_blob"],
            wrapped_dek=row["wrapped_dek"],
            dek_kid=row["dek_kid"],
        )
        aad = b"kanban/totp/v1|" + principal_id.bytes
        try:
            secret = open_bound(sealed, aad, self._kek)
        except (EnvelopeDecryptError, EnvelopeInputError):
            logger.exception("Failed to decrypt pending TOTP factor secret")
            return False

        try:
            valid, step = verify_totp(
                bytes(secret),
                code,
                last_accepted_step=0,
                timestamp=timestamp,
            )
            if not valid:
                return False

            conf_res = await session.execute(
                text("SELECT kb_auth.totp_confirm(:p_factor_id, :p_step)"),
                {"p_factor_id": row["id"], "p_step": step},
            )
            return bool(conf_res.scalar_one())
        finally:
            for i in range(len(secret)):
                secret[i] = 0

    async def verify(
        self,
        session: AsyncSession,
        principal_id: uuid.UUID,
        code: str,
        timestamp: int | None = None,
    ) -> bool:
        """Verify TOTP code against active factor, advancing step atomically."""
        res = await session.execute(
            text("SELECT * FROM kb_auth.totp_get_active(:p_id)"),
            {"p_id": principal_id},
        )
        row = res.mappings().first()
        if not row:
            return False

        sealed = SealedSecret(
            encrypted_secret_blob=row["encrypted_secret_blob"],
            wrapped_dek=row["wrapped_dek"],
            dek_kid=row["dek_kid"],
        )
        aad = b"kanban/totp/v1|" + principal_id.bytes
        try:
            secret = open_bound(sealed, aad, self._kek)
        except (EnvelopeDecryptError, EnvelopeInputError):
            logger.exception("Failed to decrypt active TOTP factor secret")
            return False

        try:
            valid, step = verify_totp(
                bytes(secret),
                code,
                last_accepted_step=row["last_accepted_step"],
                timestamp=timestamp,
            )
            if not valid:
                return False

            upd_res = await session.execute(
                text("SELECT kb_auth.totp_update_step(:p_factor_id, :p_step)"),
                {"p_factor_id": row["id"], "p_step": step},
            )
            return bool(upd_res.scalar_one())
        finally:
            for i in range(len(secret)):
                secret[i] = 0

    async def delete(
        self,
        session: AsyncSession,
        principal_id: uuid.UUID,
    ) -> bool:
        """Revoke active TOTP factor."""
        res = await session.execute(
            text("SELECT kb_auth.totp_delete(:p_id)"),
            {"p_id": principal_id},
        )
        return bool(res.scalar_one())
