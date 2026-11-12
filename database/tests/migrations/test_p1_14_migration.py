"""Migration lifecycle test for p1_14_force_rls."""

import pytest

from database.tests.migration_harness import MigrationHarness

RLS_CATALOG_CHECK = """
SELECT c.relname
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p')
  AND c.relname NOT IN ('alembic_version', 'link_type_matrix')
  AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity);
"""


@pytest.mark.migration
async def test_07_force_rls_migration_lifecycle() -> None:
    """Verify p1_14 upgrade applies RLS, downgrade reverts policies, and re-upgrade succeeds."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p1_14_force_rls")
        assert prev_rev == "p1_07_creator_provenance"

        # 1. Upgrade to p1_14_force_rls
        await harness.upgrade("p1_14_force_rls")

        # Verify catalog gate: 0 unprotected tenant tables/partitions
        unprotected = await harness.fetch(RLS_CATALOG_CHECK)
        assert len(unprotected) == 0, f"Found unprotected tables after upgrade: {unprotected}"

        # Verify helper functions exist
        helpers = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' "
            "  AND proname IN ("
            "    'app_current_token_scopes', 'app_current_aal_level', 'app_has_object_capability'"
            "  )"
        )
        assert {r["proname"] for r in helpers} == {
            "app_current_token_scopes",
            "app_current_aal_level",
            "app_has_object_capability",
        }

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # Verify policies are removed
        policies = await harness.fetch(
            "SELECT policyname FROM pg_policies WHERE schemaname = 'public'"
        )
        assert len(policies) == 0, f"Expected 0 policies after downgrade, found: {policies}"

        # Verify helper functions are dropped
        helpers_down = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' "
            "  AND proname IN ("
            "    'app_current_token_scopes', 'app_current_aal_level', 'app_has_object_capability'"
            "  )"
        )
        assert len(helpers_down) == 0, f"Expected helpers dropped, found: {helpers_down}"

        # 3. Re-upgrade to p1_14_force_rls
        await harness.upgrade("p1_14_force_rls")

        # Verify catalog gate passes again
        unprotected_reup = await harness.fetch(RLS_CATALOG_CHECK)
        assert len(unprotected_reup) == 0, (
            f"Found unprotected tables after re-upgrade: {unprotected_reup}"
        )
