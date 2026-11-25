# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for standalone entrypoint environment, attachments directory, ownership, and Ops RPC (KB-MIGRATION-PLANE-DB-01, KAN-82, KAN-423)."""

# ruff: noqa: E501, PLR0915, PLC0415, PT018, S104, S106, SIM117, F841

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

    # 2. Restore with raw_key_b64
    with patch("deploy.standalone.entrypoint.restore_backup", return_value=mock_report):
        execute_privileged_op(
            json.dumps(
                {
                    "op": "restore_backup",
                    "archive_path": str(test_archive),
                    "raw_key_b64": base64.b64encode(b"0" * 32).decode("ascii"),
                    "run_dir": str(tmp_path),
                }
            )
        )
    captured2 = capsys.readouterr().out.strip()
    assert json.loads(captured2)["status"] == "ok"

    # 3. Restore with fallback keyring
    mock_kr = MagicMock(master_kek=b"1" * 32)
    with (
        patch("deploy.standalone.entrypoint.load_or_create_keyring", return_value=mock_kr),
        patch("deploy.standalone.entrypoint.restore_backup", return_value=mock_report),
    ):
        execute_privileged_op(
            json.dumps(
                {
                    "op": "restore_backup",
                    "archive_path": str(test_archive),
                    "run_dir": str(tmp_path),
                }
            )
        )
    captured3 = capsys.readouterr().out.strip()
    assert json.loads(captured3)["status"] == "ok"


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

    # 2. Scheduled backup with raw_key_b64
    with patch("deploy.standalone.entrypoint.create_backup", return_value=mock_report):
        execute_privileged_op(
            json.dumps(
                {
                    "op": "scheduled_backup",
                    "backup_dir": str(tmp_path / "backups"),
                    "raw_key_b64": base64.b64encode(b"0" * 32).decode("ascii"),
                    "run_dir": str(tmp_path),
                }
            )
        )


def test_ops_socket_server_lifecycle_and_rpc(tmp_path: Path) -> None:
    """Verify OpsSocketServer lifecycle and RPC communication over Unix socket."""
    # Pre-create old socket to test unlink on startup
    old_sock = tmp_path / ".kb_ops.sock"
    old_sock.write_text("old")
    mock_kr = MagicMock(master_kek=b"2" * 32)
    server = OpsSocketServer(run_dir=str(tmp_path), keyring=mock_kr)
    server.start()
    assert server.sock_path.exists()

    try:
        # 1. Connect and close immediately without data (tested as non-root)
        with patch("os.geteuid", return_value=1000):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client0:
                client0.connect(str(server.sock_path))

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

        # 2. Test os.geteuid() == 0 branch with mock run_as_postgres
        mock_proc_ok = SimpleNamespace(
            returncode=0, stdout=json.dumps({"status": "ok", "msg": "root"}), stderr=""
        )
        with (
            patch("os.geteuid", return_value=0),
            patch("deploy.standalone.entrypoint.run_as_postgres", return_value=mock_proc_ok),
        ):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(str(server.sock_path))
                client.sendall(json.dumps({"op": "any"}).encode("utf-8") + b"\n")
                raw2 = b""
                while not raw2.endswith(b"\n"):
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    raw2 += chunk
                resp2 = json.loads(raw2.decode("utf-8"))
                assert resp2["status"] == "ok"

        # 3. Test os.geteuid() == 0 empty stdout fallback
        mock_proc_empty = SimpleNamespace(returncode=1, stdout="", stderr="Privileged error")
        with (
            patch("os.geteuid", return_value=0),
            patch("deploy.standalone.entrypoint.run_as_postgres", return_value=mock_proc_empty),
        ):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(str(server.sock_path))
                client.sendall(json.dumps({"op": "any"}).encode("utf-8") + b"\n")
                raw3 = b""
                while not raw3.endswith(b"\n"):
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    raw3 += chunk
                resp3 = json.loads(raw3.decode("utf-8"))
                assert resp3["status"] == "error"
                assert "Privileged error" in resp3["message"]

        # 4. Test malformed json error response
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(server.sock_path))
            client.sendall(b"not-json\n")
            raw4 = b""
            while not raw4.endswith(b"\n"):
                chunk = client.recv(4096)
                if not chunk:
                    break
                raw4 += chunk
            resp4 = json.loads(raw4.decode("utf-8"))
            assert resp4["status"] == "error"
            assert resp4["error_type"] == "JSONDecodeError"
    finally:
        server.stop()
        assert not server.sock_path.exists()


