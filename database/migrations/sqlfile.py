"""Alembic SQL file execution helper."""

import re
from pathlib import Path
from typing import Any

from alembic import op
from sqlalchemy.util import await_only

SQL_DIR = Path(__file__).resolve().parent / "sql"
NAME_PATTERN = re.compile(r"^p[0-9]_[0-9]{2}[a-z]?_[a-z0-9_]+\.(up|down)\.sql$")


def execute_sql_file(name: str) -> None:
    """Execute a raw SQL migration file using the asyncpg simple query protocol."""
    if not NAME_PATTERN.match(name):
        msg = f"Invalid SQL file name: {name}"
        raise ValueError(msg)

    file_path = SQL_DIR / name
    if not file_path.is_file():
        msg = f"SQL file not found: {file_path}"
        raise FileNotFoundError(msg)

    sql = file_path.read_text(encoding="utf-8")
    bind: Any = op.get_bind()
    raw: Any = bind.connection.dbapi_connection.driver_connection
    await_only(raw.execute(sql))
