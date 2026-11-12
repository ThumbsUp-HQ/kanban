"""Migration tests for p3_04_creator_override_reason up/down lifecycle."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p3_04_creator_override_reason_lifecycle() -> None:
    """Verify p3_04 upgrade updates trigger with reason, downgrade reverts, and re-upgrade."""
    async with MigrationHarness() as harness:
        assert harness.previous_of("p3_04_creator_override_reason") == "p3_10b_modules"

        # 1. Upgrade to p3_04_creator_override_reason
        await harness.upgrade("p3_04_creator_override_reason")

        # Verify trigger function routine exists and contains 'app.override_reason'
        rows_up = await harness.fetch(
            "SELECT routine_definition FROM information_schema.routines "
            "WHERE routine_schema = 'public' "
            "  AND routine_name = 'issues_creator_provenance_bu'"
        )
        assert len(rows_up) == 1
        defn_up = rows_up[0]["routine_definition"]
        assert "app.override_reason" in defn_up
        assert "old_created_by_id" in defn_up
        assert "new_created_by_id" in defn_up

        # 2. Downgrade to p2_02_sessions
        prev_rev = harness.previous_of("p3_04_creator_override_reason")
        await harness.downgrade(prev_rev)

        rows_down = await harness.fetch(
            "SELECT routine_definition FROM information_schema.routines "
            "WHERE routine_schema = 'public' "
            "  AND routine_name = 'issues_creator_provenance_bu'"
        )
        assert len(rows_down) == 1
        defn_down = rows_down[0]["routine_definition"]
        assert "app.override_reason" not in defn_down

        # 3. Re-upgrade to p3_04_creator_override_reason succeeds
        await harness.upgrade("p3_04_creator_override_reason")

        rows_reup = await harness.fetch(
            "SELECT routine_definition FROM information_schema.routines "
            "WHERE routine_schema = 'public' "
            "  AND routine_name = 'issues_creator_provenance_bu'"
        )
        assert len(rows_reup) == 1
        defn_reup = rows_reup[0]["routine_definition"]
        assert "app.override_reason" in defn_reup
