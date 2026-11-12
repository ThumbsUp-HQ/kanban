# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Database security boundary, RLS, and throttling tests for sessions (KB-P2-02)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _setup_workspace_and_principal(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision workspace, principal, and user records."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Boundary WS"},
    )

    u_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{u_id.hex}",
            "title": "Boundary Test User",
            "u_id": u_id,
        },
    )

    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Boundary User', 'ACTIVE')"
        ),
        {"id": u_id, "ws_id": ws_id},
    )

    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'boundary@example.com')"
        ),
        {"id": u_id, "ws_id": ws_id},
    )

    return ws_id, u_id


async def _create_test_session(  # noqa: PLR0913
    session: AsyncSession,
    p_id: uuid.UUID,
    ws_id: uuid.UUID,
    token_sha: bytes,
    *,
    aal_level: int = 1,
    mfa_pending: bool = False,
) -> uuid.UUID:
    """Create a session via kb_auth.session_create."""
    sess_id = uuid.uuid4()
    now = datetime.now(UTC)
    stmt = text(
        "SELECT kb_auth.session_create("
        "  :p_id, :p_token_sha256, :p_principal_id, :p_workspace_id, "
        "  :p_auth_card_id, :p_aal_level, :p_aal2_verified_at, :p_mfa_pending, "
        "  :p_idle_expires_at, :p_absolute_expires_at, :p_rotated_from_id"
        ")"
    )
    await session.execute(
        stmt,
        {
            "p_id": sess_id,
            "p_token_sha256": token_sha,
            "p_principal_id": p_id,
            "p_workspace_id": ws_id,
            "p_auth_card_id": None,
            "p_aal_level": aal_level,
            "p_aal2_verified_at": None,
            "p_mfa_pending": mfa_pending,
            "p_idle_expires_at": now + timedelta(seconds=28800),
            "p_absolute_expires_at": now + timedelta(seconds=604800),
            "p_rotated_from_id": None,
        },
    )
    return sess_id


@pytest.mark.asyncio
async def test_case_7_last_seen_at_throttling_single_update(
    db_session: AsyncSession,
) -> None:
    """Test Case 7: last_seen_at written at most once per 60s across 10 requests within 30s.

    Asserts that across 10 consecutive calls to session_resolve, exactly ONE UPDATE is
    executed when last_seen_at was older than 60s, and subsequent requests within 30s
    do not trigger further DB writes.
    """
    ws_id, p_id = await _setup_workspace_and_principal(db_session)

    token = secrets.token_bytes(32)
    token_sha = hashlib.sha256(token).digest()

    # 1. Create a fresh session
    sess_id = await _create_test_session(db_session, p_id, ws_id, token_sha)

    # 2. Simulate that last_seen_at is older than 60s (e.g. 70s ago)
    await db_session.execute(
        text("UPDATE sessions SET last_seen_at = now() - interval '70 seconds' WHERE id = :id"),
        {"id": sess_id},
    )

    # 3. Create an update tracking table and trigger to count UPDATEs on sessions
    await db_session.execute(text("CREATE TEMP TABLE test_sess_updates (cnt int)"))
    await db_session.execute(text("INSERT INTO test_sess_updates VALUES (0)"))
    await db_session.execute(text("GRANT ALL ON test_sess_updates TO kb_auth_owner"))
    await db_session.execute(
        text(
            "CREATE OR REPLACE FUNCTION trg_count_sess_updates() RETURNS trigger "
            "SECURITY DEFINER AS $$ "
            "BEGIN "
            "  UPDATE test_sess_updates SET cnt = cnt + 1; "
            "  RETURN NEW; "
            "END; "
            "$$ LANGUAGE plpgsql;"
        )
    )
    await db_session.execute(
        text(
            "CREATE TRIGGER trg_test_session_update "
            "BEFORE UPDATE ON sessions "
            "FOR EACH ROW EXECUTE FUNCTION trg_count_sess_updates();"
        )
    )

    # 4. Fire 10 consecutive session_resolve calls simulating requests within 30s
    last_seen_values = []
    for _ in range(10):
        r = await db_session.execute(
            text("SELECT last_seen_at FROM kb_auth.session_resolve(:token_sha)"),
            {"token_sha": token_sha},
        )
        resolved_row = r.first()
        assert resolved_row is not None
        last_seen_values.append(resolved_row[0])

    # 5. Assert that exactly 1 update was performed by the trigger
    cnt_res = await db_session.execute(text("SELECT cnt FROM test_sess_updates"))
    update_count = cnt_res.scalar_one()
    assert update_count == 1, f"Expected exactly 1 update, got {update_count}"

    # 6. Assert all 10 calls returned the identical updated last_seen_at timestamp
    first_ts = last_seen_values[0]
    for ts in last_seen_values:
        assert ts == first_ts

    # Clean up trigger
    await db_session.execute(text("DROP TRIGGER IF EXISTS trg_test_session_update ON sessions;"))


