"""Migration tests for p1_11_object_links up/down lifecycle."""

from __future__ import annotations

import pytest

from database.tests.migration_harness import MigrationHarness

EXPECTED_LINK_KIND_LABELS: list[str] = [
    "BLOCKS",
    "BLOCKED_BY",
    "RELATES_TO",
    "DUPLICATES",
    "PARENT_OF",
    "ASSIGNED_TO",
    "IN_CYCLE",
    "IN_MODULE",
    "PROMOTED_TO_DOC",
    "VERIFIED_BY_DOC",
    "DERIVED_FROM_STICKY",
    "EMBEDS_OBJECT",
    "GOVERNED_BY_VIEW",
]


@pytest.mark.migration
async def test_07_object_links_migration_lifecycle() -> None:
    """Verify p1_11 upgrade creates tables/enums, downgrade removes, and re-up works."""
    async with MigrationHarness() as harness:
        assert harness.previous_of("p1_11_object_links") == "p1_04_projects"

        # 1. Upgrade to p1_11_object_links
        await harness.upgrade("p1_11_object_links")

        # Verify link_kind enum has exactly the 13 labels in spec order
        enum_rows = await harness.fetch(
            "SELECT e.enumlabel "
            "FROM pg_enum e "
            "JOIN pg_type t ON e.enumtypid = t.oid "
            "WHERE t.typname = 'link_kind' "
            "ORDER BY e.enumsortorder"
        )
        labels = [r["enumlabel"] for r in enum_rows]
        assert labels == EXPECTED_LINK_KIND_LABELS

        # Verify tables exist
        tables_up = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN ('object_links', 'link_type_matrix')"
        )
        assert {r["table_name"] for r in tables_up} == {"object_links", "link_type_matrix"}

        funcs_up = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name IN "
            "('object_links_validate_bi', 'object_links_guard_bu')"
        )
        assert {r["routine_name"] for r in funcs_up} == {
            "object_links_validate_bi",
            "object_links_guard_bu",
        }

        # 2. Downgrade to p1_02_objects_spine
        prev_rev = harness.previous_of("p1_11_object_links")
        await harness.downgrade(prev_rev)

        tables_down = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN ('object_links', 'link_type_matrix')"
        )
        assert len(tables_down) == 0

        types_down = await harness.fetch("SELECT typname FROM pg_type WHERE typname = 'link_kind'")
        assert len(types_down) == 0

        funcs_down = await harness.fetch(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_name IN "
            "('object_links_validate_bi', 'object_links_guard_bu')"
        )
        assert len(funcs_down) == 0

        # 3. Re-upgrade to p1_11_object_links succeeds
        await harness.upgrade("p1_11_object_links")
        tables_reup = await harness.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN ('object_links', 'link_type_matrix')"
        )
        assert {r["table_name"] for r in tables_reup} == {"object_links", "link_type_matrix"}
