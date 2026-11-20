# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p4_23_oidc_link_intent_fk."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p4_23_oidc_link_intent_fk_migration_lifecycle() -> None:
    """Verify p4_23_oidc_link_intent_fk upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p4_23_oidc_link_intent_fk")
        assert prev_rev == "p4_22_outbox_replay_reader"

        fk_query = (
            "SELECT ccu.table_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON tc.constraint_name = ccu.constraint_name "
            "WHERE tc.table_name = 'oidc_auth_requests' "
            "  AND tc.constraint_name = 'oidc_auth_requests_link_intent_id_fkey' "
            "  AND tc.constraint_type = 'FOREIGN KEY';"
        )

        # 1. Upgrade to p4_23_oidc_link_intent_fk
        await harness.upgrade("p4_23_oidc_link_intent_fk")
        target = await harness.fetchval(fk_query)
        assert target == "identity_link_intents"

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)
        target = await harness.fetchval(fk_query)
        assert target == "principals"

        # 3. Upgrade back to head
        await harness.upgrade("p4_23_oidc_link_intent_fk")
        target = await harness.fetchval(fk_query)
        assert target == "identity_link_intents"
