# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p6_01_import_entity_mappings (KB-P6-01)."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p6_01_import_entity_mappings_migration_lifecycle() -> None:
    """Verify p6_01 upgrade applies import_entity_mappings with FORCE RLS, and downgrade reverts."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p6_01_import_entity_mappings")
        assert prev_rev == "p5_12_custom_field_approvals"

        # 1. Upgrade to p6_01_import_entity_mappings
        await harness.upgrade("p6_01_import_entity_mappings")

        # Verify table exists with FORCE RLS
        table_info = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = $1",
            "import_entity_mappings",
        )
        assert len(table_info) == 1, "Table import_entity_mappings missing"
        assert table_info[0]["relrowsecurity"] is True
        assert table_info[0]["relforcerowsecurity"] is True

        # Verify index exists
        idx_info = await harness.fetch(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = $1",
            "import_entity_mappings_target_idx",
        )
        assert len(idx_info) == 1, "Index import_entity_mappings_target_idx missing"

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # Verify table removed
        table_info_post = await harness.fetch(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = $1",
            "import_entity_mappings",
        )
        assert len(table_info_post) == 0, "Table import_entity_mappings was not dropped"

        # 3. Upgrade back to head
        await harness.upgrade("p6_01_import_entity_mappings")
