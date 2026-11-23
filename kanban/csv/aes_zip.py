# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""WinZip AE-2 (AES-256) password-protected ZIP archive packing and extraction (KAN-316)."""

from __future__ import annotations

import hmac
import os
import struct
import zlib
from typing import Final

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

__all__ = [
    "COMPRESSION_DEFLATED",
    "COMPRESSION_METHOD_WINZIP_AES",
    "COMPRESSION_STORED",
    "EXTRA_FIELD_WINZIP_AES",
    "MAX_COMPRESSION_RATIO",
    "MAX_UNCOMPRESSED_SIZE",
    "MIN_PASSWORD_LENGTH",
    "CorruptZipError",
    "InvalidPasswordError",
    "PasswordTooShortError",
    "PathTraversalError",
    "WinZipAesZipError",
    "ZipBombError",
    "create_winzip_aes256_zip",
    "extract_winzip_aes256_zip",
    "zeroize",
]

MIN_PASSWORD_LENGTH: Final[int] = 12
MAX_UNCOMPRESSED_SIZE: Final[int] = 50 * 1024 * 1024  # 50 MiB safety limit
MAX_COMPRESSION_RATIO: Final[float] = 100.0

EXTRA_FIELD_WINZIP_AES: Final[int] = 0x9901
WINZIP_AE_VERSION_2: Final[int] = 0x0002
VENDOR_ID_AE: Final[bytes] = b"AE"
ENCRYPTION_STRENGTH_256: Final[int] = 0x03
COMPRESSION_METHOD_WINZIP_AES: Final[int] = 99
COMPRESSION_STORED: Final[int] = 0
COMPRESSION_DEFLATED: Final[int] = 8

LOCAL_HEADER_MAGIC: Final[int] = 0x04034B50
CENTRAL_DIR_MAGIC: Final[int] = 0x02014B50
EOCD_MAGIC: Final[int] = 0x06054B50


class WinZipAesZipError(Exception):
    """Base exception for WinZip AES-256 ZIP operations."""


class PasswordTooShortError(WinZipAesZipError):
    """Raised when encryption password does not meet the 12-character minimum."""


class InvalidPasswordError(WinZipAesZipError):
    """Raised when decryption password fails verification or HMAC check."""


class ZipBombError(WinZipAesZipError):
    """Raised when decompression exceeds max size or compression ratio ceiling."""


class PathTraversalError(WinZipAesZipError):
    """Raised when an entry filename contains directory traversal sequences."""


class CorruptZipError(WinZipAesZipError):
    """Raised when archive headers or structures are malformed."""


def zeroize(*buffers: bytearray | memoryview) -> None:
    """Overwrite mutable memory buffers with zeros."""
    for buf in buffers:
        if isinstance(buf, memoryview) and buf.readonly:
            continue
        for i in range(len(buf)):
            buf[i] = 0


def _derive_keys(
    password: str, salt: bytes, *, use_sha256: bool = True
) -> tuple[bytearray, bytearray, bytes]:
    """Derive 66 bytes (32-byte AES key, 32-byte HMAC key, 2-byte pwd_verify)."""
    hash_alg = hashes.SHA256() if use_sha256 else hashes.SHA1()  # noqa: S303
    kdf = PBKDF2HMAC(
        algorithm=hash_alg,
        length=66,
        salt=salt,
        iterations=1000,
    )
    derived = bytearray(kdf.derive(password.encode("utf-8")))
    aes_key = bytearray(derived[:32])
    hmac_key = bytearray(derived[32:64])
    pwd_verify = bytes(derived[64:66])
    return aes_key, hmac_key, pwd_verify


def _ctr_crypt(data: bytes, aes_key: bytes) -> bytes:
    """Encrypt/decrypt data using WinZip AES-CTR mode (little-endian 128-bit counter)."""
    if not data:
        return b""
    blocks = (len(data) + 15) // 16
    buf = bytearray(blocks * 16)
    for i in range(blocks):
        struct.pack_into("<Q", buf, i * 16, i + 1)
    cipher = Cipher(algorithms.AES(aes_key), modes.ECB())  # noqa: S305
    encryptor = cipher.encryptor()
    keystream = encryptor.update(buf) + encryptor.finalize()

    k_int = int.from_bytes(keystream[: len(data)], "big")
    d_int = int.from_bytes(data, "big")
    return (k_int ^ d_int).to_bytes(len(data), "big")


