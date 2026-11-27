# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p6_25_drop_mcp_read_taint."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p6_25_drop_mcp_read_taint_migration_lifecycle() -> None:
    """Verify p6_25_drop_mcp_read_taint upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p6_25_drop_mcp_read_taint")
        assert prev_rev == "p6_24_default_workflow_hooks"

        # 1. Upgrade to p6_25_drop_mcp_read_taint
        await harness.upgrade("p6_25_drop_mcp_read_taint")

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # 3. Upgrade back to head
        await harness.upgrade("p6_25_drop_mcp_read_taint")
