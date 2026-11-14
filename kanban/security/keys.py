"""Cryptographic key material provider and purpose-separated HKDF derivation (S2.2)."""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_PURPOSE_REGEX = re.compile(r"^[a-z0-9][a-z0-9./-]{2,63}$")
KEY_LENGTH_BYTES = 32
MIN_ROOT_KEY_BYTES = 16
REQUIRED_KEYRING_KEYS = ("MASTER_KEK", "KB_AUTH_PEPPER", "SESSION_HMAC_KEY")


class KeyMaterialError(Exception):
    """Raised when key material fails validation, permissions, or loading constraints."""


@dataclass(frozen=True, slots=True)
class KeyMaterial:
    """Immutable provider holding root symmetric keying material for the platform.

    Never prints key bytes in logs or exception traces.
    """

    master_kek: bytes
    auth_pepper: bytes
    session_hmac_key: bytes
    master_kek_kid: str = "kek-v1"

    def __post_init__(self) -> None:
        """Validate key lengths and identifier integrity."""
        if len(self.master_kek) != KEY_LENGTH_BYTES:
            msg = f"master_kek must be exactly {KEY_LENGTH_BYTES} bytes"
            raise KeyMaterialError(msg)
        if len(self.auth_pepper) != KEY_LENGTH_BYTES:
            msg = f"auth_pepper must be exactly {KEY_LENGTH_BYTES} bytes"
            raise KeyMaterialError(msg)
        if len(self.session_hmac_key) != KEY_LENGTH_BYTES:
            msg = f"session_hmac_key must be exactly {KEY_LENGTH_BYTES} bytes"
            raise KeyMaterialError(msg)
        if not self.master_kek_kid.strip():
            msg = "master_kek_kid must be a non-empty string"
            raise KeyMaterialError(msg)

    def __repr__(self) -> str:
        """Sanitize string representation to prevent key leakage in debug traces."""
        return "KeyMaterial(<redacted>)"


def _decode_b64url_key(value: object, name: str) -> bytes:
    """Decode an unpadded or padded base64url key ensuring exact 32-byte length."""
    if not isinstance(value, str) or not value.strip():
        msg = f"Key {name} must be a non-empty string"
        raise KeyMaterialError(msg)

    padding = "=" * (-len(value) % 4)
    try:
        raw = base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except Exception as err:
        msg = f"Failed to decode base64url key {name}: {err}"
        raise KeyMaterialError(msg) from err

    if len(raw) != KEY_LENGTH_BYTES:
        msg = f"Key {name} must be exactly {KEY_LENGTH_BYTES} bytes (got {len(raw)})"
        raise KeyMaterialError(msg)

    return raw


def _load_from_keyring_file(target_path: Path) -> KeyMaterial:
    """Load key material from a strictly-permissioned JSON file."""
    if not target_path.exists():
        msg = f"Keyring file does not exist: {target_path}"
        raise KeyMaterialError(msg)

    if target_path.is_symlink():
        msg = f"Keyring file must not be a symlink: {target_path}"
        raise KeyMaterialError(msg)

    if not target_path.is_file():
        msg = f"Keyring target must be a regular file: {target_path}"
        raise KeyMaterialError(msg)

    mode = target_path.stat().st_mode
    if bool(mode & 0o077):
        msg = f"Keyring file permissions {oct(mode)} too permissive; must be mode 0600 or stricter"
        raise KeyMaterialError(msg)

    try:
        content = target_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except Exception as err:
        msg = f"Failed to read or parse keyring JSON from {target_path}: {err}"
        raise KeyMaterialError(msg) from err

    if not isinstance(data, dict):
        msg = "Keyring JSON root must be an object"
        raise KeyMaterialError(msg)

    for required_key in REQUIRED_KEYRING_KEYS:
        if required_key not in data:
            msg = f"Missing required key {required_key} in keyring file {target_path}"
            raise KeyMaterialError(msg)

    master_kek = _decode_b64url_key(data["MASTER_KEK"], "MASTER_KEK")
    auth_pepper = _decode_b64url_key(data["KB_AUTH_PEPPER"], "KB_AUTH_PEPPER")
    session_hmac_key = _decode_b64url_key(data["SESSION_HMAC_KEY"], "SESSION_HMAC_KEY")
    kid = data.get("MASTER_KEK_KID", "kek-v1")
    if not isinstance(kid, str) or not kid.strip():
        msg = "MASTER_KEK_KID in keyring file must be a non-empty string"
        raise KeyMaterialError(msg)

    return KeyMaterial(
        master_kek=master_kek,
        master_kek_kid=kid,
        auth_pepper=auth_pepper,
        session_hmac_key=session_hmac_key,
    )


