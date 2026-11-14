# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Database and DDL tests for LOCKOUT_PREVENTED 3-layer safeguards (KB-P2-09)."""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


async def _setup_workspace(session: AsyncSession, slug_prefix: str = "ws") -> uuid.UUID:
    """Create a test workspace."""
    ws_id = uuid.uuid4()
    slug = f"{slug_prefix}-{ws_id.hex[:10]}"
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": slug, "name": f"Workspace {slug}"},
    )
    return ws_id


async def _create_user(
    session: AsyncSession,
    ws_id: uuid.UUID,
    role: str = "SERVER_ADMIN",
    status: str = "ACTIVE",
    display_name: str = "Admin User",
) -> uuid.UUID:
    """Register user in objects spine, principals, users, and bind role."""
    u_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object("
            "  'user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id"
            ")"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{u_id.hex}",
            "title": display_name,
            "u_id": u_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, :name, :status)"
        ),
        {"id": u_id, "ws_id": ws_id, "name": display_name, "status": status},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, :email)"
        ),
        {"id": u_id, "ws_id": ws_id, "email": f"{u_id.hex[:8]}@example.com"},
    )
    if role:
        rb_id = uuid.uuid4()
        scope_type = "server" if role == "SERVER_ADMIN" else "workspace"
        await session.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :p_id, :role, :scope, NULL)"
            ),
            {"id": rb_id, "ws_id": ws_id, "p_id": u_id, "role": role, "scope": scope_type},
        )
    return u_id


async def _create_card(  # noqa: PLR0913
    session: AsyncSession,
    ws_id: uuid.UUID,
    kind: str,
    slug: str,
    *,
    enabled: bool = True,
    handshake_at: dt.datetime | None = None,
) -> uuid.UUID:
    """Insert an auth_provider_cards row."""
    card_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO auth_provider_cards ("
            "  id, workspace_id, provider_kind, slug, display_name, "
            "  sort_rank, is_enabled, last_admin_handshake_at"
            ") VALUES (:id, :ws_id, :kind, :slug, :name, '0|hzzzzz:', :enabled, :handshake_at)"
        ),
        {
            "id": card_id,
            "ws_id": ws_id,
            "kind": kind,
            "slug": slug,
            "name": f"Card {slug}",
            "enabled": enabled,
            "handshake_at": handshake_at,
        },
    )
    return card_id


async def _create_local_admin_cred(
    session: AsyncSession,
    principal_id: uuid.UUID,
    username: str,
) -> None:
    """Insert into local_admin_credentials."""
    await session.execute(
        text(
            "INSERT INTO local_admin_credentials (principal_id, username, password_hash) "
            "VALUES (:p_id, :username, '$argon2id$v=19$m=65536,t=3,p=4$fakehash$fakehash')"
        ),
        {"p_id": principal_id, "username": username},
    )


async def _create_user_identity(
    session: AsyncSession,
    principal_id: uuid.UUID,
    card_id: uuid.UUID,
    subject: str,
) -> uuid.UUID:
    """Insert into user_identities."""
    ident_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO user_identities ("
            "  id, principal_id, auth_card_id, immutable_subject_id, email_at_link"
            ") VALUES (:id, :p_id, :c_id, :sub, :email)"
        ),
        {
            "id": ident_id,
            "p_id": principal_id,
            "c_id": card_id,
            "sub": subject,
            "email": f"{subject}@example.com",
        },
    )
    return ident_id


@pytest.mark.asyncio
async def test_case_1_layer_1_sole_admin_card_disable_or_delete_prevented(
    db_session: AsyncSession,
) -> None:
    """Test Case 1: Workspace with 1 SERVER_ADMIN; disabling or deleting sole card aborts."""
    ws_id = await _setup_workspace(db_session, "tc1")
    admin_id = await _create_user(db_session, ws_id, role="SERVER_ADMIN")
    card_id = await _create_card(db_session, ws_id, "OIDC", f"oidc-{uuid.uuid4().hex[:6]}")
    await _create_user_identity(db_session, admin_id, card_id, "sub-admin-tc1")

    # 1. Attempt to disable sole admin card -> aborts with LOCKOUT_PREVENTED, DETAIL = 'db_trigger'
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE auth_provider_cards SET is_enabled = FALSE WHERE id = :id"),
                {"id": card_id},
            )
    err = str(exc_info.value)
    assert "LOCKOUT_PREVENTED" in err
    assert "db_trigger" in err

    # 2. Attempt to delete sole admin card -> aborts with LOCKOUT_PREVENTED, DETAIL = 'db_trigger'
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM auth_provider_cards WHERE id = :id"),
                {"id": card_id},
            )
    err = str(exc_info.value)
    assert "LOCKOUT_PREVENTED" in err
    assert "db_trigger" in err