@pytest.mark.asyncio
async def test_ops_socket_export_service_dump(tmp_path: Path) -> None:
    """Verify run_pg_dump interacts with OpsSocketServer for privileged pg_dump."""
    server = OpsSocketServer(run_dir=str(tmp_path))
    server.start()
    try:
        with (
            patch("os.geteuid", return_value=1000),
            patch.dict(os.environ, {"KB_OPS_SOCK": str(server.sock_path)}),
        ):
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
        with (
            patch("os.geteuid", return_value=1000),
            patch.dict(os.environ, {"KB_OPS_SOCK": str(server.sock_path)}),
        ):
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


def test_log_phase(capsys: pytest.CaptureFixture[str]) -> None:
    """Test log_phase icon and level formatting."""
    from deploy.standalone.entrypoint import log_phase

    log_phase("test", "info message", level="INFO")
    captured = capsys.readouterr().out
    assert "👍" in captured and "info message" in captured

    log_phase("test", "warn message", level="WARNING")
    captured = capsys.readouterr().out
    assert "⛔" in captured and "warn message" in captured

    log_phase("test", "err message", level="ERROR")
    captured = capsys.readouterr().out
    assert "❌" in captured and "err message" in captured


def test_run_as_postgres_helpers() -> None:
    """Test run_as_postgres and run_as_postgres_bytes invocations."""
    from deploy.standalone.entrypoint import (
        BIN_SETPRIV,
        run_as_postgres,
        run_as_postgres_bytes,
    )

    mock_cp_str = SimpleNamespace(returncode=0, stdout="output", stderr="")
    mock_cp_bytes = SimpleNamespace(returncode=0, stdout=b"output_bytes", stderr=b"")

    with patch("subprocess.run", return_value=mock_cp_str) as mock_run:
        res = run_as_postgres(["echo", "hello"], timeout=5.0)
        assert res.stdout == "output"
        args = mock_run.call_args[0][0]
        assert args[0] == BIN_SETPRIV
        assert "--reuid=postgres" in args

    with patch("subprocess.run", return_value=mock_cp_bytes) as mock_run_bytes:
        res_b = run_as_postgres_bytes(["echo", "hello"], timeout=5.0)
        assert res_b.stdout == b"output_bytes"
        args_b = mock_run_bytes.call_args[0][0]
        assert "--reuid=postgres" in args_b


def test_initialize_cluster(tmp_path: Path) -> None:
    """Test initialize_cluster skips existing cluster and handles cold init + error."""
    import subprocess

    from deploy.standalone.entrypoint import initialize_cluster

    # 1. Existing cluster skips initdb
    pgdata_warm = tmp_path / "warm"
    pgdata_warm.mkdir()
    (pgdata_warm / "PG_VERSION").write_text("16\n")
    with patch("deploy.standalone.entrypoint.run_as_postgres") as mock_run:
        initialize_cluster(pgdata_warm)
        mock_run.assert_not_called()

    # 2. Cold cluster runs initdb
    pgdata_cold = tmp_path / "cold"
    with patch("deploy.standalone.entrypoint.run_as_postgres") as mock_run:
        initialize_cluster(pgdata_cold)
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert "--auth-local=peer" in cmd

    # 3. Initdb failure raises CalledProcessError
    pgdata_err = tmp_path / "err"
    with (
        patch(
            "deploy.standalone.entrypoint.run_as_postgres",
            side_effect=subprocess.CalledProcessError(1, ["initdb"], stderr="initdb failed"),
        ),
        pytest.raises(subprocess.CalledProcessError),
    ):
        initialize_cluster(pgdata_err)


