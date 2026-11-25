# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for Admin Auth Cards access and server-admin role scoping (KAN-398)."""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from database.session import RLSContext, RLSSessionFactory
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.auth.cards.service import AuthCardAdminService
from kanban.auth.mfa.policy import assert_admin_routes_protected
from kanban.auth.sessions.cookies import SESSION_COOKIE_NAME
from kanban.auth.sessions.csrf import CsrfMiddleware
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionService
from kanban.security.envelope import StaticKekProvider
from kanban.security.keys import KeyMaterial


@pytest.fixture
def key_material() -> KeyMaterial:
    """Fixture providing testing key material."""
    return KeyMaterial(
        master_kek=b"k" * 32,
        master_kek_kid="kek-v1",
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )


@pytest.fixture
def kek_provider(key_material: KeyMaterial) -> StaticKekProvider:
    """Fixture providing StaticKekProvider with test keys."""
    return StaticKekProvider(
        keys={"kek-v1": key_material.master_kek, "kek-v2": os.urandom(32)},
        current="kek-v1",
    )


async def _setup_workspace_and_multi_role_principals(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Provision test workspace and multiple role principals for access matrix testing."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Access Test WS"},
    )

    # 1. Server Admin principal
    server_admin_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, 'Server Admin', "
            ":u_id, :u_id)"
        ),
        {"ws_id": ws_id, "ckey": f"usr-{server_admin_id.hex}", "u_id": server_admin_id},
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Server Admin', 'ACTIVE')"
        ),
        {"id": server_admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'server-admin@example.com')"
        ),
        {"id": server_admin_id, "ws_id": ws_id},
    )
    # Server-scoped role binding (scope_type='server')
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": server_admin_id},
    )

    # 2. Workspace Admin principal
    ws_admin_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, 'Workspace Admin', "
            ":u_id, :u_id)"
        ),
        {"ws_id": ws_id, "ckey": f"usr-{ws_admin_id.hex}", "u_id": ws_admin_id},
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Workspace Admin', 'ACTIVE')"
        ),
        {"id": ws_admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'ws-admin@example.com')"
        ),
        {"id": ws_admin_id, "ws_id": ws_id},
    )
    # Workspace-scoped role binding (scope_type='workspace')
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'WORKSPACE_ADMIN', 'workspace', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": ws_admin_id},
    )

    # 3. Project Admin principal
    proj_id = uuid.uuid4()
    proj_ident = f"PRJ{proj_id.hex[:4].upper()}"
    await session.execute(
        text(
            "SELECT register_object('project'::object_kind, :ws_id, NULL, :ckey, 'Test Project', "
            ":creator_id, :proj_id)"
        ),
        {"ws_id": ws_id, "ckey": proj_ident, "creator_id": server_admin_id, "proj_id": proj_id},
    )
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, name, identifier) "
            "VALUES (:id, :ws_id, 'Test Project', :ident)"
        ),
        {"id": proj_id, "ws_id": ws_id, "ident": proj_ident},
    )

    project_admin_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, 'Project Admin', "
            ":u_id, :u_id)"
        ),
        {"ws_id": ws_id, "ckey": f"usr-{project_admin_id.hex}", "u_id": project_admin_id},
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Project Admin', 'ACTIVE')"
        ),
        {"id": project_admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'proj-admin@example.com')"
        ),
        {"id": project_admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'PROJECT_ADMIN', 'project', :proj_id)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": project_admin_id, "proj_id": proj_id},
    )

    # 4. Member principal
    member_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, 'Standard Member', "
            ":u_id, :u_id)"
        ),
        {"ws_id": ws_id, "ckey": f"usr-{member_id.hex}", "u_id": member_id},
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Standard Member', 'ACTIVE')"
        ),
        {"id": member_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'member@example.com')"
        ),
        {"id": member_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'WORKSPACE_MEMBER', 'workspace', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": member_id},
    )

    # 5. Viewer principal
    viewer_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, 'Standard Viewer', "
            ":u_id, :u_id)"
        ),
        {"ws_id": ws_id, "ckey": f"usr-{viewer_id.hex}", "u_id": viewer_id},
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Standard Viewer', 'ACTIVE')"
        ),
        {"id": viewer_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'viewer@example.com')"
        ),
        {"id": viewer_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'VIEWER', 'project', :proj_id)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": viewer_id, "proj_id": proj_id},
    )

    # Register MFA TOTP for all test principals to satisfy require_admin_aal2
    for p_id in (server_admin_id, ws_admin_id, project_admin_id, member_id, viewer_id):
        await session.execute(
            text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
            {
                "p_id": p_id,
                "blob": b"\x01" + b"\x00" * 28,
                "dek": b"\x01" + b"\x00" * 44,
            },
        )
        res = await session.execute(
            text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
            {"p_id": p_id},
        )
        p_row = res.mappings().first()
        if p_row:
            await session.execute(
                text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
                {"p_fid": p_row["id"]},
            )

    return ws_id, server_admin_id, ws_admin_id, project_admin_id, member_id, viewer_id


