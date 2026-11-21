# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p6_03_multi_source_imports_and_aliases."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p6_03_multi_source_imports_and_aliases_migration_lifecycle() -> None:
    """Verify p6_03_multi_source_imports_and_aliases upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p6_03_multi_source_imports_and_aliases")
        assert prev_rev == "p6_02_pdf_attachments"

        # 1. Upgrade to p6_03_multi_source_imports_and_aliases
        await harness.upgrade("p6_03_multi_source_imports_and_aliases")

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # 3. Upgrade back to head
        await harness.upgrade("p6_03_multi_source_imports_and_aliases")
