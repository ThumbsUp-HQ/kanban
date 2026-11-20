# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p4_24_agent_safe_sequences."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p4_24_agent_safe_sequences_migration_lifecycle() -> None:
    """Verify p4_24_agent_safe_sequences upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p4_24_agent_safe_sequences")
        assert prev_rev == "p4_23_oidc_link_intent_fk"

        # 1. Upgrade to p4_24_agent_safe_sequences
        await harness.upgrade("p4_24_agent_safe_sequences")

        cols_up = await harness.fetch(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND ("
            "  (table_name = 'projects' AND column_name = 'skip_loaded_sequence_numbers') OR "
            "  (table_name = 'workspace_settings' AND "
            "   column_name = 'default_skip_loaded_sequence_numbers')"
            ")"
        )
        assert len(cols_up) == 2

        funcs_up = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name IN ("
            "  'compute_agent_safe_sequence_batch', "
            "  'allocate_issue_sequences', "
            "  'allocate_issue_sequence'"
            ")"
        )
        assert {r["routine_name"] for r in funcs_up} == {
            "compute_agent_safe_sequence_batch",
            "allocate_issue_sequences",
            "allocate_issue_sequence",
        }

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        cols_down = await harness.fetch(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND ("
            "  (table_name = 'projects' AND column_name = 'skip_loaded_sequence_numbers') OR "
            "  (table_name = 'workspace_settings' AND "
            "   column_name = 'default_skip_loaded_sequence_numbers')"
            ")"
        )
        assert len(cols_down) == 0

        funcs_down = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name IN ("
            "  'compute_agent_safe_sequence_batch', 'allocate_issue_sequences'"
            ")"
        )
        assert len(funcs_down) == 0

        # allocate_issue_sequence should still exist (restored)
        funcs_orig = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name = 'allocate_issue_sequence'"
        )
        assert len(funcs_orig) == 1

        # 3. Upgrade back to head
        await harness.upgrade("p4_24_agent_safe_sequences")

        cols_reup = await harness.fetch(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND ("
            "  (table_name = 'projects' AND column_name = 'skip_loaded_sequence_numbers') OR "
            "  (table_name = 'workspace_settings' AND "
            "   column_name = 'default_skip_loaded_sequence_numbers')"
            ")"
        )
        assert len(cols_reup) == 2
