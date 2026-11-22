# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p6_05_issue_leases_and_fencing."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p6_05_issue_leases_and_fencing_migration_lifecycle() -> None:
    """Verify p6_05_issue_leases_and_fencing upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p6_05_issue_leases_and_fencing")
        assert prev_rev == "p6_04_enforce_credential_boundary_rls_gucs"

        # 1. Upgrade to p6_05_issue_leases_and_fencing
        await harness.upgrade("p6_05_issue_leases_and_fencing")

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # 3. Upgrade back to head
        await harness.upgrade("p6_05_issue_leases_and_fencing")