def _load_from_env() -> KeyMaterial | None:
    """Load key material from direct environment variables, or None if absent."""
    env_master = os.environ.get("KANBAN_MASTER_KEK") or os.environ.get("KB_MASTER_KEK_B64")
    env_pepper = os.environ.get("KANBAN_AUTH_PEPPER") or os.environ.get("KB_AUTH_PEPPER_B64")
    env_session = os.environ.get("KANBAN_SESSION_HMAC_KEY") or os.environ.get(
        "KB_SESSION_HMAC_KEY_B64"
    )

    if env_master and env_pepper and env_session:
        master_kek = _decode_b64url_key(env_master, "KANBAN_MASTER_KEK")
        auth_pepper = _decode_b64url_key(env_pepper, "KANBAN_AUTH_PEPPER")
        session_hmac_key = _decode_b64url_key(env_session, "KANBAN_SESSION_HMAC_KEY")
        kid = os.environ.get("KANBAN_MASTER_KEK_KID", "kek-v1")
        if not kid.strip():
            msg = "KANBAN_MASTER_KEK_KID must be a non-empty string"
            raise KeyMaterialError(msg)

        return KeyMaterial(
            master_kek=master_kek,
            master_kek_kid=kid,
            auth_pepper=auth_pepper,
            session_hmac_key=session_hmac_key,
        )

    return None


def load_key_material(keyring_file: str | Path | None = None) -> KeyMaterial:
    """Load platform key material from KANBAN_KEYRING_FILE or fallback environment variables.

    Fails closed if keys are missing, corrupt, too short, or if keyring file permissions
    exceed mode 0600 or if the file is a symlink.
    """
    file_target = keyring_file or os.environ.get("KANBAN_KEYRING_FILE")
    if file_target is not None:
        return _load_from_keyring_file(Path(file_target))

    from_env = _load_from_env()
    if from_env is not None:
        return from_env

    msg = (
        "No valid key material source found. Provide either KANBAN_KEYRING_FILE "
        "(JSON with MASTER_KEK, KB_AUTH_PEPPER, SESSION_HMAC_KEY) or environment variables "
        "KANBAN_MASTER_KEK, KANBAN_AUTH_PEPPER, KANBAN_SESSION_HMAC_KEY."
    )
    raise KeyMaterialError(msg)


def derive_subkey(root: bytes, purpose: str, length: int = KEY_LENGTH_BYTES) -> bytes:
    """Derive a purpose-separated cryptographic subkey using HKDF-SHA256 (RFC 5869).

    All downstream HMAC and symmetric encryption usage must derive dedicated subkeys.
    """
    if not _PURPOSE_REGEX.match(purpose):
        msg = (
            f"Invalid subkey purpose: {purpose!r}. "
            "Must match regex '^[a-z0-9][a-z0-9./-]{2,63}$'."
        )
        raise ValueError(msg)

    if len(root) < MIN_ROOT_KEY_BYTES:
        msg = f"Root key material must be bytes with length >= {MIN_ROOT_KEY_BYTES}"
        raise KeyMaterialError(msg)

    info = b"kanban/" + purpose.encode("ascii")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=None,
        info=info,
    )
    return hkdf.derive(root)