def _create_test_app(
    factory: RLSSessionFactory,
    service: AuthCardAdminService,
    key_material: KeyMaterial,
    session_service: SessionService,
) -> FastAPI:
    """Create test FastAPI application configured with dependencies."""
    app = FastAPI()
    app.state.session_factory = factory
    app.state.session_service = session_service
    app.state.key_material = key_material
    app.state.auth_card_admin_service = service
    app.state.principal_resolver = SessionCookieResolver(session_service, factory)

    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    v1_router = build_v1_router()
    app.include_router(v1_router, prefix="/api/v1")

    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_middleware(RequestIdMiddleware)
    return app


@pytest.mark.asyncio
async def test_app_principal_has_role_sql_server_admin_without_workspace(
    db_session: AsyncSession,
) -> None:
    """Verify app_principal_has_role matches SERVER_ADMIN without requiring workspace context."""
    (
        ws_id,
        server_admin_id,
        _ws_admin_id,
        _proj_admin_id,
        _member_id,
        _viewer_id,
    ) = await _setup_workspace_and_multi_role_principals(db_session)

    # 1. Bind RLSContext to server_admin with workspace_id unset (app.workspace_id = NULL)
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', '', true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"p_id": str(server_admin_id)},
    )

    # SERVER_ADMIN role must match even when app.workspace_id is NULL
    res = await db_session.execute(
        text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
    )
    assert res.scalar_one() is True

    # But WORKSPACE_ADMIN role must return False when app.workspace_id is NULL
    res_ws = await db_session.execute(
        text("SELECT app_principal_has_role(NULL, ARRAY['WORKSPACE_ADMIN'])")
    )
    assert res_ws.scalar_one() is False

    # 2. Bind RLSContext to server_admin with workspace_id set
    await db_session.execute(
        text("SELECT set_config('app.workspace_id', :ws_id, true)"),
        {"ws_id": str(ws_id)},
    )
    res_with_ws = await db_session.execute(
        text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
    )
    assert res_with_ws.scalar_one() is True


@pytest.mark.asyncio
async def test_app_principal_has_role_sql_workspace_and_project_scoping(
    db_session: AsyncSession,
) -> None:
    """Verify WORKSPACE_ADMIN, PROJECT_ADMIN, and MEMBER bindings strictly enforce workspace_id."""
    (
        ws_id,
        _,
        ws_admin_id,
        _proj_admin_id,
        member_id,
        _viewer_id,
    ) = await _setup_workspace_and_multi_role_principals(db_session)
    other_ws_id = uuid.uuid4()

    # 1. Workspace Admin with workspace_id unset -> False
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', '', true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"p_id": str(ws_admin_id)},
    )
    res_no_ws = await db_session.execute(
        text("SELECT app_principal_has_role(NULL, ARRAY['WORKSPACE_ADMIN'])")
    )
    assert res_no_ws.scalar_one() is False

    # Workspace Admin with other workspace -> False
    await db_session.execute(
        text("SELECT set_config('app.workspace_id', :ws_id, true)"),
        {"ws_id": str(other_ws_id)},
    )
    res_other_ws = await db_session.execute(
        text("SELECT app_principal_has_role(NULL, ARRAY['WORKSPACE_ADMIN'])")
    )
    assert res_other_ws.scalar_one() is False

    # Workspace Admin with matching workspace -> True
    await db_session.execute(
        text("SELECT set_config('app.workspace_id', :ws_id, true)"),
        {"ws_id": str(ws_id)},
    )
    res_matching_ws = await db_session.execute(
        text("SELECT app_principal_has_role(NULL, ARRAY['WORKSPACE_ADMIN'])")
    )
    assert res_matching_ws.scalar_one() is True

    # Workspace Admin does NOT possess SERVER_ADMIN
    res_not_server = await db_session.execute(
        text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
    )
    assert res_not_server.scalar_one() is False

    # 2. Member does NOT possess SERVER_ADMIN or WORKSPACE_ADMIN
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :ws_id, true)"
        ),
        {"p_id": str(member_id), "ws_id": str(ws_id)},
    )
    res_member = await db_session.execute(
        text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])")
    )
    assert res_member.scalar_one() is False


