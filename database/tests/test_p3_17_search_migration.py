# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p3_17_search_indexes (KB-P3-17)."""

from __future__ import annotations

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p3_17_search_indexes_migration_lifecycle() -> None:
    """Verify p3_17 upgrade creates tsvector columns and GIN indexes, and reverts cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p3_17_search_indexes")
        assert prev_rev == "p3_10b_modules"

        # 1. Upgrade to p3_17_search_indexes
        await harness.upgrade("p3_17_search_indexes")

        # Verify generated search_tsv columns on docs, pages, and stickies
        for table in ("docs", "pages", "stickies"):
            cols = await harness.fetch(
                "SELECT column_name, data_type, is_generated "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = $1 AND column_name = 'search_tsv'",
                table,
            )
            assert len(cols) == 1, f"Missing search_tsv column on {table}"
            assert cols[0]["data_type"] == "tsvector"
            assert cols[0]["is_generated"] == "ALWAYS"

        # Verify all 8 GIN indexes exist
        expected_indexes = {
            "issues_search_tsv_gin",
            "issues_summary_trgm_gin",
            "docs_search_tsv_gin",
            "docs_title_trgm_gin",
            "pages_search_tsv_gin",
            "pages_title_trgm_gin",
            "stickies_search_tsv_gin",
            "stickies_body_trgm_gin",
        }
        indexes = await harness.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname = ANY($1::text[])",
            list(expected_indexes),
        )
        found_indexes = {r["indexname"] for r in indexes}
        assert found_indexes == expected_indexes

        # Verify websearch_to_tsquery and word_similarity execute cleanly
        query_check = await harness.fetch(
            "SELECT "
            "  websearch_to_tsquery('english', 'OIDC & \"login flow\"') AS tsq, "
            "  word_similarity('Authenitcation', 'Harden OIDC authentication') AS sim"
        )
        assert len(query_check) == 1
        assert float(query_check[0]["sim"]) >= 0.25

        # 2. Downgrade to previous revision (p3_10b_modules)
        await harness.downgrade(prev_rev)

        # Verify columns dropped
        for table in ("docs", "pages", "stickies"):
            cols = await harness.fetch(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = $1 AND column_name = 'search_tsv'",
                table,
            )
            assert len(cols) == 0, f"search_tsv column still exists on {table}"

        # Verify indexes dropped
        indexes_down = await harness.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname = ANY($1::text[])",
            list(expected_indexes),
        )
        assert len(indexes_down) == 0

        # 3. Re-upgrade to p3_17_search_indexes
        await harness.upgrade("p3_17_search_indexes")

        indexes_reup = await harness.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname = ANY($1::text[])",
            list(expected_indexes),
        )
        assert {r["indexname"] for r in indexes_reup} == expected_indexes
