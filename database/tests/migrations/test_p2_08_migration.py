# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p2_08_user_identities (KB-P2-08)."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p2_08_user_identities_migration_lifecycle() -> None:
    """Verify p2_08 upgrade applies user_identities with FORCE RLS, and downgrade reverts."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p2_08_user_identities")
        assert prev_rev == "p4_02b_oauth_clients_codes"

        # 1. Upgrade to p2_08_user_identities
        await harness.upgrade("p2_08_user_identities")

        # Verify tables exist with FORCE RLS
        for table_name in ("user_identities", "identity_link_intents"):
            table_info = await harness.fetch(
                "SELECT c.relrowsecurity, c.relforcerowsecurity "
                "FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = $1",
                table_name,
            )
            assert len(table_info) == 1, f"Table {table_name} missing"
            assert table_info[0]["relrowsecurity"] is True
            assert table_info[0]["relforcerowsecurity"] is True

        # Verify kb_auth functions exist
        funcs = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'kb_auth' AND proname LIKE 'identity_%'"
        )
        func_names = {r["proname"] for r in funcs}
        assert "identity_lookup" in func_names
        assert "identity_record_login" in func_names
        assert "identity_provision_new_user" in func_names
        assert "identity_list_for_principal" in func_names
        assert "identity_link_intent_create" in func_names
        assert "identity_link_consume_and_bind" in func_names
        assert "identity_unlink" in func_names

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        for table_name in ("user_identities", "identity_link_intents"):
            table_gone = await harness.fetch(
                "SELECT c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = $1",
                table_name,
            )
            assert len(table_gone) == 0, f"Table {table_name} not dropped"

        funcs_gone = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'kb_auth' AND proname LIKE 'identity_%'"
        )
        assert len(funcs_gone) == 0

        # 3. Re-upgrade to p2_08_user_identities
        await harness.upgrade("p2_08_user_identities")

        for table_name in ("user_identities", "identity_link_intents"):
            table_recheck = await harness.fetch(
                "SELECT c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = $1",
                table_name,
            )
            assert len(table_recheck) == 1
