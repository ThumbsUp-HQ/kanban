# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p4_22_outbox_replay_reader."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p4_22_outbox_replay_reader_migration_lifecycle() -> None:
    """Verify p4_22_outbox_replay_reader upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p4_22_outbox_replay_reader")
        assert prev_rev == "p4_21_workspace_project_rbac_fix"

        # 1. Upgrade to p4_22_outbox_replay_reader
        await harness.upgrade("p4_22_outbox_replay_reader")

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # 3. Upgrade back to head
        await harness.upgrade("p4_22_outbox_replay_reader")
