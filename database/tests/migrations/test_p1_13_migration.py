"""Migration tests for p1_13_access_control up/down lifecycle."""

import pytest

from database.tests.migration_harness import MigrationHarness

EXPECTED_TABLES = {"role_bindings", "resource_acl_entries", "effective_resource_access"}
EXPECTED_ROLES = {
    "SERVER_ADMIN",
    "WORKSPACE_ADMIN",
    "WORKSPACE_MEMBER",
    "WORKSPACE_GUEST",
    "PROJECT_ADMIN",
    "MEMBER",
    "VIEWER",
}


@pytest.mark.migration
async def test_07_access_control_migration_lifecycle() -> None:
    """Verify p1_13 upgrade creates 3 tables + enum, downgrade removes them, and re-upgrade."""
    async with MigrationHarness() as harness:
        assert harness.previous_of("p1_13_access_control") == "p1_10_views"

        # 1. Upgrade to p1_13_access_control
        await harness.upgrade("p1_13_access_control")

        # Verify 3 tables exist
        tables_up = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "  AND table_name IN ("
            "    'role_bindings', 'resource_acl_entries', 'effective_resource_access'"
            "  )"
        )
        assert {r["table_name"] for r in tables_up} == EXPECTED_TABLES

        # Verify rbac_role enum exists with exactly 7 values
        roles_up = await harness.fetch(
            "SELECT e.enumlabel "
            "FROM pg_enum e "
            "JOIN pg_type t ON e.enumtypid = t.oid "
            "WHERE t.typname = 'rbac_role'"
        )
        assert {r["enumlabel"] for r in roles_up} == EXPECTED_ROLES

        # Verify functions exist
        funcs_up = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' "
            "  AND routine_name IN ("
            "    'capability_bit', "
            "    'rbac_role_mask', "
            "    'app_effective_principal_set', "
            "    'app_principal_has_role', "
            "    'rebuild_effective_access_for_workspace'"
            "  )"
        )
        assert len(funcs_up) == 5

        # 2. Downgrade to p1_10_views
        prev_rev = harness.previous_of("p1_13_access_control")
        await harness.downgrade(prev_rev)

        # Verify tables are absent
        tables_down = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "  AND table_name IN ("
            "    'role_bindings', 'resource_acl_entries', 'effective_resource_access'"
            "  )"
        )
        assert len(tables_down) == 0

        # Verify enum is absent
        enum_down = await harness.fetch("SELECT typname FROM pg_type WHERE typname = 'rbac_role'")
        assert len(enum_down) == 0

        # Verify functions are absent
        funcs_down = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' "
            "  AND routine_name IN ("
            "    'capability_bit', "
            "    'rbac_role_mask', "
            "    'app_effective_principal_set', "
            "    'app_principal_has_role', "
            "    'rebuild_effective_access_for_workspace'"
            "  )"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to p1_13_access_control succeeds
        await harness.upgrade("p1_13_access_control")

        tables_reup = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "  AND table_name IN ("
            "    'role_bindings', 'resource_acl_entries', 'effective_resource_access'"
            "  )"
        )
        assert {r["table_name"] for r in tables_reup} == EXPECTED_TABLES
