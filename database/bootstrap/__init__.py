"""Database cluster bootstrap routines."""

from pathlib import Path
from typing import Any

import asyncpg  # type: ignore[import-untyped]  # asyncpg does not distribute PEP 561 py.typed marker
from sqlalchemy.engine.url import make_url

BOOTSTRAP_DIR = Path(__file__).resolve().parent


def _to_asyncpg_kwargs(dsn: str) -> dict[str, Any]:
    """Parse DSN string into asyncpg connect arguments."""
    url = make_url(dsn)
    kwargs: dict[str, Any] = {
        "user": url.username or "postgres",
        "database": url.database or "postgres",
    }
    if url.password:
        kwargs["password"] = url.password
    host = url.query.get("host") or url.host
    if host:
        kwargs["host"] = host
    if url.port:
        kwargs["port"] = url.port
    return kwargs


async def bootstrap_cluster(superuser_dsn: str) -> None:
    """Bootstrap cluster-wide roles and database extensions idempotently."""
    kwargs = _to_asyncpg_kwargs(superuser_dsn)
    conn = await asyncpg.connect(**kwargs)
    try:
        roles_sql = (BOOTSTRAP_DIR / "roles.sql").read_text(encoding="utf-8")
        await conn.execute(roles_sql)
        ext_sql = (BOOTSTRAP_DIR / "extensions.sql").read_text(encoding="utf-8")
        await conn.execute(ext_sql)
    finally:
        await conn.close()
