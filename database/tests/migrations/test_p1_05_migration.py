"""Migration tests for p1_05_issues up/down lifecycle."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_08_issues_migration_lifecycle() -> None:
    """Verify p1_05 upgrade creates issues, downgrade removes them, and re-up works."""
    async with MigrationHarness() as harness:
        assert harness.previous_of("p1_05_issues") == "p1_10_views"

        # 1. Upgrade to p1_05_issues
        await harness.upgrade("p1_05_issues")

        tables_up = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'issues'"
        )
        assert len(tables_up) == 1

        funcs_up = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name IN ("
            "  'build_markdown_tsvector', 'allocate_issue_sequence'"
            ")"
        )
        assert {r["routine_name"] for r in funcs_up} == {
            "build_markdown_tsvector",
            "allocate_issue_sequence",
        }

        # 2. Downgrade to p1_11_object_links
        prev_rev = harness.previous_of("p1_05_issues")
        await harness.downgrade(prev_rev)

        tables_down = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'issues'"
        )
        assert len(tables_down) == 0

        funcs_down = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name IN ("
            "  'build_markdown_tsvector', 'allocate_issue_sequence'"
            ")"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to p1_05_issues succeeds
        await harness.upgrade("p1_05_issues")

        tables_reup = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'issues'"
        )
        assert len(tables_reup) == 1
