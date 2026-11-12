"""First-boot CSPRNG keyring generator, validator, and SCRAM verifier helper.

Generates 256-bit cryptographic secrets on first boot into an atomic 0600 file,
validates integrity on warm boots, and computes RFC 7677 SCRAM-SHA-256 verifiers.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

KEYRING_VERSION: int = 1
KEYRING_MAX_SIZE_BYTES: int = 64 * 1024  # 64 KiB
SECRET_BYTE_LENGTH: int = 32
KEYRING_FILE_MODE: int = 0o600
KEYRING_DIR_MODE: int = 0o700

EXPECTED_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "version",
        "created_at",
        "MASTER_KEK",
        "KB_AUTH_PEPPER",
        "SESSION_HMAC_KEY",
        "db_roles",
    }
)
EXPECTED_DB_ROLES: frozenset[str] = frozenset({"kanban_app", "kanban_migrator"})


class KeyringError(Exception):
    """Raised when the standalone keyring cannot be loaded or is invalid."""


@dataclass(frozen=True)
class Keyring:
    """Immutable representation of standalone keyring secrets."""

    master_kek: bytes
    auth_pepper: bytes
    session_hmac_key: bytes
    kanban_app_password: bytes
    kanban_migrator_password: bytes
    created_at: str
    version: int = KEYRING_VERSION

    @property
    def master_kek_b64(self) -> str:
        """URL-safe base64 string without padding for MASTER_KEK."""
        return base64.urlsafe_b64encode(self.master_kek).decode("ascii").rstrip("=")

    @property
    def auth_pepper_b64(self) -> str:
        """URL-safe base64 string without padding for KB_AUTH_PEPPER."""
        return base64.urlsafe_b64encode(self.auth_pepper).decode("ascii").rstrip("=")

    @property
    def session_hmac_key_b64(self) -> str:
        """URL-safe base64 string without padding for SESSION_HMAC_KEY."""
        return base64.urlsafe_b64encode(self.session_hmac_key).decode("ascii").rstrip("=")

    @property
    def kanban_app_password_str(self) -> str:
        """URL-safe base64 string without padding for kanban_app password."""
        return base64.urlsafe_b64encode(self.kanban_app_password).decode("ascii").rstrip("=")

    @property
    def kanban_migrator_password_str(self) -> str:
        """URL-safe base64 string without padding for kanban_migrator password."""
        return base64.urlsafe_b64encode(self.kanban_migrator_password).decode("ascii").rstrip("=")

    def __repr__(self) -> str:
        """Redacted representation preventing secret disclosure."""
        return "Keyring(<redacted>)"

    def __str__(self) -> str:
        """Redacted string representation preventing secret disclosure."""
        return "Keyring(<redacted>)"


_B64URL_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]+$")


def _decode_b64url_secret(raw: object, name: str) -> bytes:
    """Decode an unpadded URL-safe base64 string and verify exact 32 bytes length."""
    if not isinstance(raw, str):
        msg = f"Secret {name} must be a string, got {type(raw).__name__}"
        raise KeyringError(msg)
    if not _B64URL_REGEX.fullmatch(raw):
        msg = f"Secret {name} is not valid base64url: contains invalid characters"
        raise KeyringError(msg)
    padding = "=" * ((4 - len(raw) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode((raw + padding).encode("ascii"))
    except Exception as err:
        msg = f"Secret {name} is not valid base64url: {err}"
        raise KeyringError(msg) from err

    if len(decoded) != SECRET_BYTE_LENGTH:
        msg = f"Secret {name} decoded to {len(decoded)} bytes (expected {SECRET_BYTE_LENGTH})"
        raise KeyringError(msg)

    return decoded


def _encode_b64url_secret(raw: bytes) -> str:
    """Encode bytes into URL-safe base64 string without padding."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _validate_file_attributes(path: Path) -> None:
    """Verify symlink status, owner UID, permission bits, and file size."""
    if path.is_symlink():
        msg = f"Keyring file {path} must not be a symlink"
        raise KeyringError(msg)

    parent = path.parent
    if parent.exists():
        parent_mode = stat.S_IMODE(parent.stat().st_mode)
        if (parent_mode & 0o077) != 0:
            msg = f"Keyring parent directory {parent} must have mode 0700, got {oct(parent_mode)}"
            raise KeyringError(msg)

    st = path.stat()
    if os.getuid() == 0 and st.st_uid != 0:
        msg = f"Keyring file {path} must be owned by UID 0 (root), got {st.st_uid}"
        raise KeyringError(msg)

    mode = stat.S_IMODE(st.st_mode)
    if mode != KEYRING_FILE_MODE:
        msg = f"Keyring file {path} must have mode 0600, got {oct(mode)}"
        raise KeyringError(msg)

    if st.st_size > KEYRING_MAX_SIZE_BYTES:
        msg = f"Keyring file {path} exceeds maximum size of 64 KiB: {st.st_size} bytes"
        raise KeyringError(msg)


