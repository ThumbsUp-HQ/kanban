"""Migration lifecycle test for p2_03_auth_provider_cards (KB-P2-03)."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_20_auth_provider_cards_migration_lifecycle() -> None:
    """Verify p2_03 upgrade applies auth_provider_cards and functions, and downgrade reverts."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p2_03_auth_provider_cards")
        assert prev_rev == "p5_06_object_embeddings"

        # 1. Upgrade to p2_03_auth_provider_cards
        await harness.upgrade("p2_03_auth_provider_cards")

        # Verify role and schema exist
        roles = await harness.fetch("SELECT rolname FROM pg_roles WHERE rolname = 'kb_auth_owner'")
        assert len(roles) == 1

        schemas = await harness.fetch("SELECT nspname FROM pg_namespace WHERE nspname = 'kb_auth'")
        assert len(schemas) == 1

        # Verify table exists with FORCE RLS
        table_info = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity, r.rolname as owner "
            "FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "JOIN pg_roles r ON r.oid = c.relowner "
            "WHERE n.nspname = 'public' AND c.relname = 'auth_provider_cards'"
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
            "WHERE n.nspname = 'kb_auth'"
        )
        func_names = {r["proname"] for r in funcs}
        assert func_names == {
            "card_list_enabled_public",
            "card_get_for_login",
            "card_admin_upsert",
            "card_admin_get",
            "card_admin_list",
            "card_rewrap",
        }
        for r in funcs:
            assert r["owner"] == "kb_auth_owner"
            assert r["prosecdef"] is True

        # Verify trigger exists
        triggers = await harness.fetch(
            "SELECT tgname FROM pg_trigger WHERE tgname = 'auth_provider_cards_set_updated_at'"
        )
        assert len(triggers) == 1

        # Verify RLS policy exists
        policies = await harness.fetch(
            "SELECT polname FROM pg_policy pol "
            "JOIN pg_class c ON c.oid = pol.polrelid "
            "WHERE c.relname = 'auth_provider_cards'"
        )
        assert {r["polname"] for r in policies} == {"kb_auth_owner_all"}

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # Verify table is dropped
        table_down = await harness.fetch(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'auth_provider_cards'"
        )
        assert len(table_down) == 0

        # Verify schema is dropped
        schema_down = await harness.fetch("SELECT 1 FROM pg_namespace WHERE nspname = 'kb_auth'")
        assert len(schema_down) == 0

        # 3. Re-upgrade to p2_03_auth_provider_cards
        await harness.upgrade("p2_03_auth_provider_cards")

        # Verify table exists again
        table_reup = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'auth_provider_cards'"
        )
        assert len(table_reup) == 1
        assert table_reup[0]["relrowsecurity"] is True
        assert table_reup[0]["relforcerowsecurity"] is True
