"""Migration tests for p1_09_prose_tables up/down lifecycle."""

import pytest

from database.tests.migration_harness import MigrationHarness

EXPECTED_TABLES = {"issue_comments", "docs", "pages", "page_versions", "stickies"}


@pytest.mark.migration
async def test_07_prose_tables_migration_lifecycle() -> None:
    """Verify p1_09 upgrade creates 5 tables, downgrade removes them, and re-upgrade succeeds."""
    async with MigrationHarness() as harness:
        assert harness.previous_of("p1_09_prose_tables") == "p1_06_parent_dag"

        # 1. Upgrade to p1_09_prose_tables
        await harness.upgrade("p1_09_prose_tables")

        # Verify 5 tables exist
        tables_up = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "  AND table_name IN ("
            "    'issue_comments', 'docs', 'pages', 'page_versions', 'stickies'"
            "  )"
        )
        assert {r["table_name"] for r in tables_up} == EXPECTED_TABLES

        # 2. Downgrade to p1_13_access_control
        prev_rev = harness.previous_of("p1_09_prose_tables")
        await harness.downgrade(prev_rev)

        # Verify 5 tables are absent
        tables_down = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "  AND table_name IN ("
            "    'issue_comments', 'docs', 'pages', 'page_versions', 'stickies'"
            "  )"
        )
        assert len(tables_down) == 0

        # 3. Re-upgrade to p1_09_prose_tables
        await harness.upgrade("p1_09_prose_tables")

        tables_reup = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "  AND table_name IN ("
            "    'issue_comments', 'docs', 'pages', 'page_versions', 'stickies'"
            "  )"
        )
        assert {r["table_name"] for r in tables_reup} == EXPECTED_TABLES
