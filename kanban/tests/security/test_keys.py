"""Unit tests for cryptographic key material provider and HKDF derivation (S2.2)."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from kanban.security.keys import (
    KEY_LENGTH_BYTES,
    KeyMaterial,
    KeyMaterialError,
    _decode_b64url_key,
    derive_subkey,
    load_key_material,
)

if TYPE_CHECKING:
    from pathlib import Path


def _b64url(data: bytes) -> str:
    """Encode bytes to unpadded base64url string."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def test_decode_b64url_key_valid() -> None:
    """Test decoding valid 32-byte keys with and without padding."""
    raw = b"0123456789abcdef0123456789abcdef"
    encoded = _b64url(raw)
    assert _decode_b64url_key(encoded, "test") == raw

    # With padding
    padded = base64.urlsafe_b64encode(raw).decode("ascii")
    assert _decode_b64url_key(padded, "test") == raw


def test_decode_b64url_key_invalid() -> None:
    """Test rejection of non-string, empty, corrupt, or invalid length keys."""
    with pytest.raises(KeyMaterialError, match="must be a non-empty string"):
        _decode_b64url_key("", "test")

    with pytest.raises(KeyMaterialError, match="must be a non-empty string"):
        _decode_b64url_key(12345, "test")

    with pytest.raises(KeyMaterialError, match="Failed to decode base64url"):
        _decode_b64url_key("???not-valid-base64???", "test")

    short_key = _b64url(b"too_short")
    with pytest.raises(KeyMaterialError, match="must be exactly 32 bytes"):
        _decode_b64url_key(short_key, "test")


def test_case_11_keyring_file_valid_and_repr(tmp_path: Path) -> None:
    """Test Case 11: Valid keyring file loads and repr masks all key material."""
    kek = b"k" * 32
    pepper = b"p" * 32
    hmac_key = b"h" * 32

    keyring_data = {
        "MASTER_KEK": _b64url(kek),
        "KB_AUTH_PEPPER": _b64url(pepper),
        "SESSION_HMAC_KEY": _b64url(hmac_key),
        "MASTER_KEK_KID": "kek-v2",
    }
    keyring_file = tmp_path / "keyring.json"
    keyring_file.write_text(json.dumps(keyring_data), encoding="utf-8")
    keyring_file.chmod(0o600)

    km = load_key_material(keyring_file=keyring_file)
    assert km.master_kek == kek
    assert km.auth_pepper == pepper
    assert km.session_hmac_key == hmac_key
    assert km.master_kek_kid == "kek-v2"

    # Representation check: must be strictly KeyMaterial(<redacted>)
    rep = repr(km)
    assert rep == "KeyMaterial(<redacted>)"
    assert _b64url(kek) not in rep
    assert _b64url(pepper) not in rep
    assert _b64url(hmac_key) not in rep
    assert "kek" not in rep or rep == "KeyMaterial(<redacted>)"


def test_case_11_file_mode_0644_rejected(tmp_path: Path) -> None:
    """Test Case 11: File mode 0644 raises KeyMaterialError."""
    keyring_file = tmp_path / "insecure_keyring.json"
    keyring_file.write_text(
        json.dumps(
            {
                "MASTER_KEK": _b64url(b"k" * 32),
                "KB_AUTH_PEPPER": _b64url(b"p" * 32),
                "SESSION_HMAC_KEY": _b64url(b"h" * 32),
            }
        ),
        encoding="utf-8",
    )
    keyring_file.chmod(0o644)

    with pytest.raises(KeyMaterialError, match="too permissive"):
        load_key_material(keyring_file=keyring_file)


def test_case_11_symlink_keyring_rejected(tmp_path: Path) -> None:
    """Test Case 11: Symlinked keyring file raises KeyMaterialError."""
    real_file = tmp_path / "real_keyring.json"
    real_file.write_text(
        json.dumps(
            {
                "MASTER_KEK": _b64url(b"k" * 32),
                "KB_AUTH_PEPPER": _b64url(b"p" * 32),
                "SESSION_HMAC_KEY": _b64url(b"h" * 32),
            }
        ),
        encoding="utf-8",
    )
    real_file.chmod(0o600)

    symlink_file = tmp_path / "symlink_keyring.json"
    symlink_file.symlink_to(real_file)

    with pytest.raises(KeyMaterialError, match="must not be a symlink"):
        load_key_material(keyring_file=symlink_file)


def test_case_11_31_byte_key_rejected(tmp_path: Path) -> None:
    """Test Case 11: 31-byte key in keyring or direct constructor raises KeyMaterialError."""
    key_31 = b"x" * 31
    with pytest.raises(KeyMaterialError, match="master_kek must be exactly 32 bytes"):
        KeyMaterial(master_kek=key_31, auth_pepper=b"p" * 32, session_hmac_key=b"h" * 32)

    with pytest.raises(KeyMaterialError, match="auth_pepper must be exactly 32 bytes"):
        KeyMaterial(master_kek=b"k" * 32, auth_pepper=key_31, session_hmac_key=b"h" * 32)

    with pytest.raises(KeyMaterialError, match="session_hmac_key must be exactly 32 bytes"):
        KeyMaterial(master_kek=b"k" * 32, auth_pepper=b"p" * 32, session_hmac_key=key_31)

    with pytest.raises(KeyMaterialError, match="master_kek_kid must be a non-empty string"):
        KeyMaterial(
            master_kek=b"k" * 32,
            auth_pepper=b"p" * 32,
            session_hmac_key=b"h" * 32,
            master_kek_kid="   ",
        )

    # In file
    bad_file = tmp_path / "bad_31_byte.json"
    bad_file.write_text(
        json.dumps(
            {
                "MASTER_KEK": _b64url(key_31),
                "KB_AUTH_PEPPER": _b64url(b"p" * 32),
                "SESSION_HMAC_KEY": _b64url(b"h" * 32),
            }
        ),
        encoding="utf-8",
    )
    bad_file.chmod(0o600)
    with pytest.raises(KeyMaterialError, match="must be exactly 32 bytes"):
        load_key_material(keyring_file=bad_file)


