# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p6_02_pdf_attachments."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p6_02_pdf_attachments_migration_lifecycle() -> None:
    """Verify p6_02_pdf_attachments upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p6_02_pdf_attachments")
        assert prev_rev == "p4_24_agent_safe_sequences"

        # 1. Upgrade to p6_02_pdf_attachments
        await harness.upgrade("p6_02_pdf_attachments")

        # Verify page_count column exists
        col_res = await harness.fetch(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "  AND table_name = 'attachments' "
            "  AND column_name = 'page_count';"
        )
        assert len(col_res) == 1
        assert col_res[0]["column_name"] == "page_count"
        assert col_res[0]["data_type"] == "integer"
        assert col_res[0]["is_nullable"] == "YES"

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # Verify page_count column is removed
        col_down = await harness.fetch(
            "SELECT column_name "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "  AND table_name = 'attachments' "
            "  AND column_name = 'page_count';"
        )
        assert len(col_down) == 0

        # 3. Upgrade back to head
        await harness.upgrade("p6_02_pdf_attachments")

        # Verify column is present again
        col_reup = await harness.fetch(
            "SELECT column_name "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "  AND table_name = 'attachments' "
            "  AND column_name = 'page_count';"
        )
        assert len(col_reup) == 1
