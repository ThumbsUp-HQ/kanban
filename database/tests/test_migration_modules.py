# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle and constraint tests for p3_10b_modules (KB-P3-10b)."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.asyncio
async def test_migration_modules_lifecycle_and_constraints() -> None:
    """Verify upgrade adds module columns, index, view, and downgrade reverts cleanly."""
    async with MigrationHarness() as harness:
        # 1. Upgrade to prior revision
        await harness.upgrade("p2_05a_mfa_totp_recovery")

        pre_cols_rows = await harness.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'modules'"
        )
        pre_col_names = {r["column_name"] for r in pre_cols_rows}
        assert "description_markdown" not in pre_col_names
        assert "lead_principal_id" not in pre_col_names
        assert "status" not in pre_col_names

        # 2. Upgrade to p3_10b_modules
        await harness.upgrade("p3_10b_modules")

        post_cols_rows = await harness.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'modules'"
        )
        post_col_names = {r["column_name"] for r in post_cols_rows}
        assert "description_markdown" in post_col_names
        assert "lead_principal_id" in post_col_names
        assert "status" in post_col_names

        # Check unique index on (project_id, lower(name))
        idx_rows = await harness.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'modules' AND indexname = 'modules_project_lower_name_uq'"
        )
        assert len(idx_rows) == 1

        # Check issue_modules columns and module_issues view
        im_cols_rows = await harness.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'issue_modules'"
        )
        im_col_names = {r["column_name"] for r in im_cols_rows}
        assert "added_at" in im_col_names
        assert "added_by_id" in im_col_names

        view_rows = await harness.fetch(
            "SELECT table_name FROM information_schema.views WHERE table_name = 'module_issues'"
        )
        assert len(view_rows) == 1

        # 3. Downgrade to p2_05a_mfa_totp_recovery
        await harness.downgrade("p2_05a_mfa_totp_recovery")

        down_cols_rows = await harness.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'modules'"
        )
        down_col_names = {r["column_name"] for r in down_cols_rows}
        assert "description_markdown" not in down_col_names
        assert "lead_principal_id" not in down_col_names
        assert "status" not in down_col_names

        down_view = await harness.fetch(
            "SELECT table_name FROM information_schema.views WHERE table_name = 'module_issues'"
        )
        assert len(down_view) == 0

        # 4. Re-upgrade to head
        await harness.upgrade("p3_10b_modules")