def test_case_11_no_source_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test Case 11: Absence of all keyring sources raises KeyMaterialError."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.delenv("KANBAN_MASTER_KEK", raising=False)
    monkeypatch.delenv("KANBAN_AUTH_PEPPER", raising=False)
    monkeypatch.delenv("KANBAN_SESSION_HMAC_KEY", raising=False)

    with pytest.raises(KeyMaterialError, match="No valid key material source found"):
        load_key_material()


def test_keyring_file_missing_or_directory(tmp_path: Path) -> None:
    """Test handling of non-existent files, directories, and corrupt JSON."""
    missing = tmp_path / "non_existent.json"
    with pytest.raises(KeyMaterialError, match="does not exist"):
        load_key_material(keyring_file=missing)

    directory = tmp_path / "a_dir"
    directory.mkdir()
    with pytest.raises(KeyMaterialError, match="must be a regular file"):
        load_key_material(keyring_file=directory)

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not valid json", encoding="utf-8")
    corrupt.chmod(0o600)
    with pytest.raises(KeyMaterialError, match="Failed to read or parse keyring JSON"):
        load_key_material(keyring_file=corrupt)

    json_array = tmp_path / "array.json"
    json_array.write_text("[]", encoding="utf-8")
    json_array.chmod(0o600)
    with pytest.raises(KeyMaterialError, match="JSON root must be an object"):
        load_key_material(keyring_file=json_array)


def test_keyring_file_missing_fields(tmp_path: Path) -> None:
    """Test rejection when required keys or kid are invalid in keyring JSON."""
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps({"MASTER_KEK": _b64url(b"k" * 32)}), encoding="utf-8")
    partial.chmod(0o600)
    with pytest.raises(KeyMaterialError, match="Missing required key"):
        load_key_material(keyring_file=partial)

    bad_kid = tmp_path / "bad_kid.json"
    bad_kid.write_text(
        json.dumps(
            {
                "MASTER_KEK": _b64url(b"k" * 32),
                "KB_AUTH_PEPPER": _b64url(b"p" * 32),
                "SESSION_HMAC_KEY": _b64url(b"h" * 32),
                "MASTER_KEK_KID": "   ",
            }
        ),
        encoding="utf-8",
    )
    bad_kid.chmod(0o600)
    with pytest.raises(KeyMaterialError, match="MASTER_KEK_KID in keyring file"):
        load_key_material(keyring_file=bad_kid)


def test_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test loading key material directly from environment variables."""
    kek = b"1" * 32
    pepper = b"2" * 32
    session_k = b"3" * 32

    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64url(kek))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64url(pepper))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64url(session_k))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "env-kid-1")

    km = load_key_material()
    assert km.master_kek == kek
    assert km.auth_pepper == pepper
    assert km.session_hmac_key == session_k
    assert km.master_kek_kid == "env-kid-1"


def test_load_from_env_empty_kid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test loading from env with empty kid raises KeyMaterialError."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64url(b"1" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64url(b"2" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64url(b"3" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "   ")

    with pytest.raises(KeyMaterialError, match="KANBAN_MASTER_KEK_KID must be a non-empty string"):
        load_key_material()


def test_case_12_purpose_separation() -> None:
    """Test Case 12: Distinct purposes yield distinct subkeys."""
    k = b"m" * 32
    sub1 = derive_subkey(k, "session/cookie")
    sub2 = derive_subkey(k, "session/csrf")

    assert sub1 != sub2
    assert len(sub1) == KEY_LENGTH_BYTES
    assert len(sub2) == KEY_LENGTH_BYTES
    # Deterministic
    assert derive_subkey(k, "session/cookie") == sub1


def test_case_12_invalid_purpose() -> None:
    """Test Case 12: Invalid purposes raise ValueError."""
    k = b"m" * 32

    invalid_purposes = [
        "Session Cookie",  # uppercase and space
        "invalid purpose",  # space
        "a",  # too short (<3)
        "-invalid-start",  # starts with dash
        ".invalid-start",  # starts with dot
        "UPPERCASE",  # uppercase
        "bad@symbol",  # invalid symbol
        "x" * 65,  # too long (>64)
    ]

    for p in invalid_purposes:
        with pytest.raises(ValueError, match="Invalid subkey purpose"):
            derive_subkey(k, p)


def test_case_12_short_root_key() -> None:
    """Test Case 12: Short root key raises KeyMaterialError."""
    with pytest.raises(KeyMaterialError, match="must be bytes with length >= 16"):
        derive_subkey(b"too_short_root", "session/csrf")


def test_case_12_rfc5869_test_vector_1_primitive_match() -> None:
    """Test Case 12: RFC 5869 Test Case 1 adapted via HKDF primitive matches standard."""
    # Verification using official RFC 5869 Test Case 1 with SHA-256
    ikm = bytes([0x0B] * 22)
    salt = bytes(range(0x0D))
    info = bytes(range(0xF0, 0xFA))
    length = 42
    expected_okm = bytes.fromhex(
        "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865"
    )

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        info=info,
    )
    derived = hkdf.derive(ikm)
    assert derived == expected_okm
