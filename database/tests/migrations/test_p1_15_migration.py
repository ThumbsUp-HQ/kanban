"""Migration lifecycle test for p1_15_link_auditor."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_15_link_auditor_migration_lifecycle() -> None:
    """Verify p1_15 upgrade applies auditor, downgrade reverts, and re-upgrade succeeds."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p1_15_link_auditor")
        assert prev_rev == "p1_14_force_rls"

        # 1. Upgrade to p1_15_link_auditor
        await harness.upgrade("p1_15_link_auditor")

        # Verify enum exists
        enums = await harness.fetch(
            "SELECT typname FROM pg_type WHERE typname = 'invalid_link_reason'"
        )
        assert len(enums) == 1

        # Verify table exists with FORCE RLS
        table_info = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'invalid_object_link_audits'"
        )
        assert len(table_info) == 1
        assert table_info[0]["relrowsecurity"] is True
        assert table_info[0]["relforcerowsecurity"] is True

        # Verify functions exist
        funcs = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' "
            "  AND proname IN ("
            "    'audit_single_object_link', 'audit_object_links', 'audit_object_links_for_object'"
            "  )"
        )
        assert {r["proname"] for r in funcs} == {
            "audit_single_object_link",
            "audit_object_links",
            "audit_object_links_for_object",
        }

        # Verify triggers exist
        triggers = await harness.fetch(
            "SELECT tgname FROM pg_trigger WHERE tgname IN ("
            "  'objects_link_audit_trg', 'z_resource_acl_link_audit_trg', "
            "  'z_role_bindings_link_audit_trg', 'invalid_link_audits_guard_bud_trg'"
            ")"
        )
        assert {r["tgname"] for r in triggers} == {
            "objects_link_audit_trg",
            "z_resource_acl_link_audit_trg",
            "z_role_bindings_link_audit_trg",
            "invalid_link_audits_guard_bud_trg",
        }

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # Verify table is dropped
        table_down = await harness.fetch(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'invalid_object_link_audits'"
        )
        assert len(table_down) == 0

        # Verify enum is dropped
        enum_down = await harness.fetch(
            "SELECT 1 FROM pg_type WHERE typname = 'invalid_link_reason'"
        )
        assert len(enum_down) == 0

        # Verify functions are dropped
        funcs_down = await harness.fetch(
            "SELECT proname FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' "
            "  AND proname IN ("
            "    'audit_single_object_link', 'audit_object_links', 'audit_object_links_for_object'"
            "  )"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to p1_15_link_auditor
        await harness.upgrade("p1_15_link_auditor")

        # Verify table exists again
        table_reup = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'invalid_object_link_audits'"
        )
        assert len(table_reup) == 1
        assert table_reup[0]["relrowsecurity"] is True
        assert table_reup[0]["relforcerowsecurity"] is True
