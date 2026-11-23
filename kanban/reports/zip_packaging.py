# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""WinZip AE-2 (AES-256) password-protected ZIP archive packaging engine (KAN-317 / KAN-316).

Implements the official WinZip AE-2 specification:
- Compression method 99 (AES encryption wrapper).
- Extra data field 0x9901 with vendor version 2 (AE-2).
- PBKDF2-HMAC-SHA1 1,000-iteration key derivation for 256-bit encryption key,
  256-bit HMAC authentication key, and 2-byte password verification code.
- AES in CTR mode with 128-bit little-endian counter starting at 1.
- HMAC-SHA1 10-byte authentication tag over ciphertext.
- Pure Python implementation with zero GPL/LGPL dependencies (uses cryptography).
"""

from __future__ import annotations

import os
import struct
from typing import Final

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

AE2_EXTRA_FIELD_ID: Final[int] = 0x9901
AE2_SALT_LEN: Final[int] = 16
AE2_PWD_VERIFY_LEN: Final[int] = 2
AE2_AUTH_CODE_LEN: Final[int] = 10
AE2_ITERATIONS: Final[int] = 1000


def create_aes256_zip(
    files_or_filename: list[tuple[str, bytes]] | str,
    password_or_data: str | bytes,
    maybe_password: str | None = None,
) -> bytes:
    """Create a WinZip AE-2 AES-256 password-protected ZIP archive.

    Args:
        files_or_filename: List of (filename, data) tuples or a single filename string.
        password_or_data: Password string for list of files, or bytes if filename was passed.
        maybe_password: Password string if single filename was passed.

    Returns:
        Raw bytes of the valid .zip archive.
    """
    if isinstance(files_or_filename, str):
        fn = files_or_filename
        data = (
            password_or_data
            if isinstance(password_or_data, bytes)
            else str(password_or_data).encode("utf-8")
        )
        password = maybe_password or ""
        entries = [(fn, data)]
    else:
        entries = list(files_or_filename)
        password = str(password_or_data)

    if not password:
        raise ValueError("Password cannot be empty for AES-256 ZIP packaging.")

    pw_bytes = password.encode("utf-8")
    body = bytearray()
    cd_records = bytearray()

    for fn, data in entries:
        local_offset = len(body)
        salt = os.urandom(AE2_SALT_LEN)

        # Derive 32 bytes encryption key + 32 bytes auth key + 2 bytes verification code
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA1(),  # WinZip AES standard uses SHA-1 for PBKDF2
            length=66,
            salt=salt,
            iterations=AE2_ITERATIONS,
            backend=default_backend(),
        )
        keys = kdf.derive(pw_bytes)
        enc_key = keys[:32]
        auth_key = keys[32:64]
        pwd_verify = keys[64:66]

        # WinZip AE-2 counter starts at 1, incremented little-endian block by block
        aes_ecb = Cipher(algorithms.AES(enc_key), modes.ECB(), default_backend()).encryptor()

        ciphertext = bytearray()
        counter = 1
        for i in range(0, len(data), 16):
            block = data[i : i + 16]
            cnt_block = counter.to_bytes(16, byteorder="little")
            keystream = aes_ecb.update(cnt_block)
            ciphertext.extend(b ^ k for b, k in zip(block, keystream[: len(block)]))
            counter += 1

        h = hmac.HMAC(auth_key, hashes.SHA1(), default_backend())
        h.update(ciphertext)
        auth_code = h.finalize()[:AE2_AUTH_CODE_LEN]

        payload = salt + pwd_verify + bytes(ciphertext) + auth_code
        comp_size = len(payload)
        uncomp_size = len(data)
        fn_bytes = fn.encode("utf-8")

        # Extra field 0x9901:
        # 2 bytes vendor version (2 for AE-2)
        # 2 bytes vendor ID ("AE")
        # 1 byte strength (3 = 256-bit)
        # 2 bytes actual compression method (0 = Stored)
        extra_field_data = struct.pack("<H2sBH", 2, b"AE", 3, 0)
        extra_field_hdr = struct.pack("<HH", AE2_EXTRA_FIELD_ID, len(extra_field_data))
        extra_field = extra_field_hdr + extra_field_data

        # Local file header
        lfh = (
            struct.pack(
                "<IHHHHHIIIHH",
                0x04034B50,  # Signature
                51,  # Version needed (5.1 for AES)
                1,  # General purpose flag (bit 0 = encrypted)
                99,  # Compression method 99 (AES encryption)
                0,
                0,  # File time, date
                0,  # CRC-32 (0 for AE-2)
                comp_size,
                uncomp_size,
                len(fn_bytes),
                len(extra_field),
            )
            + fn_bytes
            + extra_field
        )
        body.extend(lfh)
        body.extend(payload)

        # Central directory header
        cdh = (
            struct.pack(
                "<IHHHHHHIIIHHHHHII",
                0x02014B50,  # Signature
                0x0333,  # Version made by (Unix 5.1)
                51,  # Version needed
                1,  # Flags (encrypted)
                99,  # Method
                0,
                0,  # File time, date
                0,  # CRC-32
                comp_size,
                uncomp_size,
                len(fn_bytes),
                len(extra_field),
                0,  # Comment len
                0,  # Disk start
                0,  # Internal file attributes
                0o100644 << 16,  # External file attributes (-rw-r--r--)
                local_offset,  # Relative offset of local header
            )
            + fn_bytes
            + extra_field
        )
        cd_records.extend(cdh)

    cd_offset = len(body)
    cd_size = len(cd_records)
    total_entries = len(entries)

    # End of central directory record
    eocd = struct.pack(
        "<IHHHHIIH",
        0x06054B50,  # Signature
        0,
        0,  # Disk number, disk with CD
        total_entries,
        total_entries,  # Entries on disk, total entries
        cd_size,
        cd_offset,
        0,  # Comment length
    )

    return bytes(body + cd_records + eocd)


def read_aes256_zip(
    zip_bytes: bytes,
    password: str,
) -> dict[str, bytes]:
    """Parse and decrypt files from a WinZip AE-2 AES-256 ZIP archive.

    Args:
        zip_bytes: Raw bytes of the encrypted .zip archive.
        password: Password used for decryption.

    Returns:
        Dictionary mapping filename to decrypted byte contents.

    Raises:
        ValueError: If archive format is invalid or password verification fails.
    """
    if len(zip_bytes) < 22:
        raise ValueError("Invalid ZIP file: header too short.")

    # Locate End of Central Directory signature (0x06054B50)
    eocd_idx = zip_bytes.rfind(b"\x50\x4b\x05\x06")
    if eocd_idx == -1 or len(zip_bytes) - eocd_idx < 22:
        raise ValueError("Invalid ZIP file: missing end of central directory signature.")

    (
        _sig,
        _disk,
        _cd_disk,
        _disk_entries,
        total_entries,
        _cd_size,
        cd_offset,
        _comment_len,
    ) = struct.unpack("<IHHHHIIH", zip_bytes[eocd_idx : eocd_idx + 22])

    pw_bytes = password.encode("utf-8")
    results: dict[str, bytes] = {}

    cd_ptr = cd_offset
    for _ in range(total_entries):
        if cd_ptr + 46 > len(zip_bytes):
            break
        sig = struct.unpack("<I", zip_bytes[cd_ptr : cd_ptr + 4])[0]
        if sig != 0x02014B50:
            break

        (
            _cd_sig,
            _ver_made,
            _ver_need,
            flags,
            method,
            _time,
            _date,
            _crc,
            comp_size,
            uncomp_size,
            fn_len,
            extra_len,
            comment_len,
            _disk_start,
            _int_attr,
            _ext_attr,
            local_offset,
        ) = struct.unpack("<IHHHHHHIIIHHHHHII", zip_bytes[cd_ptr : cd_ptr + 46])

        if method != 99 or (flags & 1) == 0:
            raise ValueError("Archive is not encrypted with WinZip AES (method 99).")

        fn_start = cd_ptr + 46
        filename = zip_bytes[fn_start : fn_start + fn_len].decode("utf-8")
        cd_ptr += 46 + fn_len + extra_len + comment_len

        meta = (local_offset, comp_size, uncomp_size, filename)
        results[filename] = _decrypt_single_entry(zip_bytes, meta, pw_bytes)

    return results


def _decrypt_single_entry(
    zip_bytes: bytes,
    meta: tuple[int, int, int, str],
    pw_bytes: bytes,
) -> bytes:
    """Validate headers, verify HMAC auth code, and decrypt payload for one ZIP entry."""
    local_offset, comp_size, uncomp_size, filename = meta
    if local_offset + 30 > len(zip_bytes):
        raise ValueError(f"Corrupt ZIP: local header out of bounds for {filename}")

    loc_sig, _v, _f, _m, _t, _d, _c, _l_comp, _l_uncomp, l_fn_len, l_extra_len = (
        struct.unpack("<IHHHHHIIIHH", zip_bytes[local_offset : local_offset + 30])
    )
    if loc_sig != 0x04034B50:
        raise ValueError(f"Corrupt ZIP: invalid local header signature for {filename}")

    payload_start = local_offset + 30 + l_fn_len + l_extra_len
    payload = zip_bytes[payload_start : payload_start + comp_size]
    if len(payload) < AE2_SALT_LEN + AE2_PWD_VERIFY_LEN + AE2_AUTH_CODE_LEN:
        raise ValueError(f"Payload too short for {filename}")

    salt = payload[:AE2_SALT_LEN]
    pwd_verify_in = payload[AE2_SALT_LEN : AE2_SALT_LEN + AE2_PWD_VERIFY_LEN]
    ciphertext = payload[
        AE2_SALT_LEN + AE2_PWD_VERIFY_LEN : len(payload) - AE2_AUTH_CODE_LEN
    ]
    auth_code_in = payload[len(payload) - AE2_AUTH_CODE_LEN :]

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA1(),
        length=66,
        salt=salt,
        iterations=AE2_ITERATIONS,
        backend=default_backend(),
    )
    keys = kdf.derive(pw_bytes)
    enc_key = keys[:32]
    auth_key = keys[32:64]
    pwd_verify = keys[64:66]

    if pwd_verify != pwd_verify_in:
        raise ValueError("Incorrect password for AES-256 ZIP archive.")

    h = hmac.HMAC(auth_key, hashes.SHA1(), default_backend())
    h.update(ciphertext)
    auth_code_calc = h.finalize()[:AE2_AUTH_CODE_LEN]
    if auth_code_calc != auth_code_in:
        raise ValueError("Authentication code verification failed (data corrupted or tampered).")

    aes_ecb = Cipher(algorithms.AES(enc_key), modes.ECB(), default_backend()).encryptor()
    plaintext = bytearray()
    counter = 1
    for i in range(0, len(ciphertext), 16):
        block = ciphertext[i : i + 16]
        cnt_block = counter.to_bytes(16, byteorder="little")
        keystream = aes_ecb.update(cnt_block)
        plaintext.extend(b ^ k for b, k in zip(block, keystream[: len(block)]))
        counter += 1

    return bytes(plaintext)[:uncomp_size]
