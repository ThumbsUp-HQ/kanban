"""Migration tests for p1_06_parent_dag up/down lifecycle."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_08_parent_dag_migration_lifecycle() -> None:
    """Verify p1_06 upgrade creates triggers/indexes, downgrade reverts them, and re-up works."""
    async with MigrationHarness() as harness:
        assert harness.previous_of("p1_06_parent_dag") == "p1_08_planning_joins"

        # 1. Upgrade to p1_06_parent_dag
        await harness.upgrade("p1_06_parent_dag")

        indexes_up = await harness.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = 'issues' "
            "AND indexname = 'issues_ancestry_gist'"
        )
        assert len(indexes_up) == 1

        constraints_up = await harness.fetch(
            "SELECT conname FROM pg_constraint WHERE conname = 'issues_ancestry_depth_chk'"
        )
        assert len(constraints_up) == 1

        funcs_up = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name IN ("
            "  'issue_ltree_label', 'issues_parent_dag_biu', 'issues_parent_dag_au'"
            ")"
        )
        assert {r["routine_name"] for r in funcs_up} == {
            "issue_ltree_label",
            "issues_parent_dag_biu",
            "issues_parent_dag_au",
        }

        triggers_up = await harness.fetch(
            "SELECT trigger_name FROM information_schema.triggers "
            "WHERE event_object_schema = 'public' AND event_object_table = 'issues' "
            "AND trigger_name IN ('issues_parent_dag_biu_trg', 'issues_parent_dag_au_trg')"
        )
        assert {r["trigger_name"] for r in triggers_up} == {
            "issues_parent_dag_biu_trg",
            "issues_parent_dag_au_trg",
        }

        # 2. Downgrade to p1_05_issues
        prev_rev = harness.previous_of("p1_06_parent_dag")
        await harness.downgrade(prev_rev)

        indexes_down = await harness.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = 'issues' "
            "AND indexname = 'issues_ancestry_gist'"
        )
        assert len(indexes_down) == 0

        constraints_down = await harness.fetch(
            "SELECT conname FROM pg_constraint WHERE conname = 'issues_ancestry_depth_chk'"
        )
        assert len(constraints_down) == 0

        funcs_down = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name IN ("
            "  'issue_ltree_label', 'issues_parent_dag_biu', 'issues_parent_dag_au'"
            ")"
        )
        assert len(funcs_down) == 0

        triggers_down = await harness.fetch(
            "SELECT trigger_name FROM information_schema.triggers "
            "WHERE event_object_schema = 'public' AND event_object_table = 'issues' "
            "AND trigger_name IN ('issues_parent_dag_biu_trg', 'issues_parent_dag_au_trg')"
        )
        assert len(triggers_down) == 0

        # 3. Re-upgrade to p1_06_parent_dag
        await harness.upgrade("p1_06_parent_dag")
        indexes_reup = await harness.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = 'issues' "
            "AND indexname = 'issues_ancestry_gist'"
        )
        assert len(indexes_reup) == 1
