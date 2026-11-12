"""Standalone single-container entrypoint for embedded PostgreSQL and Uvicorn.

Initializes an embedded PostgreSQL 16 instance accessible strictly via Unix domain
sockets, applies migrations under a dedicated migration role, drops privileges to
UID 65532 to run Uvicorn, and coordinates graceful shutdown under tini.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from deploy.standalone.pg_config import configure_postgres

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


def log_phase(phase: str, message: str) -> None:
    """Log a phase transition with monotonic elapsed milliseconds."""
    elapsed_ms = int((time.monotonic() - START_TIME) * 1000)
    sys.stdout.write(f"[kanban-standalone] [{elapsed_ms:05d}ms] {phase}: {message}\n")
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
        sys.stderr.write(f"INITDB_FAILED: {exc.stderr}\n")
        raise


def start_postgres(pgdata: Path, run_dir: str = DEFAULT_RUN_DIR) -> None:
    """Start PostgreSQL and wait for socket readiness."""
    log_phase("pg_start", "starting embedded PostgreSQL")
    cmd = [
        BIN_PG_CTL,
        "-D",
        str(pgdata),
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
        time.sleep(0.2)

    if not ready:
        sys.stderr.write("PG_START_TIMEOUT: postgres failed to start within 10s\n")
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


def bootstrap_database(run_dir: str = DEFAULT_RUN_DIR) -> None:
    """Create roles, database, and extensions idempotently."""
    log_phase("bootstrap_sql", "creating roles and kanban database")

    # 1. Create roles if missing
    role_sql = """
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kanban_migrator') THEN
        CREATE ROLE kanban_migrator LOGIN NOSUPERUSER NOCREATEROLE NOBYPASSRLS;
      END IF;
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kanban_app') THEN
        CREATE ROLE kanban_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
      END IF;
    END
    $$;
    """
    run_psql_script(role_sql, dbname="postgres", run_dir=run_dir)

    # 2. Create database kanban if missing
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
    ALTER ROLE kanban_migrator LOGIN;
    """
    run_psql_script(ext_sql, dbname="kanban", run_dir=run_dir)
    log_phase("bootstrap_sql", "roles, database, and extensions initialized")


def run_migrations(pgdata: Path, alembic_ini: Path, run_dir: str = DEFAULT_RUN_DIR) -> None:
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
        sys.stderr.write(f"MIGRATION_FAILED: {res.stderr}\n")
        stop_postgres(pgdata, mode="fast")
        sys.exit(70)

    log_phase("migrations", "schema migrations applied successfully")

    # Privilege drop: revoke LOGIN on kanban_migrator
    run_psql_script("ALTER ROLE kanban_migrator NOLOGIN;", dbname="kanban", run_dir=run_dir)
    log_phase("migrations", "privilege dropped: kanban_migrator set to NOLOGIN")


def build_uvicorn_command() -> list[str]:
    """Construct the setpriv argv list for spawning Uvicorn as UID 65532."""
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
        '--forwarded-allow-ips=""',
    ]


def build_child_env(db_url: str | None = None) -> dict[str, str]:
    """Build the explicit allowlist child environment for Uvicorn."""
    effective_url = db_url or "postgresql+asyncpg://kanban_app@/kanban?host=/run/postgresql"
    return {
        "PATH": "/opt/kanban/.venv/bin:/usr/local/bin:/usr/bin:/bin",
        "KB_WEB_DIST": os.environ.get("KB_WEB_DIST", "/opt/kanban/web/dist"),
        "KB_DEPLOYMENT_MODE": "standalone",
        "DATABASE_URL": effective_url,
        "LANG": "C.UTF-8",
    }


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
                sys.stderr.write("PG_DIED: postgres postmaster process died\n")
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


def main(_argv: Sequence[str] | None = None) -> int:
    """Coordinate standalone single-container startup."""
    # 1. Mode selection
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        log_phase("mode", "MODE=external_db")
        child_env = build_child_env(db_url=database_url)
        cmd = build_uvicorn_command()
        os.execv(cmd[0], cmd)  # noqa: S606

    log_phase("mode", "MODE=standalone_embedded_pg")

    # Check root UID
    if os.getuid() != 0:
        sys.stderr.write(
            "STANDALONE_REQUIRES_ROOT_ENTRYPOINT: Standalone mode requires UID 0 entrypoint\n"
        )
        return 78

    pgdata = Path(os.environ.get("KB_PGDATA_DIR", str(DEFAULT_PGDATA)))
    run_dir = os.environ.get("KB_RUN_DIR", DEFAULT_RUN_DIR)
    alembic_ini = Path(os.environ.get("KB_ALEMBIC_INI", str(DEFAULT_ALEMBIC_INI)))

    # 2. Cluster Init
    initialize_cluster(pgdata)

    # 3. Write configuration
    configure_postgres(pgdata, run_dir=run_dir)

    # 4. Start PostgreSQL
    start_postgres(pgdata, run_dir=run_dir)

    # 5. Bootstrap SQL
    bootstrap_database(run_dir=run_dir)

    # 6. Migrations & Privilege drop
    run_migrations(pgdata, alembic_ini, run_dir=run_dir)

    # 7. Spawn Uvicorn as UID 65532
    log_phase("uvicorn_spawn", "spawning uvicorn as UID 65532")
    uvicorn_cmd = build_uvicorn_command()
    child_env = build_child_env()

    uvicorn_proc = subprocess.Popen(  # noqa: S603
        uvicorn_cmd,
        env=child_env,
        shell=False,
        text=True,
    )

    # Install signal handlers
    def handle_signal(_signum: int, _frame: object) -> None:
        log_phase("shutdown", "shutdown signal received; terminating services")
        shutdown_uvicorn(uvicorn_proc)
        stop_postgres(pgdata, mode="fast")
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # 8. Enter supervisor loop
    return supervisor_loop(uvicorn_proc, pgdata)


if __name__ == "__main__":
    sys.exit(main())