def test_start_and_stop_postgres(tmp_path: Path) -> None:
    """Test start_postgres readiness polling, timeout, and stop_postgres."""
    from deploy.standalone.entrypoint import (
        start_postgres,
        stop_postgres,
    )

    pgdata = tmp_path / "pgdata"
    pgdata.mkdir()

    # 1. Successful start
    mock_ready = SimpleNamespace(returncode=0, stdout="", stderr="")
    with patch("deploy.standalone.entrypoint.run_as_postgres", return_value=mock_ready):
        start_postgres(pgdata, run_dir=str(tmp_path))

    # 2. Start timeout -> calls stop_postgres and exits with code 70
    mock_not_ready = SimpleNamespace(returncode=1, stdout="", stderr="")
    with (
        patch("deploy.standalone.entrypoint.run_as_postgres", return_value=mock_not_ready),
        patch("time.sleep"),
        pytest.raises(SystemExit) as exc_info,
    ):
        start_postgres(pgdata, run_dir=str(tmp_path))
    assert exc_info.value.code == 70

    # 3. Stop postgres
    with patch("deploy.standalone.entrypoint.run_as_postgres") as mock_run:
        stop_postgres(pgdata, mode="fast")
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert "stop" in cmd and "fast" in cmd


def test_database_bootstrap_and_migrations(tmp_path: Path) -> None:
    """Test bootstrap_database, run_migrations, and backup grant procedures."""
    from deploy.standalone.entrypoint import (
        bootstrap_database,
        ensure_backup_grants,
        run_migrations,
        run_psql_script,
    )

    # 1. run_psql_script
    with patch("deploy.standalone.entrypoint.run_as_postgres") as mock_run:
        run_psql_script("SELECT 1;", dbname="testdb", run_dir=str(tmp_path))
        cmd = mock_run.call_args[0][0]
        assert "-c" in cmd and "SELECT 1;" in cmd
        assert "-d" in cmd and "testdb" in cmd

    # 2. bootstrap_database with and without keyring
    mock_db_exists = SimpleNamespace(returncode=0, stdout="1\n", stderr="")
    mock_keyring = MagicMock(
        kanban_app_password_str="app_pass",
        kanban_migrator_password_str="mig_pass",
        master_kek=b"\x00" * 32,
    )
    with (
        patch("deploy.standalone.entrypoint.run_psql_script") as mock_psql,
        patch("deploy.standalone.entrypoint.run_as_postgres", return_value=mock_db_exists),
    ):
        bootstrap_database(run_dir=str(tmp_path), keyring=mock_keyring)
        assert mock_psql.call_count >= 3

    # bootstrap_database when database does not exist ("0" in stdout)
    mock_db_missing = SimpleNamespace(returncode=0, stdout="0\n", stderr="")
    with (
        patch("deploy.standalone.entrypoint.run_psql_script") as mock_psql2,
        patch("deploy.standalone.entrypoint.run_as_postgres", return_value=mock_db_missing),
    ):
        bootstrap_database(run_dir=str(tmp_path), keyring=None)
        assert any("CREATE DATABASE kanban" in str(c) for c in mock_psql2.call_args_list)

    # 3. run_migrations: skip when alembic_ini missing
    alembic_missing = tmp_path / "missing.ini"
    run_migrations(tmp_path, alembic_missing, run_dir=str(tmp_path))

    # 4. run_migrations: success
    alembic_present = tmp_path / "alembic.ini"
    alembic_present.write_text("[alembic]\n", encoding="utf-8")
    mock_mig_ok = SimpleNamespace(returncode=0, stdout="upgrade head ok", stderr="")
    with (
        patch("deploy.standalone.entrypoint.run_as_postgres", return_value=mock_mig_ok),
        patch("deploy.standalone.entrypoint.run_psql_script"),
    ):
        run_migrations(tmp_path, alembic_present, run_dir=str(tmp_path))

    # 5. run_migrations: failure exits 70
    mock_mig_fail = SimpleNamespace(returncode=1, stdout="", stderr="migration error")
    with (
        patch("deploy.standalone.entrypoint.run_as_postgres", return_value=mock_mig_fail),
        patch("deploy.standalone.entrypoint.stop_postgres"),
        pytest.raises(SystemExit) as exc_mig,
    ):
        run_migrations(tmp_path, alembic_present, run_dir=str(tmp_path))
    assert exc_mig.value.code == 70

    # 6. ensure_backup_grants catches exceptions gracefully
    with patch(
        "deploy.standalone.entrypoint.run_psql_script", side_effect=RuntimeError("psql err")
    ):
        ensure_backup_grants(run_dir=str(tmp_path))


