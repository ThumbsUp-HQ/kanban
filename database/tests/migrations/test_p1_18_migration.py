"""Migration lifecycle test for p1_18_outbox."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_18_outbox_migration_lifecycle() -> None:
    """Verify p1_18 upgrade applies outbox table, trigger, and functions, and downgrade reverts."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p1_18_outbox")
        assert prev_rev == "p1_16_link_purger"

        # 1. Upgrade to p1_18_outbox
        await harness.upgrade("p1_18_outbox")

        # Verify table exists with FORCE RLS
        table_info = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'outbox_events'"
        )
        assert len(table_info) == 1
        assert table_info[0]["relrowsecurity"] is True
        assert table_info[0]["relforcerowsecurity"] is True

        # Verify functions exist
        funcs = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' "
            "  AND proname IN ("
            "    'claim_outbox_batch', 'mark_outbox_published', "
            "    'mark_outbox_failed', 'outbox_events_wakeup_fn'"
            "  )"
        )
        assert {r["proname"] for r in funcs} == {
            "claim_outbox_batch",
            "mark_outbox_published",
            "mark_outbox_failed",
            "outbox_events_wakeup_fn",
        }

        # Verify trigger exists
        triggers = await harness.fetch(
            "SELECT tgname FROM pg_trigger WHERE tgname = 'outbox_events_wakeup_ai'"
        )
        assert len(triggers) == 1

        # Verify RLS policies exist
        policies = await harness.fetch(
            "SELECT polname FROM pg_policy pol "
            "JOIN pg_class c ON c.oid = pol.polrelid "
            "WHERE c.relname = 'outbox_events'"
        )
        assert {r["polname"] for r in policies} == {
            "outbox_events_insert_rls",
            "outbox_events_select_rls",
        }

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # Verify table is dropped
        table_down = await harness.fetch(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'outbox_events'"
        )
        assert len(table_down) == 0

        # Verify functions are dropped
        funcs_down = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' "
            "  AND proname IN ("
            "    'claim_outbox_batch', 'mark_outbox_published', "
            "    'mark_outbox_failed', 'outbox_events_wakeup_fn'"
            "  )"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to p1_18_outbox
        await harness.upgrade("p1_18_outbox")

        # Verify table exists again
        table_reup = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'outbox_events'"
        )
        assert len(table_reup) == 1
        assert table_reup[0]["relrowsecurity"] is True
        assert table_reup[0]["relforcerowsecurity"] is True
