# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p3_06_notifications (S7.2 8l, KB-P3-06)."""

from __future__ import annotations

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p3_06_notifications_migration_lifecycle() -> None:
    """Verify p3_06 upgrade applies notifications and subscriptions alterations with FORCE RLS."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p3_06_notifications")
        assert prev_rev == "p3_05_comment_threads_reactions"

        # 1. Upgrade to p3_06_notifications
        await harness.upgrade("p3_06_notifications")

        # Verify notifications exists with FORCE RLS
        table_info = await harness.fetch(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'notifications'"
        )
        assert len(table_info) == 1
        assert table_info[0]["relrowsecurity"] is True
        assert table_info[0]["relforcerowsecurity"] is True

        # Verify issue_subscriptions has new columns
        cols = await harness.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'issue_subscriptions' "
            "  AND column_name IN ('muted_event_types', 'unsubscribed_at')"
        )
        col_names = {c["column_name"] for c in cols}
        assert col_names == {"muted_event_types", "unsubscribed_at"}

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # Verify notifications table dropped
        table_down = await harness.fetch(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'notifications'"
        )
        assert len(table_down) == 0

        # Verify columns removed from issue_subscriptions
        cols_down = await harness.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'issue_subscriptions' "
            "  AND column_name IN ('muted_event_types', 'unsubscribed_at')"
        )
        assert len(cols_down) == 0

        # 3. Re-upgrade to p3_06_notifications
        await harness.upgrade("p3_06_notifications")