@pytest.mark.asyncio
async def test_case_2_layer_1_card_without_admin_identity_does_not_count(
    db_session: AsyncSession,
) -> None:
    """Test Case 2: Enabling card with 0 admin identities does not allow disabling admin card."""
    ws_id = await _setup_workspace(db_session, "tc2")
    admin_id = await _create_user(db_session, ws_id, role="SERVER_ADMIN")
    card_loc = await _create_card(db_session, ws_id, "LOCAL_ADMIN", f"loc-{uuid.uuid4().hex[:6]}")
    await _create_local_admin_cred(db_session, admin_id, f"admin-{uuid.uuid4().hex[:6]}")

    # Add second OIDC card (enabled) but NO user_identities linking to any SERVER_ADMIN
    await _create_card(db_session, ws_id, "OIDC", f"oidc-{uuid.uuid4().hex[:6]}", enabled=True)

    # Even though OIDC card is enabled, disabling card_loc must fail
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE auth_provider_cards SET is_enabled = FALSE WHERE id = :id"),
                {"id": card_loc},
            )
    err = str(exc_info.value)
    assert "LOCKOUT_PREVENTED" in err


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_case_3_layer_1_concurrency_dual_disable_serializes(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test Case 3: Two concurrent transactions simultaneously disabling Card A and B."""
    ws_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    card_a = uuid.uuid4()
    card_b = uuid.uuid4()

    # Setup committed baseline using a dedicated session
    async with AsyncSession(bind=pg_worker_db, expire_on_commit=False) as setup_session:
        await _setup_workspace(setup_session, "tc3")
        # Update ws_id to our known ws_id
        await setup_session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Concurrency WS')"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:8]}"},
        )
        await setup_session.execute(
            text(
                "SELECT register_object("
                "  'user'::object_kind, :ws_id, NULL, :ckey, 'Admin User', :u_id, :u_id"
                ")"
            ),
            {"ws_id": ws_id, "ckey": f"usr-{admin_id.hex}", "u_id": admin_id},
        )
        await setup_session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'Admin', 'ACTIVE')"
            ),
            {"id": admin_id, "ws_id": ws_id},
        )
        await setup_session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, 'admin@example.com')"
            ),
            {"id": admin_id, "ws_id": ws_id},
        )
        await setup_session.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
            ),
            {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": admin_id},
        )
        # Two OIDC cards enabled
        now = dt.datetime.now(dt.UTC)
        await setup_session.execute(
            text(
                "INSERT INTO auth_provider_cards ("
                "  id, workspace_id, provider_kind, slug, display_name, "
                "  sort_rank, is_enabled, last_admin_handshake_at"
                ") VALUES (:id, :ws_id, 'OIDC', :slug, 'Card A', '0|a', TRUE, :now)"
            ),
            {"id": card_a, "ws_id": ws_id, "slug": f"card-a-{ws_id.hex[:6]}", "now": now},
        )
        await setup_session.execute(
            text(
                "INSERT INTO auth_provider_cards ("
                "  id, workspace_id, provider_kind, slug, display_name, "
                "  sort_rank, is_enabled, last_admin_handshake_at"
                ") VALUES (:id, :ws_id, 'OIDC', :slug, 'Card B', '0|b', TRUE, :now)"
            ),
            {"id": card_b, "ws_id": ws_id, "slug": f"card-b-{ws_id.hex[:6]}", "now": now},
        )
        # Link admin to both cards
        await _create_user_identity(setup_session, admin_id, card_a, "sub-a")
        await _create_user_identity(setup_session, admin_id, card_b, "sub-b")
        await setup_session.commit()

    # Now attempt concurrent disable of card_a and card_b
    results: list[str | None] = []

    async def disable_card(target_card_id: uuid.UUID) -> None:
        async with AsyncSession(bind=pg_worker_db, expire_on_commit=False) as s:
            try:
                await s.execute(
                    text("UPDATE auth_provider_cards SET is_enabled = FALSE WHERE id = :id"),
                    {"id": target_card_id},
                )
                await s.commit()
                results.append("SUCCESS")
            except DBAPIError as e:
                await s.rollback()
                results.append(str(e))

    await asyncio.gather(disable_card(card_a), disable_card(card_b))

    # Exactly one must succeed, and the other must fail with LOCKOUT_PREVENTED
    assert results.count("SUCCESS") == 1
    failures = [r for r in results if r != "SUCCESS"]
    assert len(failures) == 1
    fail_msg = failures[0]
    assert fail_msg is not None
    assert "LOCKOUT_PREVENTED" in fail_msg


@pytest.mark.asyncio
async def test_case_4_layer_2_handshake_probe_15m(db_session: AsyncSession) -> None:
    """Test Case 4: Disabling LOCAL_ADMIN requires verified external login within 15m."""
    ws_id = await _setup_workspace(db_session, "tc4")
    admin_id = await _create_user(db_session, ws_id, role="SERVER_ADMIN")
    card_loc = await _create_card(db_session, ws_id, "LOCAL_ADMIN", f"loc-{uuid.uuid4().hex[:6]}")
    await _create_local_admin_cred(db_session, admin_id, f"admin-{uuid.uuid4().hex[:6]}")

    # Add OIDC card linked to admin
    card_oidc = await _create_card(
        db_session, ws_id, "OIDC", f"oidc-{uuid.uuid4().hex[:6]}", enabled=True
    )
    await _create_user_identity(db_session, admin_id, card_oidc, "sub-oidc")

    # 1. With last_admin_handshake_at IS NULL -> aborts with handshake_probe_15m
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE auth_provider_cards SET is_enabled = FALSE WHERE id = :id"),
                {"id": card_loc},
            )
    err = str(exc_info.value)
    assert "handshake_probe_15m" in err or "15 minutes" in err

    # 2. With last_admin_handshake_at 901 seconds ago -> aborts with handshake_probe_15m
    old_time = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=901)
    await db_session.execute(
        text("UPDATE auth_provider_cards SET last_admin_handshake_at = :ts WHERE id = :id"),
        {"ts": old_time, "id": card_oidc},
    )
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE auth_provider_cards SET is_enabled = FALSE WHERE id = :id"),
                {"id": card_loc},
            )
    err = str(exc_info.value)
    assert "handshake_probe_15m" in err or "15 minutes" in err

    # 3. With handshake 899 seconds ago -> succeeds
    recent_time = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=899)
    await db_session.execute(
        text("UPDATE auth_provider_cards SET last_admin_handshake_at = :ts WHERE id = :id"),
        {"ts": recent_time, "id": card_oidc},
    )
    await db_session.execute(
        text("UPDATE auth_provider_cards SET is_enabled = FALSE WHERE id = :id"),
        {"id": card_loc},
    )
    status = await db_session.scalar(
        text("SELECT is_enabled FROM auth_provider_cards WHERE id = :id"),
        {"id": card_loc},
    )
    assert status is False


@pytest.mark.asyncio
async def test_case_5_layer_2_member_login_does_not_satisfy_handshake_gate(
    db_session: AsyncSession,
) -> None:
    """Test Case 5: Regular WORKSPACE_MEMBER login does not satisfy handshake gate."""
    ws_id = await _setup_workspace(db_session, "tc5")
    admin_id = await _create_user(db_session, ws_id, role="SERVER_ADMIN")
    member_id = await _create_user(
        db_session, ws_id, role="WORKSPACE_MEMBER", display_name="Regular Member"
    )

    card_loc = await _create_card(db_session, ws_id, "LOCAL_ADMIN", f"loc-{uuid.uuid4().hex[:6]}")
    await _create_local_admin_cred(db_session, admin_id, f"admin-{uuid.uuid4().hex[:6]}")

    card_oidc = await _create_card(
        db_session, ws_id, "OIDC", f"oidc-{uuid.uuid4().hex[:6]}", enabled=True
    )
    # Member is linked to OIDC card, but SERVER_ADMIN is NOT linked to OIDC card
    await _create_user_identity(db_session, member_id, card_oidc, "member-sub")

    # Disabling LOCAL_ADMIN fails because OIDC card cannot authenticate an active SERVER_ADMIN
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE auth_provider_cards SET is_enabled = FALSE WHERE id = :id"),
                {"id": card_loc},
            )
    err = str(exc_info.value)
    assert "LOCKOUT_PREVENTED" in err


@pytest.mark.asyncio
async def test_case_6_credentials_and_identity_delete_prevented(
    db_session: AsyncSession,
) -> None:
    """Deleting local_admin_credentials for sole active admin raises db_trigger."""
    ws_id = await _setup_workspace(db_session, "tc6")
    admin_id = await _create_user(db_session, ws_id, role="SERVER_ADMIN")
    await _create_card(db_session, ws_id, "LOCAL_ADMIN", f"loc-{uuid.uuid4().hex[:6]}")
    await _create_local_admin_cred(db_session, admin_id, f"admin-{uuid.uuid4().hex[:6]}")

    # Deleting the local_admin_credentials row removes the only admin credential for workspace
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM local_admin_credentials WHERE principal_id = :p_id"),
                {"p_id": admin_id},
            )
    err = str(exc_info.value)
    assert "LOCKOUT_PREVENTED" in err
    assert "db_trigger" in err


@pytest.mark.asyncio
async def test_case_7_bootstrap_allowance_when_zero_admins_exist(
    db_session: AsyncSession,
) -> None:
    """Workspace with 0 active SERVER_ADMIN principals allows disabling/deleting cards."""
    ws_id = await _setup_workspace(db_session, "tc7-boot")
    card_id = await _create_card(db_session, ws_id, "LOCAL_ADMIN", f"loc-{uuid.uuid4().hex[:6]}")

    # Since no active admin exists in this workspace yet, disabling card is permitted
    await db_session.execute(
        text("UPDATE auth_provider_cards SET is_enabled = FALSE WHERE id = :id"),
        {"id": card_id},
    )
    status = await db_session.scalar(
        text("SELECT is_enabled FROM auth_provider_cards WHERE id = :id"),
        {"id": card_id},
    )
    assert status is False
