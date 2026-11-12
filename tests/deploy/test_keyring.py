"""Unit tests for deploy.standalone.keyring module.

Covers:
- First boot atomic creation with permissions 0600 / 0700 and 5 distinct CSPRNG keys.
- Second boot idempotent reuse without mutation.
- Fail-closed security validations (permissions, symlinks, size limits, schema/fields, lengths).
- Omit secrets from repr and str.
- RFC 7677 SCRAM-SHA-256 test vectors.
- Race conditions during atomic creation.
"""

from __future__ import annotations

import base64
import json
import stat
from typing import TYPE_CHECKING

import pytest

from deploy.standalone.keyring import (
    KEYRING_DIR_MODE,
    KEYRING_FILE_MODE,
    Keyring,
    KeyringError,
    compute_scram_sha256_verifier,
    load_or_create_keyring,
)

if TYPE_CHECKING:
    from pathlib import Path


def _decode_b64url(s: str) -> bytes:
    padding = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + padding).encode("ascii"))


# -----------------------------------------------------------------------------
# Case 1: First boot generation & second boot reuse
# -----------------------------------------------------------------------------
def test_case_1_first_boot_creation_and_reuse(tmp_path: Path) -> None:
    """First boot generates 5 distinct 32-byte keys with 0600 file and 0700 dir."""
    keyring_path = tmp_path / "secrets" / "keyring.json"

    # First boot: creates file
    keyring1 = load_or_create_keyring(keyring_path)
    assert keyring_path.is_file()

    # Verify directory permissions 0700
    dir_stat = keyring_path.parent.stat()
    assert stat.S_IMODE(dir_stat.st_mode) == KEYRING_DIR_MODE

    # Verify file permissions 0600
    file_stat = keyring_path.stat()
    assert stat.S_IMODE(file_stat.st_mode) == KEYRING_FILE_MODE

    # Verify 5 distinct keys, each 32 bytes
    keys = [
        keyring1.master_kek,
        keyring1.auth_pepper,
        keyring1.session_hmac_key,
        keyring1.kanban_app_password,
        keyring1.kanban_migrator_password,
    ]
    for k in keys:
        assert isinstance(k, bytes)
        assert len(k) == 32
    assert len(set(keys)) == 5

    # Verify base64 representations
    assert len(_decode_b64url(keyring1.master_kek_b64)) == 32
    assert len(_decode_b64url(keyring1.auth_pepper_b64)) == 32
    assert len(_decode_b64url(keyring1.session_hmac_key_b64)) == 32
    assert len(keyring1.kanban_app_password_str) > 0
    assert len(keyring1.kanban_migrator_password_str) > 0

    # Record mtime and content
    orig_content = keyring_path.read_bytes()
    orig_mtime_ns = file_stat.st_mtime_ns

    # Second boot: reuses existing without mutation
    keyring2 = load_or_create_keyring(keyring_path)
    assert keyring2.master_kek == keyring1.master_kek
    assert keyring2.auth_pepper == keyring1.auth_pepper
    assert keyring2.session_hmac_key == keyring1.session_hmac_key
    assert keyring2.kanban_app_password == keyring1.kanban_app_password
    assert keyring2.kanban_migrator_password == keyring1.kanban_migrator_password

    # Confirm file was not rewritten
    new_stat = keyring_path.stat()
    assert new_stat.st_mtime_ns == orig_mtime_ns
    assert keyring_path.read_bytes() == orig_content


# -----------------------------------------------------------------------------
# Case 2: Negative fail-closed validation tests
# -----------------------------------------------------------------------------
def test_case_2_insecure_file_permissions_rejected(tmp_path: Path) -> None:
    """Group-readable or world-readable permissions raise KeyringError."""
    keyring_path = tmp_path / "secrets" / "keyring.json"
    load_or_create_keyring(keyring_path)

    # Insecure file mode 0644
    keyring_path.chmod(0o644)
    with pytest.raises(KeyringError, match="must have mode 0600"):
        load_or_create_keyring(keyring_path)

    # Insecure file mode 0660
    keyring_path.chmod(0o660)
    with pytest.raises(KeyringError, match="must have mode 0600"):
        load_or_create_keyring(keyring_path)


def test_case_2_insecure_parent_dir_permissions_rejected(tmp_path: Path) -> None:
    """Group-writable or world-writable parent directory raises KeyringError."""
    keyring_path = tmp_path / "secrets" / "keyring.json"
    load_or_create_keyring(keyring_path)

    keyring_path.parent.chmod(0o777)
    with pytest.raises(KeyringError, match="must have mode 0700"):
        load_or_create_keyring(keyring_path)


