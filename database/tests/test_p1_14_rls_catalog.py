"""Schema-wide catalog gate verifying FORCE ROW LEVEL SECURITY across all tenant tables."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

CATALOG_RLS_QUERY = """
SELECT
    c.relname,
    c.relkind,
    c.relrowsecurity,
    c.relforcerowsecurity
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p')
  AND c.relname NOT IN ('alembic_version', 'link_type_matrix')
ORDER BY c.relname;
"""

EXEMPT_TABLES = {"alembic_version", "link_type_matrix"}


@pytest.mark.asyncio
async def test_06_rls_catalog_gate(db_session: AsyncSession) -> None:
    """Assert every public tenant table and partition has relrowsecurity and relforcerowsecurity."""
    result = await db_session.execute(text(CATALOG_RLS_QUERY))
    rows = result.mappings().all()

    # Must find all tenant tables and activity partition tables
    assert len(rows) >= 25, f"Expected at least 25 tenant tables/partitions, found {len(rows)}"

    unprotected = [
        r["relname"] for r in rows if not r["relrowsecurity"] or not r["relforcerowsecurity"]
    ]

    assert len(unprotected) == 0, (
        f"Found {len(unprotected)} tenant tables/partitions missing FORCE RLS: {unprotected}"
    )

    # Verify exempt tables exist and are not flagged
    exempt_res = await db_session.execute(
        text(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname IN ('alembic_version', 'link_type_matrix')"
        )
    )
    found_exempt = {r[0] for r in exempt_res.all()}
    assert found_exempt == EXEMPT_TABLES, (
        f"Missing exempt catalog tables: {EXEMPT_TABLES - found_exempt}"
    )
