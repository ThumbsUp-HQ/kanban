# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p6_20_oauth_clients_status_check."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p6_20_oauth_clients_status_check_migration_lifecycle() -> None:
    """Verify p6_20_oauth_clients_status_check upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p6_20_oauth_clients_status_check")
        assert prev_rev == "p6_19_server_admin_cross_workspace_role_access"

        # 1. Upgrade to p6_20_oauth_clients_status_check
        await harness.upgrade("p6_20_oauth_clients_status_check")

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # 3. Upgrade back to head
        await harness.upgrade("p6_20_oauth_clients_status_check")
