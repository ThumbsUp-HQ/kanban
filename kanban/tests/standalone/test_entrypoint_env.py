# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for standalone entrypoint environment, attachments directory, ownership, and Ops RPC (KB-MIGRATION-PLANE-DB-01, KAN-82, KAN-423)."""

# ruff: noqa: E501

from __future__ import annotations

import base64
import json
import os
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deploy.standalone.entrypoint import (
    _PASSTHROUGH_ENV_VARS,
    OpsSocketServer,
    build_child_env,
    ensure_attachments_dir,
    execute_privileged_op,
)
from kanban.api.problems import ProblemException
from kanban.api.v1.system_status import (
    restore_backup_endpoint,
    run_backup_now_endpoint,
)
from kanban.ops.backup_crypto import BackupIntegrityError
from kanban.standalone.export_service import (
    BackupError as ExportBackupError,
)
from kanban.standalone.export_service import (
    run_pg_dump,
)


def test_passthrough_env_vars_includes_attachment_dir() -> None:
    """Verify KANBAN_ATTACHMENT_DIR is explicitly in _PASSTHROUGH_ENV_VARS allowlist."""
    assert "KANBAN_ATTACHMENT_DIR" in _PASSTHROUGH_ENV_VARS


def test_build_child_env_attachment_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify build_child_env defaults KANBAN_ATTACHMENT_DIR to /var/lib/kanban/data/attachments."""
    monkeypatch.delenv("KANBAN_ATTACHMENT_DIR", raising=False)
    env = build_child_env(db_url="postgresql+asyncpg://app@/kanban")
    assert env["KANBAN_ATTACHMENT_DIR"] == "/var/lib/kanban/data/attachments"


def test_build_child_env_attachment_dir_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify build_child_env respects KANBAN_ATTACHMENT_DIR from environment."""
    monkeypatch.setenv("KANBAN_ATTACHMENT_DIR", "/custom/data/attachments")
    env = build_child_env(db_url="postgresql+asyncpg://app@/kanban")
    assert env["KANBAN_ATTACHMENT_DIR"] == "/custom/data/attachments"


def test_build_child_env_kb_ops_sock_and_no_migrator_url() -> None:
    """Verify build_child_env sets KB_OPS_SOCK and omits KANBAN_MIGRATOR_DATABASE_URL."""
    env = build_child_env(db_url="postgresql+asyncpg://app@/kanban", run_dir="/custom/run")
    assert env["KB_OPS_SOCK"] == "/custom/run/.kb_ops.sock"
    assert "KANBAN_MIGRATOR_DATABASE_URL" not in env


