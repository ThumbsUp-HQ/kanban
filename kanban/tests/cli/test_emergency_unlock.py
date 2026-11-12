# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for host CLI emergency unlock and privilege wall (KB-P2-09, S4.3)."""

from __future__ import annotations

import argparse
import io
import os
import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from kanban.cli.auth import _get_admin_dsn, handle_emergency_unlock
from kanban.cli.ctl import main

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_case_7_layer_3_privilege_wall_kanban_app(db_session: AsyncSession) -> None:
    """Test Case 7: Calling kb_auth.emergency_enable_local_admin as kanban_app raises 42501."""
    ws_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Priv WS')"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:8]}"},
    )

    # Switch session authorization to kanban_app
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "SELECT * FROM kb_auth.emergency_enable_local_admin("
                    ":ws_id, 1000, 'pts/0', 'test reason')"
                ),
                {"ws_id": ws_id},
            )

    err = str(exc_info.value)
    sqlstate = getattr(exc_info.value.orig, "sqlstate", "")
    assert (
        sqlstate == "42501"
        or "42501" in err
        or "permission denied" in err.lower()
        or "insufficient_privilege" in err.lower()
    )


def test_case_9_cli_negative_validations() -> None:
    """Test Case 9: CLI negative validations: missing flag, reason length > 256, empty reason."""
    # 1. Missing --enable-local-admin flag exits 2
    stderr_buf = io.StringIO()
    stdout_buf = io.StringIO()
    with patch("sys.stderr", stderr_buf), patch("sys.stdout", stdout_buf):
        ret = main(["auth", "emergency-unlock", "--reason", "Test reason"])
    assert ret == 2
    assert "--enable-local-admin flag is required" in stderr_buf.getvalue()

    # 2. Reason exceeds 256 characters exits 2
    long_reason = "X" * 300
    stderr_buf = io.StringIO()
    stdout_buf = io.StringIO()
    with patch("sys.stderr", stderr_buf), patch("sys.stdout", stdout_buf):
        ret = main(["auth", "emergency-unlock", "--enable-local-admin", "--reason", long_reason])
    assert ret == 2
    assert "exceeds 256 characters" in stderr_buf.getvalue()

    # 3. Reason with only control characters / whitespace exits 2
    stderr_buf = io.StringIO()
    stdout_buf = io.StringIO()
    with patch("sys.stderr", stderr_buf), patch("sys.stdout", stdout_buf):
        ret = main(["auth", "emergency-unlock", "--enable-local-admin", "--reason", "\x01\x02  \t"])
    assert ret == 2
    assert "cannot be empty" in stderr_buf.getvalue()


