# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""AES-256-GCM envelope encryption and DEK rotation (KB-P2-03)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping

    from kanban.security.keys import KeyMaterial

__all__ = [
    "BLOB_VERSION",
    "CODE_BAD_VERSION",
    "CODE_TAG_MISMATCH",
    "CODE_TRUNCATED",
    "CODE_UNKNOWN_KID",
    "KEY_LENGTH_BYTES",
    "MAX_PLAINTEXT_BYTES",
    "MIN_BLOB_LENGTH_BYTES",
    "NONCE_LENGTH_BYTES",
    "TAG_LENGTH_BYTES",
    "EnvelopeDecryptError",
    "EnvelopeInputError",
    "KekProvider",
    "SealedSecret",
    "StaticKekProvider",
    "UnknownKekError",
    "open_card_secret",
    "rewrap_dek",
    "seal_card_secret",
]

BLOB_VERSION = 0x01
MAX_PLAINTEXT_BYTES = 16384
KEY_LENGTH_BYTES = 32
NONCE_LENGTH_BYTES = 12
TAG_LENGTH_BYTES = 16
MIN_BLOB_LENGTH_BYTES = 1 + NONCE_LENGTH_BYTES + TAG_LENGTH_BYTES

CODE_UNKNOWN_KID = "UNKNOWN_KID"
CODE_TRUNCATED = "TRUNCATED"
CODE_BAD_VERSION = "BAD_VERSION"
CODE_TAG_MISMATCH = "TAG_MISMATCH"


class UnknownKekError(Exception):
    """Raised when an unrecognized key identifier is requested from a KekProvider."""

    def __init__(self, kid: str) -> None:
        """Initialize UnknownKekError with unrecognized key identifier."""
        super().__init__(f"Unknown KEK identifier: {kid}")
        self.kid = kid


class EnvelopeDecryptError(Exception):
    """Raised on decryption failure without leaking key or ciphertext details."""

    def __init__(self, code: str) -> None:
        """Initialize EnvelopeDecryptError with standardized error code."""
        super().__init__(f"Decryption failed: {code}")
        self.code = code


class EnvelopeInputError(Exception):
    """Raised when plaintext input exceeds size limits."""

    def __init__(self, length: int, max_length: int = MAX_PLAINTEXT_BYTES) -> None:
        """Initialize EnvelopeInputError with length bounds detail."""
        super().__init__(f"Plaintext length {length} exceeds maximum {max_length} bytes")
        self.length = length
        self.max_length = max_length


class KekProvider(Protocol):
    """Protocol for root key provider retrieving KEK bytes by key identifier."""

    def current_kid(self) -> str:
        """Return the active default key identifier."""
        ...

    def get(self, kid: str) -> bytes:
        """Return 32-byte key material for the requested identifier."""
        ...


class StaticKekProvider:
    """In-memory key material provider for KEK keys."""

    def __init__(self, keys: Mapping[str, bytes], current: str) -> None:
        """Initialize StaticKekProvider with mapped key dictionary and current kid."""
        if not keys:
            err_msg = "Key map cannot be empty"
            raise ValueError(err_msg)
        if current not in keys:
            err_msg = f"Current key identifier {current!r} not in provided keys"
            raise ValueError(err_msg)
        for kid, kbytes in keys.items():
            if len(kbytes) != KEY_LENGTH_BYTES:
                err_msg = f"KEK key {kid!r} must be {KEY_LENGTH_BYTES} bytes"
                raise ValueError(err_msg)
        self._keys = dict(keys)
        self._current = current

    def current_kid(self) -> str:
        """Return the active default key identifier."""
        return self._current

    def get(self, kid: str) -> bytes:
        """Retrieve 32-byte KEK material for the requested key identifier."""
        if kid not in self._keys:
            raise UnknownKekError(kid)
        return self._keys[kid]

    @classmethod
    def from_key_material(cls, km: KeyMaterial) -> StaticKekProvider:
        """Construct StaticKekProvider from security KeyMaterial configuration."""
        keys = {km.master_kek_kid: km.master_kek}
        return cls(keys=keys, current=km.master_kek_kid)


@dataclass(frozen=True)
class SealedSecret:
    """Envelope-encrypted secret and wrapped per-card DEK."""

    encrypted_secret_blob: bytes
    wrapped_dek: bytes
    dek_kid: str


def _build_secret_aad(card_id: uuid.UUID, provider_kind: str) -> bytes:
    """Generate canonical authenticated data binding for card secret blob."""
    return b"kanban/card-secret/v1|" + card_id.bytes + b"|" + provider_kind.encode("utf-8")


def _build_dek_aad(card_id: uuid.UUID, kid: str) -> bytes:
    """Generate canonical authenticated data binding for wrapped card DEK."""
    return b"kanban/card-dek/v1|" + card_id.bytes + b"|" + kid.encode("utf-8")


