# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Security tests for hardened workspace switching and tenant isolation (KAN-329)."""
# ruff: noqa: E501, D103

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import text

from database.session import RLSSessionFactory
from kanban.auth.sessions.cookies import SESSION_COOKIE_NAME
from kanban.auth.sessions.csrf import CSRF_HEADER_NAME
from kanban.auth.sessions.service import SessionService
from kanban.security.keys import KeyMaterial
from kanban.tests.api.test_workspaces_api import (
    _create_test_app,
    _login_and_elevate,
    _setup_workspace_and_principals,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def key_material() -> KeyMaterial:
    return KeyMaterial(
        master_kek=b"k" * 32,
        master_kek_kid="kek-v1",
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )


@pytest.mark.asyncio
async def test_direct_member_workspace_switch_succeeds(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Verify that a principal directly belonging to a target workspace can switch to it."""
    ws1_id, _, member_id = await _setup_workspace_and_principals(db_session)

    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        _, csrf_token = await _login_and_elevate(
            client, session_service, db_session, member_id, ws1_id, aal_level=1
        )
        resp = await client.post(
            f"/api/v1/workspaces/{ws1_id}/switch",
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace_id"] == str(ws1_id)
        assert data["status"] == "switched"


@pytest.mark.asyncio
async def test_verified_user_identities_cross_workspace_switch_succeeds(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Verify that cross-workspace principals linked via user_identities can switch."""
    ws1_id, _, p1_id = await _setup_workspace_and_principals(db_session)

    ws2_id = uuid.uuid4()
    p2_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Ident WS2')"),
        {"id": ws2_id, "slug": f"ws-{ws2_id.hex[:10]}"},
    )
    await db_session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, 'User WS2', :u_id, :u_id)"
        ),
        {"ws_id": ws2_id, "ckey": f"usr-{p2_id.hex[:10]}", "u_id": p2_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'User WS2', 'ACTIVE')"
        ),
        {"id": p2_id, "ws_id": ws2_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'shared.user@example.com')"
        ),
        {"id": p2_id, "ws_id": ws2_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'WORKSPACE_MEMBER', 'workspace', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws2_id, "p_id": p2_id},
    )

    # Link both via same auth provider card and subject
    card_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO auth_provider_cards ("
            "  id, workspace_id, provider_kind, slug, display_name, is_enabled, sort_rank"
            ") VALUES ("
            "  :id, :ws_id, 'OIDC', :slug, 'Corp OIDC', true, '0|h00000:'"
            ")"
        ),
        {"id": card_id, "ws_id": ws1_id, "slug": f"card-{uuid.uuid4().hex[:8]}"},
    )
    shared_sub = f"sub-{uuid.uuid4().hex[:12]}"
    await db_session.execute(
        text(
            "INSERT INTO user_identities (id, workspace_id, principal_id, auth_card_id, immutable_subject_id) "
            "VALUES (:id, :ws_id, :p_id, :card_id, :sub)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws1_id, "p_id": p1_id, "card_id": card_id, "sub": shared_sub},
    )
    await db_session.execute(
        text(
            "INSERT INTO user_identities (id, workspace_id, principal_id, auth_card_id, immutable_subject_id) "
            "VALUES (:id, :ws_id, :p_id, :card_id, :sub)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws2_id, "p_id": p2_id, "card_id": card_id, "sub": shared_sub},
    )

    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        _, csrf_token = await _login_and_elevate(
            client, session_service, db_session, p1_id, ws1_id, aal_level=1
        )
        resp = await client.post(
            f"/api/v1/workspaces/{ws2_id}/switch",
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace_id"] == str(ws2_id)
        assert data["status"] == "switched"

        # Verify session was updated to p2_id in target workspace
        session_cookie = resp.cookies.get(SESSION_COOKIE_NAME)
        assert session_cookie is not None
        client.cookies.set(SESSION_COOKIE_NAME, session_cookie)
        resp_session = await client.get("/api/v1/auth/session")
        assert resp_session.status_code == 200
        assert resp_session.json()["workspace_id"] == str(ws2_id)
        assert resp_session.json()["principal_id"] == str(p2_id)


@pytest.mark.asyncio
async def test_unverified_matching_email_cross_tenant_switch_rejected(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Verify that an unverified matching email across tenants is strictly rejected (KAN-329/GSF-001)."""
    ws1_id, _, attacker_id = await _setup_workspace_and_principals(db_session)

    # Set attacker email to victim's email
    victim_email = "victim@targetcorp.example"
    await db_session.execute(
        text("UPDATE users SET email = :email WHERE id = :id"),
        {"email": victim_email, "id": attacker_id},
    )

    # Victim workspace with same email
    ws2_id = uuid.uuid4()
    victim_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Victim WS')"),
        {"id": ws2_id, "slug": f"ws-{ws2_id.hex[:10]}"},
    )
    await db_session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, 'Victim User', :u_id, :u_id)"
        ),
        {"ws_id": ws2_id, "ckey": f"usr-{victim_id.hex[:10]}", "u_id": victim_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Victim User', 'ACTIVE')"
        ),
        {"id": victim_id, "ws_id": ws2_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, :email)"
        ),
        {"id": victim_id, "ws_id": ws2_id, "email": victim_email},
    )
    await db_session.execute(
        text(
            "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'WORKSPACE_ADMIN', 'workspace', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws2_id, "p_id": victim_id},
    )

    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        _, csrf_token = await _login_and_elevate(
            client, session_service, db_session, attacker_id, ws1_id, aal_level=1
        )
        resp = await client.post(
            f"/api/v1/workspaces/{ws2_id}/switch",
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp.status_code == 403
        assert "FORBIDDEN_WORKSPACE_SWITCH" in resp.text


@pytest.mark.asyncio
async def test_non_admin_with_admin_email_cannot_elevate_server_admin(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Verify that a regular user sharing an email with a server admin in another workspace cannot elevate."""
    ws1_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    admin_email = "superadmin@corp.example"
    await db_session.execute(
        text("UPDATE users SET email = :email WHERE id = :id"),
        {"email": admin_email, "id": admin_id},
    )

    # Separate workspace where an attacker registers with the server admin's email
    ws_attacker = uuid.uuid4()
    attacker_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Attacker WS')"),
        {"id": ws_attacker, "slug": f"ws-{ws_attacker.hex[:10]}"},
    )
    await db_session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, 'Attacker User', :u_id, :u_id)"
        ),
        {"ws_id": ws_attacker, "ckey": f"usr-{attacker_id.hex[:10]}", "u_id": attacker_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Attacker User', 'ACTIVE')"
        ),
        {"id": attacker_id, "ws_id": ws_attacker},
    )
    await db_session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, :email)"
        ),
        {"id": attacker_id, "ws_id": ws_attacker, "email": admin_email},
    )
    await db_session.execute(
        text(
            "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'WORKSPACE_MEMBER', 'workspace', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_attacker, "p_id": attacker_id},
    )

    # Target workspace that attacker attempts to switch into as server admin
    ws_target = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Target WS')"),
        {"id": ws_target, "slug": f"ws-{ws_target.hex[:10]}"},
    )

    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        _, csrf_token = await _login_and_elevate(
            client, session_service, db_session, attacker_id, ws_attacker, aal_level=1
        )
        # Attacker cannot switch into target workspace
        resp = await client.post(
            f"/api/v1/workspaces/{ws_target}/switch",
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp.status_code == 403
        assert "FORBIDDEN_WORKSPACE_SWITCH" in resp.text

        # Attacker cannot switch into admin's workspace
        resp_admin_ws = await client.post(
            f"/api/v1/workspaces/{ws1_id}/switch",
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_admin_ws.status_code == 403
        assert "FORBIDDEN_WORKSPACE_SWITCH" in resp_admin_ws.text
