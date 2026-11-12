# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle and constraint tests for p3_01b_workflow_state_wip_limits."""

import asyncpg  # type: ignore[import-untyped]  # asyncpg does not distribute PEP 561 py.typed marker
import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.asyncio
async def test_migration_wip_limits_lifecycle_and_constraints() -> None:
    """Verify upgrade adds WIP limits and constraint, downgrade restores catalog identically."""
    async with MigrationHarness() as harness:
        # 1. Upgrade to revision prior to p3_01b
        await harness.upgrade("p2_18_rate_limit_buckets")

        # Snapshot workflow_states columns before upgrade
        pre_cols_rows = await harness.fetch(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'workflow_states' "
            "ORDER BY ordinal_position"
        )
        pre_columns = [(r["column_name"], r["data_type"], r["is_nullable"]) for r in pre_cols_rows]
        pre_col_names = {c[0] for c in pre_columns}
        assert "wip_soft_limit" not in pre_col_names
        assert "wip_hard_limit" not in pre_col_names

        # 2. Upgrade to p3_01b_workflow_state_wip_limits
        await harness.upgrade("p3_01b_workflow_state_wip_limits")

        post_cols_rows = await harness.fetch(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'workflow_states' "
            "ORDER BY ordinal_position"
        )
        post_col_names = {r["column_name"] for r in post_cols_rows}
        assert "wip_soft_limit" in post_col_names
        assert "wip_hard_limit" in post_col_names

        # Check constraint existence
        constraints = await harness.fetch(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'workflow_states'::regclass "
            "  AND conname = 'wip_soft_le_hard'"
        )
        assert len(constraints) == 1

        # Check project_labels policy allows capability 4 post-upgrade
        pol_rows = await harness.fetch(
            "SELECT polname, pg_get_expr(polwithcheck, polrelid) as with_check "
            "FROM pg_policy "
            "WHERE polrelid = 'project_labels'::regclass AND polname = 'project_labels_insert_rls'"
        )
        assert len(pol_rows) == 1
        assert "4" in pol_rows[0]["with_check"]

        # Verify CHECK constraint enforcement in DB
        # Seed minimal workspace and project to test constraint on workflow_states
        seed_ws = await harness.fetch(
            "INSERT INTO workspaces (id, name, slug) "
            "VALUES (uuidv7(), 'Test WS', 'test-ws') RETURNING id"
        )
        ws_id = seed_ws[0]["id"]
        proj_uuid = await harness.fetch("SELECT uuidv7() AS id")
        proj_id = proj_uuid[0]["id"]
        user_uuid = await harness.fetch("SELECT uuidv7() AS id")
        user_id = user_uuid[0]["id"]

        await harness.execute(
            "INSERT INTO objects "
            "(id, object_type, workspace_id, canonical_key, display_title, created_by_id) "
            "VALUES ($1, 'project', $2, 'WIPPROJ', 'WIP Test Project', $3)",
            proj_id,
            ws_id,
            user_id,
        )
        await harness.execute(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES ($1, $2, 'WIPPROJ', 'WIP Test Project')",
            proj_id,
            ws_id,
        )

        cols = (
            "(id, workspace_id, project_id, name, state_group, color_hex, "
            "sort_order, is_default, wip_soft_limit, wip_hard_limit) "
        )

        # Valid WIP limits
        await harness.execute(
            f"INSERT INTO workflow_states {cols}"
            "VALUES (uuidv7(), $1, $2, 'Valid WIP', 'started', '#3B82F6', 10, false, 3, 5)",
            ws_id,
            proj_id,
        )

        # Soft limit greater than hard limit violates wip_soft_le_hard constraint
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await harness.execute(
                f"INSERT INTO workflow_states {cols}"
                "VALUES (uuidv7(), $1, $2, 'Invalid LE', 'started', '#3B82F6', 20, false, 6, 5)",
                ws_id,
                proj_id,
            )

        # Soft limit greater than 999 boundary violates range check
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await harness.execute(
                f"INSERT INTO workflow_states {cols}"
                "VALUES (uuidv7(), $1, $2, 'Invalid Range', 'started', "
                "'#3B82F6', 30, false, 1000, 1000)",
                ws_id,
                proj_id,
            )

        # 3. Downgrade to p2_18_rate_limit_buckets
        await harness.downgrade("p2_18_rate_limit_buckets")

        # Snapshot workflow_states columns after downgrade
        reverted_cols_rows = await harness.fetch(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'workflow_states' "
            "ORDER BY ordinal_position"
        )
        reverted_columns = [
            (r["column_name"], r["data_type"], r["is_nullable"]) for r in reverted_cols_rows
        ]

        # Verify catalog is 100% identical to pre-upgrade
        assert reverted_columns == pre_columns

        # Verify constraint removed
        no_constraints = await harness.fetch(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'workflow_states'::regclass "
            "  AND conname = 'wip_soft_le_hard'"
        )
        assert len(no_constraints) == 0

        # Check project_labels policy restored to capability 64
        reverted_pol_rows = await harness.fetch(
            "SELECT polname, pg_get_expr(polwithcheck, polrelid) as with_check "
            "FROM pg_policy "
            "WHERE polrelid = 'project_labels'::regclass AND polname = 'project_labels_insert_rls'"
        )
        assert len(reverted_pol_rows) == 1
        assert "64" in reverted_pol_rows[0]["with_check"]

        # 4. Re-upgrade to head
        await harness.upgrade("head")
