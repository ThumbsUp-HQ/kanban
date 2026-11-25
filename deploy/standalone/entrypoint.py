"""Standalone single-container entrypoint for embedded PostgreSQL and Uvicorn.

Initializes an embedded PostgreSQL 16 instance accessible strictly via Unix domain
sockets, applies migrations under a dedicated migration role, drops privileges to
UID 65532 to run Uvicorn, and coordinates graceful shutdown under tini.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from deploy.standalone.keyring import (
    Keyring,
    KeyringError,
    compute_scram_sha256_verifier,
    load_or_create_keyring,
)
from deploy.standalone.pg_config import configure_postgres, generate_role_passwords_sql
from deploy.standalone.storage_probe import (
    DEFAULT_STATUS_PATH,
    emit_ephemeral_warning,
    probe,
    write_standalone_status,
)
from kanban.ops.backup_crypto import KeySource, PassphraseKeySource, RawKeySource
from kanban.ops.backup_service import create_backup, restore_backup

if TYPE_CHECKING:
    from collections.abc import Sequence

# Binary paths
BIN_SETPRIV: str = "/usr/bin/setpriv"
BIN_INITDB: str = "/usr/lib/postgresql/16/bin/initdb"
BIN_PG_CTL: str = "/usr/lib/postgresql/16/bin/pg_ctl"
BIN_PG_ISREADY: str = "/usr/lib/postgresql/16/bin/pg_isready"
BIN_PSQL: str = "/usr/lib/postgresql/16/bin/psql"
BIN_ALEMBIC: str = "/opt/kanban/.venv/bin/alembic"
BIN_UVICORN: str = "/opt/kanban/.venv/bin/uvicorn"

DEFAULT_PGDATA: Path = Path("/var/lib/kanban/data/pgdata")
DEFAULT_RUN_DIR: str = "/run/postgresql"
DEFAULT_ALEMBIC_INI: Path = Path("/opt/kanban/alembic.ini")

PG_CHECK_INTERVAL_SEC: float = 2.0
SHUTDOWN_TIMEOUT_SEC: float = 10.0

START_TIME: float = time.monotonic()


def log_phase(phase: str, message: str, *, level: str = "INFO") -> None:
    """Log a phase transition with monotonic elapsed milliseconds."""
    elapsed_ms = int((time.monotonic() - START_TIME) * 1000)
    icon = (
        "⛔"
        if level.upper() == "WARNING"
        else ("❌" if level.upper() in ("ERROR", "CRITICAL") else "👍")
    )
    sys.stdout.write(f"{icon} [kanban-standalone] [{elapsed_ms:05d}ms] {phase}: {message}\n")
    sys.stdout.flush()


def run_as_postgres(
    cmd: list[str],
    *,
    timeout: float = 30.0,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute a command as OS user 'postgres' via setpriv."""
    full_cmd = [
        BIN_SETPRIV,
        "--reuid=postgres",
        "--regid=postgres",
        "--init-groups",
        "--inh-caps=-all",
        "--no-new-privs",
        "--",
        *cmd,
    ]
    return subprocess.run(  # noqa: S603
        full_cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
        env=env,
    )