@pytest.mark.asyncio
async def test_admin_auth_cards_endpoint_access_matrix(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
) -> None:
    """Verify /api/v1/admin/auth-cards authorizes SERVER_ADMIN and rejects non-server admins."""
    (
        ws_id,
        server_admin_id,
        ws_admin_id,
        proj_admin_id,
        member_id,
        viewer_id,
    ) = await _setup_workspace_and_multi_role_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    service = AuthCardAdminService(kek_provider=kek_provider)
    app = _create_test_app(factory, service, key_material, session_service)

    # Route audit
    assert assert_admin_routes_protected(app) == []

    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unauthenticated -> 401
        res_anon = await client.get("/api/v1/admin/auth-cards")
        assert res_anon.status_code == 401

        # 2. SERVER_ADMIN with AAL2 session -> 200 OK
        async with factory.session(anon_ctx) as sess:
            sess_server_admin = await session_service.create_after_login(
                sess,
                principal_id=server_admin_id,
                workspace_id=ws_id,
                aal_level=2,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_server_admin.cookie_val)
        res_admin = await client.get("/api/v1/admin/auth-cards")
        assert res_admin.status_code == 200
        data = res_admin.json()
        assert "cards" in data

        # 3. WORKSPACE_ADMIN with AAL2 session -> 403 INSUFFICIENT_CAPABILITY
        async with factory.session(anon_ctx) as sess:
            sess_ws_admin = await session_service.create_after_login(
                sess,
                principal_id=ws_admin_id,
                workspace_id=ws_id,
                aal_level=2,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_ws_admin.cookie_val)
        res_ws_admin = await client.get("/api/v1/admin/auth-cards")
        assert res_ws_admin.status_code == 403
        assert res_ws_admin.json()["code"] == "INSUFFICIENT_CAPABILITY"

        # 4. PROJECT_ADMIN with AAL2 session -> 403 INSUFFICIENT_CAPABILITY
        async with factory.session(anon_ctx) as sess:
            sess_proj = await session_service.create_after_login(
                sess,
                principal_id=proj_admin_id,
                workspace_id=ws_id,
                aal_level=2,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_proj.cookie_val)
        res_proj = await client.get("/api/v1/admin/auth-cards")
        assert res_proj.status_code == 403
        assert res_proj.json()["code"] == "INSUFFICIENT_CAPABILITY"

        # 5. MEMBER with AAL2 session -> 403 FORBIDDEN
        async with factory.session(anon_ctx) as sess:
            sess_member = await session_service.create_after_login(
                sess,
                principal_id=member_id,
                workspace_id=ws_id,
                aal_level=2,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_member.cookie_val)
        res_member = await client.get("/api/v1/admin/auth-cards")
        assert res_member.status_code == 403
        assert res_member.json()["code"] == "FORBIDDEN"

        # 6. VIEWER with AAL2 session -> 403 FORBIDDEN
        async with factory.session(anon_ctx) as sess:
            sess_viewer = await session_service.create_after_login(
                sess,
                principal_id=viewer_id,
                workspace_id=ws_id,
                aal_level=2,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_viewer.cookie_val)
        res_viewer = await client.get("/api/v1/admin/auth-cards")
        assert res_viewer.status_code == 403
        assert res_viewer.json()["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_server_admin_cross_workspace_access(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
) -> None:
    """Verify SERVER_ADMIN on workspace A active on secondary workspace B has full access."""
    (
        _ws_a,
        server_admin_id,
        ws_admin_id,
        _proj_admin_id,
        _member_id,
        _viewer_id,
    ) = await _setup_workspace_and_multi_role_principals(db_session)

    # Provision secondary workspace B
    ws_b = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_b, "slug": f"ws-{ws_b.hex[:10]}", "name": "Secondary Workspace B"},
    )

    # 1. Direct SQL check with app.workspace_id = ws_b
    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :ws_id, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"p_id": str(server_admin_id), "ws_id": str(ws_b)},
    )
    res_sql = await db_session.execute(
        text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
    )
    assert res_sql.scalar_one() is True

    # 2. API level tests: GET /api/v1/auth/me and GET /api/v1/admin/auth-cards
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    service = AuthCardAdminService(kek_provider=kek_provider)
    app = _create_test_app(factory, service, key_material, session_service)

    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create session on secondary workspace ws_b
        async with factory.session(anon_ctx) as sess:
            sess_server_admin_b = await session_service.create_after_login(
                sess,
                principal_id=server_admin_id,
                workspace_id=ws_b,
                aal_level=2,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_server_admin_b.cookie_val)

        # GET /api/v1/auth/me receives is_server_admin == True
        res_me = await client.get("/api/v1/auth/me")
        assert res_me.status_code == 200
        me_data = res_me.json()
        assert me_data["is_server_admin"] is True
        assert me_data["workspace_role"] == "SERVER_ADMIN"

        # GET /api/v1/admin/auth-cards receives 200 OK
        res_cards = await client.get("/api/v1/admin/auth-cards")
        assert res_cards.status_code == 200
        assert "cards" in res_cards.json()

        # With X-KB-Scope-Workspace header pointing to ws_b
        res_cards_scoped = await client.get(
            "/api/v1/admin/auth-cards",
            headers={"X-KB-Scope-Workspace": str(ws_b)},
        )
        assert res_cards_scoped.status_code == 200

        # WORKSPACE_ADMIN on workspace A denied on workspace B at API level
        async with factory.session(anon_ctx) as sess:
            sess_ws_admin_b = await session_service.create_after_login(
                sess,
                principal_id=ws_admin_id,
                workspace_id=ws_b,
                aal_level=2,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_ws_admin_b.cookie_val)

        res_ws_admin_me = await client.get("/api/v1/auth/me")
        assert res_ws_admin_me.status_code == 200
        assert res_ws_admin_me.json()["is_server_admin"] is False
        assert res_ws_admin_me.json()["is_workspace_admin"] is False

        res_ws_admin_cards = await client.get("/api/v1/admin/auth-cards")
        assert res_ws_admin_cards.status_code == 403


