# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and integration tests for lockout safeguards and problem mapping (KB-P2-09)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from kanban.auth.cards.lockout import (
    LOCKOUT_TYPE_URI,
    LockoutPreventedError,
    assert_local_admin_disable_allowed,
    map_sqlstate_to_lockout_error,
    record_external_admin_handshake,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class _MockPgError(Exception):
    def __init__(self, message: str, sqlstate: str = "P0001", detail: str | None = None) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate
        self.detail = detail


def test_lockout_prevented_error_problem_mapping() -> None:
    """Test Case 6: LockoutPreventedError maps to HTTP 409 RFC 7807 problem."""
    # 1. db_trigger layer
    err_db = LockoutPreventedError(
        layer="db_trigger",
        detail="zero enabled cards can authenticate an active SERVER_ADMIN",
    )
    prob_db = err_db.to_problem_exception()
    assert prob_db.status == 409
    assert prob_db.code == "LOCKOUT_PREVENTED"
    assert prob_db.type_uri == LOCKOUT_TYPE_URI
    assert prob_db.extra is not None
    assert prob_db.extra.get("layer") == "db_trigger"
    assert prob_db.detail is not None
    assert "zero enabled cards" in prob_db.detail

    # 2. handshake_probe_15m layer
    hs_detail = (
        "disabling LOCAL_ADMIN requires a verified external SERVER_ADMIN login within 15 minutes"
    )
    err_hs = LockoutPreventedError(layer="handshake_probe_15m", detail=hs_detail)
    prob_hs = err_hs.to_problem_exception()
    assert prob_hs.status == 409
    assert prob_hs.code == "LOCKOUT_PREVENTED"
    assert prob_hs.type_uri == LOCKOUT_TYPE_URI
    assert prob_hs.extra is not None
    assert prob_hs.extra.get("layer") == "handshake_probe_15m"
    assert prob_hs.detail is not None
    assert "15 minutes" in prob_hs.detail


def test_map_sqlstate_to_lockout_error_parsing() -> None:
    """Verify map_sqlstate_to_lockout_error parses db_trigger and handshake_probe_15m."""
    # 1. Mock DBAPIError with handshake_probe_15m
    msg_hs = (
        "LOCKOUT_PREVENTED: disabling LOCAL_ADMIN requires "
        "a verified external SERVER_ADMIN login within 15 minutes"
    )
    orig_hs = _MockPgError(msg_hs, sqlstate="P0001", detail="handshake_probe_15m")
    exc_hs = DBAPIError("SELECT 1", {}, orig_hs)

    parsed_hs = map_sqlstate_to_lockout_error(exc_hs)
    assert parsed_hs is not None
    assert parsed_hs.layer == "handshake_probe_15m"
    assert "15 minutes" in parsed_hs.detail

    # 2. Mock DBAPIError with db_trigger
    msg_db = "LOCKOUT_PREVENTED: zero enabled cards can authenticate an active SERVER_ADMIN"
    orig_db = _MockPgError(msg_db, sqlstate="P0001", detail="db_trigger")
    exc_db = DBAPIError("SELECT 1", {}, orig_db)

    parsed_db = map_sqlstate_to_lockout_error(exc_db)
    assert parsed_db is not None
    assert parsed_db.layer == "db_trigger"
    assert "zero enabled cards" in parsed_db.detail

    # 3. Unrelated SQL error -> returns None
    orig_other = _MockPgError(
        "duplicate key value violates unique constraint",
        sqlstate="23505",
        detail="Key (slug)=(...) already exists",
    )
    exc_other = DBAPIError("INSERT ...", {}, orig_other)
    assert map_sqlstate_to_lockout_error(exc_other) is None

    # Plain non-DBAPI exception
    assert map_sqlstate_to_lockout_error(ValueError("random error")) is None

    # DBAPIError with non-BaseException or generic BaseException
    base_err = BaseException()
    assert map_sqlstate_to_lockout_error(DBAPIError("SELECT 1", {}, base_err)) is None

    # 4. Fallback default detail when pattern doesn't match
    orig_nomatch = _MockPgError(
        "P0001 custom error without pattern",
        sqlstate="P0001",
        detail="handshake_probe_15m",
    )
    exc_nomatch = DBAPIError("UPDATE ...", {}, orig_nomatch)
    parsed_nomatch = map_sqlstate_to_lockout_error(exc_nomatch)
    assert parsed_nomatch is not None
    assert parsed_nomatch.layer == "handshake_probe_15m"
    assert "15 minutes" in parsed_nomatch.detail

    # Fallback db_trigger default detail
    orig_nomatch_db = _MockPgError(
        "P0001 custom db_trigger error",
        sqlstate="P0001",
        detail="db_trigger",
    )
    exc_nomatch_db = DBAPIError("UPDATE ...", {}, orig_nomatch_db)
    parsed_nomatch_db = map_sqlstate_to_lockout_error(exc_nomatch_db)
    assert parsed_nomatch_db is not None
    assert parsed_nomatch_db.layer == "db_trigger"
    assert "zero enabled cards" in parsed_nomatch_db.detail


