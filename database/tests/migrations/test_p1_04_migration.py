"""Migration tests for p1_04_projects up/down lifecycle."""

import pytest

from database.tests.migration_harness import MigrationHarness

EXPECTED_TABLES = {"projects", "workflow_states", "project_priorities", "project_labels"}


@pytest.mark.migration
async def test_08_projects_migration_lifecycle() -> None:
    """Verify p1_04 upgrade creates 4 tables + FK, downgrade removes them, and re-upgrade works."""
    async with MigrationHarness() as harness:
        assert harness.previous_of("p1_04_projects") == "p1_02_objects_spine"

        # 1. Upgrade to p1_04_projects
        await harness.upgrade("p1_04_projects")

        # Verify all 4 tables exist
        tables_up = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "  AND table_name IN ("
            "    'projects', 'workflow_states', 'project_priorities', 'project_labels'"
            "  )"
        )
        assert {r["table_name"] for r in tables_up} == EXPECTED_TABLES

        # Verify objects_project_fk constraint exists on objects table
        fk_up = await harness.fetch(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_schema = 'public' "
            "  AND table_name = 'objects' "
            "  AND constraint_name = 'objects_project_fk'"
        )
        assert len(fk_up) == 1

        # Verify seeding trigger function exists
        funcs_up = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' "
            "  AND routine_name IN ('projects_seed_defaults_ai', 'workflow_states_group_guard_bd')"
        )
        assert len(funcs_up) == 2

        # 2. Downgrade to p1_02_objects_spine
        prev_rev = harness.previous_of("p1_04_projects")
        await harness.downgrade(prev_rev)

        # Verify tables are absent
        tables_down = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "  AND table_name IN ("
            "    'projects', 'workflow_states', 'project_priorities', 'project_labels'"
            "  )"
        )
        assert len(tables_down) == 0

        # Verify FK is absent
        fk_down = await harness.fetch(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_schema = 'public' "
            "  AND table_name = 'objects' "
            "  AND constraint_name = 'objects_project_fk'"
        )
        assert len(fk_down) == 0

        # Verify functions are absent
        funcs_down = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' "
            "  AND routine_name IN ('projects_seed_defaults_ai', 'workflow_states_group_guard_bd')"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to p1_04_projects succeeds
        await harness.upgrade("p1_04_projects")

        tables_reup = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "  AND table_name IN ("
            "    'projects', 'workflow_states', 'project_priorities', 'project_labels'"
            "  )"
        )
        assert {r["table_name"] for r in tables_reup} == EXPECTED_TABLES
