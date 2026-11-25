# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p6_17_server_admin_role_access."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p6_17_server_admin_role_access_migration_lifecycle() -> None:
    """Verify p6_17_server_admin_role_access upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p6_17_server_admin_role_access")
        assert prev_rev == "p6_16_oauth_confidential_clients"

        # 1. Upgrade to p6_17_server_admin_role_access
        await harness.upgrade("p6_17_server_admin_role_access")

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # 3. Upgrade back to head
        await harness.upgrade("p6_17_server_admin_role_access")