@pytest.mark.asyncio
async def test_record_external_admin_handshake_integration(db_session: AsyncSession) -> None:
    """Verify record_external_admin_handshake updates last_admin_handshake_at."""
    ws_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Handshake WS')"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:8]}"},
    )
    card_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO auth_provider_cards "
            "(id, workspace_id, provider_kind, slug, display_name, sort_rank, is_enabled) "
            "VALUES (:id, :ws_id, 'OIDC', :slug, 'OIDC Card', '0|', TRUE)"
        ),
        {"id": card_id, "ws_id": ws_id, "slug": f"card-{ws_id.hex[:6]}"},
    )

    before = await db_session.scalar(
        text("SELECT last_admin_handshake_at FROM auth_provider_cards WHERE id = :id"),
        {"id": card_id},
    )
    assert before is None

    await record_external_admin_handshake(db_session, card_id)

    after = await db_session.scalar(
        text("SELECT last_admin_handshake_at FROM auth_provider_cards WHERE id = :id"),
        {"id": card_id},
    )
    assert after is not None
    assert isinstance(after, dt.datetime)


@pytest.mark.asyncio
async def test_assert_local_admin_disable_allowed_integration(db_session: AsyncSession) -> None:
    """Verify Python pre-validation via assert_local_admin_disable_allowed."""
    # 1. Non-existent card -> no error
    await assert_local_admin_disable_allowed(db_session, uuid.uuid4(), None)

    # 2. Workspace without active admin (bootstrap) -> no error
    ws_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'WS')"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:8]}"},
    )
    card_loc = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO auth_provider_cards "
            "(id, workspace_id, provider_kind, slug, display_name, sort_rank, is_enabled) "
            "VALUES (:id, :ws_id, 'LOCAL_ADMIN', :slug, 'Local', '0|', TRUE)"
        ),
        {"id": card_loc, "ws_id": ws_id, "slug": f"loc-{ws_id.hex[:6]}"},
    )
    await assert_local_admin_disable_allowed(db_session, card_loc, ws_id)

    # 3. Add active admin and local admin credentials
    admin_id = uuid.uuid4()
    await db_session.execute(
        text(
            "SELECT register_object("
            "  'user'::object_kind, :ws_id, NULL, :ckey, 'Admin', :u_id, :u_id"
            ")"
        ),
        {"ws_id": ws_id, "ckey": f"usr-{admin_id.hex}", "u_id": admin_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Admin', 'ACTIVE')"
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

    # Now disabling LOCAL_ADMIN must raise LockoutPreventedError (handshake_probe_15m)
    with pytest.raises(LockoutPreventedError) as exc_info:
        await assert_local_admin_disable_allowed(db_session, card_loc, ws_id)
    assert exc_info.value.layer == "handshake_probe_15m"

    # 4. Add OIDC card with recent handshake
    card_oidc = uuid.uuid4()
    now = dt.datetime.now(dt.UTC)
    await db_session.execute(
        text(
            "INSERT INTO auth_provider_cards ("
            "  id, workspace_id, provider_kind, slug, display_name, "
            "  sort_rank, is_enabled, last_admin_handshake_at"
            ") VALUES (:id, :ws_id, 'OIDC', :slug, 'OIDC', '0|', TRUE, :now)"
        ),
        {"id": card_oidc, "ws_id": ws_id, "slug": f"oidc-{ws_id.hex[:6]}", "now": now},
    )
    await db_session.execute(
        text(
            "INSERT INTO user_identities ("
            "  id, principal_id, auth_card_id, immutable_subject_id, email_at_link"
            ") VALUES (:id, :p_id, :c_id, 'sub1', 'admin@example.com')"
        ),
        {"id": uuid.uuid4(), "p_id": admin_id, "c_id": card_oidc},
    )

    # Now disabling LOCAL_ADMIN succeeds
    await assert_local_admin_disable_allowed(db_session, card_loc, ws_id)

    # 5. Add a third card that is enabled but has 0 admin identities (can_auth=False)
    card_dummy = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO auth_provider_cards "
            "(id, workspace_id, provider_kind, slug, display_name, sort_rank, is_enabled) "
            "VALUES (:id, :ws_id, 'OIDC', :slug, 'Dummy OIDC', '0|', TRUE)"
        ),
        {"id": card_dummy, "ws_id": ws_id, "slug": f"dummy-{ws_id.hex[:6]}"},
    )

    # Disable LOCAL_ADMIN in the DB to test disabling the OIDC card
    await db_session.execute(
        text("UPDATE auth_provider_cards SET is_enabled = FALSE WHERE id = :id"),
        {"id": card_loc},
    )

    # Now attempt to disable the only remaining admin-capable card -> raises db_trigger
    with pytest.raises(LockoutPreventedError) as exc_info:
        await assert_local_admin_disable_allowed(db_session, card_oidc, ws_id)
    assert exc_info.value.layer == "db_trigger"