def create_winzip_aes256_zip(files: dict[str, bytes], password: str) -> bytes:
    """Pack files into a standards-compliant WinZip AE-2 (AES-256) ZIP archive."""
    if not files:
        msg = "files dictionary cannot be empty"
        raise ValueError(msg)
    if len(password) < MIN_PASSWORD_LENGTH:
        msg = (
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long (got {len(password)})"
        )
        raise PasswordTooShortError(msg)

    local_headers = bytearray()
    cd_entries = bytearray()

    for filename, raw_data in files.items():
        # Sanitize filename
        clean_name = filename.strip().replace("\\", "/").lstrip("/")
        if not clean_name or ".." in clean_name.split("/"):
            msg = f"Dangerous or traversal filename: '{filename}'"
            raise PathTraversalError(msg)
        fname_bytes = clean_name.encode("utf-8")

        # 1. Deflate raw stream
        comp = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15)
        compressed = comp.compress(raw_data) + comp.flush()

        # 2. Key derivation
        salt = os.urandom(16)
        aes_key, hmac_key, pwd_verify = _derive_keys(password, salt, use_sha256=True)

        try:
            # 3. Encrypt payload
            ciphertext = _ctr_crypt(compressed, bytes(aes_key))

            # 4. Auth tag
            h = hmac.new(bytes(hmac_key), ciphertext, "sha256")
            auth_tag = h.digest()[:10]
        finally:
            zeroize(aes_key, hmac_key)

        file_payload = salt + pwd_verify + ciphertext + auth_tag

        # Extra field 0x9901 for WinZip AE-2
        extra = struct.pack(
            "<HHH2sBH",
            EXTRA_FIELD_WINZIP_AES,
            7,
            WINZIP_AE_VERSION_2,
            VENDOR_ID_AE,
            ENCRYPTION_STRENGTH_256,
            COMPRESSION_DEFLATED,
        )

        offset = len(local_headers)
        lh = (
            struct.pack(
                "<IHHHHHIIIHH",
                LOCAL_HEADER_MAGIC,
                51,  # Version needed: 5.1
                1,  # Bit 0: encrypted
                COMPRESSION_METHOD_WINZIP_AES,
                0,  # Mod time
                0,  # Mod date
                0,  # CRC-32 (0 for AE-2)
                len(file_payload),
                len(raw_data),
                len(fname_bytes),
                len(extra),
            )
            + fname_bytes
            + extra
            + file_payload
        )
        local_headers.extend(lh)

        cd = (
            struct.pack(
                "<IHHHHHHIIIHHHHHII",
                CENTRAL_DIR_MAGIC,
                51,  # Version made by
                51,  # Version needed
                1,  # Bit 0: encrypted
                COMPRESSION_METHOD_WINZIP_AES,
                0,  # Mod time
                0,  # Mod date
                0,  # CRC-32 (0 for AE-2)
                len(file_payload),
                len(raw_data),
                len(fname_bytes),
                len(extra),
                0,  # Comment length
                0,  # Disk start
                0,  # Internal attr
                0,  # External attr
                offset,
            )
            + fname_bytes
            + extra
        )
        cd_entries.extend(cd)

    cd_offset = len(local_headers)
    cd_size = len(cd_entries)
    eocd = struct.pack(
        "<IHHHHIIH",
        EOCD_MAGIC,
        0,
        0,
        len(files),
        len(files),
        cd_size,
        cd_offset,
        0,
    )
    return bytes(local_headers + cd_entries + eocd)


