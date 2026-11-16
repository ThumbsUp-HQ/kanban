"""Comprehensive edge-case and branch coverage tests for kanban.ops and kanban.cli.ops.

Targeted tests to ensure >=95% branch and line coverage across:
- kanban.ops.backup_crypto
- kanban.ops.backup_service
- kanban.ops.compose_export
- kanban.cli.ops
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import tarfile
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from kanban.cli.ctl import main as ctl_main
from kanban.cli.ops import (
    _handle_backup_create,
    _handle_backup_verify,
    _handle_promote_compose,
    _handle_restore,
    _resolve_fallback_key_source,
    _resolve_key_source,
    _validate_restore_args,
)
from kanban.cli.ops import (
    main as ops_main,
)
from kanban.ops.backup_crypto import (
    BackupIntegrityError,
    PassphraseKeySource,
    RawKeySource,
)
from kanban.ops.backup_service import (
    BackupError,
    BackupManifest,
    RestoreError,
    RestoreVerificationError,
    TargetDatabaseNotEmptyError,
    _atomic_write_encrypted_tar,
    _execute_pg_dump,
    _execute_pg_restore,
    _inspect_db_metadata,
    _parse_db_conn_params,
    _read_secrets_carryover,
    _restore_attachments,
    _restore_secrets,
    _safe_extract_tar,
    _verify_post_restore_invariants,
    resolve_pg_dump_bin,
    resolve_pg_restore_bin,
    verify_backup,
)
from kanban.ops.compose_export import (
    _load_standalone_keyring,
    export_production_bundle,
)

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

    from sqlalchemy.ext.asyncio import AsyncEngine


def test_backup_manifest_from_dict_and_to_dict() -> None:
    """Test BackupManifest serialization, deserialization, and format validation."""
    data: dict[str, Any] = {
        "format_version": 1,
        "created_at": "2026-11-11T00:00:00Z",
        "alembic_revision": "rev123",
        "pg_server_version": "PostgreSQL 16.2",
        "sha256_pgdump": "abc123sha",
        "sha256_attachments_index": "def456sha",
        "includes_keyring_secrets": True,
        "attachments_count": 5,
    }
    manifest = BackupManifest.from_dict(data)
    assert manifest.format_version == 1
    assert manifest.alembic_revision == "rev123"
    assert manifest.includes_keyring_secrets is True
    assert manifest.attachments_count == 5

    out_dict = manifest.to_dict()
    assert out_dict["format_version"] == 1
    assert out_dict["pg_server_version"] == "PostgreSQL 16.2"

    bad_data = dict(data)
    bad_data["format_version"] = 99
    with pytest.raises(BackupIntegrityError, match="Unsupported backup manifest format_version"):
        BackupManifest.from_dict(bad_data)


def test_pg_bin_resolvers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test resolver functions for pg_dump and pg_restore binaries."""
    dummy_dump = tmp_path / "custom_pg_dump"
    dummy_dump.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    dummy_dump.chmod(0o755)

    dummy_restore = tmp_path / "custom_pg_restore"
    dummy_restore.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    dummy_restore.chmod(0o755)

    monkeypatch.setenv("KB_PG_DUMP_BIN", str(dummy_dump))
    monkeypatch.setenv("KB_PG_RESTORE_BIN", str(dummy_restore))

    assert resolve_pg_dump_bin() == str(dummy_dump)
    assert resolve_pg_restore_bin() == str(dummy_restore)

    monkeypatch.delenv("KB_PG_DUMP_BIN", raising=False)
    monkeypatch.delenv("KB_PG_RESTORE_BIN", raising=False)

    dump_bin = resolve_pg_dump_bin()
    assert dump_bin is not None
    restore_bin = resolve_pg_restore_bin()
    assert restore_bin is not None


def test_parse_db_conn_params() -> None:
    """Test connection argument parsing from various database URL formats."""
    url1 = "postgresql+asyncpg://app_user:secret_pw@dbhost.internal:5433/mydb"
    args, env, dbname = _parse_db_conn_params(url1)
    assert dbname == "mydb"
    assert "-d" in args
    assert "mydb" in args
    assert "-U" in args
    assert "app_user" in args
    assert "-h" in args
    assert "dbhost.internal" in args
    assert "-p" in args
    assert "5433" in args
    assert env["PGPASSWORD"] == "secret_pw"

    url2 = "postgresql://localhost/my_local_db"
    _args2, env2, dbname2 = _parse_db_conn_params(url2)
    assert dbname2 == "my_local_db"
    assert "PGPASSWORD" not in env2

    url3 = "postgresql:///"
    _, _, dbname3 = _parse_db_conn_params(url3)
    assert dbname3 == "postgres"