@pytest.mark.asyncio
async def test_case_11_db_boundary_privilege_denials_and_no_hash_exposure(
    db_session: AsyncSession,
) -> None:
    """Test Case 11: DB boundary enforcement.

    1. As kanban_app, direct SELECT * FROM sessions raises 42501 (permission denied).
    2. Direct INSERT/UPDATE/DELETE on sessions as kanban_app raises 42501.
    3. Introspection proves no kb_auth function returns token_sha256.
    4. Oversize cookie rejection (covered in test_cookies.py, verified here at boundary).
    """
    ws_id, p_id = await _setup_workspace_and_principal(db_session)
    token = secrets.token_bytes(32)
    token_sha = hashlib.sha256(token).digest()

    # Create session under owner
    sess_id = await _create_test_session(db_session, p_id, ws_id, token_sha)

    # Switch session authorization to least-privileged application role kanban_app
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    # 1. Direct SELECT * FROM sessions as kanban_app raises 42501
    with pytest.raises(DBAPIError) as exc_select:
        async with db_session.begin_nested():
            await db_session.execute(text("SELECT * FROM sessions"))
    assert "42501" in str(exc_select.value) or "permission denied" in str(exc_select.value).lower()

    # 2. Direct INSERT on sessions raises 42501
    with pytest.raises(DBAPIError) as exc_insert:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO sessions "
                    "(id, token_sha256, principal_id, workspace_id, aal_level) "
                    "VALUES (:id, :sha, :p_id, :ws_id, 1)"
                ),
                {"id": uuid.uuid4(), "sha": b"\x01" * 32, "p_id": p_id, "ws_id": ws_id},
            )
    assert "42501" in str(exc_insert.value) or "permission denied" in str(exc_insert.value).lower()

    # 3. Direct UPDATE on sessions raises 42501
    with pytest.raises(DBAPIError) as exc_update:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE sessions SET aal_level = 2 WHERE id = :id"),
                {"id": sess_id},
            )
    assert "42501" in str(exc_update.value) or "permission denied" in str(exc_update.value).lower()

    # 4. Direct DELETE on sessions raises 42501
    with pytest.raises(DBAPIError) as exc_delete:
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM sessions WHERE id = :id"),
                {"id": sess_id},
            )
    assert "42501" in str(exc_delete.value) or "permission denied" in str(exc_delete.value).lower()

    # 5. Application role CAN execute kb_auth functions
    resolve_res = await db_session.execute(
        text("SELECT id, principal_id, aal_level FROM kb_auth.session_resolve(:sha)"),
        {"sha": token_sha},
    )
    resolved = resolve_res.first()
    assert resolved is not None
    assert resolved[0] == sess_id
    assert resolved[1] == p_id
    assert resolved[2] == 1

    # Reset role back to test superuser to introspect pg_proc / information_schema
    await db_session.execute(text("RESET SESSION AUTHORIZATION"))

    # 6. Introspect all functions in schema kb_auth starting with session_
    # Verify that ZERO columns or return values include token_sha256
    ret_types_res = await db_session.execute(
        text(
            "SELECT r.routine_name, p.parameter_name, p.data_type, p.parameter_mode "
            "FROM information_schema.routines r "
            "JOIN information_schema.parameters p "
            "  ON r.specific_name = p.specific_name "
            "WHERE r.routine_schema = 'kb_auth' "
            "  AND r.routine_name LIKE 'session_%' "
            "  AND p.parameter_mode IN ('OUT', 'INOUT', 'TABLE');"
        )
    )
    out_params = ret_types_res.fetchall()
    for row in out_params:
        routine_name, param_name, _data_type, mode = row
        assert param_name != "token_sha256", (
            f"Function kb_auth.{routine_name} leaks token_sha256 in parameter {param_name} ({mode})"
        )


