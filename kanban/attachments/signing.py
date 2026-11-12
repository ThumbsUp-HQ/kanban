"""HMAC-SHA256 signed URL minting and verification for attachment blobs (S5.4)."""

from __future__ import annotations

import base64
import hmac
import time
from typing import TYPE_CHECKING, Final

from kanban.security.keys import derive_subkey

if TYPE_CHECKING:
    import uuid

DEFAULT_SIGNED_URL_TTL_SECONDS: Final[int] = 300  # 300s exact


def _b64url_encode(data: bytes) -> str:
    """Encode bytes to base64url string without padding."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def sign_attachment_url(
    attachment_id: uuid.UUID | str,
    principal_id: uuid.UUID | str,
    session_hmac_key: bytes,
    ttl_seconds: int = DEFAULT_SIGNED_URL_TTL_SECONDS,
    now: float | None = None,
) -> str:
    """Mint an HMAC-SHA256 signed content URL bound to attachment_id and principal_id."""
    current_time = int(time.time() if now is None else now)
    exp = current_time + ttl_seconds
    att_str = str(attachment_id)
    p_str = str(principal_id)

    subkey = derive_subkey(session_hmac_key, "attachment/signed-url")
    msg = f"v1|{att_str}|{p_str}|{exp}".encode()
    sig_digest = hmac.new(subkey, msg, "sha256").digest()
    sig = _b64url_encode(sig_digest)

    return f"/api/v1/attachments/{att_str}/content?exp={exp}&p={p_str}&sig={sig}"


def verify_attachment_url(  # noqa: PLR0913, PLR0917
    attachment_id: uuid.UUID | str,
    principal_id: uuid.UUID | str,
    exp: int,
    sig: str,
    session_hmac_key: bytes,
    now: float | None = None,
) -> bool:
    """Verify HMAC signature and expiry for an attachment content request.

    Rejects expired or tampered signatures BEFORE any database or disk access.
    """
    current_time = int(time.time() if now is None else now)
    if exp < current_time:
        return False

    att_str = str(attachment_id)
    p_str = str(principal_id)

    try:
        subkey = derive_subkey(session_hmac_key, "attachment/signed-url")
        msg = f"v1|{att_str}|{p_str}|{exp}".encode()
        expected_digest = hmac.new(subkey, msg, "sha256").digest()
        expected_sig = _b64url_encode(expected_digest)
        clean_sig = sig.strip().rstrip("=")
        return hmac.compare_digest(expected_sig, clean_sig)
    except Exception:  # noqa: BLE001
        return False
