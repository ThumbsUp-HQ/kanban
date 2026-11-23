# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Forensic and unit tests for strict keyring permissions and root-execution checks (KAN-328)."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kanban.cli.ctl import load_ctl_keyring
from kanban.security.envelope import StaticKekProvider
from kanban.security.keys import (
    MAX_KEYRING_FILE_BYTES,
    KeyMaterialError,
    _load_from_keyring_file,
    validate_keyring_file_permissions,
)


def _b64url(raw: bytes) -> str:
    """Encode raw bytes as unpadded base64url string."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _make_keyring_json(
    kek: bytes = b"k" * 32,
    pepper: bytes = b"p" * 32,
    hmac_key: bytes = b"h" * 32,
    kid: str = "kek-v1",
) -> str:
    """Generate canonical keyring JSON string."""
    return json.dumps(
        {
            "MASTER_KEK": _b64url(kek),
            "KB_AUTH_PEPPER": _b64url(pepper),
            "SESSION_HMAC_KEY": _b64url(hmac_key),
            "MASTER_KEK_KID": kid,
        }
    )


def test_keyring_0600_permissions_accepted(tmp_path: Path) -> None:
    """Verify mode 0600 keyring file is valid and loads successfully."""
    keyring_file = tmp_path / "valid_0600.json"
    keyring_file.write_text(_make_keyring_json(), encoding="utf-8")
    keyring_file.chmod(0o600)

    validate_keyring_file_permissions(keyring_file)
    km = _load_from_keyring_file(keyring_file)
    assert km.master_kek == b"k" * 32
    assert km.auth_pepper == b"p" * 32
    assert km.session_hmac_key == b"h" * 32


def test_keyring_0400_permissions_accepted(tmp_path: Path) -> None:
    """Verify mode 0400 (read-only) keyring file is valid and loads successfully."""
    keyring_file = tmp_path / "valid_0400.json"
    keyring_file.write_text(_make_keyring_json(), encoding="utf-8")
    keyring_file.chmod(0o400)

    validate_keyring_file_permissions(keyring_file)
    km = _load_from_keyring_file(keyring_file)
    assert km.master_kek == b"k" * 32


@pytest.mark.parametrize("bad_mode", [0o700, 0o755, 0o777, 0o611, 0o711])
def test_keyring_execute_permission_rejected(tmp_path: Path, bad_mode: int) -> None:
    """Verify keyring files with any execute bits set are rejected."""
    keyring_file = tmp_path / f"exec_{bad_mode:o}.json"
    keyring_file.write_text(_make_keyring_json(), encoding="utf-8")
    keyring_file.chmod(bad_mode)

    with pytest.raises(KeyMaterialError, match="must not have execute permissions"):
        validate_keyring_file_permissions(keyring_file)


@pytest.mark.parametrize("permissive_mode", [0o644, 0o660, 0o664, 0o604, 0o606])
def test_keyring_group_and_other_permissions_rejected(tmp_path: Path, permissive_mode: int) -> None:
    """Verify keyring files accessible to group or others are rejected."""
    keyring_file = tmp_path / f"permissive_{permissive_mode:o}.json"
    keyring_file.write_text(_make_keyring_json(), encoding="utf-8")
    keyring_file.chmod(permissive_mode)

    with pytest.raises(KeyMaterialError, match="too permissive"):
        validate_keyring_file_permissions(keyring_file)


def test_keyring_symlink_rejected(tmp_path: Path) -> None:
    """Verify symlinked keyring files are strictly rejected."""
    real_file = tmp_path / "real.json"
    real_file.write_text(_make_keyring_json(), encoding="utf-8")
    real_file.chmod(0o600)

    symlink_file = tmp_path / "symlink.json"
    symlink_file.symlink_to(real_file)

    with pytest.raises(KeyMaterialError, match="must not be a symlink"):
        validate_keyring_file_permissions(symlink_file)


def test_keyring_directory_rejected(tmp_path: Path) -> None:
    """Verify directory target is rejected as not a regular file."""
    sub_dir = tmp_path / "dir_target"
    sub_dir.mkdir()
    sub_dir.chmod(0o700)

    with pytest.raises(KeyMaterialError, match="must be a regular file"):
        validate_keyring_file_permissions(sub_dir)


def test_keyring_nonexistent_file_rejected(tmp_path: Path) -> None:
    """Verify missing file raises KeyMaterialError."""
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(KeyMaterialError, match="does not exist"):
        validate_keyring_file_permissions(missing)


def test_keyring_file_size_exceeds_cap_rejected(tmp_path: Path) -> None:
    """Verify keyring files exceeding 64 KiB are rejected."""
    oversized = tmp_path / "oversized.json"
    oversized.write_text("x" * (MAX_KEYRING_FILE_BYTES + 1), encoding="utf-8")
    oversized.chmod(0o600)

    with pytest.raises(KeyMaterialError, match="exceeds maximum allowed size"):
        validate_keyring_file_permissions(oversized)


def test_keyring_root_execution_non_root_owner_rejected(tmp_path: Path) -> None:
    """Verify root execution (UID 0) rejects keyring owned by non-root user."""
    keyring_file = tmp_path / "root_test.json"
    keyring_file.write_text(_make_keyring_json(), encoding="utf-8")
    keyring_file.chmod(0o600)

    real_stat = keyring_file.stat()
    mock_stat = MagicMock(
        st_mode=real_stat.st_mode,
        st_size=real_stat.st_size,
        st_uid=1000,
    )

    with (
        patch("os.getuid", return_value=0),
        patch.object(Path, "stat", return_value=mock_stat),
        pytest.raises(
            KeyMaterialError,
            match="Root process cannot load keyring file owned by non-root UID",
        ),
    ):
        validate_keyring_file_permissions(keyring_file)


def test_keyring_root_execution_root_owner_accepted(tmp_path: Path) -> None:
    """Verify root execution (UID 0) accepts keyring owned by root (UID 0)."""
    keyring_file = tmp_path / "root_valid.json"
    keyring_file.write_text(_make_keyring_json(), encoding="utf-8")
    keyring_file.chmod(0o600)

    real_stat = keyring_file.stat()
    mock_stat = MagicMock(
        st_mode=real_stat.st_mode,
        st_size=real_stat.st_size,
        st_uid=0,
    )

    with (
        patch("os.getuid", return_value=0),
        patch.object(Path, "stat", return_value=mock_stat),
    ):
        validate_keyring_file_permissions(keyring_file)


def test_keyring_non_root_execution_foreign_owner_rejected(tmp_path: Path) -> None:
    """Verify unprivileged user (UID 1000) rejects keyring owned by foreign user (UID 2000)."""
    keyring_file = tmp_path / "user_test.json"
    keyring_file.write_text(_make_keyring_json(), encoding="utf-8")
    keyring_file.chmod(0o600)

    real_stat = keyring_file.stat()
    mock_stat = MagicMock(
        st_mode=real_stat.st_mode,
        st_size=real_stat.st_size,
        st_uid=2000,
    )

    with (
        patch("os.getuid", return_value=1000),
        patch.object(Path, "stat", return_value=mock_stat),
        pytest.raises(KeyMaterialError, match="Keyring file owner mismatch"),
    ):
        validate_keyring_file_permissions(keyring_file)


def test_keyring_non_root_execution_own_file_accepted(tmp_path: Path) -> None:
    """Verify unprivileged user (UID 1000) accepts keyring owned by UID 1000."""
    keyring_file = tmp_path / "user_valid.json"
    keyring_file.write_text(_make_keyring_json(), encoding="utf-8")
    keyring_file.chmod(0o600)

    real_stat = keyring_file.stat()
    mock_stat = MagicMock(
        st_mode=real_stat.st_mode,
        st_size=real_stat.st_size,
        st_uid=1000,
    )

    with (
        patch("os.getuid", return_value=1000),
        patch.object(Path, "stat", return_value=mock_stat),
    ):
        validate_keyring_file_permissions(keyring_file)


def test_keyring_parent_directory_world_writable_rejected(tmp_path: Path) -> None:
    """Verify keyring in world-writable directory without sticky bit is rejected."""
    insecure_dir = tmp_path / "insecure_dir"
    insecure_dir.mkdir()
    keyring_file = insecure_dir / "keyring.json"
    keyring_file.write_text(_make_keyring_json(), encoding="utf-8")
    keyring_file.chmod(0o600)
    insecure_dir.chmod(0o777)

    with pytest.raises(KeyMaterialError, match="world-writable without sticky bit"):
        validate_keyring_file_permissions(keyring_file)


def test_keyring_parent_directory_sticky_bit_accepted(tmp_path: Path) -> None:
    """Verify keyring in world-writable directory with sticky bit (like /tmp) is accepted."""
    sticky_dir = tmp_path / "sticky_dir"
    sticky_dir.mkdir()
    keyring_file = sticky_dir / "keyring.json"
    keyring_file.write_text(_make_keyring_json(), encoding="utf-8")
    keyring_file.chmod(0o600)
    sticky_dir.chmod(0o1777)

    validate_keyring_file_permissions(keyring_file)


def test_load_ctl_keyring_accepts_valid_file(tmp_path: Path) -> None:
    """Verify load_ctl_keyring loads valid 0600 keyring file."""
    keyring_file = tmp_path / "ctl_valid.json"
    keyring_file.write_text(_make_keyring_json(), encoding="utf-8")
    keyring_file.chmod(0o600)

    km = load_ctl_keyring(keyring_file)
    assert km.master_kek == b"k" * 32
    assert km.auth_pepper == b"p" * 32
    assert km.session_hmac_key == b"h" * 32


def test_load_ctl_keyring_rejects_insecure_file(tmp_path: Path) -> None:
    """Verify load_ctl_keyring rejects file with mode 0644."""
    insecure_keyring = tmp_path / "ctl_insecure.json"
    insecure_keyring.write_text(_make_keyring_json(), encoding="utf-8")
    insecure_keyring.chmod(0o644)

    with pytest.raises(KeyMaterialError, match="too permissive"):
        load_ctl_keyring(insecure_keyring)


def test_load_ctl_keyring_env_var_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify load_ctl_keyring uses KANBAN_KEYRING_FILE when path argument is None."""
    insecure_keyring = tmp_path / "env_insecure.json"
    insecure_keyring.write_text(_make_keyring_json(), encoding="utf-8")
    insecure_keyring.chmod(0o644)

    monkeypatch.setenv("KANBAN_KEYRING_FILE", str(insecure_keyring))
    with pytest.raises(KeyMaterialError, match="too permissive"):
        load_ctl_keyring()


def test_static_kek_provider_from_keyring_file(tmp_path: Path) -> None:
    """Verify StaticKekProvider.from_keyring_file enforces 0600 permissions."""
    valid_keyring = tmp_path / "kek_valid.json"
    valid_keyring.write_text(_make_keyring_json(), encoding="utf-8")
    valid_keyring.chmod(0o600)

    provider = StaticKekProvider.from_keyring_file(valid_keyring)
    assert provider.current_kid() == "kek-v1"
    assert provider.get("kek-v1") == b"k" * 32

    insecure_keyring = tmp_path / "kek_insecure.json"
    insecure_keyring.write_text(_make_keyring_json(), encoding="utf-8")
    insecure_keyring.chmod(0o644)

    with pytest.raises(KeyMaterialError, match="too permissive"):
        StaticKekProvider.from_keyring_file(insecure_keyring)
