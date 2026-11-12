"""Streaming chunked AEAD backup encryption and decryption (KBBAK1 format).

Implements AES-256-GCM authenticated encryption in 4 MiB streaming chunks with
Argon2id or raw-key derivation, monotonic nonce generation, and tamper-resistant AAD.
"""

from __future__ import annotations

import base64
import os
import struct
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Final

import argon2.low_level
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:
    from typing import BinaryIO

MAGIC: Final[bytes] = b"KBBAK1\x00\x01"
KDF_MODE_RAW: Final[int] = 0x01
KDF_MODE_ARGON2ID: Final[int] = 0x02

SALT_BYTE_LENGTH: Final[int] = 16
NONCE_BYTE_LENGTH: Final[int] = 12
KEY_BYTE_LENGTH: Final[int] = 32
CHUNK_SIZE: Final[int] = 4 * 1024 * 1024  # 4 MiB
HEADER_LENGTH: Final[int] = len(MAGIC) + 1 + SALT_BYTE_LENGTH + NONCE_BYTE_LENGTH  # 37 bytes
FRAME_HEADER_LENGTH: Final[int] = 5  # uint32 payload_len + uint8 is_final

DEFAULT_ARGON2_MEMORY_COST: Final[int] = 64 * 1024  # 64 MiB
DEFAULT_ARGON2_TIME_COST: Final[int] = 3
DEFAULT_ARGON2_PARALLELISM: Final[int] = 4


class BackupCryptoError(Exception):
    """Base exception for backup cryptographic operations."""


class BackupIntegrityError(BackupCryptoError):
    """Raised when an encrypted backup archive is corrupted, tampered, or invalid."""


def derive_key_argon2id(
    passphrase: bytes,
    salt: bytes,
    *,
    memory_cost: int = DEFAULT_ARGON2_MEMORY_COST,
    time_cost: int = DEFAULT_ARGON2_TIME_COST,
    parallelism: int = DEFAULT_ARGON2_PARALLELISM,
) -> bytes:
    """Derive 32-byte key from passphrase using RFC 9106 Argon2id."""
    return argon2.low_level.hash_secret_raw(
        secret=passphrase,
        salt=salt,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=KEY_BYTE_LENGTH,
        type=argon2.low_level.Type.ID,
    )


