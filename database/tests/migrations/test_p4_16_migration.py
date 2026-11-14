# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p4_16_oauth_device_codes (KB-P4-16)."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p4_16_oauth_device_codes_migration_lifecycle() -> None:
    """Verify p4_16 upgrade applies oauth_device_codes with FORCE RLS, and downgrade reverts."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p4_16_oauth_device_codes")
        assert prev_rev == "p4_13_mcp_ephemeral_tokens"

        # 1. Upgrade to p4_16_oauth_device_codes
        await harness.upgrade("p4_16_oauth_device_codes")

        # Verify table exists with FORCE RLS
        table_info = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = $1",
            "oauth_device_codes",
        )
        assert len(table_info) == 1, "Table oauth_device_codes missing"
        assert table_info[0]["relrowsecurity"] is True
        assert table_info[0]["relforcerowsecurity"] is True

        # Verify index exists
        idx_info = await harness.fetch(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = $1",
            "idx_oauth_device_codes_user_code",
        )
        assert len(idx_info) == 1, "Index idx_oauth_device_codes_user_code missing"

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # Verify table removed
        table_info_post = await harness.fetch(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = $1",
            "oauth_device_codes",
        )
        assert len(table_info_post) == 0, "Table oauth_device_codes was not dropped"

        # 3. Upgrade back to head
        await harness.upgrade("p4_16_oauth_device_codes")
