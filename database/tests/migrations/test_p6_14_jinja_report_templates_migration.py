# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p6_14_jinja_report_templates."""

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p6_14_jinja_report_templates_migration_lifecycle() -> None:
    """Verify p6_14_jinja_report_templates upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p6_14_jinja_report_templates")
        assert prev_rev == "p6_09_scm_webhooks_and_outbound_bus"

        # 1. Upgrade to p6_14_jinja_report_templates
        await harness.upgrade("p6_14_jinja_report_templates")

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # 3. Upgrade back to head
        await harness.upgrade("p6_14_jinja_report_templates")
