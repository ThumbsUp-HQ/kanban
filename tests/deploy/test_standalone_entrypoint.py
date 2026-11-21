"""Unit tests for deploy.standalone entrypoint and configuration writer."""

from __future__ import annotations

import runpy
import signal
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from deploy.standalone.entrypoint import (
    _PASSTHROUGH_ENV_VARS,
    BIN_ALEMBIC,
    BIN_INITDB,
    BIN_PG_CTL,
    BIN_PG_ISREADY,
    BIN_SETPRIV,
    BIN_UVICORN,
    _compute_migrations_digest,
    bootstrap_database,
    build_child_env,
    build_uvicorn_command,
    ensure_backup_grants,
    initialize_cluster,
    log_phase,
    main,
    run_as_postgres,
    run_migrations,
    shutdown_uvicorn,
    start_postgres,
    supervisor_loop,
)
from deploy.standalone.keyring import Keyring, KeyringError
from deploy.standalone.pg_config import configure_postgres


# -----------------------------------------------------------------------------
# Case 1: Positive First Boot
# -----------------------------------------------------------------------------
def test_case_1_first_boot(  # noqa: PLR0915
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First boot (no PG_VERSION) runs initdb, pg_ctl, bootstrap, migrations, and uvicorn."""
    pgdata = tmp_path / "pgdata"
    alembic_ini = tmp_path / "alembic.ini"
    alembic_ini.write_text("[alembic]\n", encoding="utf-8")

    recorded_runs: list[dict[str, Any]] = []

    def mock_run(
        cmd: list[str],
        *,
        timeout: float = 30.0,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        recorded_runs.append(
            {
                "cmd": cmd,
                "timeout": timeout,
                "check": check,
                "env": env,
            }
        )
        stdout = "1" if "-tAc" in cmd else ""
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=stdout, stderr="")

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.returncode = 0

    def mock_popen(
        cmd: list[str],
        env: dict[str, str] | None = None,
        *,
        shell: bool = False,
        text: bool = True,
    ) -> MagicMock:
        recorded_runs.append({"popen_cmd": cmd, "env": env, "shell": shell, "text": text})
        return mock_proc

    chown_calls: list[tuple[str, int | str, int | str]] = []
    chmod_calls: list[tuple[str, int]] = []

    def mock_chown(path: str, user: int | str, group: int | str) -> None:
        chown_calls.append((path, user, group))

    def mock_chmod(self: Path, mode: int) -> None:
        chmod_calls.append((str(self), mode))

    orig_is_dir = Path.is_dir

    def mock_is_dir(self: Path) -> bool:
        if str(self) == "/run/kanban":
            return True
        return orig_is_dir(self)

    orig_mkdir = Path.mkdir

    def mock_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        if str(self) == "/run/kanban":
            return
        orig_mkdir(self, *args, **kwargs)

    monkeypatch.setattr("shutil.chown", mock_chown)
    monkeypatch.setattr(Path, "chmod", mock_chmod)
    monkeypatch.setattr(Path, "is_dir", mock_is_dir)
    monkeypatch.setattr(Path, "mkdir", mock_mkdir)
    monkeypatch.setattr("deploy.standalone.entrypoint.run_as_postgres", mock_run)
    monkeypatch.setattr(subprocess, "Popen", mock_popen)
    monkeypatch.setattr("os.getuid", lambda: 0)

    monkeypatch.setenv("KB_PGDATA_DIR", str(pgdata))
    monkeypatch.setenv("KB_RUN_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("KB_ALEMBIC_INI", str(alembic_ini))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    rc = main([])
    assert rc == 0

    # Assert chown and chmod calls for data_dir, backups_dir, and /run/kanban
    assert (str(tmp_path), 65532, 65532) in chown_calls
    assert (str(tmp_path / "backups"), 65532, 65532) in chown_calls
    assert ("/run/kanban", 65532, 65532) in chown_calls
    assert (str(tmp_path), 0o775) in chmod_calls
    assert (str(tmp_path / "backups"), 0o775) in chmod_calls
    assert ("/run/kanban", 0o775) in chmod_calls

    commands = [r.get("cmd") for r in recorded_runs if "cmd" in r]

    # 1. Assert initdb command structure
    initdb_calls = [c for c in commands if c and BIN_INITDB in c]
    assert len(initdb_calls) == 1
    assert "--encoding=UTF8" in initdb_calls[0]
    assert "--locale=C.UTF-8" in initdb_calls[0]
    assert "--auth-host=reject" in initdb_calls[0]

    # 2. Assert pg_ctl start called
    pg_start_calls = [c for c in commands if c and BIN_PG_CTL in c and "start" in c]
    assert len(pg_start_calls) == 1

    # 3. Assert alembic upgrade head called
    alembic_calls = [c for c in commands if c and BIN_ALEMBIC in c]
    assert len(alembic_calls) == 1
    assert "upgrade" in alembic_calls[0]
    assert "head" in alembic_calls[0]

    # 4. Assert ALTER ROLE kanban_migrator NOLOGIN called
    nologin_calls = [c for c in commands if c and "ALTER ROLE kanban_migrator NOLOGIN;" in c]
    assert len(nologin_calls) == 1

    # 5. Assert Uvicorn Popen called
    popen_calls = [r for r in recorded_runs if "popen_cmd" in r]
    assert len(popen_calls) == 1
    assert popen_calls[0]["popen_cmd"][0] == BIN_SETPRIV
    assert BIN_UVICORN in popen_calls[0]["popen_cmd"]


# -----------------------------------------------------------------------------
# Case 2: Positive Warm Boot and External DB
# -----------------------------------------------------------------------------
def test_case_2_warm_boot_skips_initdb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Warm boot with existing PG_VERSION skips initdb and runs migrations if present."""
    pgdata = tmp_path / "pgdata"
    pgdata.mkdir(parents=True)
    (pgdata / "PG_VERSION").write_text("16\n", encoding="utf-8")

    recorded_cmds: list[list[str]] = []

    def mock_run(
        cmd: list[str],
        *,
        timeout: float = 30.0,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, env)
        recorded_cmds.append(cmd)
        stdout = "1" if "-tAc" in cmd else ""
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=stdout, stderr="")

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.returncode = 0

    monkeypatch.setattr("deploy.standalone.entrypoint.run_as_postgres", mock_run)
    monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=mock_proc))
    monkeypatch.setattr("os.getuid", lambda: 0)

    monkeypatch.setenv("KB_PGDATA_DIR", str(pgdata))
    monkeypatch.setenv("KB_RUN_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("KB_ALEMBIC_INI", str(tmp_path / "missing_alembic.ini"))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    rc = main([])
    assert rc == 0

    # Assert initdb was NEVER called
    initdb_calls = [c for c in recorded_cmds if BIN_INITDB in c]
    assert len(initdb_calls) == 0


def test_case_2_external_db_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When DATABASE_URL is set, MODE=external_db execv Uvicorn with zero PG commands."""
    recorded_execv: list[tuple[str, list[str]]] = []

    def mock_execv(path: str, args: list[str]) -> None:
        recorded_execv.append((path, args))
        raise SystemExit(0)

    monkeypatch.setattr("os.execv", mock_execv)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://remote-db:5432/kanban")
    monkeypatch.setenv("KB_STANDALONE_STATUS_PATH", str(tmp_path / "standalone_status.json"))

    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 0
    assert len(recorded_execv) == 1
    path, args = recorded_execv[0]
    assert path == BIN_SETPRIV
    assert "--reuid=65532" in args
    assert BIN_UVICORN in args


# -----------------------------------------------------------------------------
# Case 3: Security Configuration, Conf, Ident, Child Env, No Shell
# -----------------------------------------------------------------------------
def test_case_3_security_configuration(tmp_path: Path) -> None:
    """Validate zero host lines in pg_hba.conf, listen_addresses empty, and strict child env."""
    pgdata = tmp_path / "pgdata"
    run_dir = str(tmp_path / "run")

    # Create dummy postgresql.conf
    pgdata.mkdir(parents=True)
    main_conf = pgdata / "postgresql.conf"
    main_conf.write_text("# main config\n", encoding="utf-8")

    configure_postgres(pgdata, run_dir=run_dir)

    # 1. Assert pg_hba.conf contains zero host lines
    hba_text = (pgdata / "pg_hba.conf").read_text(encoding="utf-8")
    for line in hba_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            assert not stripped.startswith("host"), f"Forbidden host line: {stripped}"
            assert stripped.startswith("local")

    # 2. Assert kanban.conf has listen_addresses = ''
    kanban_conf = (pgdata / "conf.d" / "kanban.conf").read_text(encoding="utf-8")
    assert "listen_addresses = ''" in kanban_conf
    assert f"unix_socket_directories = '{run_dir}'" in kanban_conf
    assert "unix_socket_permissions = 0770" in kanban_conf

    # 3. Assert postgresql.conf has include_dir = 'conf.d'
    updated_main = main_conf.read_text(encoding="utf-8")
    assert "include_dir = 'conf.d'" in updated_main

    # Re-run configure_postgres to verify idempotency when include_dir already exists
    configure_postgres(pgdata, run_dir=run_dir)
    assert main_conf.read_text(encoding="utf-8").count("include_dir = 'conf.d'") == 1

    # 4. Assert Uvicorn command contains security flags
    cmd = build_uvicorn_command()
    assert cmd[0] == BIN_SETPRIV
    assert "--reuid=65532" in cmd
    assert "--regid=65532" in cmd
    assert "--clear-groups" in cmd
    assert "--inh-caps=-all" in cmd
    assert "--no-new-privs" in cmd

    # 5. Assert child env allowlist strictly enforced
    child_env = build_child_env()
    assert set(child_env.keys()) == {
        "PATH",
        "KB_WEB_DIST",
        "KB_DEPLOYMENT_MODE",
        "DATABASE_URL",
        "LANG",
        "KB_STANDALONE_STATUS_PATH",
        "KANBAN_ATTACHMENT_DIR",
    }
    assert child_env["KB_DEPLOYMENT_MODE"] == "standalone"

    kr = Keyring(
        version=1,
        created_at="2026-01-01T00:00:00Z",
        master_kek=b"\x01" * 32,
        auth_pepper=b"\x02" * 32,
        session_hmac_key=b"\x03" * 32,
        kanban_app_password=b"\x04" * 32,
        kanban_migrator_password=b"\x05" * 32,
    )
    kr_env = build_child_env(keyring=kr)
    assert set(kr_env.keys()) == {
        "PATH",
        "KB_WEB_DIST",
        "KB_DEPLOYMENT_MODE",
        "DATABASE_URL",
        "LANG",
        "KB_STANDALONE_STATUS_PATH",
        "KANBAN_ATTACHMENT_DIR",
        "KB_MASTER_KEK_B64",
        "KB_AUTH_PEPPER_B64",
        "KB_SESSION_HMAC_KEY_B64",
    }
    assert kr_env["KB_MASTER_KEK_B64"] == kr.master_kek_b64


def test_trusted_proxies_passthrough_and_uvicorn_non_wildcard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify KB_TRUSTED_PROXIES is passed to child env and safe non-wildcard uvicorn command."""
    monkeypatch.setenv("KB_TRUSTED_PROXIES", "10.0.0.0/8,172.16.0.0/12")
    monkeypatch.delenv("KB_FORWARDED_ALLOW_IPS", raising=False)

    env = build_child_env()
    assert env["KB_TRUSTED_PROXIES"] == "10.0.0.0/8,172.16.0.0/12"

    cmd = build_uvicorn_command()
    assert "--forwarded-allow-ips=10.0.0.0/8,172.16.0.0/12" in cmd

    # When both are unset, default is safe non-wildcard
    monkeypatch.delenv("KB_TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("KANBAN_TRUSTED_PROXIES", raising=False)
    cmd_default = build_uvicorn_command()
    assert '--forwarded-allow-ips=""' in cmd_default


def test_setup_token_file_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify KB_SETUP_TOKEN_FILE is included in _PASSTHROUGH_ENV_VARS and passed to child env."""
    assert "KB_SETUP_TOKEN_FILE" in _PASSTHROUGH_ENV_VARS
    monkeypatch.setenv("KB_SETUP_TOKEN_FILE", "/custom/token_path")
    env = build_child_env()
    assert env["KB_SETUP_TOKEN_FILE"] == "/custom/token_path"


# -----------------------------------------------------------------------------
# Case 4: Negative Error Handlers (Non-root, Timeout, Migration Failure)
# -----------------------------------------------------------------------------
def test_case_4_non_root_uid_exits_78(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-root UID in standalone mode exits 78 with STANDALONE_REQUIRES_ROOT_ENTRYPOINT."""
    monkeypatch.setattr("os.getuid", lambda: 1000)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    rc = main([])
    captured = capsys.readouterr()

    assert rc == 78
    assert "STANDALONE_REQUIRES_ROOT_ENTRYPOINT" in captured.err


def test_case_4_pg_start_timeout_exits_70(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pg_isready never succeeding within timeout calls pg_ctl stop and exits 70."""
    pgdata = tmp_path / "pgdata"
    pgdata.mkdir(parents=True)
    (pgdata / "postgresql.conf").write_text("", encoding="utf-8")

    stopped_calls: list[list[str]] = []

    def mock_run(
        cmd: list[str],
        *,
        timeout: float = 30.0,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, env)
        if BIN_PG_ISREADY in cmd:
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="")
        if BIN_PG_CTL in cmd and "stop" in cmd:
            stopped_calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    simulated_time = 0.0

    def mock_monotonic() -> float:
        nonlocal simulated_time
        simulated_time += 4.0
        return simulated_time

    monkeypatch.setattr("time.monotonic", mock_monotonic)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    monkeypatch.setattr("deploy.standalone.entrypoint.run_as_postgres", mock_run)

    with pytest.raises(SystemExit) as exc_info:
        start_postgres(pgdata, run_dir=str(tmp_path / "run"))

    assert exc_info.value.code == 70
    assert len(stopped_calls) == 1
    assert "stop" in stopped_calls[0]
    assert "immediate" in stopped_calls[0]


def test_case_4_migration_failure_exits_70(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Alembic upgrade failure calls pg_ctl stop and exits 70."""
    pgdata = tmp_path / "pgdata"
    alembic_ini = tmp_path / "alembic.ini"
    alembic_ini.write_text("[alembic]\n", encoding="utf-8")

    stopped_calls: list[list[str]] = []

    def mock_run(
        cmd: list[str],
        *,
        timeout: float = 30.0,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, env)
        if BIN_ALEMBIC in cmd:
            return subprocess.CompletedProcess(
                cmd, returncode=1, stdout="", stderr="Migration failed syntax error"
            )
        if BIN_PG_CTL in cmd and "stop" in cmd:
            stopped_calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("deploy.standalone.entrypoint.run_as_postgres", mock_run)

    with pytest.raises(SystemExit) as exc_info:
        run_migrations(pgdata, alembic_ini, run_dir=str(tmp_path / "run"))

    assert exc_info.value.code == 70
    assert len(stopped_calls) == 1
    assert "fast" in stopped_calls[0]


# -----------------------------------------------------------------------------
# Case 5: Boundary Signals, Termination Escalation, and Postmaster Death
# -----------------------------------------------------------------------------
def test_case_5_shutdown_uvicorn_escalates_to_sigkill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uvicorn ignoring SIGTERM for > 10s receives SIGKILL."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None

    simulated_time = 0.0

    def mock_monotonic() -> float:
        nonlocal simulated_time
        simulated_time += 4.0
        return simulated_time

    monkeypatch.setattr("time.monotonic", mock_monotonic)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    shutdown_uvicorn(mock_proc)

    mock_proc.send_signal.assert_called_once()
    mock_proc.kill.assert_called_once()
    mock_proc.wait.assert_called_once()


def test_case_5_shutdown_uvicorn_clean_exit() -> None:
    """Uvicorn exiting cleanly after SIGTERM does not receive SIGKILL."""
    mock_proc = MagicMock()
    # First call None, subsequent call 0 (terminated)
    mock_proc.poll.side_effect = [None, 0]

    shutdown_uvicorn(mock_proc)

    mock_proc.send_signal.assert_called_once()
    mock_proc.kill.assert_not_called()


def test_case_5_shutdown_uvicorn_already_dead() -> None:
    """shutdown_uvicorn on an already terminated process is a no-op."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0

    shutdown_uvicorn(mock_proc)
    mock_proc.send_signal.assert_not_called()


def test_case_5_supervisor_detects_postmaster_death(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When PostgreSQL postmaster dies during supervisor loop, Uvicorn terminates and exits 70."""
    pgdata = tmp_path / "pgdata"
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None

    def mock_run(
        cmd: list[str],
        *,
        timeout: float = 30.0,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, env)
        if BIN_PG_CTL in cmd and "status" in cmd:
            return subprocess.CompletedProcess(
                cmd, returncode=3, stdout="", stderr="no server running"
            )
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    simulated_time = 0.0

    def mock_monotonic() -> float:
        nonlocal simulated_time
        simulated_time += 1.0
        return simulated_time

    monkeypatch.setattr("deploy.standalone.entrypoint.run_as_postgres", mock_run)
    monkeypatch.setattr("time.monotonic", mock_monotonic)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    rc = supervisor_loop(mock_proc, pgdata)
    captured = capsys.readouterr()

    assert rc == 70
    assert "PG_DIED" in captured.err
    mock_proc.send_signal.assert_called_once()


def test_signal_handler_clean_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Directly test the signal handler installed in main."""
    registered_handlers: dict[int, Any] = {}

    def mock_signal(sig: int, handler: object) -> None:
        registered_handlers[sig] = handler

    monkeypatch.setattr(signal, "signal", mock_signal)
    monkeypatch.setattr("deploy.standalone.entrypoint.supervisor_loop", lambda *_args: 0)
    monkeypatch.setattr("deploy.standalone.entrypoint.run_as_postgres", MagicMock())
    monkeypatch.setattr("deploy.standalone.entrypoint.start_postgres", MagicMock())
    monkeypatch.setattr("deploy.standalone.entrypoint.initialize_cluster", MagicMock())
    monkeypatch.setattr("deploy.standalone.entrypoint.bootstrap_database", MagicMock())
    monkeypatch.setattr("deploy.standalone.entrypoint.run_migrations", MagicMock())
    monkeypatch.setattr("deploy.standalone.entrypoint.configure_postgres", MagicMock())
    monkeypatch.setattr(subprocess, "Popen", MagicMock())
    monkeypatch.setattr("os.getuid", lambda: 0)

    monkeypatch.setenv("KB_PGDATA_DIR", str(tmp_path / "pgdata"))
    monkeypatch.setenv("KB_RUN_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("KB_STANDALONE_STATUS_PATH", str(tmp_path / "standalone_status.json"))

    main([])
    assert signal.SIGTERM in registered_handlers

    # Invoke signal handler
    stopped_pg: list[str] = []
    monkeypatch.setattr(
        "deploy.standalone.entrypoint.stop_postgres",
        lambda _p, **_k: stopped_pg.append("stopped"),
    )

    with pytest.raises(SystemExit) as exc_info:
        registered_handlers[signal.SIGTERM](signal.SIGTERM, None)

    assert exc_info.value.code == 0
    assert len(stopped_pg) == 1


# -----------------------------------------------------------------------------
# Additional Unit Coverage Tests
# -----------------------------------------------------------------------------
def test_log_phase(capsys: pytest.CaptureFixture[str]) -> None:
    """Log phase output matches expected formatting."""
    log_phase("test_phase", "sample message")
    captured = capsys.readouterr()
    assert "[kanban-standalone]" in captured.out
    assert "test_phase: sample message" in captured.out


def test_initialize_cluster_called_process_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Initdb error raises CalledProcessError and writes INITDB_FAILED."""
    pgdata = tmp_path / "pgdata"

    def mock_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, ["initdb"], stderr="initdb failed")

    monkeypatch.setattr("deploy.standalone.entrypoint.run_as_postgres", mock_run)

    with pytest.raises(subprocess.CalledProcessError):
        initialize_cluster(pgdata)


def test_bootstrap_database_creates_database_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap_database executes CREATE DATABASE when check returns not found."""
    recorded_psql: list[str] = []

    def mock_run(
        cmd: list[str],
        *,
        timeout: float = 30.0,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, env)
        if "-tAc" in cmd:
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
        if "-c" in cmd:
            idx = cmd.index("-c")
            recorded_psql.append(cmd[idx + 1])
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("deploy.standalone.entrypoint.run_as_postgres", mock_run)
    bootstrap_database(run_dir=str(tmp_path))

    create_db_calls = [s for s in recorded_psql if "CREATE DATABASE kanban" in s]
    assert len(create_db_calls) == 1


def test_keyring_error_exits_78(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When load_or_create_keyring raises KeyringError, main exits 78 with KEYRING_INVALID."""
    msg = "Insecure keyring permissions"

    def mock_keyring_fail(*_args: object, **_kwargs: object) -> None:
        raise KeyringError(msg)

    monkeypatch.setattr("deploy.standalone.entrypoint.load_or_create_keyring", mock_keyring_fail)
    monkeypatch.setattr("os.getuid", lambda: 0)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KB_PGDATA_DIR", str(tmp_path / "pgdata"))
    monkeypatch.setenv("KB_RUN_DIR", str(tmp_path / "run"))

    rc = main([])
    assert rc == 78
    captured = capsys.readouterr()
    assert "KEYRING_INVALID" in captured.err
    assert "Insecure keyring permissions" in captured.err


def test_bootstrap_database_with_keyring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap_database applies SCRAM passwords when keyring is provided."""
    recorded_psql: list[str] = []

    def mock_run(
        cmd: list[str],
        *,
        timeout: float = 30.0,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, env)
        if "-tAc" in cmd:
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="1", stderr="")
        if "-c" in cmd:
            idx = cmd.index("-c")
            recorded_psql.append(cmd[idx + 1])
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("deploy.standalone.entrypoint.run_as_postgres", mock_run)

    kr = Keyring(
        version=1,
        created_at="2026-01-01T00:00:00Z",
        master_kek=b"\x01" * 32,
        auth_pepper=b"\x02" * 32,
        session_hmac_key=b"\x03" * 32,
        kanban_app_password=b"\x04" * 32,
        kanban_migrator_password=b"\x05" * 32,
    )

    bootstrap_database(run_dir=str(tmp_path), keyring=kr)

    scram_calls = [s for s in recorded_psql if "SCRAM-SHA-256$" in s]
    assert len(scram_calls) == 1
    assert "ALTER ROLE kanban_app PASSWORD 'SCRAM-SHA-256$" in scram_calls[0]
    assert "ALTER ROLE kanban_migrator PASSWORD 'SCRAM-SHA-256$" in scram_calls[0]


def test_run_as_postgres_real_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify run_as_postgres wraps commands with setpriv correctly."""
    recorded_full: list[list[str]] = []

    def mock_sub_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        recorded_full.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_sub_run)
    run_as_postgres(["echo", "hello"], timeout=5.0)

    assert len(recorded_full) == 1
    assert recorded_full[0][:7] == [
        BIN_SETPRIV,
        "--reuid=postgres",
        "--regid=postgres",
        "--init-groups",
        "--inh-caps=-all",
        "--no-new-privs",
        "--",
    ]
    assert recorded_full[0][7:] == ["echo", "hello"]


def test_warm_boot_stale_alembic_digest_runs_migrations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing cluster with stale .alembic_head digest runs alembic upgrade head."""
    pgdata = tmp_path / "pgdata"
    pgdata.mkdir(parents=True)
    (pgdata / "PG_VERSION").write_text("16\n", encoding="utf-8")
    (pgdata / ".alembic_head").write_text("stale-old-digest\n", encoding="utf-8")
    alembic_ini = tmp_path / "alembic.ini"
    alembic_ini.write_text("[alembic]\n", encoding="utf-8")

    recorded_cmds: list[list[str]] = []

    def mock_run(
        cmd: list[str],
        *,
        timeout: float = 30.0,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        _ = (timeout, check, env)
        recorded_cmds.append(cmd)
        stdout = "1" if "-tAc" in cmd else ""
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=stdout, stderr="")

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.returncode = 0

    monkeypatch.setattr("deploy.standalone.entrypoint.run_as_postgres", mock_run)
    monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=mock_proc))
    monkeypatch.setattr("os.getuid", lambda: 0)

    monkeypatch.setenv("KB_PGDATA_DIR", str(pgdata))
    monkeypatch.setenv("KB_RUN_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("KB_ALEMBIC_INI", str(alembic_ini))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    rc = main([])
    assert rc == 0

    # Assert initdb was skipped, but alembic upgrade head WAS executed
    initdb_calls = [c for c in recorded_cmds if BIN_INITDB in c]
    assert len(initdb_calls) == 0
    alembic_calls = [c for c in recorded_cmds if BIN_ALEMBIC in c]
    assert len(alembic_calls) == 1
    assert "upgrade" in alembic_calls[0]
    assert "head" in alembic_calls[0]
    assert (pgdata / ".alembic_head").read_text(encoding="utf-8").strip() != "stale-old-digest"


def test_ensure_backup_grants_executes_alembic_version_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate ensure_backup_grants grants SELECT on alembic_version (KANBA-208)."""
    executed_sqls: list[str] = []

    def mock_run_psql(sql: str, dbname: str = "postgres", run_dir: str = "/tmp") -> None:
        _ = (dbname, run_dir)
        executed_sqls.append(sql)

    monkeypatch.setattr("deploy.standalone.entrypoint.run_psql_script", mock_run_psql)

    ensure_backup_grants(run_dir="/tmp/test_run")
    assert len(executed_sqls) == 1
    assert "alembic_version" in executed_sqls[0]
    assert "GRANT SELECT ON TABLE alembic_version TO kanban_app" in executed_sqls[0]


def test_first_boot_chown_oserror_handled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When shutil.chown raises OSError, main catches it, logs a warning, and continues."""
    pgdata = tmp_path / "pgdata"
    alembic_ini = tmp_path / "alembic.ini"
    alembic_ini.write_text("[alembic]\n", encoding="utf-8")

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.returncode = 0

    monkeypatch.setattr(
        "deploy.standalone.entrypoint.run_as_postgres",
        lambda *_a, **_k: subprocess.CompletedProcess([], 0, "1", ""),
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: mock_proc)
    monkeypatch.setattr("os.getuid", lambda: 0)
    msg = "Permission denied"
    monkeypatch.setattr("shutil.chown", MagicMock(side_effect=OSError(msg)))

    monkeypatch.setenv("KB_PGDATA_DIR", str(pgdata))
    monkeypatch.setenv("KB_RUN_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("KB_ALEMBIC_INI", str(alembic_ini))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    rc = main([])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Warning: chown failed: Permission denied" in captured.out


def test_first_boot_run_kanban_mkdir_oserror_handled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When /run/kanban mkdir raises OSError, main logs a warning and proceeds."""
    pgdata = tmp_path / "pgdata"
    alembic_ini = tmp_path / "alembic.ini"
    alembic_ini.write_text("[alembic]\n", encoding="utf-8")

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.returncode = 0

    orig_mkdir = Path.mkdir

    def mock_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        if str(self) == "/run/kanban":
            msg = "Read-only filesystem"
            raise OSError(msg)
        orig_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mock_mkdir)
    monkeypatch.setattr(
        "deploy.standalone.entrypoint.run_as_postgres",
        lambda *_a, **_k: subprocess.CompletedProcess([], 0, "1", ""),
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: mock_proc)
    monkeypatch.setattr("os.getuid", lambda: 0)
    monkeypatch.setattr("shutil.chown", lambda *_a, **_k: None)

    monkeypatch.setenv("KB_PGDATA_DIR", str(pgdata))
    monkeypatch.setenv("KB_RUN_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("KB_ALEMBIC_INI", str(alembic_ini))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    rc = main([])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Warning: mkdir /run/kanban failed: Read-only filesystem" in captured.out


def test_warm_boot_concurrent_uvicorn_and_postgres(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Full warm boot: PG_VERSION present, migrations_current True, keyring present."""
    pgdata = tmp_path / "pgdata"
    pgdata.mkdir(parents=True)
    (pgdata / "PG_VERSION").write_text("16\n", encoding="utf-8")

    digest = _compute_migrations_digest()
    (pgdata / ".alembic_head").write_text(digest, encoding="utf-8")

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(parents=True)
    keyring_file = secrets_dir / "keyring.json"
    keyring_file.write_text("{}", encoding="utf-8")

    kr = Keyring(
        version=1,
        created_at="2026-01-01T00:00:00Z",
        master_kek=b"\x01" * 32,
        auth_pepper=b"\x02" * 32,
        session_hmac_key=b"\x03" * 32,
        kanban_app_password=b"\x04" * 32,
        kanban_migrator_password=b"\x05" * 32,
    )
    monkeypatch.setattr("deploy.standalone.entrypoint.load_or_create_keyring", lambda _p: kr)

    recorded_calls: list[str] = []

    def mock_start_pg(path: Path, run_dir: str = "/tmp") -> None:
        _ = (path, run_dir)
        recorded_calls.append("start_postgres")

    def mock_ensure_grants(run_dir: str = "/tmp") -> None:
        _ = run_dir
        recorded_calls.append("ensure_backup_grants")

    def mock_configure_pg(path: Path, run_dir: str = "/tmp") -> None:
        _ = (path, run_dir)
        recorded_calls.append("configure_postgres")

    def mock_supervisor(proc: object, path: Path) -> int:
        _ = (proc, path)
        recorded_calls.append("supervisor_loop")
        return 0

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0

    def mock_popen(cmd: list[str], **kwargs: object) -> MagicMock:
        _ = (cmd, kwargs)
        recorded_calls.append("uvicorn_popen")
        return mock_proc

    monkeypatch.setattr("deploy.standalone.entrypoint.start_postgres", mock_start_pg)
    monkeypatch.setattr("deploy.standalone.entrypoint.ensure_backup_grants", mock_ensure_grants)
    monkeypatch.setattr("deploy.standalone.entrypoint.configure_postgres", mock_configure_pg)
    monkeypatch.setattr("deploy.standalone.entrypoint.supervisor_loop", mock_supervisor)
    monkeypatch.setattr(subprocess, "Popen", mock_popen)
    monkeypatch.setattr("os.getuid", lambda: 0)
    monkeypatch.setattr("shutil.chown", lambda *_a, **_k: None)

    monkeypatch.setenv("KB_PGDATA_DIR", str(pgdata))
    monkeypatch.setenv("KB_RUN_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("KB_KEYRING_PATH", str(keyring_file))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    rc = main([])
    assert rc == 0
    assert "configure_postgres" in recorded_calls
    assert "uvicorn_popen" in recorded_calls
    assert "start_postgres" in recorded_calls
    assert "ensure_backup_grants" in recorded_calls
    assert "supervisor_loop" in recorded_calls

    captured = capsys.readouterr()
    assert "migrations up to date, skipping alembic upgrade" in captured.out


def test_warm_boot_keyring_error_exits_78(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When warm boot encounters KeyringError, it exits 78."""
    pgdata = tmp_path / "pgdata"
    pgdata.mkdir(parents=True)
    (pgdata / "PG_VERSION").write_text("16\n", encoding="utf-8")

    digest = _compute_migrations_digest()
    (pgdata / ".alembic_head").write_text(digest, encoding="utf-8")

    keyring_file = tmp_path / "keyring.json"
    keyring_file.write_text("{}", encoding="utf-8")

    def mock_keyring_fail(*_a: object, **_k: object) -> None:
        msg = "Insecure warm keyring permissions"
        raise KeyringError(msg)

    monkeypatch.setattr("deploy.standalone.entrypoint.load_or_create_keyring", mock_keyring_fail)
    monkeypatch.setattr("os.getuid", lambda: 0)
    monkeypatch.setattr("shutil.chown", lambda *_a, **_k: None)

    monkeypatch.setenv("KB_PGDATA_DIR", str(pgdata))
    monkeypatch.setenv("KB_RUN_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("KB_KEYRING_PATH", str(keyring_file))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    rc = main([])
    assert rc == 78
    captured = capsys.readouterr()
    assert "KEYRING_INVALID" in captured.err
    assert "Insecure warm keyring permissions" in captured.err


def test_ensure_backup_grants_handles_exception(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """ensure_backup_grants catches and logs exceptions without raising."""

    def mock_fail(*_a: object, **_k: object) -> None:
        msg = "db connection refused"
        raise RuntimeError(msg)

    monkeypatch.setattr("deploy.standalone.entrypoint.run_psql_script", mock_fail)
    ensure_backup_grants(run_dir="/tmp/test_run")

    captured = capsys.readouterr()
    assert "Warning: grant SELECT on alembic_version failed: db connection refused" in captured.out


def test_supervisor_loop_healthy_poll(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """supervisor_loop executes healthy pg_ctl status check and exits when uvicorn cleanly exits."""
    pgdata = tmp_path / "pgdata"
    mock_proc = MagicMock()
    mock_proc.poll.side_effect = [None, 0]
    mock_proc.returncode = 0

    checked_cmds: list[list[str]] = []

    def mock_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        checked_cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    simulated_time = 0.0

    def mock_monotonic() -> float:
        nonlocal simulated_time
        simulated_time += 3.0
        return simulated_time

    monkeypatch.setattr("deploy.standalone.entrypoint.run_as_postgres", mock_run)
    monkeypatch.setattr("time.monotonic", mock_monotonic)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    rc = supervisor_loop(mock_proc, pgdata)
    assert rc == 0
    assert any(BIN_PG_CTL in c and "status" in c for c in checked_cmds)


def test_compute_migrations_digest_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test _compute_migrations_digest branch edges."""
    orig_is_dir = Path.is_dir

    # Case 1: sql_dir does not exist
    def mock_is_dir_no_sql(self: Path) -> bool:
        if "sql" in str(self):
            return False
        return orig_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", mock_is_dir_no_sql)
    d1 = _compute_migrations_digest()
    assert len(d1) == 64

    # Case 2: neither candidates directory exists
    monkeypatch.setattr(Path, "is_dir", lambda _s: False)
    d2 = _compute_migrations_digest()
    assert d2 == ""


def test_entrypoint_dunder_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test __name__ == '__main__' invocation branch."""

    def mock_execv(_path: str, _args: list[str]) -> None:
        raise SystemExit(0)

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://remote-db:5432/kanban")
    monkeypatch.setenv("KB_STANDALONE_STATUS_PATH", str(tmp_path / "status.json"))
    monkeypatch.setattr("os.execv", mock_execv)
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("deploy.standalone.entrypoint", run_name="__main__")
    assert exc_info.value.code == 0