def decode_raw_key(raw_key: str | bytes) -> bytes:
    """Decode raw or base64url encoded 256-bit key into 32 bytes."""
    if isinstance(raw_key, bytes):
        if len(raw_key) == KEY_BYTE_LENGTH:
            return raw_key
        try:
            raw_key_str = raw_key.decode("ascii")
        except UnicodeDecodeError as err:
            msg = f"Raw key must be {KEY_BYTE_LENGTH} bytes or valid base64url string"
            raise BackupCryptoError(msg) from err
    else:
        raw_key_str = raw_key

    cleaned = raw_key_str.strip()
    padding = "=" * ((4 - len(cleaned) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode((cleaned + padding).encode("ascii"))
    except Exception as err:
        msg = f"Failed to decode base64url key: {err}"
        raise BackupCryptoError(msg) from err

    if len(decoded) != KEY_BYTE_LENGTH:
        msg = f"Decoded key length is {len(decoded)} bytes (expected {KEY_BYTE_LENGTH})"
        raise BackupCryptoError(msg)
    return decoded


class KeySource(ABC):
    """Abstract base provider for encryption and decryption keys."""

    @property
    @abstractmethod
    def default_kdf_mode(self) -> int:
        """Default KDF mode identifier."""

    @abstractmethod
    def get_salt(self) -> bytes:
        """Generate or provide salt for archive creation."""

    @abstractmethod
    def resolve_key(self, kdf_mode: int, salt: bytes) -> bytes:
        """Resolve or derive 32-byte AES key given KDF mode and salt."""


class RawKeySource(KeySource):
    """Key provider utilizing a pre-shared 256-bit raw key."""

    def __init__(self, key: str | bytes) -> None:
        """Initialize with a raw 32-byte or base64url encoded key."""
        self._key = decode_raw_key(key)

    @property
    def default_kdf_mode(self) -> int:
        """Return RAW KDF mode identifier."""
        return KDF_MODE_RAW

    def get_salt(self) -> bytes:
        """Generate 16-byte random salt."""
        return os.urandom(SALT_BYTE_LENGTH)

    def resolve_key(self, kdf_mode: int, salt: bytes) -> bytes:
        """Return pre-shared raw key validating KDF mode matches RAW."""
        del salt
        if kdf_mode != KDF_MODE_RAW:
            msg = f"Archive requires KDF mode {kdf_mode:#x}, but raw key was provided"
            raise BackupCryptoError(msg)
        return self._key


class PassphraseKeySource(KeySource):
    """Key provider utilizing an Argon2id derived key from a passphrase."""

    def __init__(
        self,
        passphrase: str | bytes,
        *,
        memory_cost: int = DEFAULT_ARGON2_MEMORY_COST,
        time_cost: int = DEFAULT_ARGON2_TIME_COST,
        parallelism: int = DEFAULT_ARGON2_PARALLELISM,
    ) -> None:
        """Initialize with passphrase and tunable Argon2id parameters."""
        if isinstance(passphrase, str):
            self._passphrase = passphrase.encode("utf-8")
        else:
            self._passphrase = passphrase
        self.memory_cost = memory_cost
        self.time_cost = time_cost
        self.parallelism = parallelism

    @property
    def default_kdf_mode(self) -> int:
        """Return Argon2id KDF mode identifier."""
        return KDF_MODE_ARGON2ID

    def get_salt(self) -> bytes:
        """Generate 16-byte CSPRNG salt."""
        return os.urandom(SALT_BYTE_LENGTH)

    def resolve_key(self, kdf_mode: int, salt: bytes) -> bytes:
        """Derive 32-byte key from passphrase and salt via Argon2id."""
        if kdf_mode != KDF_MODE_ARGON2ID:
            msg = f"Archive requires KDF mode {kdf_mode:#x}, but passphrase was provided"
            raise BackupCryptoError(msg)
        return derive_key_argon2id(
            self._passphrase,
            salt,
            memory_cost=self.memory_cost,
            time_cost=self.time_cost,
            parallelism=self.parallelism,
        )


def _compute_chunk_nonce(base_nonce: bytes, chunk_index: int) -> bytes:
    """Compute 12-byte nonce by XORing base nonce with big-endian chunk index."""
    chunk_idx_be64 = struct.pack(">Q", chunk_index)
    mask = b"\x00\x00\x00\x00" + chunk_idx_be64
    return bytes(b ^ m for b, m in zip(base_nonce, mask, strict=True))


def _compute_chunk_aad(chunk_index: int, *, is_final: bool) -> bytes:
    """Compute tamper-resistant AAD binding chunk index and finality flag."""
    chunk_idx_be64 = struct.pack(">Q", chunk_index)
    is_final_byte = b"\x01" if is_final else b"\x00"
    return b"KBBAK1:" + chunk_idx_be64 + is_final_byte


def encrypt_stream(
    input_stream: BinaryIO,
    output_stream: BinaryIO,
    key_source: KeySource,
    *,
    chunk_size: int = CHUNK_SIZE,
) -> int:
    """Encrypt input stream into output stream in authenticated chunks.

    Returns the total number of plaintext bytes read and encrypted.
    """
    kdf_mode = key_source.default_kdf_mode
    salt = key_source.get_salt()
    base_nonce = os.urandom(NONCE_BYTE_LENGTH)
    key = key_source.resolve_key(kdf_mode, salt)
    aesgcm = AESGCM(key)

    header = MAGIC + bytes([kdf_mode]) + salt + base_nonce
    output_stream.write(header)

    chunk_index = 0
    total_plain_bytes = 0

    current_chunk = input_stream.read(chunk_size)
    total_plain_bytes += len(current_chunk)

    while True:
        next_chunk = input_stream.read(chunk_size)
        is_final = len(next_chunk) == 0

        nonce = _compute_chunk_nonce(base_nonce, chunk_index)
        aad = _compute_chunk_aad(chunk_index, is_final=is_final)

        ciphertext = aesgcm.encrypt(nonce, current_chunk, aad)
        frame_header = struct.pack(">IB", len(ciphertext), 1 if is_final else 0)
        output_stream.write(frame_header)
        output_stream.write(ciphertext)

        if is_final:
            break

        chunk_index += 1
        current_chunk = next_chunk
        total_plain_bytes += len(current_chunk)

    return total_plain_bytes


def _parse_and_validate_header(
    input_stream: BinaryIO,
    key_source: KeySource,
) -> tuple[AESGCM, bytes]:
    """Read archive header, validate magic, and initialize AESGCM cipher."""
    header = input_stream.read(HEADER_LENGTH)
    if len(header) < HEADER_LENGTH:
        msg = "Truncated archive: invalid header length"
        raise BackupIntegrityError(msg)

    magic = header[: len(MAGIC)]
    if magic != MAGIC:
        msg = f"Invalid archive header magic: {magic!r}"
        raise BackupIntegrityError(msg)

    kdf_mode = header[len(MAGIC)]
    salt_start = len(MAGIC) + 1
    salt_end = salt_start + SALT_BYTE_LENGTH
    salt = header[salt_start:salt_end]
    base_nonce = header[salt_end : salt_end + NONCE_BYTE_LENGTH]

    try:
        key = key_source.resolve_key(kdf_mode, salt)
    except Exception as err:
        msg = f"Failed to resolve decryption key: {err}"
        raise BackupIntegrityError(msg) from err

    return AESGCM(key), base_nonce


def _decrypt_single_chunk(
    input_stream: BinaryIO,
    aesgcm: AESGCM,
    base_nonce: bytes,
    chunk_index: int,
) -> tuple[bytes, bool]:
    """Read and authenticate a single framed chunk from the input stream."""
    frame_header = input_stream.read(FRAME_HEADER_LENGTH)
    if not frame_header:
        msg = "Truncated archive: missing is_final marker"
        raise BackupIntegrityError(msg)

    if len(frame_header) < FRAME_HEADER_LENGTH:
        msg = "Truncated archive: incomplete chunk frame header"
        raise BackupIntegrityError(msg)

    payload_len, is_final_int = struct.unpack(">IB", frame_header)
    is_final = is_final_int == 1

    ciphertext = input_stream.read(payload_len)
    if len(ciphertext) < payload_len:
        msg = "Truncated archive: incomplete chunk ciphertext"
        raise BackupIntegrityError(msg)

    nonce = _compute_chunk_nonce(base_nonce, chunk_index)
    aad = _compute_chunk_aad(chunk_index, is_final=is_final)

    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
    except InvalidTag as err:
        msg = (
            f"Cryptographic authentication failed on chunk {chunk_index} "
            "(corrupted data or wrong key)"
        )
        raise BackupIntegrityError(msg) from err

    return plaintext, is_final


def decrypt_stream(
    input_stream: BinaryIO,
    output_stream: BinaryIO,
    key_source: KeySource,
) -> int:
    """Decrypt archive stream into output stream while verifying all AEAD tags.

    Returns the total number of plaintext bytes written.
    Raises BackupIntegrityError if any authentication tag, header, or framing check fails.
    """
    aesgcm, base_nonce = _parse_and_validate_header(input_stream, key_source)
    chunk_index = 0
    total_plain_bytes = 0

    while True:
        plaintext, is_final = _decrypt_single_chunk(input_stream, aesgcm, base_nonce, chunk_index)
        output_stream.write(plaintext)
        total_plain_bytes += len(plaintext)
        chunk_index += 1

        if is_final:
            trailing = input_stream.read(1)
            if trailing:
                msg = "Trailing unexpected bytes after final chunk"
                raise BackupIntegrityError(msg)
            break

    return total_plain_bytes
