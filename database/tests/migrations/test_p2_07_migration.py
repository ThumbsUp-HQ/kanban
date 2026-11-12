# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p2_07_ldap_group_mappings (KB-P2-07)."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_25_ldap_group_mappings_migration_lifecycle() -> None:
    """Verify p2_07 upgrade applies ldap_group_mappings with FORCE RLS, and downgrade reverts."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p2_07_ldap_group_mappings")
        assert prev_rev == "p3_10b_modules"

        # 1. Upgrade to p2_07_ldap_group_mappings
        await harness.upgrade("p2_07_ldap_group_mappings")

        # Verify table exists with FORCE RLS
        table_info = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'ldap_group_mappings'"
        )
        assert len(table_info) == 1
        assert table_info[0]["relrowsecurity"] is True
        assert table_info[0]["relforcerowsecurity"] is True

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        table_gone = await harness.fetch(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'ldap_group_mappings'"
        )
        assert len(table_gone) == 0

        # 3. Re-upgrade to p2_07_ldap_group_mappings
        await harness.upgrade("p2_07_ldap_group_mappings")

        table_recheck = await harness.fetch(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'ldap_group_mappings'"
        )
        assert len(table_recheck) == 1
