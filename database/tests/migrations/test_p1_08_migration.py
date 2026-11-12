"""Migration tests for p1_08_planning_joins up/down lifecycle."""

import pytest

from database.tests.migration_harness import MigrationHarness

_TARGET_TABLES = {
    "cycles",
    "modules",
    "project_module_defaults",
    "issue_modules",
    "issue_assignees",
    "issue_labels",
    "issue_subscriptions",
}


@pytest.mark.migration
async def test_08_planning_joins_migration_lifecycle() -> None:
    """Verify p1_08 upgrade creates 7 tables and FK, downgrade removes them, and re-up works."""
    async with MigrationHarness() as harness:
        assert harness.previous_of("p1_08_planning_joins") == "p1_13_access_control"

        # 1. Upgrade to p1_08_planning_joins
        await harness.upgrade("p1_08_planning_joins")

        tables_up = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ANY($1)",
            list(_TARGET_TABLES),
        )
        assert {r["table_name"] for r in tables_up} == _TARGET_TABLES

        fk_up = await harness.fetch(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_schema = 'public' AND table_name = 'issues' "
            "AND constraint_name = 'issues_cycle_fk'"
        )
        assert len(fk_up) == 1

        # 2. Downgrade to p1_05_issues
        prev_rev = harness.previous_of("p1_08_planning_joins")
        await harness.downgrade(prev_rev)

        tables_down = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ANY($1)",
            list(_TARGET_TABLES),
        )
        assert len(tables_down) == 0

        fk_down = await harness.fetch(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_schema = 'public' AND table_name = 'issues' "
            "AND constraint_name = 'issues_cycle_fk'"
        )
        assert len(fk_down) == 0

        # 3. Re-upgrade to p1_08_planning_joins
        await harness.upgrade("p1_08_planning_joins")

        tables_reup = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ANY($1)",
            list(_TARGET_TABLES),
        )
        assert {r["table_name"] for r in tables_reup} == _TARGET_TABLES
