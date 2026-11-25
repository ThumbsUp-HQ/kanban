"""PostgreSQL configuration writer for standalone single-container deployment.

Enforces Unix-socket-only access, peer authentication mapping, and isolated
database roles with zero TCP socket listeners.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

PG_HBA_CONTENT = """\
# PostgreSQL Client Authentication Configuration File
# Standalone mode: Unix-socket only, zero TCP host listeners permitted
local  all     postgres                         peer
local  kanban  kanban_migrator                  scram-sha-256
local  kanban  kanban_app                       scram-sha-256
"""

PG_IDENT_CONTENT = """\
# PostgreSQL User Name Mapping Configuration File
# Maps OS users to PostgreSQL roles via peer authentication
kanban_map postgres kanban_migrator
kanban_map kanban kanban_app
"""

KANBAN_CONF_CONTENT = """\
# Standalone single-container configuration for kanban
listen_addresses = ''
unix_socket_directories = '{run_dir}'
unix_socket_permissions = 0770
unix_socket_group = 'kanban'
shared_buffers = 32MB
fsync = on
"""


def configure_postgres(pgdata: Path, run_dir: str = "/run/postgresql") -> None:
    """Idempotently write PostgreSQL configuration, pg_hba.conf, and pg_ident.conf.

    Args:
        pgdata: Path to the PostgreSQL data directory.
        run_dir: Path to the directory where Unix domain sockets reside.

    """
    conf_dir = pgdata / "conf.d"
    conf_dir.mkdir(parents=True, exist_ok=True)

    # Write conf.d/kanban.conf
    kanban_conf = conf_dir / "kanban.conf"
    kanban_conf.write_text(
        KANBAN_CONF_CONTENT.format(run_dir=run_dir),
        encoding="utf-8",
    )

    # Ensure postgresql.conf includes conf.d if it exists
    main_conf = pgdata / "postgresql.conf"
    if main_conf.is_file():
        existing = main_conf.read_text(encoding="utf-8")
        if "include_dir = 'conf.d'" not in existing and 'include_dir = "conf.d"' not in existing:
            with main_conf.open("a", encoding="utf-8") as f:
                f.write("\ninclude_dir = 'conf.d'\n")

    # Rewrite pg_hba.conf (zero host lines)
    hba_conf = pgdata / "pg_hba.conf"
    hba_conf.write_text(PG_HBA_CONTENT, encoding="utf-8")

    # Rewrite pg_ident.conf
    ident_conf = pgdata / "pg_ident.conf"
    ident_conf.write_text(PG_IDENT_CONTENT, encoding="utf-8")


def generate_role_passwords_sql(app_scram: str, mig_scram: str) -> str:
    """Generate ALTER ROLE statements with pre-computed SCRAM-SHA-256 verifiers."""
    return f"""\
ALTER ROLE kanban_app PASSWORD '{app_scram}';
ALTER ROLE kanban_migrator PASSWORD '{mig_scram}';
"""
