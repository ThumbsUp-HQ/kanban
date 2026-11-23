# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p6_13_csv_import_export_governance."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p6_13_csv_import_export_governance_migration_lifecycle() -> None:
    """Verify p6_13_csv_import_export_governance upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p6_13_csv_import_export_governance")
        assert prev_rev == "p6_09_scm_webhooks_and_outbound_bus"

        # 1. Upgrade to p6_13_csv_import_export_governance
        await harness.upgrade("p6_13_csv_import_export_governance")

        cols_up = await harness.fetch(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'workspace_settings' "
            "  AND column_name IN ('issue_export_enabled', 'issue_import_enabled', 'issue_export_allowed_roles') "
            "ORDER BY column_name;"
        )
        assert len(cols_up) == 3
        col_names = {c["column_name"] for c in cols_up}
        assert col_names == {"issue_export_enabled", "issue_import_enabled", "issue_export_allowed_roles"}

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        cols_down = await harness.fetch(
            "SELECT column_name "
            "FROM information_schema.columns "
            "WHERE table_name = 'workspace_settings' "
            "  AND column_name IN ('issue_export_enabled', 'issue_import_enabled', 'issue_export_allowed_roles');"
        )
        assert len(cols_down) == 0

        # 3. Upgrade back to head
        await harness.upgrade("p6_13_csv_import_export_governance")

        cols_up_again = await harness.fetch(
            "SELECT column_name "
            "FROM information_schema.columns "
            "WHERE table_name = 'workspace_settings' "
            "  AND column_name IN ('issue_export_enabled', 'issue_import_enabled', 'issue_export_allowed_roles');"
        )
        assert len(cols_up_again) == 3
