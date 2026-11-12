"""Migration tests for p1_10_views up/down lifecycle."""

import pytest

from database.tests.migration_harness import MigrationHarness

EXPECTED_ENUM_LABELS = {"list", "board", "table", "calendar", "timeline"}


@pytest.mark.migration
async def test_06_views_migration_lifecycle() -> None:
    """Verify p1_10 upgrade creates views table + enum, downgrade removes them, and re-upgrade."""
    async with MigrationHarness() as harness:
        assert harness.previous_of("p1_10_views") == "p1_11_object_links"

        # 1. Upgrade to p1_10_views
        await harness.upgrade("p1_10_views")

        # Verify views table exists
        tables_up = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'views'"
        )
        assert len(tables_up) == 1

        # Verify view_layout enum exists and has exactly 5 labels
        enum_up = await harness.fetch(
            "SELECT e.enumlabel "
            "FROM pg_enum e "
            "JOIN pg_type t ON e.enumtypid = t.oid "
            "WHERE t.typname = 'view_layout'"
        )
        labels = {r["enumlabel"] for r in enum_up}
        assert labels == EXPECTED_ENUM_LABELS

        # Verify functions exist
        funcs_up = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' "
            "  AND routine_name IN ("
            "    'validate_view_filters_json', "
            "    'validate_view_wip_limits_json', "
            "    'views_spine_match_biu'"
            "  )"
        )
        assert len(funcs_up) == 3

        # 2. Downgrade to p1_11_object_links
        prev_rev = harness.previous_of("p1_10_views")
        await harness.downgrade(prev_rev)

        # Verify table is absent
        tables_down = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'views'"
        )
        assert len(tables_down) == 0

        # Verify enum is absent
        enum_down = await harness.fetch("SELECT typname FROM pg_type WHERE typname = 'view_layout'")
        assert len(enum_down) == 0

        # Verify functions are absent
        funcs_down = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' "
            "  AND routine_name IN ("
            "    'validate_view_filters_json', "
            "    'validate_view_wip_limits_json', "
            "    'views_spine_match_biu'"
            "  )"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to p1_10_views succeeds
        await harness.upgrade("p1_10_views")

        tables_reup = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'views'"
        )
        assert len(tables_reup) == 1
