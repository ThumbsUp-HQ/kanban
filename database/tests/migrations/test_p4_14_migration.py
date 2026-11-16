# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p4_14_mcp_scopable_keys (KB-P4-14 / KANBA-106)."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p4_14_mcp_scopable_keys_migration_lifecycle() -> None:
    """Verify p4_14 upgrade applies scopable key columns, constraints, and downgrade reverts."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p4_14_mcp_scopable_keys")
        assert prev_rev == "p5_13_approved_wasm_modules"

        # 1. Upgrade to p4_14_mcp_scopable_keys
        await harness.upgrade("p4_14_mcp_scopable_keys")

        # Verify table exists with FORCE RLS
        table_info = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = $1",
            "mcp_api_keys",
        )
        assert len(table_info) == 1, "Table mcp_api_keys missing"
        assert table_info[0]["relrowsecurity"] is True
        assert table_info[0]["relforcerowsecurity"] is True

        # Verify new columns exist
        cols = await harness.fetch(
            "SELECT column_name, is_nullable, data_type "
            "FROM information_schema.columns "
            "WHERE table_name = 'mcp_api_keys'"
        )
        col_map = {r["column_name"]: (r["is_nullable"], r["data_type"]) for r in cols}
        assert "scope_tier" in col_map
        assert "owner_kind" in col_map
        assert "project_id" in col_map
        assert "allowed_workspace_ids" in col_map
        assert "allowed_project_ids" in col_map
        assert "capability_mask" in col_map
        assert "allowed_tools" in col_map
        assert "disabled_tools" in col_map
        assert "allowed_cidrs" in col_map
        assert col_map["workspace_id"][0] == "YES", "workspace_id must be nullable for global tier"
        assert col_map["expires_at"][0] == "YES", "expires_at must be nullable for unlimited keys"

        # Verify check constraint mcp_keys_tier_shape_chk exists
        constrs = await harness.fetch(
            "SELECT conname FROM pg_constraint WHERE conname = 'mcp_keys_tier_shape_chk'"
        )
        assert len(constrs) == 1, "Constraint mcp_keys_tier_shape_chk missing"

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # Verify columns removed and workspace_id NOT NULL restored
        cols_post = await harness.fetch(
            "SELECT column_name, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'mcp_api_keys'"
        )
        col_map_post = {r["column_name"]: r["is_nullable"] for r in cols_post}
        assert "scope_tier" not in col_map_post
        assert "disabled_tools" not in col_map_post
        assert col_map_post["workspace_id"] == "NO", "workspace_id must be NOT NULL after downgrade"
        assert col_map_post["expires_at"] == "NO", "expires_at must be NOT NULL after downgrade"

        # 3. Upgrade back to head
        await harness.upgrade("p4_14_mcp_scopable_keys")
