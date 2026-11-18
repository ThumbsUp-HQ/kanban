# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Reversible lifecycle test for p2_05b_webauthn_credentials migration (KB-P2-05b)."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.asyncio
async def test_25b_webauthn_credentials_migration_lifecycle() -> None:
    """Verify upgrade to p2_05b_webauthn_credentials, downgrade -1, and re-upgrade."""
    async with MigrationHarness() as harness:
        # 1. Upgrade to head (p2_05b_webauthn_credentials)
        await harness.upgrade("head")

        # Verify webauthn tables exist and are owned by kb_auth_owner with RLS
        tables = await harness.fetch(
            "SELECT tablename, tableowner, rowsecurity FROM pg_tables "
            "WHERE tablename IN ('webauthn_credentials', 'webauthn_challenges') "
            "ORDER BY tablename"
        )
        assert len(tables) == 2
        assert tables[0]["tablename"] == "webauthn_challenges"
        assert tables[0]["tableowner"] == "kb_auth_owner"
        assert tables[0]["rowsecurity"] is True
        assert tables[1]["tablename"] == "webauthn_credentials"
        assert tables[1]["tableowner"] == "kb_auth_owner"
        assert tables[1]["rowsecurity"] is True

        # Verify FORCE RLS on both tables
        force_rls = await harness.fetch(
            "SELECT relname, relforcerowsecurity FROM pg_class "
            "WHERE relname IN ('webauthn_credentials', 'webauthn_challenges') "
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
            "  AND proname LIKE 'webauthn_%'"
        )
        func_names = {f["proname"] for f in funcs}
        assert func_names == {
            "webauthn_challenge_create",
            "webauthn_challenge_consume",
            "webauthn_credential_create",
            "webauthn_credential_get",
            "webauthn_credentials_for_principal",
            "webauthn_update_sign_count",
            "webauthn_mark_clone",
            "webauthn_credential_delete",
            "webauthn_count",
            "webauthn_credential_update_nickname",
        }
        for f in funcs:
            assert f["prosecdef"] is True

        # 2. Downgrade -1 (to p2_05a_mfa_totp_recovery)
        await harness.downgrade("p2_05a_mfa_totp_recovery")

        # Verify tables dropped
        tbl_down = await harness.fetch(
            "SELECT 1 FROM pg_tables "
            "WHERE tablename IN ('webauthn_credentials', 'webauthn_challenges')"
        )
        assert len(tbl_down) == 0

        # Verify functions dropped
        funcs_down = await harness.fetch(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid "
            "WHERE n.nspname = 'kb_auth' "
            "  AND proname LIKE 'webauthn_%'"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to head
        await harness.upgrade("head")

        # Verify tables restored
        tbl_restored = await harness.fetch(
            "SELECT tablename FROM pg_tables "
            "WHERE tablename IN ('webauthn_credentials', 'webauthn_challenges')"
        )
        assert len(tbl_restored) == 2
