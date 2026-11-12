"""Migration lifecycle test for p2_18_rate_limit_buckets (S2.2, S2.4, KB-P2-18)."""

from __future__ import annotations

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_2_18_rate_limit_buckets_migration_lifecycle() -> None:
    """Verify p2_18 upgrade applies rate_limit_buckets and kb_infra, and downgrade reverts."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p2_18_rate_limit_buckets")
        assert prev_rev == "p2_03_auth_provider_cards"

        # 1. Upgrade to p2_18_rate_limit_buckets
        await harness.upgrade("p2_18_rate_limit_buckets")

        # Verify rate_limit_buckets exists with FORCE RLS
        table_info = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'rate_limit_buckets'"
        )
        assert len(table_info) == 1
        assert table_info[0]["relrowsecurity"] is True
        assert table_info[0]["relforcerowsecurity"] is True

        # Verify schema kb_infra exists
        schema_info = await harness.fetch("SELECT 1 FROM pg_namespace WHERE nspname = 'kb_infra'")
        assert len(schema_info) == 1

        # Verify functions exist in kb_infra
        funcs = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'kb_infra' "
            "  AND proname IN ('rate_limit_hit', 'rate_limit_reset')"
        )
        assert {r["proname"] for r in funcs} == {"rate_limit_hit", "rate_limit_reset"}

        # 2. Downgrade to p1_18_outbox
        await harness.downgrade(prev_rev)

        # Verify table dropped
        table_down = await harness.fetch(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'rate_limit_buckets'"
        )
        assert len(table_down) == 0

        # Verify schema dropped
        schema_down = await harness.fetch("SELECT 1 FROM pg_namespace WHERE nspname = 'kb_infra'")
        assert len(schema_down) == 0

        # 3. Re-upgrade to p2_18_rate_limit_buckets
        await harness.upgrade("p2_18_rate_limit_buckets")

        table_reup = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'rate_limit_buckets'"
        )
        assert len(table_reup) == 1
        assert table_reup[0]["relrowsecurity"] is True
        assert table_reup[0]["relforcerowsecurity"] is True
