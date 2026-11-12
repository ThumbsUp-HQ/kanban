"""Unit tests for streaming chunked AEAD backup encryption and decryption."""

from __future__ import annotations

import io
import os
import struct

import pytest

from kanban.ops.backup_crypto import (
    CHUNK_SIZE,
    FRAME_HEADER_LENGTH,
    HEADER_LENGTH,
    MAGIC,
    BackupCryptoError,
    BackupIntegrityError,
    PassphraseKeySource,
    RawKeySource,
    decode_raw_key,
    decrypt_stream,
    encrypt_stream,
)


def test_decode_raw_key_validations() -> None:
    """Test raw key decoding from binary and base64url strings."""
    raw_32 = os.urandom(32)
    assert decode_raw_key(raw_32) == raw_32

    # base64url string
    b64_str = "abcdefghijklmnopqrstuvwxyz0123456789-_ABCDE"[:43]
    decoded = decode_raw_key(b64_str)
    assert len(decoded) == 32

    with pytest.raises(BackupCryptoError):
        decode_raw_key(b"too_short")

    with pytest.raises(BackupCryptoError, match="must be 32 bytes or valid base64url string"):
        decode_raw_key(b"\xff\xfe\xfd")

    with pytest.raises(BackupCryptoError, match="Failed to decode base64url key"):
        decode_raw_key("invalid@#$characters!!!")

    with pytest.raises(BackupCryptoError, match="Decoded key length is"):
        decode_raw_key("YWJj")  # 'abc' in base64, 3 bytes


def test_key_source_implementations() -> None:
    """Test RawKeySource and PassphraseKeySource behaviors and error handling."""
    raw_key = os.urandom(32)
    raw_src = RawKeySource(raw_key)
    assert raw_src.default_kdf_mode == 0x01
    assert len(raw_src.get_salt()) == 16
    assert raw_src.resolve_key(0x01, b"") == raw_key

    with pytest.raises(BackupCryptoError, match="requires KDF mode"):
        raw_src.resolve_key(0x02, b"")

    pass_src = PassphraseKeySource(
        "operator-secret-passphrase",
        memory_cost=1024,
        time_cost=1,
        parallelism=1,
    )
    assert pass_src.default_kdf_mode == 0x02
    salt = pass_src.get_salt()
    derived = pass_src.resolve_key(0x02, salt)
    assert len(derived) == 32

    with pytest.raises(BackupCryptoError, match="requires KDF mode"):
        pass_src.resolve_key(0x01, salt)

    # Passphrase as raw bytes
    pass_bytes_src = PassphraseKeySource(
        b"raw-bytes-passphrase",
        memory_cost=1024,
        time_cost=1,
        parallelism=1,
    )
    assert len(pass_bytes_src.resolve_key(0x02, salt)) == 32


def test_empty_stream_encryption_roundtrip() -> None:
    """Test encrypting and decrypting an empty input stream."""
    raw_key = os.urandom(32)
    key_src = RawKeySource(raw_key)

    in_f = io.BytesIO(b"")
    enc_f = io.BytesIO()
    plain_bytes = encrypt_stream(in_f, enc_f, key_src)
    assert plain_bytes == 0

    enc_f.seek(0)
    out_f = io.BytesIO()
    dec_bytes = decrypt_stream(enc_f, out_f, key_src)
    assert dec_bytes == 0
    assert out_f.getvalue() == b""


def test_multichunk_streaming_roundtrip() -> None:
    """Test multi-chunk (> 9 MiB = 3 chunks) encryption round-trip."""
    raw_key = os.urandom(32)
    key_src = RawKeySource(raw_key)

    # Synthetic payload: 2 full chunks (4 MiB each) + 1 partial chunk (1 MiB) = 9 MiB
    chunk_1 = b"A" * CHUNK_SIZE
    chunk_2 = b"B" * CHUNK_SIZE
    chunk_3 = b"C" * (1024 * 1024)
    original_data = chunk_1 + chunk_2 + chunk_3

    in_f = io.BytesIO(original_data)
    enc_f = io.BytesIO()
    plain_bytes = encrypt_stream(in_f, enc_f, key_src)
    assert plain_bytes == len(original_data)

    enc_f.seek(0)
    out_f = io.BytesIO()
    dec_bytes = decrypt_stream(enc_f, out_f, key_src)
    assert dec_bytes == len(original_data)
    assert out_f.getvalue() == original_data