@pytest.mark.asyncio
async def test_case_8_cli_positive_emergency_unlock_and_hash_chain(
    db_session: AsyncSession,
) -> None:
    """Test Case 8: Positive CLI emergency unlock under migrator authority.

    Re-enables LOCAL_ADMIN, appends EMERGENCY_BREAK_GLASS_INVOKED to activity_records,
    verifies activity chain is valid, and verifies UPDATE/DELETE on ledger row raises.
    """
    ws_id = uuid.uuid4()
    slug = f"ws-{ws_id.hex[:8]}"
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Break Glass WS')"),
        {"id": ws_id, "slug": slug},
    )

    admin_id = uuid.uuid4()
    await db_session.execute(
        text(
            "SELECT register_object("
            "  'user'::object_kind, :ws_id, NULL, :ckey, 'Admin User', :u_id, :u_id"
            ")"
        ),
        {"ws_id": ws_id, "ckey": f"usr-{admin_id.hex}", "u_id": admin_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Admin User', 'ACTIVE')"
        ),
        {"id": admin_id, "ws_id": ws_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'admin@example.com')"
        ),
        {"id": admin_id, "ws_id": ws_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type) "
            "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server')"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": admin_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO local_admin_credentials (principal_id, username, password_hash) "
            "VALUES (:p_id, :uname, '$argon2id$fake')"
        ),
        {"p_id": admin_id, "uname": f"admin-{ws_id.hex[:6]}"},
    )

    # LOCAL_ADMIN card is disabled
    card_loc = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO auth_provider_cards "
            "(id, workspace_id, provider_kind, slug, display_name, sort_rank, is_enabled) "
            "VALUES (:id, :ws_id, 'LOCAL_ADMIN', :slug, 'Local Admin', '0|', FALSE)"
        ),
        {"id": card_loc, "ws_id": ws_id, "slug": f"loc-{ws_id.hex[:6]}"},
    )

    # Execute kb_auth.emergency_enable_local_admin directly under kanban_migrator / db_session
    row = (
        (
            await db_session.execute(
                text(
                    "SELECT workspace_id, card_id, activity_id "
                    "FROM kb_auth.emergency_enable_local_admin("
                    ":ws_id, :uid, 'pts/1', 'Okta outage')"
                ),
                {"ws_id": ws_id, "uid": os.getuid()},
            )
        )
        .mappings()
        .first()
    )

    assert row is not None
    assert row["workspace_id"] == ws_id
    assert row["card_id"] == card_loc
    activity_id = row["activity_id"]
    assert activity_id is not None

    # 1. LOCAL_ADMIN is now enabled
    is_enabled = await db_session.scalar(
        text("SELECT is_enabled FROM auth_provider_cards WHERE id = :id"),
        {"id": card_loc},
    )
    assert is_enabled is True

    # 2. Activity record is written with event_type = EMERGENCY_BREAK_GLASS_INVOKED
    act_row = (
        (
            await db_session.execute(
                text(
                    "SELECT id, workspace_id, event_type, payload "
                    "FROM activity_records WHERE id = :id"
                ),
                {"id": activity_id},
            )
        )
        .mappings()
        .first()
    )
    assert act_row is not None
    assert act_row["event_type"] == "EMERGENCY_BREAK_GLASS_INVOKED"
    assert act_row["payload"]["reason"] == "Okta outage"
    assert "os_uid" in act_row["payload"]

    # 3. verify_activity_chain() is valid
    chain_status = (
        (
            await db_session.execute(
                text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws_id)"),
                {"ws_id": ws_id},
            )
        )
        .mappings()
        .first()
    )
    assert chain_status is not None
    assert chain_status["is_valid"] is True
    assert chain_status["checked_rows"] >= 1

    # 4. Attempting UPDATE on activity_records raises immutable trigger exception
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE activity_records SET event_type = 'MODIFIED' WHERE id = :id"),
                {"id": activity_id},
            )
    assert (
        "ACTIVITY_LEDGER_IMMUTABLE" in str(exc_info.value)
        or "immutable" in str(exc_info.value).lower()
    )

    # 5. Attempting DELETE on activity_records raises immutable trigger exception
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM activity_records WHERE id = :id"),
                {"id": activity_id},
            )
    assert (
        "ACTIVITY_LEDGER_IMMUTABLE" in str(exc_info.value)
        or "immutable" in str(exc_info.value).lower()
    )


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_cli_end_to_end_subcommand_dispatch(
    committed_db_session: AsyncSession,
) -> None:
    """End-to-end test invoking kanban-ctl auth emergency-unlock via main()."""
    ws_id = uuid.uuid4()
    slug = f"ws-{ws_id.hex[:8]}"
    await committed_db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'E2E WS')"),
        {"id": ws_id, "slug": slug},
    )

    admin_id = uuid.uuid4()
    await committed_db_session.execute(
        text(
            "SELECT register_object("
            "  'user'::object_kind, :ws_id, NULL, :ckey, 'Admin User', :u_id, :u_id"
            ")"
        ),
        {"ws_id": ws_id, "ckey": f"usr-{admin_id.hex}", "u_id": admin_id},
    )
    await committed_db_session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Admin User', 'ACTIVE')"
        ),
        {"id": admin_id, "ws_id": ws_id},
    )
    await committed_db_session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'admin@example.com')"
        ),
        {"id": admin_id, "ws_id": ws_id},
    )
    await committed_db_session.execute(
        text(
            "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type) "
            "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server')"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": admin_id},
    )
    await committed_db_session.execute(
        text(
            "INSERT INTO local_admin_credentials (principal_id, username, password_hash) "
            "VALUES (:p_id, :uname, '$argon2id$fake')"
        ),
        {"p_id": admin_id, "uname": f"admin-{ws_id.hex[:6]}"},
    )

    # Enable a local admin card (disabled initially)
    await committed_db_session.execute(
        text(
            "INSERT INTO auth_provider_cards "
            "(id, workspace_id, provider_kind, slug, display_name, sort_rank, is_enabled) "
            "VALUES (:id, :ws_id, 'LOCAL_ADMIN', :slug, 'Local Admin', '0|', FALSE)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "slug": f"loc-{ws_id.hex[:6]}"},
    )
    await committed_db_session.commit()

    # Use current session's engine DSN or environment
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock-17")
    user = os.environ.get("KB_TEST_PGUSER", "kanban_test")
    db_name = await committed_db_session.scalar(text("SELECT current_database()"))
    env_dsn = f"postgresql+asyncpg://{user}@/{db_name}?host={socket_dir}"

    with patch.dict(os.environ, {"KANBAN_ADMIN_DATABASE_URL": env_dsn}):
        stderr_buf = io.StringIO()
        stdout_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf), patch("sys.stdout", stdout_buf):
            ret = main(
                [
                    "auth",
                    "emergency-unlock",
                    "--enable-local-admin",
                    "--workspace",
                    slug,
                    "--reason",
                    "E2E automated test",
                ]
            )

        err_out = stderr_buf.getvalue()
        output = stdout_buf.getvalue()
        assert ret == 0, f"Command failed with {ret}: stderr={err_out}, stdout={output}"
        assert "EMERGENCY_UNLOCK_SUCCESS" in output
        assert f"workspace={ws_id}" in output


def test_get_admin_dsn_resolution() -> None:
    """Verify DSN resolution priority and fallback."""
    # 1. KANBAN_ADMIN_DATABASE_URL
    with patch.dict(os.environ, {"KANBAN_ADMIN_DATABASE_URL": "postgresql+asyncpg://admin@/db1"}):
        assert _get_admin_dsn() == "postgresql+asyncpg://admin@/db1"

    # 2. KANBAN_DATABASE_URL
    with patch.dict(
        os.environ, {"KANBAN_DATABASE_URL": "postgresql+asyncpg://app@/db2"}, clear=True
    ):
        assert _get_admin_dsn() == "postgresql+asyncpg://app@/db2"

    # 3. Fallback
    with patch.dict(os.environ, {}, clear=True):
        dsn = _get_admin_dsn()
        assert "postgresql+asyncpg://" in dsn
        assert "kanban_migrator" in dsn


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_cli_workspace_resolution_paths(committed_db_session: AsyncSession) -> None:
    """Test workspace resolution edge cases: not found, auto-detect 1, and ambiguous multiple."""
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock-17")
    user = os.environ.get("KB_TEST_PGUSER", "kanban_test")
    db_name = await committed_db_session.scalar(text("SELECT current_database()"))
    env_dsn = f"postgresql+asyncpg://{user}@/{db_name}?host={socket_dir}"

    with patch.dict(os.environ, {"KANBAN_ADMIN_DATABASE_URL": env_dsn}):
        # 1. Non-existent slug -> returns 1
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            ret = main(
                [
                    "auth",
                    "emergency-unlock",
                    "--enable-local-admin",
                    "--workspace",
                    "non-existent-slug",
                ]
            )
        assert ret == 1
        assert "Workspace not found with slug" in stderr_buf.getvalue()

        # 2. When 0 workspaces exist -> returns 1
        await committed_db_session.execute(text("TRUNCATE workspaces RESTART IDENTITY CASCADE"))
        await committed_db_session.commit()

        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            ret = main(
                [
                    "auth",
                    "emergency-unlock",
                    "--enable-local-admin",
                ]
            )
        assert ret == 1
        assert "No workspaces exist" in stderr_buf.getvalue()

        # 3. When multiple workspaces exist without --workspace -> returns 2
        ws1 = uuid.uuid4()
        ws2 = uuid.uuid4()
        await committed_db_session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'WS1')"),
            {"id": ws1, "slug": f"ws-{ws1.hex[:8]}"},
        )
        await committed_db_session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'WS2')"),
            {"id": ws2, "slug": f"ws-{ws2.hex[:8]}"},
        )
        await committed_db_session.commit()

        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            ret = main(
                [
                    "auth",
                    "emergency-unlock",
                    "--enable-local-admin",
                ]
            )
        assert ret == 2
        assert "Multiple workspaces exist" in stderr_buf.getvalue()

        # 4. When exactly 1 workspace exists and --workspace is omitted -> auto-selects it
        await committed_db_session.execute(
            text("DELETE FROM workspaces WHERE id = :id"),
            {"id": ws2},
        )
        # Add local admin card and admin user for ws1
        await committed_db_session.execute(
            text(
                "SELECT register_object("
                "  'user'::object_kind, :ws_id, NULL, :ckey, 'Admin User', :u_id, :u_id"
                ")"
            ),
            {"ws_id": ws1, "ckey": f"usr-{ws1.hex[:8]}", "u_id": ws1},
        )
        await committed_db_session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'Admin User', 'ACTIVE')"
            ),
            {"id": ws1, "ws_id": ws1},
        )
        await committed_db_session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, 'adm@example.com')"
            ),
            {"id": ws1, "ws_id": ws1},
        )
        await committed_db_session.execute(
            text(
                "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type) "
                "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server')"
            ),
            {"id": uuid.uuid4(), "ws_id": ws1, "p_id": ws1},
        )
        await committed_db_session.execute(
            text(
                "INSERT INTO local_admin_credentials (principal_id, username, password_hash) "
                "VALUES (:p_id, :uname, '$argon2id$fake')"
            ),
            {"p_id": ws1, "uname": f"admin-{ws1.hex[:6]}"},
        )
        await committed_db_session.execute(
            text(
                "INSERT INTO auth_provider_cards "
                "(id, workspace_id, provider_kind, slug, display_name, sort_rank, is_enabled) "
                "VALUES (:id, :ws_id, 'LOCAL_ADMIN', :slug, 'Local Admin', '0|', FALSE)"
            ),
            {"id": uuid.uuid4(), "ws_id": ws1, "slug": f"loc-{ws1.hex[:6]}"},
        )
        await committed_db_session.commit()

        stderr_buf = io.StringIO()
        stdout_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf), patch("sys.stdout", stdout_buf):
            ret = main(
                [
                    "auth",
                    "emergency-unlock",
                    "--enable-local-admin",
                ]
            )
        assert ret == 0
        assert f"workspace={ws1}" in stdout_buf.getvalue()


