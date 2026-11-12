# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Reversible lifecycle test for p2_04_local_admin_credentials migration (KB-P2-04)."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.asyncio
async def test_24_local_admin_credentials_migration_lifecycle() -> None:
    """Verify upgrade to p2_04_local_admin_credentials, downgrade -1, and re-upgrade."""
    async with MigrationHarness() as harness:
        # 1. Upgrade to head (p2_04_local_admin_credentials)
        await harness.upgrade("head")

        # Verify table exists and is owned by kb_auth_owner with RLS forced
        tables = await harness.fetch(
            "SELECT tableowner, rowsecurity FROM pg_tables "
            "WHERE tablename = 'local_admin_credentials'"
        )
        assert len(tables) == 1
        assert tables[0]["tableowner"] == "kb_auth_owner"
        assert tables[0]["rowsecurity"] is True

        # Verify functions exist in kb_auth
        funcs = await harness.fetch(
            "SELECT proname, prosecdef FROM pg_proc p "
            "JOIN pg_namespace n ON p.pronamespace = n.oid "
            "WHERE n.nspname = 'kb_auth' AND proname LIKE 'local_%'"
        )
        func_names = {f["proname"] for f in funcs}
        assert func_names == {
            "local_get_credential",
            "local_set_password_hash",
            "local_admin_create",
        }
        for f in funcs:
            assert f["prosecdef"] is True

        # 2. Downgrade -1 (to p2_15_attachments)
        await harness.downgrade("p2_15_attachments")

        # Verify table is dropped
        tbl_down = await harness.fetch(
            "SELECT 1 FROM pg_tables WHERE tablename = 'local_admin_credentials'"
        )
        assert len(tbl_down) == 0

        # Verify functions are dropped
        funcs_down = await harness.fetch(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid "
            "WHERE n.nspname = 'kb_auth' AND proname LIKE 'local_%'"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to head
        await harness.upgrade("head")

        # Verify table restored
        tables_re = await harness.fetch(
            "SELECT tableowner FROM pg_tables WHERE tablename = 'local_admin_credentials'"
        )
        assert len(tables_re) == 1
        assert tables_re[0]["tableowner"] == "kb_auth_owner"