def test_attachments_directory_permissions_and_ownership(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify attachments directory is created with 65532:65532 ownership and 0750 permissions."""
    data_dir = tmp_path / "data"
    pgdata_dir = data_dir / "pgdata"
    custom_att_dir = data_dir / "attachments"

    monkeypatch.setenv("KB_PGDATA_DIR", str(pgdata_dir))
    monkeypatch.setenv("KANBAN_ATTACHMENT_DIR", str(custom_att_dir))

    chown_calls: list[tuple[str, int, int]] = []
    chmod_calls: list[tuple[str, int]] = []

    def fake_chown(path: str, user: int, group: int) -> None:
        chown_calls.append((path, user, group))

    def fake_chmod(self: Path, mode: int) -> None:
        chmod_calls.append((str(self), mode))

    with (
        patch("os.getuid", return_value=0),
        patch("shutil.chown", side_effect=fake_chown),
        patch.object(Path, "chmod", fake_chmod),
    ):
        attachments_dir = ensure_attachments_dir(data_dir)

    assert (str(custom_att_dir), 65532, 65532) in chown_calls
    assert (str(custom_att_dir), 0o750) in chmod_calls
    assert attachments_dir.is_dir()


def test_execute_privileged_op_unknown_op(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify execute_privileged_op rejects unknown operations cleanly with error JSON."""
    exit_code = execute_privileged_op(json.dumps({"op": "invalid_operation"}))
    captured = capsys.readouterr().out.strip()
    resp = json.loads(captured)
    assert exit_code == 1
    assert resp["status"] == "error"
    assert "Unknown operation: invalid_operation" in resp["message"]


def test_execute_privileged_op_restore_restricted_path(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify execute_privileged_op rejects archive paths outside allowed directories."""
    exit_code = execute_privileged_op(
        json.dumps({"op": "restore_backup", "archive_path": "/etc/passwd"})
    )
    captured = capsys.readouterr().out.strip()
    resp = json.loads(captured)
    assert exit_code == 1
    assert resp["status"] == "error"
    assert "Restricted archive path" in resp["message"]


def test_execute_privileged_op_restore_not_found(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Verify execute_privileged_op handles missing archive path inside allowed dir."""
    missing = tmp_path / "nonexistent.kbbak"
    exit_code = execute_privileged_op(
        json.dumps({"op": "restore_backup", "archive_path": str(missing)})
    )
    captured = capsys.readouterr().out.strip()
    resp = json.loads(captured)
    assert exit_code == 1
    assert resp["status"] == "error"
    assert "Archive not found" in resp["message"]


def test_execute_privileged_op_pg_dump_raw(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify execute_privileged_op pg_dump_raw returns base64 dump data."""
    fake_proc = MagicMock()
    fake_proc.stdout = b"PGDUMP_CUSTOM_FORMAT_STREAM"
    with patch("subprocess.run", return_value=fake_proc):
        exit_code = execute_privileged_op(
            json.dumps({"op": "pg_dump_raw", "run_dir": "/tmp/testrun"})
        )
    captured = capsys.readouterr().out.strip()
    resp = json.loads(captured)
    assert exit_code == 0
    assert resp["status"] == "ok"
    assert base64.b64decode(resp["data_b64"]) == b"PGDUMP_CUSTOM_FORMAT_STREAM"
    assert resp["size_bytes"] == len(b"PGDUMP_CUSTOM_FORMAT_STREAM")


def test_execute_privileged_op_restore_backup_success(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Verify execute_privileged_op restore_backup executes and returns report."""
    test_archive = tmp_path / "test_archive.kbbak"
    test_archive.write_bytes(b"KBBAK1_RAW")

    mock_report = MagicMock()
    mock_report.workspaces_verified = 2
    mock_report.links_audited = 5
    mock_report.duration_seconds = 0.42

    with patch("deploy.standalone.entrypoint.restore_backup", return_value=mock_report):
        exit_code = execute_privileged_op(
            json.dumps(
                {
                    "op": "restore_backup",
                    "archive_path": str(test_archive),
                    "passphrase": "test-password",
                    "run_dir": str(tmp_path),
                }
            )
        )
    captured = capsys.readouterr().out.strip()
    resp = json.loads(captured)
    assert exit_code == 0
    assert resp["status"] == "ok"
    assert resp["report"]["workspaces_verified"] == 2
    assert resp["report"]["links_audited"] == 5


def test_execute_privileged_op_scheduled_backup_success(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Verify execute_privileged_op scheduled_backup executes and returns archive details."""
    mock_keyring = MagicMock()
    mock_keyring.master_kek = b"0" * 32
    mock_report = MagicMock()
    mock_report.size_bytes = 1024
    mock_report.duration_seconds = 0.33

    with (
        patch("deploy.standalone.entrypoint.load_or_create_keyring", return_value=mock_keyring),
        patch("deploy.standalone.entrypoint.create_backup", return_value=mock_report),
        patch("pathlib.Path.mkdir"),
    ):
        exit_code = execute_privileged_op(
            json.dumps(
                {
                    "op": "scheduled_backup",
                    "keyring_path": str(tmp_path / "keyring.json"),
                    "run_dir": str(tmp_path),
                }
            )
        )
    captured = capsys.readouterr().out.strip()
    resp = json.loads(captured)
    assert exit_code == 0
    assert resp["status"] == "ok"
    assert resp["size_bytes"] == 1024


def test_ops_socket_server_lifecycle_and_rpc(tmp_path: Path) -> None:
    """Verify OpsSocketServer lifecycle and RPC communication over Unix socket."""
    server = OpsSocketServer(run_dir=str(tmp_path))
    server.start()
    assert server.sock_path.exists()

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(5.0)
            client.connect(str(server.sock_path))
            client.sendall(json.dumps({"op": "ping_test_op"}).encode("utf-8") + b"\n")
            raw = b""
            while not raw.endswith(b"\n"):
                chunk = client.recv(4096)
                if not chunk:
                    break
                raw += chunk
        resp = json.loads(raw.decode("utf-8"))
        assert resp["status"] == "error"
        assert "Unknown operation: ping_test_op" in resp["message"]
    finally:
        server.stop()
        assert not server.sock_path.exists()


@pytest.mark.asyncio
async def test_ops_socket_export_service_dump(tmp_path: Path) -> None:
    """Verify run_pg_dump interacts with OpsSocketServer for privileged pg_dump."""
    server = OpsSocketServer(run_dir=str(tmp_path))
    server.start()
    try:
        with patch.dict(os.environ, {"KB_OPS_SOCK": str(server.sock_path)}):
            mock_proc = SimpleNamespace(stdout=b"DUMP_OUTPUT", returncode=0)
            with patch("deploy.standalone.entrypoint.subprocess.run", return_value=mock_proc):
                data = await run_pg_dump(socket_dir=str(tmp_path))
                assert data == b"DUMP_OUTPUT"

            with (
                patch(
                    "deploy.standalone.entrypoint.subprocess.run",
                    side_effect=RuntimeError("Dump failed"),
                ),
                pytest.raises(ExportBackupError, match="Privileged pg_dump failed"),
            ):
                await run_pg_dump(socket_dir=str(tmp_path))
    finally:
        server.stop()


@pytest.mark.asyncio
async def test_ops_socket_system_status_endpoints(tmp_path: Path) -> None:
    """Verify system_status backup and restore endpoints interact with OpsSocketServer."""
    server = OpsSocketServer(run_dir=str(tmp_path))
    server.start()
    try:
        with patch.dict(os.environ, {"KB_OPS_SOCK": str(server.sock_path)}):
            # 1. run_backup_now_endpoint success
            mock_report = MagicMock()
            mock_report.size_bytes = 2048
            mock_report.duration_seconds = 0.5
            mock_keyring = MagicMock(master_kek=b"0" * 32)
            mock_req = MagicMock()
            mock_req.app.state.settings = MagicMock()

            with (
                patch(
                    "deploy.standalone.entrypoint.load_or_create_keyring", return_value=mock_keyring
                ),
                patch("deploy.standalone.entrypoint.create_backup", return_value=mock_report),
                patch("pathlib.Path.mkdir"),
            ):
                res = await run_backup_now_endpoint(mock_req)
                assert res["status"] == "success"
                assert res["size_bytes"] == 2048

            # 2. run_backup_now_endpoint error
            with patch(
                "deploy.standalone.entrypoint.create_backup",
                side_effect=RuntimeError("Backup error"),
            ):
                with pytest.raises(ProblemException) as exc_info:
                    await run_backup_now_endpoint(mock_req)
                assert exc_info.value.code == "BACKUP_RUN_FAILED"

            # 3. restore_backup_endpoint success
            restore_req = MagicMock()
            restore_req.headers = {"content-type": "application/json"}
            restore_req.json = AsyncMock(
                return_value={
                    "file_base64": base64.b64encode(b"DATA").decode("ascii"),
                    "confirm_overwrite": "RESTORE",
                    "passphrase": "pass",
                }
            )
            restore_req.app.state.engine = None
            mock_restore_report = MagicMock(
                workspaces_verified=3, links_audited=7, duration_seconds=0.1
            )

            with patch(
                "deploy.standalone.entrypoint.restore_backup", return_value=mock_restore_report
            ):
                res_restore = await restore_backup_endpoint(restore_req)
                assert res_restore["status"] == "success"
                assert res_restore["workspaces_verified"] == 3

            # 4. restore_backup_endpoint validation failure (BackupIntegrityError)
            with patch(
                "deploy.standalone.entrypoint.restore_backup",
                side_effect=BackupIntegrityError("Corrupt tag"),
            ):
                with pytest.raises(ProblemException) as exc_v:
                    await restore_backup_endpoint(restore_req)
                assert exc_v.value.code == "BACKUP_VERIFICATION_FAILED"
                assert exc_v.value.status == 422

            # 5. restore_backup_endpoint execution failure (RuntimeError)
            with patch(
                "deploy.standalone.entrypoint.restore_backup",
                side_effect=RuntimeError("Disk failure"),
            ):
                with pytest.raises(ProblemException) as exc_e:
                    await restore_backup_endpoint(restore_req)
                assert exc_e.value.code == "RESTORE_EXECUTION_FAILED"
                assert exc_e.value.status == 500
    finally:
        server.stop()
