# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p6_22_mcp_api_keys_capability_mask_boundary."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p6_22_mcp_api_keys_capability_mask_boundary_migration_lifecycle() -> None:
    """Verify p6_22_mcp_api_keys_capability_mask_boundary upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p6_22_mcp_api_keys_capability_mask_boundary")
        assert prev_rev == "p6_21_agent_onboarding_preferences"

        # 1. Upgrade to p6_22_mcp_api_keys_capability_mask_boundary
        await harness.upgrade("p6_22_mcp_api_keys_capability_mask_boundary")

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # 3. Upgrade back to head
        await harness.upgrade("p6_22_mcp_api_keys_capability_mask_boundary")
