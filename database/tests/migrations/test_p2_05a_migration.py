# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Reversible lifecycle test for p2_05a_mfa_totp_recovery migration (KB-P2-05a)."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.asyncio
async def test_25a_mfa_totp_recovery_migration_lifecycle() -> None:
    """Verify upgrade to p2_05a_mfa_totp_recovery, downgrade -1, and re-upgrade."""
    async with MigrationHarness() as harness:
        # 1. Upgrade to head (p2_05a_mfa_totp_recovery)
        await harness.upgrade("head")

        # Verify totp_factors and recovery_codes exist and are owned by kb_auth_owner with RLS
        tables = await harness.fetch(
            "SELECT tablename, tableowner, rowsecurity FROM pg_tables "
            "WHERE tablename IN ('totp_factors', 'recovery_codes') "
            "ORDER BY tablename"
        )
        assert len(tables) == 2
        assert tables[0]["tablename"] == "recovery_codes"
        assert tables[0]["tableowner"] == "kb_auth_owner"
        assert tables[0]["rowsecurity"] is True
        assert tables[1]["tablename"] == "totp_factors"
        assert tables[1]["tableowner"] == "kb_auth_owner"
        assert tables[1]["rowsecurity"] is True

        # Verify FORCE RLS on both tables
        force_rls = await harness.fetch(
            "SELECT relname, relforcerowsecurity FROM pg_class "
            "WHERE relname IN ('totp_factors', 'recovery_codes') "
            "ORDER BY relname"
        )
        assert len(force_rls) == 2
        assert force_rls[0]["relforcerowsecurity"] is True
        assert force_rls[1]["relforcerowsecurity"] is True

        # Verify functions exist in kb_auth
        funcs = await harness.fetch(
            "SELECT proname, prosecdef FROM pg_proc p "
            "JOIN pg_namespace n ON p.pronamespace = n.oid "
            "WHERE n.nspname = 'kb_auth' "
            "  AND (proname LIKE 'totp_%' OR proname LIKE 'recovery_%' OR proname = 'mfa_status')"
        )
        func_names = {f["proname"] for f in funcs}
        assert func_names == {
            "totp_enroll",
            "totp_get_pending",
            "totp_confirm",
            "totp_get_active",
            "totp_update_step",
            "totp_delete",
            "recovery_codes_replace",
            "recovery_code_consume",
            "mfa_status",
        }
        for f in funcs:
            assert f["prosecdef"] is True

        # 2. Downgrade -1 (to p3_05_comment_threads_reactions)
        await harness.downgrade("p3_05_comment_threads_reactions")

        # Verify tables dropped
        tbl_down = await harness.fetch(
            "SELECT 1 FROM pg_tables WHERE tablename IN ('totp_factors', 'recovery_codes')"
        )
        assert len(tbl_down) == 0

        # Verify functions dropped
        funcs_down = await harness.fetch(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid "
            "WHERE n.nspname = 'kb_auth' "
            "  AND (proname LIKE 'totp_%' OR proname LIKE 'recovery_%' OR proname = 'mfa_status')"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to head
        await harness.upgrade("head")

        # Verify tables restored
        tbl_restored = await harness.fetch(
            "SELECT tablename FROM pg_tables WHERE tablename IN ('totp_factors', 'recovery_codes')"
        )
        assert len(tbl_restored) == 2