@pytest.mark.asyncio
async def test_cli_permission_and_general_error_handling() -> None:
    """Verify error reporting for permission denied and connection errors."""
    # Invalid DSN causing general connection error
    inv_dsn = "postgresql+asyncpg://invalid:pwd@/invalid?host=/nonexistent"
    with patch.dict(os.environ, {"KANBAN_ADMIN_DATABASE_URL": inv_dsn}):
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            ret = main(
                [
                    "auth",
                    "emergency-unlock",
                    "--enable-local-admin",
                    "--workspace",
                    str(uuid.uuid4()),
                ]
            )
        assert ret == 1
        assert "Error executing emergency unlock" in stderr_buf.getvalue()

    # Permission denied simulated
    with patch("kanban.cli.auth.create_async_engine") as mock_engine:
        mock_conn = MagicMock()
        mock_conn.__aenter__.side_effect = Exception("42501 insufficient_privilege")
        mock_engine.return_value.begin.return_value = mock_conn
        mock_engine.return_value.dispose = AsyncMock()

        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            ret = main(
                [
                    "auth",
                    "emergency-unlock",
                    "--enable-local-admin",
                    "--workspace",
                    str(uuid.uuid4()),
                ]
            )
        assert ret == 1
        assert (
            "Permission Denied: kanban_app cannot execute emergency unlock" in stderr_buf.getvalue()
        )


def test_handle_emergency_unlock_outside_event_loop() -> None:
    """Verify handle_emergency_unlock dispatch when no event loop is running."""
    args = argparse.Namespace(
        enable_local_admin=True,
        workspace="non-existent",
        reason="Test outside loop",
    )

    with (
        patch("asyncio.get_running_loop", side_effect=RuntimeError("no running loop")),
        patch("kanban.cli.auth._run_emergency_unlock", return_value=0),
    ):
        ret = handle_emergency_unlock(args)
        assert ret == 0