def _validate_and_load_keyring(path: Path) -> Keyring:
    """Validate existing keyring file against all security constraints and load it."""
    _validate_file_attributes(path)

    try:
        content = path.read_text(encoding="utf-8")
        data: Any = json.loads(content)
    except Exception as err:
        msg = f"Keyring file {path} contains invalid JSON: {err}"
        raise KeyringError(msg) from err

    if not isinstance(data, dict):
        msg = "Keyring JSON root must be an object"
        raise KeyringError(msg)

    keys = set(data.keys())
    if keys != EXPECTED_TOP_LEVEL_KEYS:
        msg = f"Keyring keys mismatch: {keys} != {EXPECTED_TOP_LEVEL_KEYS}"
        raise KeyringError(msg)

    if data.get("version") != KEYRING_VERSION:
        msg = f"Unsupported keyring version: {data.get('version')} (expected {KEYRING_VERSION})"
        raise KeyringError(msg)

    created_at = data.get("created_at")
    if not isinstance(created_at, str):
        msg = "Keyring created_at must be an ISO-8601 string"
        raise KeyringError(msg)

    db_roles = data.get("db_roles")
    if not isinstance(db_roles, dict) or set(db_roles.keys()) != EXPECTED_DB_ROLES:
        msg = f"Keyring db_roles mismatch: {db_roles}"
        raise KeyringError(msg)

    return Keyring(
        master_kek=_decode_b64url_secret(data["MASTER_KEK"], "MASTER_KEK"),
        auth_pepper=_decode_b64url_secret(data["KB_AUTH_PEPPER"], "KB_AUTH_PEPPER"),
        session_hmac_key=_decode_b64url_secret(data["SESSION_HMAC_KEY"], "SESSION_HMAC_KEY"),
        kanban_app_password=_decode_b64url_secret(db_roles["kanban_app"], "kanban_app"),
        kanban_migrator_password=_decode_b64url_secret(
            db_roles["kanban_migrator"], "kanban_migrator"
        ),
        created_at=created_at,
        version=KEYRING_VERSION,
    )


def load_or_create_keyring(
    path: Path,
    *,
    _before_replace_hook: Callable[[], None] | None = None,
) -> Keyring:
    """Load existing keyring or atomically create a new one with mode 0600."""
    if path.exists() or path.is_symlink():
        return _validate_and_load_keyring(path)

    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        parent.chmod(KEYRING_DIR_MODE)

    kek = os.urandom(SECRET_BYTE_LENGTH)
    pepper = os.urandom(SECRET_BYTE_LENGTH)
    hmac_key = os.urandom(SECRET_BYTE_LENGTH)
    app_pw = os.urandom(SECRET_BYTE_LENGTH)
    mig_pw = os.urandom(SECRET_BYTE_LENGTH)

    created_at = datetime.now(UTC).isoformat()
    payload = {
        "version": KEYRING_VERSION,
        "created_at": created_at,
        "MASTER_KEK": _encode_b64url_secret(kek),
        "KB_AUTH_PEPPER": _encode_b64url_secret(pepper),
        "SESSION_HMAC_KEY": _encode_b64url_secret(hmac_key),
        "db_roles": {
            "kanban_app": _encode_b64url_secret(app_pw),
            "kanban_migrator": _encode_b64url_secret(mig_pw),
        },
    }

    raw_bytes = json.dumps(payload, indent=2).encode("utf-8")
    rand_hex = os.urandom(8).hex()
    tmp_path = parent / f"{path.name}.{rand_hex}.tmp"

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(tmp_path), flags, KEYRING_FILE_MODE)
    try:
        os.write(fd, raw_bytes)
        os.fsync(fd)
    finally:
        os.close(fd)

    if _before_replace_hook is not None:
        _before_replace_hook()

    if path.exists():
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        return _validate_and_load_keyring(path)

    tmp_path.replace(path)

    with contextlib.suppress(OSError):
        dfd = os.open(str(parent), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)

    return Keyring(
        master_kek=kek,
        auth_pepper=pepper,
        session_hmac_key=hmac_key,
        kanban_app_password=app_pw,
        kanban_migrator_password=mig_pw,
        created_at=created_at,
        version=KEYRING_VERSION,
    )


def compute_scram_sha256_verifier(
    password: bytes | str,
    salt: bytes | None = None,
    iterations: int = 4096,
) -> str:
    """Compute an RFC 5802 / RFC 7677 SCRAM-SHA-256 verifier string for PostgreSQL.

    Format: SCRAM-SHA-256$<iterations>:<salt_b64>$<stored_key_b64>:<server_key_b64>
    """
    pw_bytes = password.encode("utf-8") if isinstance(password, str) else password

    if salt is None:
        salt = os.urandom(16)

    salted = hashlib.pbkdf2_hmac("sha256", pw_bytes, salt, iterations, 32)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()

    salt_b64 = base64.b64encode(salt).decode("ascii")
    stored_b64 = base64.b64encode(stored_key).decode("ascii")
    server_b64 = base64.b64encode(server_key).decode("ascii")

    return f"SCRAM-SHA-256${iterations}:{salt_b64}${stored_b64}:{server_b64}"