def test_case_2_symlink_rejected(tmp_path: Path) -> None:
    """Symlink target raises KeyringError."""
    real_target = tmp_path / "real_keyring.json"
    load_or_create_keyring(real_target)

    link_path = tmp_path / "secrets" / "link_keyring.json"
    link_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    link_path.symlink_to(real_target)

    with pytest.raises(KeyringError, match="must not be a symlink"):
        load_or_create_keyring(link_path)


def test_case_2_truncated_or_invalid_json_rejected(tmp_path: Path) -> None:
    """Truncated or invalid JSON content raises KeyringError."""
    keyring_path = tmp_path / "secrets" / "keyring.json"
    keyring_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    keyring_path.write_bytes(b'{"version": 1, "created_at":')
    keyring_path.chmod(KEYRING_FILE_MODE)

    with pytest.raises(KeyringError, match="contains invalid JSON"):
        load_or_create_keyring(keyring_path)


def test_case_2_json_root_not_dict_rejected(tmp_path: Path) -> None:
    """JSON root that is not a dictionary raises KeyringError."""
    keyring_path = tmp_path / "secrets" / "keyring.json"
    keyring_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    keyring_path.write_bytes(b'["not", "a", "dict"]')
    keyring_path.chmod(KEYRING_FILE_MODE)

    with pytest.raises(KeyringError, match="must be an object"):
        load_or_create_keyring(keyring_path)


def test_case_2_oversized_file_rejected(tmp_path: Path) -> None:
    """Files exceeding 64 KiB are rejected fail-closed."""
    keyring_path = tmp_path / "secrets" / "keyring.json"
    keyring_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    huge_data = b" " * 70000
    keyring_path.write_bytes(huge_data)
    keyring_path.chmod(KEYRING_FILE_MODE)

    with pytest.raises(KeyringError, match="exceeds maximum size"):
        load_or_create_keyring(keyring_path)


def test_case_2_missing_keys_rejected(tmp_path: Path) -> None:
    """Missing required key raises KeyringError."""
    keyring_path = tmp_path / "secrets" / "keyring.json"
    load_or_create_keyring(keyring_path)

    data = json.loads(keyring_path.read_text(encoding="utf-8"))
    del data["KB_AUTH_PEPPER"]
    keyring_path.write_text(json.dumps(data), encoding="utf-8")
    keyring_path.chmod(KEYRING_FILE_MODE)

    with pytest.raises(KeyringError, match="Keyring keys mismatch"):
        load_or_create_keyring(keyring_path)


def test_case_2_extra_keys_rejected(tmp_path: Path) -> None:
    """Unexpected additional keys raise KeyringError."""
    keyring_path = tmp_path / "secrets" / "keyring.json"
    load_or_create_keyring(keyring_path)

    data = json.loads(keyring_path.read_text(encoding="utf-8"))
    data["extra_backdoor"] = "malicious"
    keyring_path.write_text(json.dumps(data), encoding="utf-8")
    keyring_path.chmod(KEYRING_FILE_MODE)

    with pytest.raises(KeyringError, match="Keyring keys mismatch"):
        load_or_create_keyring(keyring_path)


def test_case_2_invalid_secret_length_rejected(tmp_path: Path) -> None:
    """Secrets decoded to length other than 32 bytes raise KeyringError."""
    keyring_path = tmp_path / "secrets" / "keyring.json"
    load_or_create_keyring(keyring_path)

    data = json.loads(keyring_path.read_text(encoding="utf-8"))
    data["MASTER_KEK"] = base64.urlsafe_b64encode(b"short").decode("ascii").rstrip("=")
    keyring_path.write_text(json.dumps(data), encoding="utf-8")
    keyring_path.chmod(KEYRING_FILE_MODE)

    with pytest.raises(KeyringError, match="decoded to 5 bytes"):
        load_or_create_keyring(keyring_path)


def test_case_2_corrupted_base64_rejected(tmp_path: Path) -> None:
    """Non-base64 characters in secret fields raise KeyringError."""
    keyring_path = tmp_path / "secrets" / "keyring.json"
    load_or_create_keyring(keyring_path)

    data = json.loads(keyring_path.read_text(encoding="utf-8"))
    data["MASTER_KEK"] = "===not!valid!base64==="
    keyring_path.write_text(json.dumps(data), encoding="utf-8")
    keyring_path.chmod(KEYRING_FILE_MODE)

    with pytest.raises(KeyringError, match="is not valid base64url"):
        load_or_create_keyring(keyring_path)


def test_case_2_unsupported_version_rejected(tmp_path: Path) -> None:
    """Versions other than 1 raise KeyringError."""
    keyring_path = tmp_path / "secrets" / "keyring.json"
    load_or_create_keyring(keyring_path)

    data = json.loads(keyring_path.read_text(encoding="utf-8"))
    data["version"] = 2
    keyring_path.write_text(json.dumps(data), encoding="utf-8")
    keyring_path.chmod(KEYRING_FILE_MODE)

    with pytest.raises(KeyringError, match="Unsupported keyring version"):
        load_or_create_keyring(keyring_path)