def extract_winzip_aes256_zip(  # noqa: C901, PLR0912, PLR0915
    zip_bytes: bytes, password: str | None = None
) -> dict[str, bytes]:
    """Extract files from a WinZip AE-2 (AES-256) ZIP archive with safety guards."""
    min_eocd_len = 22
    if len(zip_bytes) < min_eocd_len:
        msg = "ZIP payload too small to contain valid archive"
        raise CorruptZipError(msg)

    # Locate EOCD
    eocd_idx = zip_bytes.rfind(struct.pack("<I", EOCD_MAGIC))
    if eocd_idx == -1:
        msg = "End of central directory record (EOCD) not found"
        raise CorruptZipError(msg)

    eocd_fields = struct.unpack("<IHHHHIIH", zip_bytes[eocd_idx : eocd_idx + 22])
    total_entries = eocd_fields[4]
    cd_size = eocd_fields[5]
    cd_offset = eocd_fields[6]

    if cd_offset + cd_size > len(zip_bytes):
        msg = "Central directory record extends beyond file bounds"
        raise CorruptZipError(msg)

    extracted: dict[str, bytes] = {}
    cd_pos = cd_offset

    for _ in range(total_entries):
        if cd_pos + 46 > len(zip_bytes):
            msg = "Truncated central directory entry"
            raise CorruptZipError(msg)
        cd_fields = struct.unpack("<IHHHHHHIIIHHHHHII", zip_bytes[cd_pos : cd_pos + 46])
        if cd_fields[0] != CENTRAL_DIR_MAGIC:
            msg = f"Invalid central directory magic at offset {cd_pos}"
            raise CorruptZipError(msg)

        flags = cd_fields[3]
        method = cd_fields[4]
        comp_size = cd_fields[8]
        cd_fields[9]
        fname_len = cd_fields[10]
        extra_len = cd_fields[11]
        comment_len = cd_fields[12]
        local_offset = cd_fields[16]

        pos = cd_pos + 46
        filename = zip_bytes[pos : pos + fname_len].decode("utf-8", errors="replace")
        pos += fname_len
        extra_bytes = zip_bytes[pos : pos + extra_len]
        cd_pos = pos + extra_len + comment_len

        # Path traversal guard
        clean_name = filename.strip().replace("\\", "/").lstrip("/")
        if not clean_name or ".." in clean_name.split("/") or ":" in clean_name:
            msg = f"Dangerous or traversal path detected in archive: '{filename}'"
            raise PathTraversalError(msg)

        # Read local file header
        if local_offset + 30 > len(zip_bytes):
            msg = "Local header extends beyond archive bounds"
            raise CorruptZipError(msg)
        lh_fields = struct.unpack("<IHHHHHIIIHH", zip_bytes[local_offset : local_offset + 30])
        if lh_fields[0] != LOCAL_HEADER_MAGIC:
            msg = f"Invalid local header magic at offset {local_offset}"
            raise CorruptZipError(msg)

        lh_fname_len = lh_fields[9]
        lh_extra_len = lh_fields[10]
        data_start = local_offset + 30 + lh_fname_len + lh_extra_len
        data_end = data_start + comp_size

        if data_end > len(zip_bytes):
            msg = f"File data for '{clean_name}' extends beyond archive bounds"
            raise CorruptZipError(msg)

        entry_data = zip_bytes[data_start:data_end]

        is_encrypted = bool(flags & 1)

        if not is_encrypted:
            # Unencrypted entry
            if method == COMPRESSION_STORED:
                content = entry_data
            elif method == COMPRESSION_DEFLATED:
                decomp = zlib.decompressobj(wbits=-15)
                content = decomp.decompress(entry_data)
            else:
                msg = f"Unsupported unencrypted compression method: {method}"
                raise CorruptZipError(msg)
        else:
            # WinZip AES encrypted entry
            if method != COMPRESSION_METHOD_WINZIP_AES:
                msg = f"Unsupported encrypted compression method: {method}"
                raise CorruptZipError(msg)

            if not password:
                msg = "Password is required to decrypt encrypted ZIP entry"
                raise InvalidPasswordError(msg)

            # Parse extra field 0x9901
            extra_to_search = (
                extra_bytes or zip_bytes[local_offset + 30 + lh_fname_len : data_start]
            )
            extra_method = COMPRESSION_DEFLATED
            min_aes_extra_size = 7
            sha256_key_len = 32
            epos = 0
            while epos + 4 <= len(extra_to_search):
                etag, esize = struct.unpack("<HH", extra_to_search[epos : epos + 4])
                if (
                    etag == EXTRA_FIELD_WINZIP_AES
                    and esize >= min_aes_extra_size
                    and epos + 4 + esize <= len(extra_to_search)
                ):
                    _, _, _, extra_method = struct.unpack(
                        "<H2sBH", extra_to_search[epos + 4 : epos + 11]
                    )
                    break
                epos += 4 + esize

            salt = entry_data[:16]
            stored_pwd_verify = entry_data[16:18]
            ciphertext = entry_data[18:-10]
            stored_auth_tag = entry_data[-10:]

            # Try SHA-256 derivation first, then fallback to SHA-1 for compatibility
            matched = False
            aes_key: bytearray | None = None
            hmac_key: bytearray | None = None
            try:
                for use_sha256 in (True, False):
                    ak, hk, pv = _derive_keys(password, salt, use_sha256=use_sha256)
                    if pv == stored_pwd_verify:
                        aes_key = ak
                        hmac_key = hk
                        matched = True
                        break
                    zeroize(ak, hk)

                if not matched or aes_key is None or hmac_key is None:
                    msg = "Incorrect ZIP password or corrupt verification code"
                    raise InvalidPasswordError(msg)

                # Verify HMAC
                h = hmac.new(
                    bytes(hmac_key),
                    ciphertext,
                    "sha256" if len(hmac_key) == sha256_key_len else "sha1",
                )
                computed_tag = h.digest()[:10]
                if not hmac.compare_digest(computed_tag, stored_auth_tag):
                    msg = "HMAC integrity authentication failed (corrupt data or wrong password)"
                    raise InvalidPasswordError(msg)

                # Decrypt
                compressed = _ctr_crypt(ciphertext, bytes(aes_key))

                # Decompress
                if extra_method == COMPRESSION_STORED:
                    content = compressed
                elif extra_method == COMPRESSION_DEFLATED:
                    decomp = zlib.decompressobj(wbits=-15)
                    content = decomp.decompress(compressed)
                else:
                    msg = (
                        "Unsupported AES-256 password-protected ZIP (method 99) "
                        f"compression method: {extra_method}"
                    )
                    raise CorruptZipError(msg)
            finally:
                if aes_key is not None:
                    zeroize(aes_key)
                if hmac_key is not None:
                    zeroize(hmac_key)

        # Enforce Zip-Bomb guards
        if len(content) > MAX_UNCOMPRESSED_SIZE:
            msg = (
                f"Uncompressed size for '{clean_name}' exceeds "
                f"{MAX_UNCOMPRESSED_SIZE} bytes (got {len(content)})"
            )
            raise ZipBombError(msg)
        if len(entry_data) > 0 and (len(content) / len(entry_data)) > MAX_COMPRESSION_RATIO:
            msg = f"Compression ratio for '{clean_name}' exceeds {MAX_COMPRESSION_RATIO} ceiling"
            raise ZipBombError(msg)

        extracted[clean_name] = content

    return extracted
