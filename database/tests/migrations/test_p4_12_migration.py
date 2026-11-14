# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p4_12_destructive_tokens (KB-P4-12)."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p4_12_destructive_tokens_migration_lifecycle() -> None:
    """Verify p4_12 upgrade applies destructive_confirmation_tokens with FORCE RLS, and downgrade reverts."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p4_12_destructive_tokens")
        assert prev_rev == "p4_13_mcp_ephemeral_tokens"

        # 1. Upgrade to p4_12_destructive_tokens
        await harness.upgrade("p4_12_destructive_tokens")

        # Verify table exists with FORCE RLS
        table_info = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = $1",
            "destructive_confirmation_tokens",
        )
        assert len(table_info) == 1, "Table destructive_confirmation_tokens missing"
        assert table_info[0]["relrowsecurity"] is True
        assert table_info[0]["relforcerowsecurity"] is True

        # Verify indexes exist
        idx_info = await harness.fetch(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname IN ($1, $2)",
            "destructive_tokens_lookup_idx",
            "destructive_tokens_ws_target_idx",
        )
        assert len(idx_info) == 2, "Indexes on destructive_confirmation_tokens missing"

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # Verify table removed
        table_info_post = await harness.fetch(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = $1",
            "destructive_confirmation_tokens",
        )
        assert len(table_info_post) == 0, "Table destructive_confirmation_tokens was not dropped"

        # 3. Upgrade back to head
        await harness.upgrade("p4_12_destructive_tokens")