def test_case_2_invalid_created_at_or_db_roles(tmp_path: Path) -> None:
    """Invalid created_at type or db_roles schema raises KeyringError."""
    keyring_path = tmp_path / "secrets" / "keyring.json"
    load_or_create_keyring(keyring_path)

    data = json.loads(keyring_path.read_text(encoding="utf-8"))
    data["created_at"] = 12345
    keyring_path.write_text(json.dumps(data), encoding="utf-8")
    keyring_path.chmod(KEYRING_FILE_MODE)

    with pytest.raises(KeyringError, match="must be an ISO-8601 string"):
        load_or_create_keyring(keyring_path)

    data["created_at"] = "2026-01-01T00:00:00Z"
    data["db_roles"] = {"kanban_app": "foo"}  # missing kanban_migrator
    keyring_path.write_text(json.dumps(data), encoding="utf-8")
    keyring_path.chmod(KEYRING_FILE_MODE)

    with pytest.raises(KeyringError, match="Keyring db_roles mismatch"):
        load_or_create_keyring(keyring_path)


# -----------------------------------------------------------------------------
# Case 3: Redacted representation & RFC 7677 test vector
# -----------------------------------------------------------------------------
def test_case_3_repr_and_str_are_redacted() -> None:
    """Keyring __repr__ and __str__ must never disclose secret bytes or b64."""
    secret = b"\xaa" * 32
    secret_b64 = base64.urlsafe_b64encode(secret).decode("ascii")

    kr = Keyring(
        version=1,
        created_at="2026-11-11T20:00:00Z",
        master_kek=secret,
        auth_pepper=secret,
        session_hmac_key=secret,
        kanban_app_password=secret,
        kanban_migrator_password=secret,
    )

    r = repr(kr)
    s = str(kr)

    assert secret_b64 not in r
    assert secret_b64 not in s
    assert r == "Keyring(<redacted>)"
    assert s == "Keyring(<redacted>)"


def test_case_3_rfc_7677_scram_sha256_test_vector() -> None:
    """Validate SCRAM-SHA-256 verifier against RFC 7677 Section 3 test vector."""
    # RFC 7677 Section 3 test vector: password 'pencil', salt 'W22ZaJ0SNY7soEsUEjb6gQ=='
    salt_bytes = base64.b64decode("W22ZaJ0SNY7soEsUEjb6gQ==")
    verifier = compute_scram_sha256_verifier(
        b"pencil",
        salt=salt_bytes,
        iterations=4096,
    )

    expected = (
        "SCRAM-SHA-256$4096:W22ZaJ0SNY7soEsUEjb6gQ==$"
        "WG5d8oPm3OtcPnkdi4Uo7BkeZkBFzpcXkuLmtbsT4qY=:"
        "wfPLwcE6nTWhTAmQ7tl2KeoiWGPlZqQxSrmfPwDl2dU="
    )
    assert verifier == expected

    # Also test with default random salt
    random_verifier = compute_scram_sha256_verifier("my_secret_password")
    assert random_verifier.startswith("SCRAM-SHA-256$4096:")
    parts = random_verifier.split("$")
    assert len(parts) == 3
    iter_and_salt = parts[1].split(":")
    assert len(iter_and_salt) == 2
    assert iter_and_salt[0] == "4096"
    salt_decoded = base64.b64decode(iter_and_salt[1])
    assert len(salt_decoded) == 16

    keys = parts[2].split(":")
    assert len(keys) == 2
    assert len(base64.b64decode(keys[0])) == 32
    assert len(base64.b64decode(keys[1])) == 32


# -----------------------------------------------------------------------------
# Case 4: Concurrent creation with _before_replace_hook
# -----------------------------------------------------------------------------
def test_case_4_concurrent_creation_race(tmp_path: Path) -> None:
    """When another process creates the keyring before replace, load_or_create reuses it."""
    keyring_path = tmp_path / "secrets" / "keyring.json"

    def simulate_concurrent_creator() -> None:
        """Simulate a competitor process creating the keyring before we replace it."""
        competitor_keyring = load_or_create_keyring(keyring_path)
        assert competitor_keyring is not None
        assert keyring_path.is_file()

    # Call with hook simulating race
    keyring = load_or_create_keyring(
        keyring_path,
        _before_replace_hook=simulate_concurrent_creator,
    )

    # Should have loaded the competitor's keyring without error
    loaded_on_disk = load_or_create_keyring(keyring_path)
    assert keyring.master_kek == loaded_on_disk.master_kek
    assert keyring.auth_pepper == loaded_on_disk.auth_pepper