def run_as_postgres_bytes(
    cmd: list[str],
    *,
    timeout: float = 60.0,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Execute a command as OS user 'postgres' via setpriv returning binary stdout."""
    full_cmd = [
        BIN_SETPRIV,
        "--reuid=postgres",
        "--regid=postgres",
        "--init-groups",
        "--inh-caps=-all",
        "--no-new-privs",
        "--",
        *cmd,
    ]
    return subprocess.run(  # noqa: S603
        full_cmd,
        capture_output=True,
        timeout=timeout,
        check=check,
        env=env,
    )


def initialize_cluster(pgdata: Path) -> None:
    """Initialize a new PostgreSQL database cluster if PG_VERSION is absent."""
    if (pgdata / "PG_VERSION").is_file():
        log_phase("initdb", "existing cluster detected, skipping initdb")
        return

    log_phase("initdb", "initializing new database cluster")
    pgdata.mkdir(parents=True, exist_ok=True)
    cmd = [
        BIN_INITDB,
        "-D",
        str(pgdata),
        "--encoding=UTF8",
        "--locale=C.UTF-8",
        "--auth-local=peer",
        "--auth-host=reject",
        "--username=postgres",
    ]
    try:
        run_as_postgres(cmd, timeout=60.0)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"❌ INITDB_FAILED: {exc.stderr}\n")
        raise


def start_postgres(pgdata: Path, run_dir: str = DEFAULT_RUN_DIR) -> None:
    """Start PostgreSQL and wait for socket readiness."""
    log_phase("pg_start", "starting embedded PostgreSQL")
    cmd = [
        BIN_PG_CTL,
        "-D",
        str(pgdata),
        "-l",
        str(pgdata / "postgresql.log"),
        "-w",
        "-t",
        "10",
        "start",
        "-o",
        f"-c config_file={pgdata}/postgresql.conf",
    ]
    run_as_postgres(cmd, timeout=30.0)

    # Poll pg_isready until available or 10s deadline
    deadline = time.monotonic() + 10.0
    isready_cmd = [BIN_PG_ISREADY, "-h", run_dir]
    ready = False

    while time.monotonic() < deadline:
        res = run_as_postgres(isready_cmd, timeout=2.0, check=False)
        if res.returncode == 0:
            ready = True
            break
        time.sleep(0.05)

    if not ready:
        sys.stderr.write("❌ PG_START_TIMEOUT: postgres failed to start within 10s\n")
        stop_postgres(pgdata, mode="immediate")
        sys.exit(70)

    log_phase("pg_start", f"PostgreSQL is ready on {run_dir}")


def stop_postgres(pgdata: Path, mode: str = "fast") -> None:
    """Stop PostgreSQL via pg_ctl."""
    log_phase("pg_stop", f"stopping PostgreSQL (mode={mode})")
    cmd = [BIN_PG_CTL, "-D", str(pgdata), "stop", "-m", mode, "-t", "10"]
    run_as_postgres(cmd, timeout=15.0, check=False)


def run_psql_script(sql: str, dbname: str = "postgres", run_dir: str = DEFAULT_RUN_DIR) -> None:
    """Execute SQL commands via psql as postgres user."""
    cmd = [
        BIN_PSQL,
        "-h",
        run_dir,
        "-U",
        "postgres",
        "-v",
        "ON_ERROR_STOP=1",
        "-d",
        dbname,
        "-c",
        sql,
    ]
    run_as_postgres(cmd, timeout=30.0)


def bootstrap_database(
    run_dir: str = DEFAULT_RUN_DIR,
    keyring: Keyring | None = None,
) -> None:
    """Create roles, database, and extensions idempotently."""
    log_phase("bootstrap_sql", "creating roles and kanban database")

    # 1. Create roles if missing
    role_sql = """
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kanban_migrator') THEN
        CREATE ROLE kanban_migrator LOGIN;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kanban_app') THEN
        CREATE ROLE kanban_app LOGIN;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rls_reader') THEN
        CREATE ROLE app_rls_reader LOGIN;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kb_infra_owner') THEN
        CREATE ROLE kb_infra_owner NOLOGIN NOINHERIT NOBYPASSRLS;
      END IF;
    END
    $$;
    ALTER ROLE kanban_migrator NOSUPERUSER NOCREATEDB CREATEROLE NOREPLICATION BYPASSRLS;
    ALTER ROLE kanban_app      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    ALTER ROLE app_rls_reader  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    ALTER ROLE app_rls_reader  SET default_transaction_read_only = on;
    ALTER ROLE kb_infra_owner  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    GRANT kb_infra_owner TO kanban_migrator WITH ADMIN OPTION, INHERIT TRUE, SET TRUE;
    GRANT USAGE, CREATE ON SCHEMA public TO kb_infra_owner;
    """
    run_psql_script(role_sql, dbname="postgres", run_dir=run_dir)

    # 2. Apply role passwords if keyring is provided
    if keyring is not None:
        app_scram = compute_scram_sha256_verifier(keyring.kanban_app_password_str)
        mig_scram = compute_scram_sha256_verifier(keyring.kanban_migrator_password_str)
        pw_sql = generate_role_passwords_sql(app_scram, mig_scram)
        run_psql_script(pw_sql, dbname="postgres", run_dir=run_dir)

    # 3. Create database kanban if missing
    db_check = run_as_postgres(
        [
            BIN_PSQL,
            "-h",
            run_dir,
            "-U",
            "postgres",
            "-tAc",
            "SELECT 1 FROM pg_database WHERE datname = 'kanban'",
            "postgres",
        ],
        timeout=10.0,
    )
    if "1" not in db_check.stdout:
        run_psql_script(
            "CREATE DATABASE kanban OWNER kanban_migrator ENCODING 'UTF8' TEMPLATE template0;",
            dbname="postgres",
            run_dir=run_dir,
        )

    # 3. Create extensions and enable migrator login on kanban db
    ext_sql = """
    CREATE EXTENSION IF NOT EXISTS pgcrypto;
    CREATE EXTENSION IF NOT EXISTS ltree;
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE EXTENSION IF NOT EXISTS btree_gist;
    CREATE EXTENSION IF NOT EXISTS vector;
    REVOKE CREATE ON SCHEMA public FROM PUBLIC;
    GRANT USAGE, CREATE ON SCHEMA public TO kanban_migrator WITH GRANT OPTION;
    GRANT USAGE, CREATE ON SCHEMA public TO kb_infra_owner;
    GRANT USAGE ON SCHEMA public TO kanban_app, app_rls_reader;
    GRANT CREATE, TEMPORARY ON DATABASE kanban TO kanban_migrator;
    ALTER ROLE kanban_migrator LOGIN;
    """
    run_psql_script(ext_sql, dbname="kanban", run_dir=run_dir)
    log_phase("bootstrap_sql", "roles, database, and extensions initialized")


def run_migrations(
    pgdata: Path,
    alembic_ini: Path,
    run_dir: str = DEFAULT_RUN_DIR,
) -> None:
    """Run Alembic migrations under kanban_migrator and revoke login privilege afterwards."""
    if not alembic_ini.is_file():
        log_phase("migrations", "MIGRATIONS_SKIPPED_NO_ALEMBIC_INI")
        return

    log_phase("migrations", "running alembic upgrade head")
    migrator_dsn = f"postgresql+asyncpg://kanban_migrator@/kanban?host={run_dir}"
    mig_env = {
        "PATH": "/opt/kanban/.venv/bin:/usr/local/bin:/usr/bin:/bin",
        "DATABASE_URL": migrator_dsn,
        "KANBAN_MIGRATOR_DATABASE_URL": migrator_dsn,
        "LANG": "C.UTF-8",
    }
    cmd = [BIN_ALEMBIC, "-c", str(alembic_ini), "upgrade", "head"]

    res = run_as_postgres(cmd, timeout=120.0, check=False, env=mig_env)
    if res.returncode != 0:
        sys.stderr.write(f"❌ MIGRATION_FAILED: {res.stderr}\n")
        stop_postgres(pgdata, mode="fast")
        sys.exit(70)

    log_phase("migrations", "schema migrations applied successfully")

    # Ensure column-level SELECT (principal_id, username) + RLS policy for kanban_app,
    # grant SELECT on alembic_version for pg_dump backups,
    # then drop LOGIN privilege on kanban_migrator.
    post_mig_sql = """
    GRANT SELECT (principal_id, username) ON TABLE local_admin_credentials TO kanban_app;
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'local_admin_credentials'
          AND policyname = 'kanban_app_select_own_local_admin'
      ) THEN
        CREATE POLICY kanban_app_select_own_local_admin ON local_admin_credentials
          FOR SELECT TO kanban_app
          USING (principal_id = ANY (app_effective_principal_set()));
      END IF;
    END
    $$;
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'alembic_version'
      ) THEN
        GRANT SELECT ON TABLE alembic_version TO kanban_app, app_rls_reader;
      END IF;
    END
    $$;
    """
    run_psql_script(post_mig_sql, dbname="kanban", run_dir=run_dir)
    run_psql_script("ALTER ROLE kanban_migrator NOLOGIN;", dbname="kanban", run_dir=run_dir)
    log_phase("migrations", "privilege dropped: kanban_migrator set to NOLOGIN")


def ensure_backup_grants(run_dir: str = DEFAULT_RUN_DIR) -> None:
    """Ensure kanban_app has SELECT on alembic_version so pg_dump succeeds."""
    grant_sql = """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'alembic_version'
      ) THEN
        GRANT SELECT ON TABLE alembic_version TO kanban_app, app_rls_reader;
      END IF;
    END
    $$;
    """
    try:
        run_psql_script(grant_sql, dbname="kanban", run_dir=run_dir)
        log_phase("backup_grants", "granted SELECT on alembic_version to kanban_app")
    except Exception as exc:  # noqa: BLE001
        log_phase("backup_grants", f"Warning: grant SELECT on alembic_version failed: {exc}")


MAX_OPS_PAYLOAD_SIZE: int = 1_048_576


def _execute_op_inner(req: dict[str, Any]) -> dict[str, Any]:
    op = req.get("op")
    run_dir = req.get("run_dir", DEFAULT_RUN_DIR)

    if op == "pg_dump_raw":
        dump_bin = shutil.which("pg_dump") or "/usr/lib/postgresql/16/bin/pg_dump"
        cmd = [
            dump_bin,
            "-U",
            "postgres",
            "-d",
            "kanban",
            "-h",
            run_dir,
            "--format=custom",
            "--enable-row-security",
        ]
        proc = subprocess.run(cmd, capture_output=True, check=True, timeout=120.0)  # noqa: S603
        return {
            "status": "ok",
            "data_b64": base64.b64encode(proc.stdout).decode("ascii"),
            "size_bytes": len(proc.stdout),
        }

    if op == "restore_backup":
        archive_path = Path(req["archive_path"]).resolve()
        allowed = ("/var/lib/kanban/", "/tmp/")  # noqa: S108
        if not any(str(archive_path).startswith(p) for p in allowed):
            msg = f"Restricted archive path: {archive_path}"
            raise ValueError(msg)
        if not archive_path.is_file():
            msg = f"Archive not found: {archive_path}"
            raise FileNotFoundError(msg)

        passphrase = req.get("passphrase")
        raw_key_b64 = req.get("raw_key_b64")
        key_source: KeySource
        if passphrase:
            key_source = PassphraseKeySource(passphrase)
        elif raw_key_b64:
            key_source = RawKeySource(base64.b64decode(raw_key_b64))
        else:
            keyring_path = Path(
                req.get("keyring_path", "/var/lib/kanban/data/secrets/keyring.json")
            )
            keyring = load_or_create_keyring(keyring_path)
            key_source = RawKeySource(keyring.master_kek)

        target_db_url = f"postgresql+asyncpg://postgres@/kanban?host={run_dir}"
        restore_report = restore_backup(
            archive_path=archive_path,
            target_db_url=target_db_url,
            key_source=key_source,
            confirm_overwrite=req.get("confirm_overwrite", True),
        )
        return {
            "status": "ok",
            "report": {
                "workspaces_verified": restore_report.workspaces_verified,
                "links_audited": restore_report.links_audited,
                "duration_seconds": restore_report.duration_seconds,
            },
        }

    if op == "scheduled_backup":
        backup_dir = Path(req.get("backup_dir", "/var/lib/kanban/data/backups"))
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        dest = backup_dir / f"kanban-backup-{ts}.kbbak"
        raw_key_b64 = req.get("raw_key_b64")
        backup_key_source: KeySource
        if raw_key_b64:
            backup_key_source = RawKeySource(base64.b64decode(raw_key_b64))
        else:
            keyring_path = Path(
                req.get("keyring_path", "/var/lib/kanban/data/secrets/keyring.json")
            )
            keyring = load_or_create_keyring(keyring_path)
            backup_key_source = RawKeySource(keyring.master_kek)
        target_db_url = f"postgresql+asyncpg://postgres@/kanban?host={run_dir}"

        backup_summary = create_backup(
            db_url=target_db_url,
            out_path=dest,
            key_source=backup_key_source,
            include_secrets=True,
        )
        with contextlib.suppress(OSError):
            os.chown(dest, -1, 65532)
            dest.chmod(0o640)
        return {
            "status": "ok",
            "filename": dest.name,
            "size_bytes": backup_summary.size_bytes,
            "duration_seconds": backup_summary.duration_seconds,
        }

    msg = f"Unknown operation: {op}"
    raise ValueError(msg)


def execute_privileged_op(req_json_str: str) -> int:
    """Execute a privileged database operation under OS user 'postgres'."""
    try:
        req = json.loads(req_json_str)
        out = _execute_op_inner(req)
        sys.stdout.write(json.dumps(out) + "\n")
    except Exception as exc:  # noqa: BLE001
        err_out = {
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        sys.stdout.write(json.dumps(err_out) + "\n")
        return 1
    else:
        return 0


class OpsSocketServer:
    """Fixed-op Unix-domain socket RPC listener for privileged operations."""

    def __init__(
        self,
        run_dir: str = DEFAULT_RUN_DIR,
        keyring: Keyring | None = None,
    ) -> None:
        """Initialize socket server for privileged operations."""
        self.run_dir = run_dir
        self.keyring = keyring
        self.sock_path = Path(run_dir) / ".kb_ops.sock"
        self._server_sock: socket.socket | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start listening on the Unix domain socket in a daemon thread."""
        self.sock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.sock_path.exists():
            self.sock_path.unlink(missing_ok=True)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(self.sock_path))
        sock.listen(10)
        try:
            self.sock_path.chmod(0o660)
            os.chown(self.sock_path, 0, 65532)
        except (PermissionError, OSError):
            with contextlib.suppress(OSError):
                self.sock_path.chmod(0o666)
        self._server_sock = sock
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True, name="kb-ops-rpc")
        self._thread.start()
        log_phase("ops_rpc", f"Ops RPC server listening on {self.sock_path}")

    def stop(self) -> None:
        """Stop the socket listener."""
        self._running = False
        if self._server_sock:
            with contextlib.suppress(Exception):
                self._server_sock.close()
        with contextlib.suppress(OSError):
            self.sock_path.unlink(missing_ok=True)

    def _serve(self) -> None:
        while self._running:
            if self._server_sock is None:
                break
            try:
                conn, _ = self._server_sock.accept()
            except OSError:
                break
            client_thread = threading.Thread(
                target=self._handle_client,
                args=(conn,),
                daemon=True,
            )
            client_thread.start()

    def _handle_client(self, conn: socket.socket) -> None:
        with conn:
            try:
                data = b""
                while not data.endswith(b"\n") and len(data) < MAX_OPS_PAYLOAD_SIZE:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                if not data:
                    return
                req = json.loads(data.decode("utf-8"))
                req["run_dir"] = self.run_dir
                if self.keyring and "raw_key_b64" not in req and not req.get("passphrase"):
                    req["raw_key_b64"] = base64.b64encode(self.keyring.master_kek).decode("ascii")
                req_json_str = json.dumps(req)

                if os.geteuid() == 0:
                    python_bin = sys.executable or "/opt/kanban/.venv/bin/python3"
                    cmd = [
                        python_bin,
                        "-c",
                        (
                            "import sys; "
                            "from deploy.standalone.entrypoint import execute_privileged_op; "
                            "sys.exit(execute_privileged_op(sys.argv[1]))"
                        ),
                        req_json_str,
                    ]
                    proc = run_as_postgres(cmd, timeout=300.0, check=False)
                    raw_stdout: str | bytes = proc.stdout or ""
                    if isinstance(raw_stdout, bytes):
                        out_text = raw_stdout.decode("utf-8", errors="replace").strip()
                    else:
                        out_text = raw_stdout.strip()

                    if not out_text:
                        raw_stderr: str | bytes = proc.stderr or ""
                        err_msg = (
                            raw_stderr.decode("utf-8", errors="replace").strip()
                            if isinstance(raw_stderr, bytes)
                            else str(raw_stderr).strip()
                        ) or "Empty response from privileged op"
                        out_text = json.dumps(
                            {
                                "status": "error",
                                "message": err_msg,
                            }
                        )
                else:
                    old_stdout = sys.stdout
                    try:
                        buf = io.StringIO()
                        sys.stdout = buf
                        execute_privileged_op(req_json_str)
                        out_text = buf.getvalue().strip()
                    finally:
                        sys.stdout = old_stdout

                conn.sendall(out_text.encode("utf-8") + b"\n")
            except Exception as exc:  # noqa: BLE001
                err_resp = json.dumps(
                    {
                        "status": "error",
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
                with contextlib.suppress(Exception):
                    conn.sendall(err_resp.encode("utf-8") + b"\n")


def build_uvicorn_command() -> list[str]:
    """Construct the setpriv argv list for spawning Uvicorn as UID 65532."""
    forwarded_allow_ips = os.environ.get(
        "KB_FORWARDED_ALLOW_IPS",
        os.environ.get("KB_TRUSTED_PROXIES", "") or os.environ.get("KANBAN_TRUSTED_PROXIES", ""),
    )
    return [
        BIN_SETPRIV,
        "--reuid=65532",
        "--regid=65532",
        "--clear-groups",
        "--inh-caps=-all",
        "--no-new-privs",
        "--",
        BIN_UVICORN,
        "kanban.app:create_app",
        "--factory",
        "--host",
        "0.0.0.0",  # noqa: S104
        "--port",
        "8080",
        "--proxy-headers",
        (
            f"--forwarded-allow-ips={forwarded_allow_ips}"
            if forwarded_allow_ips
            else '--forwarded-allow-ips=""'
        ),
        "--loop",
        "uvloop",
        "--http",
        "httptools",
    ]


def resolve_status_path() -> Path:
    """Resolve destination path for standalone_status.json."""
    if "KB_STANDALONE_STATUS_PATH" in os.environ:
        return Path(os.environ["KB_STANDALONE_STATUS_PATH"])
    if "KB_RUN_DIR" in os.environ:
        return Path(os.environ["KB_RUN_DIR"]) / "standalone_status.json"
    return DEFAULT_STATUS_PATH


_PASSTHROUGH_ENV_VARS: tuple[str, ...] = (
    "KB_BLOCK_CLEARTEXT_HTTP",
    "KANBAN_BLOCK_CLEARTEXT_HTTP",
    "KB_ENFORCE_HTTPS",
    "KANBAN_ENFORCE_HTTPS",
    "KB_STANDALONE_CLEARTEXT_HOSTS",
    "KB_FORWARDED_ALLOW_IPS",
    "KB_TRUSTED_PROXIES",
    "KANBAN_TRUSTED_PROXIES",
    "KB_PUBLIC_ORIGIN",
    "KANBAN_PUBLIC_ORIGIN",
    "KB_PUBLIC_BASE_URL",
    "KANBAN_PUBLIC_BASE_URL",
    "KB_WEBAUTHN_RP_ID",
    "KANBAN_WEBAUTHN_RP_ID",
    "KB_WEBAUTHN_RP_NAME",
    "KANBAN_WEBAUTHN_RP_NAME",
    "KB_AIR_GAP_MODE",
    "KB_TRASH_RETENTION_DAYS",
    "KB_LOG_LEVEL",
    "KB_SETUP_TOKEN_FILE",
    "KB_GIT_COMMIT",
    "GIT_SHA",
    "KB_BUILD_TIMESTAMP",
    "KANBAN_ATTACHMENT_DIR",
)


def build_child_env(
    keyring: Keyring | None = None,
    db_url: str | None = None,
    run_dir: str = DEFAULT_RUN_DIR,
) -> dict[str, str]:
    """Build the explicit allowlist child environment for Uvicorn."""
    if db_url:
        effective_url = db_url
    elif keyring is not None:
        encoded_pw = quote(keyring.kanban_app_password_str, safe="")
        encoded_dir = quote(run_dir, safe="")
        effective_url = f"postgresql+asyncpg://kanban_app:{encoded_pw}@/kanban?host={encoded_dir}"
    else:
        encoded_dir = quote(run_dir, safe="")
        effective_url = f"postgresql+asyncpg://kanban_app@/kanban?host={encoded_dir}"

    env: dict[str, str] = {
        "PATH": "/opt/kanban/.venv/bin:/usr/local/bin:/usr/bin:/bin",
        "KB_WEB_DIST": os.environ.get("KB_WEB_DIST", "/opt/kanban/web/dist"),
        "KB_DEPLOYMENT_MODE": "standalone",
        "DATABASE_URL": effective_url,
        "LANG": "C.UTF-8",
        "KB_STANDALONE_STATUS_PATH": str(resolve_status_path()),
        "KANBAN_ATTACHMENT_DIR": os.environ.get(
            "KANBAN_ATTACHMENT_DIR", "/var/lib/kanban/data/attachments"
        ),
    }

    for var_name in _PASSTHROUGH_ENV_VARS:
        if var_name in os.environ:
            env[var_name] = os.environ[var_name]

    if keyring is not None:
        env["KB_MASTER_KEK_B64"] = keyring.master_kek_b64
        env["KB_AUTH_PEPPER_B64"] = keyring.auth_pepper_b64
        env["KB_SESSION_HMAC_KEY_B64"] = keyring.session_hmac_key_b64

    env["KB_OPS_SOCK"] = str(Path(run_dir) / ".kb_ops.sock")

    return env


def ensure_attachments_dir(data_dir: Path) -> Path:
    """Ensure attachments directory exists with 65532:65532 ownership and 0750 permissions."""
    attachments_dir = Path(os.environ.get("KANBAN_ATTACHMENT_DIR", str(data_dir / "attachments")))
    attachments_dir.mkdir(parents=True, exist_ok=True)
    if os.getuid() == 0:
        try:
            shutil.chown(str(attachments_dir), user=65532, group=65532)
            attachments_dir.chmod(0o750)
        except OSError as exc:
            log_phase("init_dirs", f"Warning: chown/chmod attachments_dir failed: {exc}")
    return attachments_dir


def supervisor_loop(
    uvicorn_proc: subprocess.Popen[str],
    pgdata: Path,
) -> int:
    """Supervise Uvicorn and PostgreSQL until termination."""
    last_pg_check = time.monotonic()

    while True:
        # Check Uvicorn process health
        ret = uvicorn_proc.poll()
        if ret is not None:
            log_phase("supervisor", f"uvicorn exited with code {ret}")
            stop_postgres(pgdata, mode="fast")
            return ret

        # Poll PostgreSQL postmaster every 2s
        now = time.monotonic()
        if now - last_pg_check >= PG_CHECK_INTERVAL_SEC:
            last_pg_check = now
            status_cmd = [BIN_PG_CTL, "-D", str(pgdata), "status"]
            res = run_as_postgres(status_cmd, timeout=5.0, check=False)
            if res.returncode != 0:
                sys.stderr.write("❌ PG_DIED: postgres postmaster process died\n")
                shutdown_uvicorn(uvicorn_proc)
                return 70

        time.sleep(0.5)


def shutdown_uvicorn(proc: subprocess.Popen[str]) -> None:
    """Gracefully terminate Uvicorn with SIGTERM, escalating to SIGKILL after 10s."""
    if proc.poll() is not None:
        return

    log_phase("shutdown", "sending SIGTERM to uvicorn")
    proc.send_signal(signal.SIGTERM)

    deadline = time.monotonic() + SHUTDOWN_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log_phase("shutdown", "uvicorn terminated cleanly")
            return
        time.sleep(0.2)

    log_phase("shutdown", "uvicorn did not terminate within 10s; sending SIGKILL")
    proc.kill()
    proc.wait()


def _compute_migrations_digest() -> str:
    """Compute SHA-256 digest of migration versions and SQL scripts."""
    candidates = [
        (
            Path("/opt/kanban/database/migrations/versions"),
            Path("/opt/kanban/database/migrations/sql"),
        ),
        (
            Path("database/migrations/versions"),
            Path("database/migrations/sql"),
        ),
    ]
    for versions_dir, sql_dir in candidates:
        if versions_dir.is_dir():
            hasher = hashlib.sha256()
            for f in sorted(versions_dir.glob("*.py")):
                hasher.update(f.name.encode("utf-8"))
                hasher.update(f.read_bytes())
            if sql_dir.is_dir():
                for f in sorted(sql_dir.glob("*.sql")):
                    hasher.update(f.name.encode("utf-8"))
                    hasher.update(f.read_bytes())
            return hasher.hexdigest()
    return ""


def main(_argv: Sequence[str] | None = None) -> int:  # noqa: C901, PLR0912, PLR0915
    """Coordinate standalone single-container startup."""
    # 1. Mode selection
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        log_phase("mode", "MODE=external_db")
        status = probe(Path("/var/lib/kanban/data"), mode="external_db")
        status_path = resolve_status_path()
        write_standalone_status(status, target_path=status_path)
        child_env = build_child_env(db_url=database_url)
        cmd = build_uvicorn_command()
        os.execv(cmd[0], cmd)  # noqa: S606

    log_phase("mode", "MODE=standalone_embedded_pg")

    # Check root UID
    if os.getuid() != 0:
        sys.stderr.write(
            "❌ STANDALONE_REQUIRES_ROOT_ENTRYPOINT: Standalone mode requires UID 0 entrypoint\n"
        )
        return 78

    pgdata = Path(os.environ.get("KB_PGDATA_DIR", str(DEFAULT_PGDATA)))
    run_dir = os.environ.get("KB_RUN_DIR", DEFAULT_RUN_DIR)
    alembic_ini = Path(os.environ.get("KB_ALEMBIC_INI", str(DEFAULT_ALEMBIC_INI)))

    # Ensure data, backups, and attachments directories exist with kanban ownership
    data_dir = pgdata.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    backups_dir = data_dir / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    ensure_attachments_dir(data_dir)
    run_kanban_dir = Path("/run/kanban")
    try:
        run_kanban_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log_phase("init_dirs", f"Warning: mkdir /run/kanban failed: {exc}")

    if os.getuid() == 0:
        try:
            shutil.chown(str(data_dir), user=65532, group=65532)
            shutil.chown(str(backups_dir), user=65532, group=65532)
            data_dir.chmod(0o775)
            backups_dir.chmod(0o775)
            if run_kanban_dir.is_dir():
                shutil.chown(str(run_kanban_dir), user=65532, group=65532)
                run_kanban_dir.chmod(0o775)
        except OSError as exc:
            log_phase("init_dirs", f"Warning: chown failed: {exc}")

    keyring_path = Path(
        os.environ.get(
            "KB_KEYRING_PATH",
            str(pgdata.parent / "secrets" / "keyring.json"),
        )
    )

    current_digest = _compute_migrations_digest()
    mig_digest_file = pgdata / ".alembic_head"
    stored_digest = (
        mig_digest_file.read_text(encoding="utf-8").strip() if mig_digest_file.is_file() else ""
    )
    migrations_current = bool(
        mig_digest_file.is_file() and (not current_digest or stored_digest == current_digest)
    )
    is_warm = (pgdata / "PG_VERSION").is_file() and migrations_current and keyring_path.is_file()

    if is_warm:
        # Storage probe & status write before spawning Uvicorn to avoid race condition
        status = probe(pgdata.parent, mode="standalone_embedded_pg")
        status_path = resolve_status_path()
        write_standalone_status(status, target_path=status_path)
        if not status.persistent_volume:
            emit_ephemeral_warning()

        try:
            keyring = load_or_create_keyring(keyring_path)
            log_phase("keyring", f"keyring loaded from {keyring_path}")
        except KeyringError as err:
            sys.stderr.write(f"❌ KEYRING_INVALID: {err}\n")
            return 78

        log_phase("initdb", "existing cluster detected, skipping initdb")
        log_phase("bootstrap_sql", "existing cluster detected, skipping bootstrap_sql")
        log_phase("migrations", "migrations up to date, skipping alembic upgrade")

        # Spawn Uvicorn concurrently as early as possible
        log_phase("uvicorn_spawn", "spawning uvicorn as UID 65532 concurrently")
        uvicorn_cmd = build_uvicorn_command()
        child_env = build_child_env(keyring=keyring, run_dir=run_dir)
        uvicorn_proc = subprocess.Popen(  # noqa: S603
            uvicorn_cmd,
            env=child_env,
            shell=False,
            text=True,
        )

        # Start PostgreSQL while Uvicorn imports modules
        if not (pgdata / "conf.d" / "kanban.conf").is_file():
            configure_postgres(pgdata, run_dir=run_dir)
        start_postgres(pgdata, run_dir=run_dir)
        ensure_backup_grants(run_dir=run_dir)
        ops_server = OpsSocketServer(run_dir=run_dir, keyring=keyring)
        ops_server.start()
    else:
        # Storage probe & ephemeral warning
        status = probe(pgdata.parent, mode="standalone_embedded_pg")
        status_path = resolve_status_path()
        write_standalone_status(status, target_path=status_path)
        if not status.persistent_volume:
            emit_ephemeral_warning()

        try:
            keyring = load_or_create_keyring(keyring_path)
            log_phase("keyring", f"keyring loaded from {keyring_path}")
        except KeyringError as err:
            sys.stderr.write(f"❌ KEYRING_INVALID: {err}\n")
            return 78

        # Cold Cluster Init
        initialize_cluster(pgdata)

        # Write configuration
        configure_postgres(pgdata, run_dir=run_dir)

        # Start PostgreSQL
        start_postgres(pgdata, run_dir=run_dir)

        # Bootstrap SQL & Migrations
        bootstrap_database(run_dir=run_dir, keyring=keyring)
        run_migrations(pgdata, alembic_ini, run_dir=run_dir)
        ensure_backup_grants(run_dir=run_dir)
        ops_server = OpsSocketServer(run_dir=run_dir, keyring=keyring)
        ops_server.start()
        if current_digest:
            mig_digest_file.parent.mkdir(parents=True, exist_ok=True)
            mig_digest_file.write_text(current_digest, encoding="utf-8")

        # Spawn Uvicorn as UID 65532
        log_phase("uvicorn_spawn", "spawning uvicorn as UID 65532")
        uvicorn_cmd = build_uvicorn_command()
        child_env = build_child_env(keyring=keyring, run_dir=run_dir)
        uvicorn_proc = subprocess.Popen(  # noqa: S603
            uvicorn_cmd,
            env=child_env,
            shell=False,
            text=True,
        )

    # Install signal handlers
    def handle_signal(_signum: int, _frame: object) -> None:
        log_phase("shutdown", "shutdown signal received; terminating services")
        ops_server.stop()
        shutdown_uvicorn(uvicorn_proc)
        stop_postgres(pgdata, mode="fast")
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # 8. Enter supervisor loop
    try:
        return supervisor_loop(uvicorn_proc, pgdata)
    finally:
        ops_server.stop()


if __name__ == "__main__":
    sys.exit(main())
