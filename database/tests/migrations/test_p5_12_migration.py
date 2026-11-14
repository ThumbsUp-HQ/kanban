# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Reversible lifecycle test for p5_12_custom_field_approvals migration (KB-P5-12)."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.asyncio
async def test_p5_12_custom_field_approvals_migration_lifecycle() -> None:
    """Verify upgrade to p5_12_custom_field_approvals, downgrade -1, and re-upgrade."""
    async with MigrationHarness() as harness:
        # 1. Upgrade to head (p5_12_custom_field_approvals)
        await harness.upgrade("head")

        # Verify custom_field_approvals exists with rowsecurity
        tables = await harness.fetch(
            "SELECT tablename, rowsecurity FROM pg_tables "
            "WHERE tablename = 'custom_field_approvals'"
        )
        assert len(tables) == 1
        assert tables[0]["tablename"] == "custom_field_approvals"
        assert tables[0]["rowsecurity"] is True

        # Verify FORCE RLS on custom_field_approvals
        force_rls = await harness.fetch(
            "SELECT relname, relforcerowsecurity FROM pg_class "
            "WHERE relname = 'custom_field_approvals'"
        )
        assert len(force_rls) == 1
        assert force_rls[0]["relforcerowsecurity"] is True

        # Verify trigger custom_field_manifest_tamper_revoke exists
        triggers = await harness.fetch(
            "SELECT tgname FROM pg_trigger WHERE tgname = 'custom_field_manifest_tamper_revoke'"
        )
        assert len(triggers) == 1

        # 2. Downgrade -1 (to p5_11_custom_fields)
        await harness.downgrade("p5_11_custom_fields")

        # Verify table dropped
        tbl_down = await harness.fetch(
            "SELECT 1 FROM pg_tables WHERE tablename = 'custom_field_approvals'"
        )
        assert len(tbl_down) == 0

        # Verify trigger dropped
        trig_down = await harness.fetch(
            "SELECT 1 FROM pg_trigger WHERE tgname = 'custom_field_manifest_tamper_revoke'"
        )
        assert len(trig_down) == 0

        # 3. Re-upgrade to head
        await harness.upgrade("head")

        # Verify table restored
        tbl_restored = await harness.fetch(
            "SELECT tablename, rowsecurity FROM pg_tables "
            "WHERE tablename = 'custom_field_approvals'"
        )
        assert len(tbl_restored) == 1
        assert tbl_restored[0]["rowsecurity"] is True