def seal_card_secret(
    card_id: uuid.UUID,
    provider_kind: str,
    plaintext: bytes,
    kek: KekProvider,
) -> SealedSecret:
    """Seal a card secret with a fresh per-card DEK wrapped under current KEK."""
    if len(plaintext) > MAX_PLAINTEXT_BYTES:
        raise EnvelopeInputError(len(plaintext), MAX_PLAINTEXT_BYTES)

    dek_raw = AESGCM.generate_key(bit_length=256)
    dek = bytearray(dek_raw)
    try:
        secret_nonce = os.urandom(NONCE_LENGTH_BYTES)
        secret_aad = _build_secret_aad(card_id, provider_kind)
        secret_cipher = AESGCM(bytes(dek)).encrypt(secret_nonce, plaintext, secret_aad)
        encrypted_secret_blob = bytes([BLOB_VERSION]) + secret_nonce + secret_cipher

        kid = kek.current_kid()
        kek_bytes = kek.get(kid)
        dek_nonce = os.urandom(NONCE_LENGTH_BYTES)
        dek_aad = _build_dek_aad(card_id, kid)
        wrapped_cipher = AESGCM(kek_bytes).encrypt(dek_nonce, bytes(dek), dek_aad)
        wrapped_dek = bytes([BLOB_VERSION]) + dek_nonce + wrapped_cipher

        return SealedSecret(
            encrypted_secret_blob=encrypted_secret_blob,
            wrapped_dek=wrapped_dek,
            dek_kid=kid,
        )
    finally:
        for idx in range(len(dek)):
            dek[idx] = 0


def open_card_secret(
    card_id: uuid.UUID,
    provider_kind: str,
    sealed: SealedSecret,
    kek: KekProvider,
) -> bytearray:
    """Open sealed card secret.

    Returns mutable bytearray so caller can zeroize (best effort in CPython).
    """
    try:
        kek_bytes = kek.get(sealed.dek_kid)
    except (UnknownKekError, KeyError):
        err_code = CODE_UNKNOWN_KID
        raise EnvelopeDecryptError(err_code) from None

    if len(sealed.wrapped_dek) < MIN_BLOB_LENGTH_BYTES:
        err_code = CODE_TRUNCATED
        raise EnvelopeDecryptError(err_code)
    if sealed.wrapped_dek[0] != BLOB_VERSION:
        err_code = CODE_BAD_VERSION
        raise EnvelopeDecryptError(err_code)

    dek_nonce = sealed.wrapped_dek[1 : 1 + NONCE_LENGTH_BYTES]
    dek_ct = sealed.wrapped_dek[1 + NONCE_LENGTH_BYTES :]
    dek_aad = _build_dek_aad(card_id, sealed.dek_kid)

    try:
        dek_plain = AESGCM(kek_bytes).decrypt(dek_nonce, dek_ct, dek_aad)
    except InvalidTag:
        err_code = CODE_TAG_MISMATCH
        raise EnvelopeDecryptError(err_code) from None

    dek = bytearray(dek_plain)
    try:
        if len(sealed.encrypted_secret_blob) < MIN_BLOB_LENGTH_BYTES:
            err_code = CODE_TRUNCATED
            raise EnvelopeDecryptError(err_code)
        if sealed.encrypted_secret_blob[0] != BLOB_VERSION:
            err_code = CODE_BAD_VERSION
            raise EnvelopeDecryptError(err_code)

        secret_nonce = sealed.encrypted_secret_blob[1 : 1 + NONCE_LENGTH_BYTES]
        secret_ct = sealed.encrypted_secret_blob[1 + NONCE_LENGTH_BYTES :]
        secret_aad = _build_secret_aad(card_id, provider_kind)

        try:
            secret_plain = AESGCM(bytes(dek)).decrypt(secret_nonce, secret_ct, secret_aad)
        except InvalidTag:
            err_code = CODE_TAG_MISMATCH
            raise EnvelopeDecryptError(err_code) from None

        return bytearray(secret_plain)
    finally:
        for idx in range(len(dek)):
            dek[idx] = 0


def rewrap_dek(
    card_id: uuid.UUID,
    sealed: SealedSecret,
    kek: KekProvider,
    new_kid: str,
) -> SealedSecret:
    """Rewrap per-card DEK under new KEK identifier without changing secret blob."""
    try:
        old_kek_bytes = kek.get(sealed.dek_kid)
    except (UnknownKekError, KeyError):
        err_code = CODE_UNKNOWN_KID
        raise EnvelopeDecryptError(err_code) from None

    try:
        new_kek_bytes = kek.get(new_kid)
    except (UnknownKekError, KeyError):
        err_code = CODE_UNKNOWN_KID
        raise EnvelopeDecryptError(err_code) from None

    if len(sealed.wrapped_dek) < MIN_BLOB_LENGTH_BYTES:
        err_code = CODE_TRUNCATED
        raise EnvelopeDecryptError(err_code)
    if sealed.wrapped_dek[0] != BLOB_VERSION:
        err_code = CODE_BAD_VERSION
        raise EnvelopeDecryptError(err_code)

    dek_nonce = sealed.wrapped_dek[1 : 1 + NONCE_LENGTH_BYTES]
    dek_ct = sealed.wrapped_dek[1 + NONCE_LENGTH_BYTES :]
    old_dek_aad = _build_dek_aad(card_id, sealed.dek_kid)

    try:
        dek_plain = AESGCM(old_kek_bytes).decrypt(dek_nonce, dek_ct, old_dek_aad)
    except InvalidTag:
        err_code = CODE_TAG_MISMATCH
        raise EnvelopeDecryptError(err_code) from None

    dek = bytearray(dek_plain)
    try:
        new_nonce = os.urandom(NONCE_LENGTH_BYTES)
        new_dek_aad = _build_dek_aad(card_id, new_kid)
        new_ct = AESGCM(new_kek_bytes).encrypt(new_nonce, bytes(dek), new_dek_aad)
        new_wrapped_dek = bytes([BLOB_VERSION]) + new_nonce + new_ct
        return SealedSecret(
            encrypted_secret_blob=sealed.encrypted_secret_blob,
            wrapped_dek=new_wrapped_dek,
            dek_kid=new_kid,
        )
    finally:
        for idx in range(len(dek)):
            dek[idx] = 0