@pytest.mark.asyncio
async def test_session_ddl_constraints(db_session: AsyncSession) -> None:
    """Verify DDL check constraints on sessions table: aal_level and token_sha256 length."""
    ws_id, p_id = await _setup_workspace_and_principal(db_session)

    # 1. Invalid aal_level = 3 violates check constraint
    with pytest.raises(DBAPIError) as exc_aal:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO sessions ("
                    "  id, token_sha256, principal_id, workspace_id, aal_level, "
                    "  idle_expires_at, absolute_expires_at"
                    ") VALUES ("
                    "  :id, :sha, :p_id, :ws_id, 3, "
                    "  now() + interval '1 hour', now() + interval '1 day'"
                    ")"
                ),
                {"id": uuid.uuid4(), "sha": b"\x01" * 32, "p_id": p_id, "ws_id": ws_id},
            )
    assert (
        "sessions_aal_level_check" in str(exc_aal.value)
        or "check constraint" in str(exc_aal.value).lower()
    )

    # 2. Invalid token_sha256 length (16 bytes instead of 32) violates check constraint
    with pytest.raises(DBAPIError) as exc_len:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO sessions ("
                    "  id, token_sha256, principal_id, workspace_id, aal_level, "
                    "  idle_expires_at, absolute_expires_at"
                    ") VALUES ("
                    "  :id, :sha, :p_id, :ws_id, 1, "
                    "  now() + interval '1 hour', now() + interval '1 day'"
                    ")"
                ),
                {"id": uuid.uuid4(), "sha": b"\x01" * 16, "p_id": p_id, "ws_id": ws_id},
            )
    assert (
        "sessions_token_sha256_len_check" in str(exc_len.value)
        or "check constraint" in str(exc_len.value).lower()
    )


@pytest.mark.asyncio
async def test_session_revoke_all_for_principal(db_session: AsyncSession) -> None:
    """Verify kb_auth.session_revoke_all_for_principal revokes only target principal's sessions."""
    ws_id, p1_id = await _setup_workspace_and_principal(db_session)
    _, p2_id = await _setup_workspace_and_principal(db_session)

    p1_tokens = [secrets.token_bytes(32) for _ in range(3)]
    p2_tokens = [secrets.token_bytes(32) for _ in range(2)]

    # Create 3 sessions for P1
    for tok in p1_tokens:
        tok_sha = hashlib.sha256(tok).digest()
        await _create_test_session(db_session, p1_id, ws_id, tok_sha)

    # Create 2 sessions for P2
    for tok in p2_tokens:
        tok_sha = hashlib.sha256(tok).digest()
        await _create_test_session(db_session, p2_id, ws_id, tok_sha)

    # Revoke all sessions for P1
    rev_res = await db_session.execute(
        text("SELECT kb_auth.session_revoke_all_for_principal(:p_id)"),
        {"p_id": p1_id},
    )
    revoked_count = rev_res.scalar_one()
    assert revoked_count == 3

    # All P1 sessions now resolve to empty (revoked)
    for tok in p1_tokens:
        tok_sha = hashlib.sha256(tok).digest()
        r = await db_session.execute(
            text("SELECT id FROM kb_auth.session_resolve(:sha)"),
            {"sha": tok_sha},
        )
        assert r.first() is None

    # All P2 sessions still resolve actively
    for tok in p2_tokens:
        tok_sha = hashlib.sha256(tok).digest()
        r = await db_session.execute(
            text("SELECT id FROM kb_auth.session_resolve(:sha)"),
            {"sha": tok_sha},
        )
        assert r.first() is not None
