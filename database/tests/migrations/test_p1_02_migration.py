"""Migration tests for p1_02_objects_spine up/down lifecycle."""

import pytest

from database.tests.migration_harness import MigrationHarness

EXPECTED_ENUM_LABELS = [
    "issue",
    "sticky",
    "doc",
    "user",
    "project",
    "cycle",
    "module",
    "view",
    "page",
]


@pytest.mark.migration
async def test_08_objects_spine_migration_lifecycle() -> None:
    """Verify p1_02 upgrade creates objects and enum, downgrade removes them, and re-up works."""
    async with MigrationHarness() as harness:
        assert harness.previous_of("p1_02_objects_spine") == "p1_01_baseline"

        # 1. Upgrade to p1_02_objects_spine
        await harness.upgrade("p1_02_objects_spine")

        # Verify object_kind enum has exactly the 9 labels in spec order
        enum_rows = await harness.fetch(
            "SELECT e.enumlabel "
            "FROM pg_enum e "
            "JOIN pg_type t ON e.enumtypid = t.oid "
            "WHERE t.typname = 'object_kind' "
            "ORDER BY e.enumsortorder"
        )
        labels = [r["enumlabel"] for r in enum_rows]
        assert labels == EXPECTED_ENUM_LABELS

        # Verify tables and function exist
        tables_up = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN ('workspaces', 'objects')"
        )
        assert {r["table_name"] for r in tables_up} == {"workspaces", "objects"}

        funcs_up = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name = 'register_object'"
        )
        assert len(funcs_up) == 1

        # 2. Downgrade to p1_01_baseline
        prev_rev = harness.previous_of("p1_02_objects_spine")
        await harness.downgrade(prev_rev)

        # Verify tables, enum, and function are absent
        tables_down = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN ('workspaces', 'objects')"
        )
        assert len(tables_down) == 0

        types_down = await harness.fetch(
            "SELECT typname FROM pg_type WHERE typname = 'object_kind'"
        )
        assert len(types_down) == 0

        funcs_down = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name = 'register_object'"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to p1_02_objects_spine succeeds
        await harness.upgrade("p1_02_objects_spine")

        tables_reup = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN ('workspaces', 'objects')"
        )
        assert {r["table_name"] for r in tables_reup} == {"workspaces", "objects"}