def test_process_lifecycle_helpers(tmp_path: Path) -> None:
    """Test uvicorn command builder, process shutdown, and supervisor loop."""
    from deploy.standalone.entrypoint import (
        _compute_migrations_digest,
        build_uvicorn_command,
        shutdown_uvicorn,
        supervisor_loop,
    )

    # 1. build_uvicorn_command
    cmd = build_uvicorn_command()
    assert any("uvicorn" in c for c in cmd)
    assert "--host" in cmd and "0.0.0.0" in cmd

    # 2. shutdown_uvicorn already exited
    mock_proc_done = MagicMock()
    mock_proc_done.poll.return_value = 0
    shutdown_uvicorn(mock_proc_done)
    mock_proc_done.send_signal.assert_not_called()

    # 3. shutdown_uvicorn with clean exit
    mock_proc_running = MagicMock()
    mock_proc_running.poll.side_effect = [None, 0]
    with patch("time.sleep"):
        shutdown_uvicorn(mock_proc_running)
    assert mock_proc_running.send_signal.called

    # 4. shutdown_uvicorn escalating to kill
    mock_proc_stubborn = MagicMock()
    mock_proc_stubborn.poll.return_value = None
    with (
        patch("time.sleep"),
        patch("time.monotonic", side_effect=[0.0, 1.0, 11.0, 12.0]),
    ):
        shutdown_uvicorn(mock_proc_stubborn)
    assert mock_proc_stubborn.kill.called

    # 5. supervisor_loop: uvicorn exits with code
    mock_proc_exit = MagicMock()
    mock_proc_exit.poll.return_value = 42
    with patch("deploy.standalone.entrypoint.stop_postgres"):
        ret = supervisor_loop(mock_proc_exit, tmp_path)
    assert ret == 42

    # 6. supervisor_loop: postgres postmaster dies -> returns 70
    mock_proc_alive = MagicMock()
    mock_proc_alive.poll.return_value = None
    mock_pg_dead = SimpleNamespace(returncode=1, stdout="", stderr="pg died")
    with (
        patch("time.sleep"),
        patch("time.monotonic", side_effect=[0.0, 0.0, 3.0, 3.0]),
        patch("deploy.standalone.entrypoint.run_as_postgres", return_value=mock_pg_dead),
        patch("deploy.standalone.entrypoint.shutdown_uvicorn"),
    ):
        ret_dead = supervisor_loop(mock_proc_alive, tmp_path)
    assert ret_dead == 70

    # 7. _compute_migrations_digest (runs on repo's database/migrations/versions)
    digest = _compute_migrations_digest()
    assert isinstance(digest, str)


