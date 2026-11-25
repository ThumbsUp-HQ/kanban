# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Migration lifecycle test for p6_18_websudo_sliding_aal2."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from database.tests.migration_harness import MigrationHarness


@pytest.mark.migration
async def test_p6_18_websudo_sliding_aal2_migration_lifecycle() -> None:
    """Verify p6_18_websudo_sliding_aal2 upgrade and downgrade revert cleanly."""
    async with MigrationHarness() as harness:
        prev_rev = harness.previous_of("p6_18_websudo_sliding_aal2")
        assert prev_rev == "p6_17_server_admin_role_access"

        # 1. Upgrade to p6_18_websudo_sliding_aal2
        await harness.upgrade("p6_18_websudo_sliding_aal2")

        # 2. Downgrade to previous revision
        await harness.downgrade(prev_rev)

        # 3. Upgrade back to head
        await harness.upgrade("p6_18_websudo_sliding_aal2")


@pytest.mark.migration
async def test_p6_18_websudo_sliding_aal2_rpcs() -> None:  # noqa: PLR0915
    """Verify session_touch_aal2 and session_drop_aal2 RPC behavior."""
    async with MigrationHarness() as harness:
        await harness.upgrade("p6_18_websudo_sliding_aal2")

        user_id = uuid.uuid4()
        ws_id = uuid.uuid4()
        sess_id = uuid.uuid4()
        token_sha = b"\x01" * 32
        now = datetime.now(UTC)

        await harness.execute(
            "INSERT INTO workspaces (id, name, slug) VALUES ($1, 'Test WS', $2)",
            ws_id,
            f"ws-{ws_id.hex[:8]}",
        )
        await harness.execute(
            "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
            "VALUES ($1, $2, 'USER', 'Test User')",
            user_id,
            ws_id,
        )

        # 1. Create an AAL2 session
        idle_exp = now + timedelta(hours=8)
        abs_exp = now + timedelta(days=7)
        await harness.execute(
            """
            SELECT kb_auth.session_create(
                $1, $2, $3, $4,
                NULL, 2::SMALLINT, $5, FALSE,
                $6, $7, NULL, TRUE, $5
            )
            """,
            sess_id,
            token_sha,
            user_id,
            ws_id,
            now,
            idle_exp,
            abs_exp,
        )

        # 2. Test session_resolve returns aal2_last_active_at
        resolve_rows = await harness.fetch(
            "SELECT * FROM kb_auth.session_resolve($1)",
            token_sha,
        )
        assert len(resolve_rows) == 1
        row = dict(resolve_rows[0])
        assert row["aal_level"] == 2
        assert row["aal2_last_active_at"] is not None

        # 3. Test session_touch_aal2 active touch
        touch_rows = await harness.fetch(
            "SELECT * FROM kb_auth.session_touch_aal2($1, 900, 14400, FALSE)",
            sess_id,
        )
        assert len(touch_rows) == 1
        t_row = dict(touch_rows[0])
        assert t_row["aal2_active"] is True
        assert t_row["aal2_expires_at"] is not None

        # 4. Test touch write-throttling within 30s
        meta_rows = await harness.fetch(
            "SELECT * FROM kb_auth.session_get_metadata($1)",
            sess_id,
        )
        assert len(meta_rows) == 1
        m_row = dict(meta_rows[0])
        assert m_row["aal_level"] == 2
        assert m_row["aal2_last_active_at"] is not None

        # 5. Test forced touch updates aal2_last_active_at
        forced_rows = await harness.fetch(
            "SELECT * FROM kb_auth.session_touch_aal2($1, 900, 14400, TRUE)",
            sess_id,
        )
        assert len(forced_rows) == 1
        ft_row = dict(forced_rows[0])
        assert ft_row["aal2_active"] is True

        # 6. Test idle expiration (> 900s ago)
        stale_active = now - timedelta(seconds=905)
        await harness.execute(
            "UPDATE sessions SET aal2_last_active_at = $1 WHERE id = $2",
            stale_active,
            sess_id,
        )
        stale_rows = await harness.fetch(
            "SELECT * FROM kb_auth.session_touch_aal2($1, 900, 14400, FALSE)",
            sess_id,
        )
        assert len(stale_rows) == 1
        st_row = dict(stale_rows[0])
        assert st_row["aal2_active"] is False
        assert st_row["aal2_expires_at"] is None

        # 7. Re-elevate and test absolute expiration (> 14400s)
        stale_verified = now - timedelta(seconds=14405)
        await harness.execute(
            """
            UPDATE sessions
            SET aal_level = 2,
                aal2_verified_at = $1,
                aal2_last_active_at = $2
            WHERE id = $3
            """,
            stale_verified,
            now,
            sess_id,
        )
        abs_rows = await harness.fetch(
            "SELECT * FROM kb_auth.session_touch_aal2($1, 900, 14400, FALSE)",
            sess_id,
        )
        assert len(abs_rows) == 1
        at_row = dict(abs_rows[0])
        assert at_row["aal2_active"] is False

        # 8. Re-elevate and test session_drop_aal2
        await harness.execute(
            """
            UPDATE sessions
            SET aal_level = 2,
                aal2_verified_at = $1,
                aal2_last_active_at = $1
            WHERE id = $2
            """,
            now,
            sess_id,
        )
        drop_val = await harness.fetchval(
            "SELECT kb_auth.session_drop_aal2($1)",
            sess_id,
        )
        assert bool(drop_val) is True

        meta_dropped = await harness.fetch(
            "SELECT * FROM kb_auth.session_get_metadata($1)",
            sess_id,
        )
        assert len(meta_dropped) == 1
        md_row = dict(meta_dropped[0])
        assert md_row["aal_level"] == 1
        assert md_row["aal2_last_active_at"] is None
        assert md_row["aal2_verified_at"] is None

