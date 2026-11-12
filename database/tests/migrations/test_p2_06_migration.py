# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p2_06_oidc_auth_requests (KB-P2-06)."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_24_oidc_auth_requests_migration_lifecycle() -> None:
    """Verify p2_06 upgrade applies oidc_auth_requests and functions, and downgrade reverts."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p2_06_oidc_auth_requests")
        assert prev_rev == "p2_02_sessions"

        # 1. Upgrade to p2_06_oidc_auth_requests
        await harness.upgrade("p2_06_oidc_auth_requests")

        # Verify table exists with FORCE RLS
        table_info = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity, r.rolname as owner "
            "FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_roles r ON r.oid = c.relowner "
            "WHERE n.nspname = 'public' AND c.relname = 'oidc_auth_requests'"
        )
        assert len(table_info) == 1
        assert table_info[0]["relrowsecurity"] is True
        assert table_info[0]["relforcerowsecurity"] is True
        assert table_info[0]["owner"] == "kb_auth_owner"

        # Verify functions exist in kb_auth
        funcs = await harness.fetch(
            "SELECT proname, r.rolname as owner, prosecdef "
            "FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "JOIN pg_roles r ON r.oid = p.proowner "
            "WHERE n.nspname = 'kb_auth' AND p.proname LIKE 'oidc_%'"
        )
        func_names = {r["proname"] for r in funcs}
        assert func_names == {
            "oidc_request_create",
            "oidc_request_consume",
        }
        for f in funcs:
            assert f["owner"] == "kb_auth_owner"
            assert f["prosecdef"] is True

        # 2. Downgrade to p2_02_sessions
        await harness.downgrade("p2_02_sessions")

        table_gone = await harness.fetch(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'oidc_auth_requests'"
        )
        assert len(table_gone) == 0

        funcs_gone = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'kb_auth' AND p.proname LIKE 'oidc_%'"
        )
        assert len(funcs_gone) == 0

        # 3. Re-upgrade to p2_06_oidc_auth_requests
        await harness.upgrade("p2_06_oidc_auth_requests")

        table_recheck = await harness.fetch(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'oidc_auth_requests'"
        )
        assert len(table_recheck) == 1