def test_read_secrets_carryover(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test reading secrets from standalone keyring or environment."""
    keyring_file = tmp_path / "test_keyring.json"
    keyring_file.write_text(
        json.dumps({"MASTER_KEK": "explicit_kek_123", "KB_AUTH_PEPPER": "explicit_pepper_456"}),
        encoding="utf-8",
    )

    secrets = _read_secrets_carryover(keyring_file)
    assert secrets["MASTER_KEK"] == "explicit_kek_123"
    assert secrets["KB_AUTH_PEPPER"] == "explicit_pepper_456"

    bad_keyring = tmp_path / "bad_keyring.json"
    bad_keyring.write_text("invalid json content", encoding="utf-8")
    monkeypatch.delenv("KB_MASTER_KEK_B64", raising=False)
    monkeypatch.delenv("KB_AUTH_PEPPER_B64", raising=False)
    fallback_secrets = _read_secrets_carryover(bad_keyring)
    assert len(fallback_secrets["MASTER_KEK"]) > 10
    assert len(fallback_secrets["KB_AUTH_PEPPER"]) > 10

    none_secrets = _read_secrets_carryover(None)
    assert len(none_secrets["MASTER_KEK"]) > 10

    monkeypatch.setenv("KB_MASTER_KEK_B64", "env_kek_b64")
    monkeypatch.setenv("KB_AUTH_PEPPER_B64", "env_pepper_b64")
    env_secrets = _read_secrets_carryover(None)
    assert env_secrets["MASTER_KEK"] == "env_kek_b64"
    assert env_secrets["KB_AUTH_PEPPER"] == "env_pepper_b64"


def test_safe_extract_tar_security(tmp_path: Path) -> None:
    """Test path-traversal prevention during tar extraction."""
    target_dir = tmp_path / "extract_dest"
    target_dir.mkdir()

    tar_path = tmp_path / "traversal.tar"
    with tarfile.open(tar_path, "w") as tar:
        data = b"malicious content"
        ti = tarfile.TarInfo(name="../escaped.txt")
        ti.size = len(data)
        tar.addfile(ti, io.BytesIO(data))

    with pytest.raises(BackupIntegrityError, match="Path traversal"):
        _safe_extract_tar(tar_path, target_dir)

    tar_abs_path = tmp_path / "absolute.tar"
    with tarfile.open(tar_abs_path, "w") as tar:
        data = b"malicious content"
        ti = tarfile.TarInfo(name="/etc/passwd")
        ti.size = len(data)
        tar.addfile(ti, io.BytesIO(data))

    with pytest.raises(BackupIntegrityError, match="Path traversal"):
        _safe_extract_tar(tar_abs_path, target_dir)


def test_verify_backup_missing_or_corrupt_files(tmp_path: Path) -> None:
    """Test verify_backup error cases for nonexistent or corrupted archive contents."""
    key_src = RawKeySource(b"\x01" * 32)

    with pytest.raises(BackupIntegrityError, match="Backup archive does not exist"):
        verify_backup(tmp_path / "nonexistent.kbbak", key_src)

    empty_tar = tmp_path / "empty.tar"
    with tarfile.open(empty_tar, "w"):
        pass

    archive_no_manifest = tmp_path / "no_manifest.kbbak"
    _atomic_write_encrypted_tar(empty_tar, archive_no_manifest, key_src)
    with pytest.raises(BackupIntegrityError, match=r"manifest\.json is missing"):
        verify_backup(archive_no_manifest, key_src)

    corrupt_manifest_tar = tmp_path / "corrupt_manifest.tar"
    with tarfile.open(corrupt_manifest_tar, "w") as tar:
        bad_json = b"not json"
        ti = tarfile.TarInfo(name="manifest.json")
        ti.size = len(bad_json)
        tar.addfile(ti, io.BytesIO(bad_json))

    archive_bad_manifest = tmp_path / "bad_manifest.kbbak"
    _atomic_write_encrypted_tar(corrupt_manifest_tar, archive_bad_manifest, key_src)
    with pytest.raises(BackupIntegrityError, match=r"manifest\.json is invalid"):
        verify_backup(archive_bad_manifest, key_src)

    no_pgdump_tar = tmp_path / "no_pgdump.tar"
    with tarfile.open(no_pgdump_tar, "w") as tar:
        man_data = json.dumps(
            {
                "format_version": 1,
                "created_at": "2026-11-11T00:00:00Z",
                "alembic_revision": "none",
                "pg_server_version": "16",
                "sha256_pgdump": "expected_sha",
            }
        ).encode("utf-8")
        ti = tarfile.TarInfo(name="manifest.json")
        ti.size = len(man_data)
        tar.addfile(ti, io.BytesIO(man_data))

    archive_no_pgdump = tmp_path / "no_pgdump.kbbak"
    _atomic_write_encrypted_tar(no_pgdump_tar, archive_no_pgdump, key_src)
    with pytest.raises(BackupIntegrityError, match=r"database\.pgdump is missing"):
        verify_backup(archive_no_pgdump, key_src)

    mismatch_tar = tmp_path / "mismatch.tar"
    with tarfile.open(mismatch_tar, "w") as tar:
        man_data = json.dumps(
            {
                "format_version": 1,
                "created_at": "2026-11-11T00:00:00Z",
                "alembic_revision": "none",
                "pg_server_version": "16",
                "sha256_pgdump": "expected_hash_does_not_match",
            }
        ).encode("utf-8")
        ti = tarfile.TarInfo(name="manifest.json")
        ti.size = len(man_data)
        tar.addfile(ti, io.BytesIO(man_data))

        dump_data = b"PGDUMP_CONTENT_DATA"
        ti2 = tarfile.TarInfo(name="database.pgdump")
        ti2.size = len(dump_data)
        tar.addfile(ti2, io.BytesIO(dump_data))

    archive_mismatch = tmp_path / "mismatch.kbbak"
    _atomic_write_encrypted_tar(mismatch_tar, archive_mismatch, key_src)
    with pytest.raises(BackupIntegrityError, match=r"database\.pgdump SHA-256 mismatch"):
        verify_backup(archive_mismatch, key_src)


def test_restore_secrets_and_attachments(tmp_path: Path) -> None:
    """Test helper functions for secret and attachment restoration."""
    ext_dir = tmp_path / "extracted_empty"
    ext_dir.mkdir()
    assert _restore_secrets(ext_dir, tmp_path / "target_keyring.json") is False

    corrupt_sec = ext_dir / "secrets_carryover.json"
    corrupt_sec.write_text("invalid json", encoding="utf-8")
    assert _restore_secrets(ext_dir, tmp_path / "target_keyring.json") is False

    assert _restore_attachments(ext_dir, None) == 0
    assert _restore_attachments(ext_dir, tmp_path / "dest_att") == 0


def test_compose_export_keyring_edge_cases(tmp_path: Path) -> None:
    """Test standalone keyring parsing and partial key carryover in compose export."""
    assert _load_standalone_keyring(tmp_path / "nonexistent.json") is None

    bad_keyring = tmp_path / "corrupt.json"
    bad_keyring.write_text("not json", encoding="utf-8")
    assert _load_standalone_keyring(bad_keyring) is None

    partial_keyring = tmp_path / "partial.json"
    partial_keyring.write_text(json.dumps({"MASTER_KEK": "only_kek"}), encoding="utf-8")
    out_dir = tmp_path / "compose_out"
    summary = export_production_bundle(out_dir, keyring_path=partial_keyring)
    assert summary.carried_over_secrets is False


def test_cli_key_resolution_edge_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI _resolve_key_source parameter combinations and validation errors."""
    with pytest.raises(ValueError, match="is not set or empty"):
        _resolve_key_source("MISSING_ENV_VAR_123", None)

    with pytest.raises(ValueError, match="Passphrase file does not exist"):
        _resolve_key_source(None, str(tmp_path / "missing_file.txt"))

    empty_p = tmp_path / "empty_pass.txt"
    empty_p.write_text("   \n", encoding="utf-8")
    with pytest.raises(ValueError, match="Passphrase file is empty"):
        _resolve_key_source(None, str(empty_p))

    valid_p = tmp_path / "valid_pass.txt"
    valid_p.write_text("valid_passphrase_secret\n", encoding="utf-8")
    src = _resolve_key_source(None, str(valid_p))
    assert isinstance(src, PassphraseKeySource)

    monkeypatch.delenv("KB_BACKUP_KEY", raising=False)
    monkeypatch.setenv("KB_BACKUP_PASSPHRASE_FILE", str(valid_p))
    fallback = _resolve_fallback_key_source()
    assert isinstance(fallback, PassphraseKeySource)

    monkeypatch.delenv("KB_BACKUP_PASSPHRASE_FILE", raising=False)
    with pytest.raises(ValueError, match="Key source required"):
        _resolve_key_source(None, None)


def test_cli_handler_error_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI subcommand error exit codes and argument validation."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("KB_DB_URL", raising=False)
    ns_create_nodb = argparse.Namespace(
        db_url=None,
        key_env=None,
        passphrase_file=None,
        out=str(tmp_path / "test.kbbak"),
        keyring=None,
        attachments_dir=None,
        include_secrets=False,
    )
    assert _handle_backup_create(ns_create_nodb) == 2

    ns_create_nokey = argparse.Namespace(
        db_url="postgresql://localhost/db",
        key_env="NONEXISTENT_KEY_ENV",
        passphrase_file=None,
        out=str(tmp_path / "test.kbbak"),
        keyring=None,
        attachments_dir=None,
        include_secrets=False,
    )
    assert _handle_backup_create(ns_create_nokey) == 2

    ns_verify_nofile = argparse.Namespace(
        in_file=str(tmp_path / "missing.kbbak"),
        key_env=None,
        passphrase_file=None,
    )
    assert _handle_backup_verify(ns_verify_nofile) == 2

    ns_restore_nofile = argparse.Namespace(
        in_file=str(tmp_path / "missing.kbbak"),
        target_db_url="postgresql://localhost/db",
        key_env=None,
        passphrase_file=None,
        target_keyring=None,
        restore_attachments_dir=None,
        confirm_overwrite=False,
    )
    assert _validate_restore_args(ns_restore_nofile) == 2

    real_archive = tmp_path / "empty_archive.kbbak"
    real_archive.write_bytes(b"data")
    monkeypatch.delenv("TARGET_DATABASE_URL", raising=False)
    ns_restore_nodb = argparse.Namespace(
        in_file=str(real_archive),
        target_db_url=None,
        key_env=None,
        passphrase_file=None,
        target_keyring=None,
        restore_attachments_dir=None,
        confirm_overwrite=False,
    )
    assert _validate_restore_args(ns_restore_nodb) == 2

    ns_restore_nokey = argparse.Namespace(
        in_file=str(real_archive),
        target_db_url="postgresql://localhost/db",
        key_env="NONEXISTENT_ENV",
        passphrase_file=None,
        target_keyring=None,
        restore_attachments_dir=None,
        confirm_overwrite=False,
    )
    assert _validate_restore_args(ns_restore_nokey) == 2

    ns_compose_bad = argparse.Namespace(
        out_dir=str(tmp_path / "out"),
        domain="localhost",
        carry_over_keyring=None,
    )
    with patch("kanban.cli.ops.export_production_bundle", side_effect=OSError("Disk full")):
        assert _handle_promote_compose(ns_compose_bad) == 1

    valid_b64_key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    monkeypatch.setenv("KB_BACKUP_KEY", valid_b64_key)
    ns_restore_mock = argparse.Namespace(
        in_file=str(real_archive),
        target_db_url="postgresql://localhost/db",
        key_env=None,
        passphrase_file=None,
        target_keyring=None,
        restore_attachments_dir=None,
        confirm_overwrite=False,
    )
    with patch("kanban.cli.ops.restore_backup", side_effect=TargetDatabaseNotEmptyError("busy")):
        assert _handle_restore(ns_restore_mock) == 2

    with patch("kanban.cli.ops.restore_backup", side_effect=RuntimeError("internal fail")):
        assert _handle_restore(ns_restore_mock) == 1


def test_cli_main_entrypoint() -> None:
    """Test top-level CLI main function with help and empty arguments."""
    assert ops_main(["--help"]) == 0
    assert ops_main([]) == 2
    assert ctl_main(["--help"]) == 0
    assert ctl_main([]) == 2


def test_subprocess_error_branches(tmp_path: Path) -> None:
    """Test pg_dump and pg_restore error handling when subprocess fails."""
    with pytest.raises(BackupError, match="pg_dump executable not found"):
        _execute_pg_dump(
            "/nonexistent/bin/pg_dump", "postgresql://localhost/db", tmp_path / "out.dump"
        )

    with pytest.raises(RestoreError, match="pg_restore executable not found"):
        _execute_pg_restore(
            "/nonexistent/bin/pg_restore",
            "postgresql://localhost/db",
            tmp_path / "out.dump",
        )

    called_err = subprocess.CalledProcessError(1, ["cmd"], stderr=b"syntax error")
    with patch("subprocess.run", side_effect=called_err):
        with pytest.raises(BackupError, match="pg_dump execution failed"):
            _execute_pg_dump("pg_dump", "postgresql://localhost/db", tmp_path / "out.dump")
        with pytest.raises(RestoreError, match="pg_restore execution failed"):
            _execute_pg_restore("pg_restore", "postgresql://localhost/db", tmp_path / "out.dump")


def test_cli_fallback_key_source_prompts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test fallback key source when interactive tty prompt or empty passphrase file."""
    monkeypatch.delenv("KB_BACKUP_KEY", raising=False)
    monkeypatch.delenv("KB_BACKUP_PASSPHRASE_FILE", raising=False)

    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("getpass.getpass", return_value="user_typed_pass"),
    ):
        src = _resolve_fallback_key_source()
        assert isinstance(src, PassphraseKeySource)

    dir_as_file = tmp_path / "dir_pass"
    dir_as_file.mkdir()
    monkeypatch.setenv("KB_BACKUP_PASSPHRASE_FILE", str(dir_as_file))
    with patch("sys.stdin.isatty", return_value=False):
        assert _resolve_fallback_key_source() is None

    empty_pass = tmp_path / "empty_pass_file"
    empty_pass.write_text("   \n", encoding="utf-8")
    monkeypatch.setenv("KB_BACKUP_PASSPHRASE_FILE", str(empty_pass))
    with patch("sys.stdin.isatty", return_value=False):
        assert _resolve_fallback_key_source() is None


def test_cli_backup_create_error_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _handle_backup_create exception paths."""
    ns = argparse.Namespace(
        db_url="postgresql://localhost/db",
        key_env="KB_KEY_ENV",
        passphrase_file=None,
        out=str(tmp_path / "out.kbbak"),
        keyring=None,
        attachments_dir=None,
        include_secrets=False,
    )
    monkeypatch.setenv("KB_KEY_ENV", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")

    with patch("kanban.cli.ops.create_backup", side_effect=BackupError("custom backup err")):
        assert _handle_backup_create(ns) == 2

    with patch("kanban.cli.ops.create_backup", side_effect=RuntimeError("unexpected err")):
        assert _handle_backup_create(ns) == 1


def test_atomic_write_encrypted_tar_cleanup(tmp_path: Path) -> None:
    """Test temporary file cleanup on write failure in _atomic_write_encrypted_tar."""
    tar_path = tmp_path / "source.tar"
    tar_path.write_bytes(b"data")
    out_path = tmp_path / "final.kbbak"
    key_src = RawKeySource(b"\x00" * 32)

    with (
        patch("kanban.ops.backup_service.encrypt_stream", side_effect=OSError("Disk write failed")),
        pytest.raises(OSError, match="Disk write failed"),
    ):
        _atomic_write_encrypted_tar(tar_path, out_path, key_src)
    assert not out_path.exists()


def test_cli_main_subcommand_dispatch(tmp_path: Path) -> None:
    """Test ops_main subcommand dispatch execution."""
    out_dir = tmp_path / "compose_dispatch"
    ret = ops_main(
        ["promote", "export-compose", "--out-dir", str(out_dir), "--domain", "test.local"]
    )
    assert ret == 0
    assert (out_dir / "docker-compose.yml").is_file()

    # Verify subcommand with missing file exits 2
    ret_fail = ops_main(["backup", "verify", "--in", str(tmp_path / "missing.kbbak")])
    assert ret_fail == 2

    # Restore subcommand with missing file exits 2
    ret_res_fail = ops_main(
        [
            "restore",
            "--in",
            str(tmp_path / "missing.kbbak"),
            "--target-db-url",
            "postgresql://localhost/db",
        ]
    )
    assert ret_res_fail == 2


@pytest.mark.asyncio
async def test_inspect_db_metadata_no_alembic() -> None:
    """Test _inspect_db_metadata against a database without alembic_version table."""
    sock = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    admin_url = f"postgresql+asyncpg://kanban_test@/postgres?host={sock}"
    pg_ver, rev = await _inspect_db_metadata(admin_url)
    assert "PostgreSQL" in pg_ver
    assert rev == "none"


@pytest.mark.asyncio
async def test_verify_post_restore_invariants_alembic_mismatch(pg_worker_db: AsyncEngine) -> None:
    """Test _verify_post_restore_invariants raising on alembic revision mismatch."""
    db_url = pg_worker_db.url.render_as_string(hide_password=False)
    mismatch_manifest = BackupManifest(
        format_version=1,
        created_at="2026-11-11T00:00:00Z",
        alembic_revision="NONEXISTENT_ALEMBIC_REVISION",
        pg_server_version="16",
        sha256_pgdump="dummy",
        sha256_attachments_index="",
        includes_keyring_secrets=False,
    )
    with pytest.raises(RestoreVerificationError, match="Post-restore Alembic revision mismatch"):
        await _verify_post_restore_invariants(db_url, mismatch_manifest)
