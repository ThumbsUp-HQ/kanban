# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p6_04_enforce_credential_boundary_rls_gucs."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p6_04_enforce_credential_boundary_rls_gucs_migration_lifecycle() -> None:
    """Verify p6_04_enforce_credential_boundary_rls_gucs upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p6_04_enforce_credential_boundary_rls_gucs")
        assert prev_rev == "p6_03_multi_source_imports_and_aliases"

        # 1. Upgrade to p6_04_enforce_credential_boundary_rls_gucs
        await harness.upgrade("p6_04_enforce_credential_boundary_rls_gucs")

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # 3. Upgrade back to head
        await harness.upgrade("p6_04_enforce_credential_boundary_rls_gucs")
