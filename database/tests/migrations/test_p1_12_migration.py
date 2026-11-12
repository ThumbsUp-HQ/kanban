"""Migration tests for p1_12_activity_ledger up/down lifecycle."""

from __future__ import annotations

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_07_activity_ledger_migration_lifecycle() -> None:
    """Verify p1_12 upgrade creates tables/functions, downgrade removes, and re-up works."""
    async with MigrationHarness() as harness:
        assert harness.previous_of("p1_12_activity_ledger") == "p1_05_issues"

        # 1. Upgrade to p1_12_activity_ledger
        await harness.upgrade("p1_12_activity_ledger")

        # Verify tables exist
        tables_up = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN "
            "('activity_records', 'activity_chain_heads')"
        )
        assert {r["table_name"] for r in tables_up} == {
            "activity_records",
            "activity_chain_heads",
        }

        # Verify functions exist
        funcs_up = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name IN ("
            "  'ensure_activity_partitions', 'compute_activity_row_hash',"
            "  'append_activity', 'verify_activity_chain'"
            ")"
        )
        assert {r["routine_name"] for r in funcs_up} == {
            "ensure_activity_partitions",
            "compute_activity_row_hash",
            "append_activity",
            "verify_activity_chain",
        }

        # 2. Downgrade to p1_11_object_links
        prev_rev = harness.previous_of("p1_12_activity_ledger")
        await harness.downgrade(prev_rev)

        tables_down = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN "
            "('activity_records', 'activity_chain_heads')"
        )
        assert len(tables_down) == 0

        funcs_down = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name IN ("
            "  'ensure_activity_partitions', 'compute_activity_row_hash',"
            "  'append_activity', 'verify_activity_chain'"
            ")"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to p1_12_activity_ledger succeeds
        await harness.upgrade("p1_12_activity_ledger")
        tables_reup = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN "
            "('activity_records', 'activity_chain_heads')"
        )
        assert {r["table_name"] for r in tables_reup} == {
            "activity_records",
            "activity_chain_heads",
        }
