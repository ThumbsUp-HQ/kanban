# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Reversible lifecycle test for p5_11_custom_fields migration (KB-P5-11)."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.asyncio
async def test_p5_11_custom_fields_migration_lifecycle() -> None:
    """Verify upgrade to p5_11_custom_fields, downgrade -1, and re-upgrade."""
    async with MigrationHarness() as harness:
        # 1. Upgrade to head (p5_11_custom_fields)
        await harness.upgrade("head")

        # Verify custom_field_definitions and custom_field_values exist with rowsecurity
        tables = await harness.fetch(
            "SELECT tablename, rowsecurity FROM pg_tables "
            "WHERE tablename IN ('custom_field_definitions', 'custom_field_values') "
            "ORDER BY tablename"
        )
        assert len(tables) == 2
        assert tables[0]["tablename"] == "custom_field_definitions"
        assert tables[0]["rowsecurity"] is True
        assert tables[1]["tablename"] == "custom_field_values"
        assert tables[1]["rowsecurity"] is True

        # Verify FORCE RLS on both tables
        force_rls = await harness.fetch(
            "SELECT relname, relforcerowsecurity FROM pg_class "
            "WHERE relname IN ('custom_field_definitions', 'custom_field_values') "
            "ORDER BY relname"
        )
        assert len(force_rls) == 2
        assert force_rls[0]["relforcerowsecurity"] is True
        assert force_rls[1]["relforcerowsecurity"] is True

        # Verify function app_caller_access_hash exists
        funcs = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON p.pronamespace = n.oid "
            "WHERE n.nspname = 'public' AND proname = 'app_caller_access_hash'"
        )
        assert len(funcs) == 1

        # 2. Downgrade -1 (to p2_05a_mfa_totp_recovery)
        await harness.downgrade("p2_05a_mfa_totp_recovery")

        # Verify tables dropped
        tbl_down = await harness.fetch(
            "SELECT 1 FROM pg_tables "
            "WHERE tablename IN ('custom_field_definitions', 'custom_field_values')"
        )
        assert len(tbl_down) == 0

        # Verify function dropped
        funcs_down = await harness.fetch(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid "
            "WHERE n.nspname = 'public' AND proname = 'app_caller_access_hash'"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to head
        await harness.upgrade("head")

        # Verify tables restored
        tbl_restored = await harness.fetch(
            "SELECT tablename, rowsecurity FROM pg_tables "
            "WHERE tablename IN ('custom_field_definitions', 'custom_field_values') "
            "ORDER BY tablename"
        )
        assert len(tbl_restored) == 2
        assert tbl_restored[0]["rowsecurity"] is True
        assert tbl_restored[1]["rowsecurity"] is True