@pytest.mark.asyncio
async def test_credential_projects_boundary_blocks_server_admin(
    db_session: AsyncSession,
) -> None:
    """Verify project-scoped app.credential_projects blocks SERVER_ADMIN outside boundary."""
    (
        ws_id,
        server_admin_id,
        _ws_admin_id,
        _proj_admin_id,
        _member_id,
        _viewer_id,
    ) = await _setup_workspace_and_multi_role_principals(db_session)

    proj_allowed = uuid.uuid4()
    proj_blocked = uuid.uuid4()

    await db_session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :ws_id, true), "
            "set_config('app.credential_projects', :allowed, true)"
        ),
        {"p_id": str(server_admin_id), "ws_id": str(ws_id), "allowed": str(proj_allowed)},
    )

    # 1. Allowed project: passes
    res_allowed = await db_session.execute(
        text("SELECT app_principal_has_role(:proj_id, ARRAY['SERVER_ADMIN'])"),
        {"proj_id": proj_allowed},
    )
    assert res_allowed.scalar_one() is True

    # 2. Blocked project: outside app.credential_projects -> returns False even for SERVER_ADMIN
    res_blocked = await db_session.execute(
        text("SELECT app_principal_has_role(:proj_id, ARRAY['SERVER_ADMIN'])"),
        {"proj_id": proj_blocked},
    )
    assert res_blocked.scalar_one() is False

    # 3. Server/Global check without project (p_project_id IS NULL): passes
    res_null = await db_session.execute(
        text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
    )
    assert res_null.scalar_one() is True

