# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Reversible lifecycle test for p2_12_setup_claim_tokens migration (KB-P2-12)."""

from __future__ import annotations

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.asyncio
async def test_212_setup_claim_tokens_migration_lifecycle() -> None:
    """Verify upgrade to p2_12_setup_claim_tokens, downgrade -1, and re-upgrade."""
    async with MigrationHarness() as harness:
        # 1. Upgrade to head
        await harness.upgrade("head")

        # Verify table exists, owned by kb_auth_owner, has row security
        tables = await harness.fetch(
            "SELECT tablename, tableowner, rowsecurity FROM pg_tables "
            "WHERE tablename = 'setup_claim_tokens'"
        )
        assert len(tables) == 1
        assert tables[0]["tablename"] == "setup_claim_tokens"
        assert tables[0]["tableowner"] == "kb_auth_owner"
        assert tables[0]["rowsecurity"] is True

        # Verify FORCE RLS
        force_rls = await harness.fetch(
            "SELECT relname, relforcerowsecurity FROM pg_class WHERE relname = 'setup_claim_tokens'"
        )
        assert len(force_rls) == 1
        assert force_rls[0]["relforcerowsecurity"] is True

        # Verify functions in kb_auth
        funcs = await harness.fetch(
            "SELECT proname, prosecdef FROM pg_proc p "
            "JOIN pg_namespace n ON p.pronamespace = n.oid "
            "WHERE n.nspname = 'kb_auth' "
            "  AND proname LIKE 'setup_%'"
        )
        func_names = {f["proname"] for f in funcs}
        assert func_names == {
            "setup_is_initialized",
            "setup_mint_token",
            "setup_consume_and_create_admin",
        }
        for f in funcs:
            assert f["prosecdef"] is True

        # 2. Downgrade -1
        await harness.downgrade("-1")

        # Verify table and functions dropped
        tbl_down = await harness.fetch(
            "SELECT 1 FROM pg_tables WHERE tablename = 'setup_claim_tokens'"
        )
        assert len(tbl_down) == 0

        funcs_down = await harness.fetch(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid "
            "WHERE n.nspname = 'kb_auth' AND proname LIKE 'setup_%'"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to head
        await harness.upgrade("head")

        # Verify table restored
        tbl_restored = await harness.fetch(
            "SELECT tablename FROM pg_tables WHERE tablename = 'setup_claim_tokens'"
        )
        assert len(tbl_restored) == 1
