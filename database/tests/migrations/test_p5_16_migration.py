"""Migration lifecycle test for p5_16_agent_definitions (KB-P5-16)."""

from __future__ import annotations

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_5_16_agent_definitions_migration_lifecycle() -> None:
    """Verify p5_16 upgrade applies agent_definitions with FORCE RLS, and downgrade reverts."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p5_16_agent_definitions")
        assert prev_rev == "p2_02_sessions"

        # 1. Upgrade to p5_16_agent_definitions
        await harness.upgrade("p5_16_agent_definitions")

        # Verify agent_definitions exists with FORCE RLS
        table_info = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'agent_definitions'"
        )
        assert len(table_info) == 1
        assert table_info[0]["relrowsecurity"] is True
        assert table_info[0]["relforcerowsecurity"] is True

        # Verify CHECK constraints exist
        constraints = await harness.fetch(
            "SELECT conname FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = 'agent_definitions' "
            "  AND conname IN ("
            "    'agent_def_harness_fields',"
            "    'agent_def_mcp_tools_subset',"
            "    'agent_def_args_is_array'"
            "  )"
        )
        found_cons = {r["conname"] for r in constraints}
        assert found_cons == {
            "agent_def_harness_fields",
            "agent_def_mcp_tools_subset",
            "agent_def_args_is_array",
        }

        # 2. Downgrade to p2_18_rate_limit_buckets
        await harness.downgrade(prev_rev)

        # Verify table dropped
        table_down = await harness.fetch(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'agent_definitions'"
        )
        assert len(table_down) == 0

        # 3. Re-upgrade to p5_16_agent_definitions
        await harness.upgrade("p5_16_agent_definitions")

        table_reup = await harness.fetch(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'agent_definitions'"
        )
        assert len(table_reup) == 1
