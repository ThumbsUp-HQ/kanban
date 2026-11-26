# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p6_24_default_workflow_hooks."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p6_24_default_workflow_hooks_migration_lifecycle() -> None:
    """Verify p6_24_default_workflow_hooks upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p6_24_default_workflow_hooks")
        assert prev_rev == "p6_23_gate_timeouts_and_project_defaults"

        # 1. Upgrade to p6_24_default_workflow_hooks
        await harness.upgrade("p6_24_default_workflow_hooks")

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # 3. Upgrade back to head
        await harness.upgrade("p6_24_default_workflow_hooks")
