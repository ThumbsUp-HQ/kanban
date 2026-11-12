"""Migration tests for p1_03_principals up/down lifecycle."""

import pytest

from database.tests.migration_harness import MigrationHarness

EXPECTED_TABLES = {
    "principals",
    "users",
    "groups",
    "principal_group_edges",
    "principal_group_closure",
}


@pytest.mark.migration
async def test_08_principals_migration_lifecycle() -> None:
    """Verify p1_03 upgrade creates principals tables, downgrade removes them, and re-up works."""
    async with MigrationHarness() as harness:
        assert harness.previous_of("p1_03_principals") == "p1_02_objects_spine"

        # 1. Upgrade to p1_03_principals
        await harness.upgrade("p1_03_principals")

        # Verify all 5 tables exist
        tables_up = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN ("
            "  'principals', 'users', 'groups', 'principal_group_edges', 'principal_group_closure'"
            ")"
        )
        assert {r["table_name"] for r in tables_up} == EXPECTED_TABLES

        # Verify rebuild_group_closure function exists
        funcs_up = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name = 'rebuild_group_closure'"
        )
        assert len(funcs_up) == 1

        # 2. Downgrade to p1_02_objects_spine
        prev_rev = harness.previous_of("p1_03_principals")
        await harness.downgrade(prev_rev)

        # Verify all 5 tables are absent
        tables_down = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN ("
            "  'principals', 'users', 'groups', 'principal_group_edges', 'principal_group_closure'"
            ")"
        )
        assert len(tables_down) == 0

        funcs_down = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name = 'rebuild_group_closure'"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to p1_03_principals succeeds
        await harness.upgrade("p1_03_principals")

        tables_reup = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN ("
            "  'principals', 'users', 'groups', 'principal_group_edges', 'principal_group_closure'"
            ")"
        )
        assert {r["table_name"] for r in tables_reup} == EXPECTED_TABLES
