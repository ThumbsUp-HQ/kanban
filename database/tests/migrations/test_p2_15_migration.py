"""Migration lifecycle test for p2_15_attachments (S5.4, KB-P2-15)."""

from __future__ import annotations

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_2_15_attachments_migration_lifecycle() -> None:
    """Verify p2_15 upgrade applies attachments table with FORCE RLS, and downgrade reverts."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p2_15_attachments")
        assert prev_rev == "p2_18_rate_limit_buckets"

        # 1. Upgrade to p2_15_attachments
        await harness.upgrade("p2_15_attachments")

        # Verify attachments exists with FORCE RLS
        table_info = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'attachments'"
        )
        assert len(table_info) == 1
        assert table_info[0]["relrowsecurity"] is True
        assert table_info[0]["relforcerowsecurity"] is True

        # Verify trigger function exists
        funcs = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND proname = 'attachments_workspace_biu'"
        )
        assert len(funcs) == 1

        # 2. Downgrade to p2_18_rate_limit_buckets
        await harness.downgrade(prev_rev)

        # Verify table dropped
        table_down = await harness.fetch(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'attachments'"
        )
        assert len(table_down) == 0

        # Verify trigger function dropped
        funcs_down = await harness.fetch(
            "SELECT 1 FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND proname = 'attachments_workspace_biu'"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to p2_15_attachments
        await harness.upgrade("p2_15_attachments")

        table_reup = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'attachments'"
        )
        assert len(table_reup) == 1
        assert table_reup[0]["relrowsecurity"] is True
        assert table_reup[0]["relforcerowsecurity"] is True