def test_entrypoint_main_flows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test main() entrypoint modes: external_db, non-root rejection, keyring failure, and cold/warm runs."""
    from deploy.standalone.entrypoint import _compute_migrations_digest
    from deploy.standalone.entrypoint import main as entrypoint_main
    from deploy.standalone.keyring import KeyringError

    data_dir = tmp_path / "data"
    pgdata = data_dir / "pgdata"
    monkeypatch.setenv("KB_PGDATA_DIR", str(pgdata))
    monkeypatch.setenv("KB_RUN_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("KB_ALEMBIC_INI", str(tmp_path / "alembic.ini"))
    monkeypatch.setenv("KB_KEYRING_PATH", str(tmp_path / "secrets" / "keyring.json"))

    # 1. External DB mode
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    with (
        patch("deploy.standalone.entrypoint.probe"),
        patch("deploy.standalone.entrypoint.write_standalone_status"),
        patch("os.execv") as mock_execv,
    ):
        entrypoint_main()
        assert mock_execv.called
    monkeypatch.delenv("DATABASE_URL", raising=False)

    # 2. Non-root user rejection (exit 78)
    with patch("os.getuid", return_value=1000):
        ret_non_root = entrypoint_main()
        assert ret_non_root == 78

    # 3. Root entrypoint with KeyringError (exit 78)
    with (
        patch("os.getuid", return_value=0),
        patch(
            "deploy.standalone.entrypoint.load_or_create_keyring",
            side_effect=KeyringError("Keyring corrupted"),
        ),
        patch("deploy.standalone.entrypoint.probe"),
        patch("deploy.standalone.entrypoint.write_standalone_status"),
    ):
        ret_kr_err = entrypoint_main()
        assert ret_kr_err == 78

    # 4. Cold start full flow
    mock_keyring = MagicMock(
        kanban_app_password_str="app_pass",
        kanban_migrator_password_str="mig_pass",
        raw_token_bytes=b"\x00" * 32,
    )
    with (
        patch("os.getuid", return_value=0),
        patch("deploy.standalone.entrypoint.load_or_create_keyring", return_value=mock_keyring),
        patch("deploy.standalone.entrypoint.probe"),
        patch("deploy.standalone.entrypoint.write_standalone_status"),
        patch("deploy.standalone.entrypoint.initialize_cluster"),
        patch("deploy.standalone.entrypoint.configure_postgres"),
        patch("deploy.standalone.entrypoint.start_postgres"),
        patch("deploy.standalone.entrypoint.bootstrap_database"),
        patch("deploy.standalone.entrypoint.run_migrations"),
        patch("deploy.standalone.entrypoint.ensure_backup_grants"),
        patch("deploy.standalone.entrypoint.OpsSocketServer") as mock_ops_srv,
        patch("subprocess.Popen") as mock_popen,
        patch("deploy.standalone.entrypoint.supervisor_loop", return_value=0),
    ):
        mock_ops_instance = MagicMock()
        mock_ops_srv.return_value = mock_ops_instance
        ret_cold = entrypoint_main()
        assert ret_cold == 0
        assert mock_ops_instance.start.called
        assert mock_ops_instance.stop.called

    # 5. Warm start flow (PG_VERSION present and keyring exists)
    pgdata.mkdir(parents=True, exist_ok=True)
    (pgdata / "PG_VERSION").write_text("16\n")
    (pgdata / ".alembic_head").write_text(_compute_migrations_digest())
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / "keyring.json").write_text("{}")
    (pgdata / "conf.d").mkdir(parents=True, exist_ok=True)
    (pgdata / "conf.d" / "kanban.conf").write_text("# conf")

    with (
        patch("os.getuid", return_value=0),
        patch("deploy.standalone.entrypoint.load_or_create_keyring", return_value=mock_keyring),
        patch("deploy.standalone.entrypoint.probe"),
        patch("deploy.standalone.entrypoint.write_standalone_status"),
        patch("deploy.standalone.entrypoint.start_postgres"),
        patch("deploy.standalone.entrypoint.ensure_backup_grants"),
        patch("deploy.standalone.entrypoint.OpsSocketServer") as mock_ops_warm,
        patch("subprocess.Popen"),
        patch("deploy.standalone.entrypoint.supervisor_loop", return_value=0),
    ):
        mock_warm_instance = MagicMock()
        mock_ops_warm.return_value = mock_warm_instance
        ret_warm = entrypoint_main()
        assert ret_warm == 0
        assert mock_warm_instance.start.called

    # 6. Test handle_signal invocation
    import signal

    with (
        patch("os.getuid", return_value=0),
        patch("deploy.standalone.entrypoint.load_or_create_keyring", return_value=mock_keyring),
        patch("deploy.standalone.entrypoint.probe"),
        patch("deploy.standalone.entrypoint.write_standalone_status"),
        patch("deploy.standalone.entrypoint.start_postgres"),
        patch("deploy.standalone.entrypoint.ensure_backup_grants"),
        patch("deploy.standalone.entrypoint.OpsSocketServer") as mock_ops_sig,
        patch("subprocess.Popen"),
        patch("signal.signal") as mock_signal,
        patch("deploy.standalone.entrypoint.supervisor_loop", return_value=0),
    ):
        mock_ops_sig.return_value = MagicMock()
        entrypoint_main()
        assert mock_signal.called
        sig_handler = mock_signal.call_args_list[0][0][1]
        with (
            patch("deploy.standalone.entrypoint.shutdown_uvicorn"),
            patch("deploy.standalone.entrypoint.stop_postgres"),
            pytest.raises(SystemExit) as exc_sig,
        ):
            sig_handler(signal.SIGTERM, None)
        assert exc_sig.value.code == 0

    # 7. build_child_env without db_url and without keyring
    env_default = build_child_env(db_url=None, keyring=None, run_dir=str(tmp_path))
    assert "postgresql+asyncpg://kanban_app@/kanban" in env_default["DATABASE_URL"]

    # 8. Warm start with ephemeral warning and missing kanban.conf (triggers configure_postgres)
    mock_ephemeral_status = MagicMock(persistent_volume=False)
    (pgdata / "conf.d" / "kanban.conf").unlink(missing_ok=True)
    with (
        patch("os.getuid", return_value=0),
        patch("deploy.standalone.entrypoint.load_or_create_keyring", return_value=mock_keyring),
        patch("deploy.standalone.entrypoint.probe", return_value=mock_ephemeral_status),
        patch("deploy.standalone.entrypoint.write_standalone_status"),
        patch("deploy.standalone.entrypoint.emit_ephemeral_warning") as mock_warn,
        patch("deploy.standalone.entrypoint.configure_postgres") as mock_cfg,
        patch("deploy.standalone.entrypoint.start_postgres"),
        patch("deploy.standalone.entrypoint.ensure_backup_grants"),
        patch("deploy.standalone.entrypoint.OpsSocketServer", return_value=MagicMock()),
        patch("subprocess.Popen"),
        patch("deploy.standalone.entrypoint.supervisor_loop", return_value=0),
    ):
        entrypoint_main()
        assert mock_warn.called
        assert mock_cfg.called

    # 9. Warm start KeyringError exits 78
    with (
        patch("os.getuid", return_value=0),
        patch(
            "deploy.standalone.entrypoint.load_or_create_keyring",
            side_effect=KeyringError("Keyring unreadable"),
        ),
        patch("deploy.standalone.entrypoint.probe", return_value=mock_ephemeral_status),
        patch("deploy.standalone.entrypoint.write_standalone_status"),
    ):
        ret_kr_warm = entrypoint_main()
        assert ret_kr_warm == 78


def test_resolve_status_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test resolve_status_path resolution precedence."""
    from deploy.standalone.entrypoint import resolve_status_path

    # 1. KB_STANDALONE_STATUS_PATH
    custom_path = str(tmp_path / "custom_status.json")
    monkeypatch.setenv("KB_STANDALONE_STATUS_PATH", custom_path)
    assert resolve_status_path() == Path(custom_path)

    # 2. KB_RUN_DIR
    monkeypatch.delenv("KB_STANDALONE_STATUS_PATH", raising=False)
    monkeypatch.setenv("KB_RUN_DIR", str(tmp_path / "run"))
    assert resolve_status_path() == Path(tmp_path / "run" / "standalone_status.json")

    # 3. Default
    monkeypatch.delenv("KB_RUN_DIR", raising=False)
    assert resolve_status_path().name == "standalone_status.json"