def test_passphrase_multichunk_roundtrip() -> None:
    """Test multi-chunk encryption round-trip using Argon2id passphrase."""
    pass_src = PassphraseKeySource(
        "strong-production-passphrase",
        memory_cost=2048,
        time_cost=1,
        parallelism=1,
    )

    data = b"Testing Argon2id streaming" * 200000  # ~5.2 MB -> 2 chunks
    in_f = io.BytesIO(data)
    enc_f = io.BytesIO()
    encrypt_stream(in_f, enc_f, pass_src)

    enc_f.seek(0)
    out_f = io.BytesIO()
    dec_bytes = decrypt_stream(enc_f, out_f, pass_src)
    assert dec_bytes == len(data)
    assert out_f.getvalue() == data


def test_tamper_defense_bit_flip() -> None:
    """Flipping 1 bit in ciphertext raises BackupIntegrityError."""
    raw_key = os.urandom(32)
    key_src = RawKeySource(raw_key)

    data = b"Sensitive payload needing tamper protection" * 1000
    in_f = io.BytesIO(data)
    enc_f = io.BytesIO()
    encrypt_stream(in_f, enc_f, key_src)

    raw_archive = bytearray(enc_f.getvalue())
    # Flip bit in ciphertext payload (past header and frame header)
    flip_index = HEADER_LENGTH + FRAME_HEADER_LENGTH + 10
    raw_archive[flip_index] ^= 0x01

    tampered_f = io.BytesIO(raw_archive)
    out_f = io.BytesIO()
    with pytest.raises(BackupIntegrityError, match="Cryptographic authentication failed"):
        decrypt_stream(tampered_f, out_f, key_src)


def test_tamper_defense_chunk_swap() -> None:
    """Swapping chunk 0 and chunk 1 raises BackupIntegrityError."""
    raw_key = os.urandom(32)
    key_src = RawKeySource(raw_key)

    chunk_1 = b"1" * CHUNK_SIZE
    chunk_2 = b"2" * CHUNK_SIZE
    chunk_3 = b"3" * 1024
    data = chunk_1 + chunk_2 + chunk_3

    in_f = io.BytesIO(data)
    enc_f = io.BytesIO()
    encrypt_stream(in_f, enc_f, key_src)

    archive_bytes = enc_f.getvalue()
    header = archive_bytes[:HEADER_LENGTH]

    # Parse chunk 0
    offset = HEADER_LENGTH
    len_0, _is_final_0 = struct.unpack(">IB", archive_bytes[offset : offset + FRAME_HEADER_LENGTH])
    chunk_0_frame = archive_bytes[offset : offset + FRAME_HEADER_LENGTH + len_0]
    offset += FRAME_HEADER_LENGTH + len_0

    # Parse chunk 1
    len_1, _is_final_1 = struct.unpack(">IB", archive_bytes[offset : offset + FRAME_HEADER_LENGTH])
    chunk_1_frame = archive_bytes[offset : offset + FRAME_HEADER_LENGTH + len_1]
    offset += FRAME_HEADER_LENGTH + len_1

    # Remaining archive (chunk 2)
    remaining = archive_bytes[offset:]

    # Reconstruct with chunk 0 and chunk 1 swapped
    swapped_archive = header + chunk_1_frame + chunk_0_frame + remaining
    swapped_f = io.BytesIO(swapped_archive)
    out_f = io.BytesIO()

    with pytest.raises(BackupIntegrityError, match="Cryptographic authentication failed"):
        decrypt_stream(swapped_f, out_f, key_src)


