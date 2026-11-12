"""Migration lifecycle test for p1_16_link_purger."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_16_link_purger_migration_lifecycle() -> None:
    """Verify p1_16 upgrade applies purger function and trigger, and downgrade reverts."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p1_16_link_purger")
        assert prev_rev == "p1_15_link_auditor"

        # 1. Upgrade to p1_16_link_purger
        await harness.upgrade("p1_16_link_purger")

        # Verify function exists
        funcs = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND proname = 'purge_invalid_object_links'"
        )
        assert len(funcs) == 1

        # Verify trigger exists
        triggers = await harness.fetch(
            "SELECT tgname FROM pg_trigger "
            "WHERE tgname = 'object_links_flagged_delete_guard_bd_trg'"
        )
        assert len(triggers) == 1

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # Verify function is dropped
        funcs_down = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND proname = 'purge_invalid_object_links'"
        )
        assert len(funcs_down) == 0

        # Verify trigger is dropped
        triggers_down = await harness.fetch(
            "SELECT tgname FROM pg_trigger "
            "WHERE tgname = 'object_links_flagged_delete_guard_bd_trg'"
        )
        assert len(triggers_down) == 0

        # 3. Re-upgrade to p1_16_link_purger
        await harness.upgrade("p1_16_link_purger")

        # Verify function exists again
        funcs_reup = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND proname = 'purge_invalid_object_links'"
        )
        assert len(funcs_reup) == 1

        # Verify trigger exists again
        triggers_reup = await harness.fetch(
            "SELECT tgname FROM pg_trigger "
            "WHERE tgname = 'object_links_flagged_delete_guard_bd_trg'"
        )
        assert len(triggers_reup) == 1
