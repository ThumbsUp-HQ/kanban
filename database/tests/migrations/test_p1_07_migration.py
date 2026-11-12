"""Migration tests for p1_07_creator_provenance up/down lifecycle."""

import pytest

from database.tests.migration_harness import MigrationHarness

EXPECTED_TRIGGERS = {"issues_creator_insert_bi_trg", "issues_creator_provenance_bu_trg"}
EXPECTED_ROUTINES = {"issues_creator_insert_bi", "issues_creator_provenance_bu"}


@pytest.mark.migration
async def test_07_creator_provenance_migration_lifecycle() -> None:
    """Verify p1_07 upgrade creates triggers, downgrade removes them, and re-upgrade."""
    async with MigrationHarness() as harness:
        assert harness.previous_of("p1_07_creator_provenance") == "p1_13_access_control"

        # 1. Upgrade to p1_07_creator_provenance
        await harness.upgrade("p1_07_creator_provenance")

        # Verify triggers exist on issues table
        triggers_up = await harness.fetch(
            "SELECT trigger_name FROM information_schema.triggers "
            "WHERE event_object_table = 'issues' "
            "  AND trigger_name IN ("
            "    'issues_creator_insert_bi_trg', 'issues_creator_provenance_bu_trg'"
            "  )"
        )
        assert {r["trigger_name"] for r in triggers_up} == EXPECTED_TRIGGERS

        # Verify trigger functions exist
        funcs_up = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' "
            "  AND routine_name IN ("
            "    'issues_creator_insert_bi', 'issues_creator_provenance_bu'"
            "  )"
        )
        assert {r["routine_name"] for r in funcs_up} == EXPECTED_ROUTINES

        # 2. Downgrade to p1_13_access_control
        prev_rev = harness.previous_of("p1_07_creator_provenance")
        await harness.downgrade(prev_rev)

        # Verify triggers are absent
        triggers_down = await harness.fetch(
            "SELECT trigger_name FROM information_schema.triggers "
            "WHERE event_object_table = 'issues' "
            "  AND trigger_name IN ("
            "    'issues_creator_insert_bi_trg', 'issues_creator_provenance_bu_trg'"
            "  )"
        )
        assert len(triggers_down) == 0

        # Verify functions are absent
        funcs_down = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' "
            "  AND routine_name IN ("
            "    'issues_creator_insert_bi', 'issues_creator_provenance_bu'"
            "  )"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to p1_07_creator_provenance succeeds
        await harness.upgrade("p1_07_creator_provenance")

        triggers_reup = await harness.fetch(
            "SELECT trigger_name FROM information_schema.triggers "
            "WHERE event_object_table = 'issues' "
            "  AND trigger_name IN ("
            "    'issues_creator_insert_bi_trg', 'issues_creator_provenance_bu_trg'"
            "  )"
        )
        assert {r["trigger_name"] for r in triggers_reup} == EXPECTED_TRIGGERS

        funcs_reup = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' "
            "  AND routine_name IN ("
            "    'issues_creator_insert_bi', 'issues_creator_provenance_bu'"
            "  )"
        )
        assert {r["routine_name"] for r in funcs_reup} == EXPECTED_ROUTINES