def test_tamper_defense_truncation() -> None:
    """Truncating the final chunk raises BackupIntegrityError (missing is_final marker)."""
    raw_key = os.urandom(32)
    key_src = RawKeySource(raw_key)

    chunk_1 = b"A" * CHUNK_SIZE
    chunk_2 = b"B" * 1024
    data = chunk_1 + chunk_2

    in_f = io.BytesIO(data)
    enc_f = io.BytesIO()
    encrypt_stream(in_f, enc_f, key_src)

    archive_bytes = enc_f.getvalue()

    # Truncate final chunk completely
    offset = HEADER_LENGTH
    len_0, _ = struct.unpack(">IB", archive_bytes[offset : offset + FRAME_HEADER_LENGTH])
    truncated_archive = archive_bytes[: offset + FRAME_HEADER_LENGTH + len_0]

    trunc_f = io.BytesIO(truncated_archive)
    out_f = io.BytesIO()
    with pytest.raises(BackupIntegrityError, match="missing is_final marker"):
        decrypt_stream(trunc_f, out_f, key_src)


def test_tamper_defense_wrong_key() -> None:
    """Supplying the wrong decryption key raises BackupIntegrityError."""
    key_src_1 = RawKeySource(os.urandom(32))
    key_src_2 = RawKeySource(os.urandom(32))

    data = b"Secret corporate data"
    enc_f = io.BytesIO()
    encrypt_stream(io.BytesIO(data), enc_f, key_src_1)

    enc_f.seek(0)
    out_f = io.BytesIO()
    with pytest.raises(BackupIntegrityError, match="Cryptographic authentication failed"):
        decrypt_stream(enc_f, out_f, key_src_2)


def test_archive_corruptions() -> None:
    """Test header corruptions, truncation, and trailing bytes."""
    raw_key = os.urandom(32)
    key_src = RawKeySource(raw_key)

    # 1. Truncated header
    with pytest.raises(BackupIntegrityError, match="invalid header length"):
        decrypt_stream(io.BytesIO(b"KBBAK"), io.BytesIO(), key_src)

    # 2. Corrupted magic
    bad_magic_hdr = b"BADMAGIC" + os.urandom(HEADER_LENGTH - 8)
    with pytest.raises(BackupIntegrityError, match="Invalid archive header magic"):
        decrypt_stream(io.BytesIO(bad_magic_hdr), io.BytesIO(), key_src)

    # 3. Key source resolution error
    wrong_mode_hdr = MAGIC + bytes([0x03]) + os.urandom(HEADER_LENGTH - len(MAGIC) - 1)
    with pytest.raises(BackupIntegrityError, match="Failed to resolve decryption key"):
        decrypt_stream(io.BytesIO(wrong_mode_hdr), io.BytesIO(), key_src)

    # 4. Incomplete chunk frame header
    data = b"Payload"
    enc_f = io.BytesIO()
    encrypt_stream(io.BytesIO(data), enc_f, key_src)
    full_archive = enc_f.getvalue()
    cut_frame = full_archive[: HEADER_LENGTH + 2]
    with pytest.raises(BackupIntegrityError, match="incomplete chunk frame header"):
        decrypt_stream(io.BytesIO(cut_frame), io.BytesIO(), key_src)

    # 5. Incomplete chunk ciphertext
    cut_cipher = full_archive[: len(full_archive) - 4]
    with pytest.raises(BackupIntegrityError, match="incomplete chunk ciphertext"):
        decrypt_stream(io.BytesIO(cut_cipher), io.BytesIO(), key_src)

    # 6. Trailing bytes after final chunk
    trailing_archive = full_archive + b"TRAILING_JUNK"
    with pytest.raises(BackupIntegrityError, match="Trailing unexpected bytes"):
        decrypt_stream(io.BytesIO(trailing_archive), io.BytesIO(), key_src)
