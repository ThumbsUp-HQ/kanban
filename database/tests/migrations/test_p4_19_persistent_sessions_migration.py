# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p4_19_persistent_sessions."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p4_19_persistent_sessions_migration_lifecycle() -> None:
    """Verify p4_19_persistent_sessions upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p4_19_persistent_sessions")
        assert prev_rev == "p4_18_oauth_mcp_scoping"

        # 1. Upgrade to p4_19_persistent_sessions
        await harness.upgrade("p4_19_persistent_sessions")

        # Check column existence
        res_sess = await harness.fetchval(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'sessions' AND column_name = 'is_persistent'"
        )
        assert res_sess == "is_persistent"

        res_oidc = await harness.fetchval(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'oidc_auth_requests' AND column_name = 'remember_me'"
        )
        assert res_oidc == "remember_me"

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        res_sess_down = await harness.fetchval(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'sessions' AND column_name = 'is_persistent'"
        )
        assert res_sess_down is None

        res_oidc_down = await harness.fetchval(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'oidc_auth_requests' AND column_name = 'remember_me'"
        )
        assert res_oidc_down is None

        # 3. Upgrade back to head
        await harness.upgrade("p4_19_persistent_sessions")
