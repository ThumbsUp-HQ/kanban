# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration and unit tests for Workspaces API (KB-UX-05, S1.1, S3.3)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from starlette.requests import Request

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from database.session import RLSSessionFactory
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.api.v1.workspaces import (
    CreateWorkspaceRequest,
    create_workspace_endpoint,
    list_workspaces_endpoint,
    switch_workspace_endpoint,
)
from kanban.auth.sessions.cookies import (
    SESSION_COOKIE_NAME,
)
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    FALLBACK_CSRF_COOKIE_NAME,
    CsrfMiddleware,
)
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionService
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


async def _setup_workspace_and_principals(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Provision workspace, SERVER_ADMIN, and regular WORKSPACE_MEMBER principals."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Primary Engineering WS"},
    )

    # 1. Server Admin
    server_admin_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{server_admin_id.hex[:10]}",
            "title": "Server Admin",
            "u_id": server_admin_id,
        },
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
            "VALUES (:id, 'user', 'USER', :ws_id, 'admin@example.com')"
        ),
        {"id": server_admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": server_admin_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'WORKSPACE_ADMIN', 'workspace', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": server_admin_id},
    )
    await session.execute(
        text(
            "INSERT INTO local_admin_credentials (principal_id, username, password_hash) "
            "VALUES (:p_id, :username, '$argon2id$v=19$m=65536,t=3,p=4$fakehash$fakehash')"
        ),
        {"p_id": server_admin_id, "username": f"admin-{server_admin_id.hex[:8]}"},
    )

    # 2. Member User
    member_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{member_id.hex[:10]}",
            "title": "Member User",
            "u_id": member_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Member User', 'ACTIVE')"
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

    # Default session RLS context to server admin
    await session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"p_id": str(server_admin_id), "w_id": str(ws_id)},
    )

    return ws_id, server_admin_id, member_id


def _create_test_app(
    factory: RLSSessionFactory,
    key_material: KeyMaterial,
    session_service: SessionService,
) -> FastAPI:
    """Instantiate configured FastAPI application with test dependencies."""
    app = FastAPI()
    app.state.session_factory = factory
    app.state.session_service = session_service
    app.state.key_material = key_material

    resolver = SessionCookieResolver(
        session_service=session_service,
        session_factory=factory,
    )
    app.state.principal_resolver = resolver

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(CsrfMiddleware)
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    v1_router = build_v1_router()
    app.include_router(v1_router, prefix="/api/v1")
    return app


async def _login_and_elevate(  # noqa: PLR0913, PLR0917
    client: httpx.AsyncClient,
    session_service: SessionService,
    db_session: AsyncSession,
    principal_id: uuid.UUID,
    workspace_id: uuid.UUID,
    aal_level: int = 1,
) -> tuple[str, str]:
    """Issue authenticated session cookie and CSRF token for testing client."""
    sess = await session_service.create_after_login(
        db_session,
        principal_id=principal_id,
        workspace_id=workspace_id,
        aal_level=aal_level,
    )
    client.cookies.set(SESSION_COOKIE_NAME, sess.cookie_val)
    client.cookies.set(CSRF_COOKIE_NAME, sess.csrf_token)
    return sess.cookie_val, sess.csrf_token


@pytest.mark.asyncio
async def test_case_1_list_workspaces_server_admin_and_member(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Case 1: GET /api/v1/workspaces for SERVER_ADMIN and MEMBER."""
    ws_id, admin_id, member_id = await _setup_workspace_and_principals(db_session)

    # Create a secondary workspace
    ws2_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Secondary WS')"),
        {"id": ws2_id, "slug": f"ws-{ws2_id.hex[:10]}"},
    )

    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. As Server Admin -> sees both workspaces
        await _login_and_elevate(client, session_service, db_session, admin_id, ws_id, aal_level=2)
        resp_admin = await client.get("/api/v1/workspaces")
        assert resp_admin.status_code == 200
        admin_data = resp_admin.json()
        assert len(admin_data) >= 2
        primary_item = next(w for w in admin_data if w["id"] == str(ws_id))
        assert primary_item["is_current"] is True
        assert primary_item["role"] == "SERVER_ADMIN"

        # 2. As Regular Member -> sees only Primary WS
        client.cookies.clear()
        await _login_and_elevate(client, session_service, db_session, member_id, ws_id, aal_level=1)
        resp_member = await client.get("/api/v1/workspaces")
        assert resp_member.status_code == 200
        member_data = resp_member.json()
        member_ids = [w["id"] for w in member_data]
        assert str(ws_id) in member_ids
        assert str(ws2_id) not in member_ids


@pytest.mark.asyncio
async def test_case_2_create_workspace_and_role_bindings(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Case 2: POST /api/v1/workspaces creates workspace, settings, and binds WORKSPACE_ADMIN."""
    ws_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        _, csrf_token = await _login_and_elevate(
            client, session_service, db_session, admin_id, ws_id, aal_level=2
        )

        new_slug = f"acme-dev-{uuid.uuid4().hex[:6]}"
        resp = await client.post(
            "/api/v1/workspaces",
            json={"name": "Acme Development", "slug": new_slug},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Acme Development"
        assert data["slug"] == new_slug
        assert data["role"] == "WORKSPACE_ADMIN"

        new_ws_id = uuid.UUID(data["id"])

        # Verify auto-initialized workspace_settings exists
        settings_res = await db_session.execute(
            text(
                "SELECT display_name, air_gap_mode FROM workspace_settings WHERE workspace_id = :id"
            ),
            {"id": new_ws_id},
        )
        settings_row = settings_res.mappings().first()
        assert settings_row is not None
        assert settings_row["display_name"] == "Acme Development"
        assert settings_row["air_gap_mode"] is False

        # Conflict on duplicate slug -> 409
        resp_conflict = await client.post(
            "/api/v1/workspaces",
            json={"name": "Another Acme", "slug": new_slug},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_conflict.status_code == 409
        assert "WORKSPACE_SLUG_CONFLICT" in resp_conflict.text

        # Invalid slug pattern -> 422
        resp_invalid_slug = await client.post(
            "/api/v1/workspaces",
            json={"name": "Bad Slug", "slug": "UPPERCASE_NOT_ALLOWED!"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert resp_invalid_slug.status_code == 422


@pytest.mark.asyncio
async def test_case_3_switch_workspace_lifecycle_and_cookies(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Case 3: POST /api/v1/workspaces/{workspace_id}/switch updates session and cookies."""
    ws_id, admin_id, member_id = await _setup_workspace_and_principals(db_session)

    # Secondary workspace
    ws2_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Design WS')"),
        {"id": ws2_id, "slug": f"ws-{ws2_id.hex[:10]}"},
    )

    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Server Admin switches to ws2_id (auto-provisions membership)
        _, admin_csrf = await _login_and_elevate(
            client, session_service, db_session, admin_id, ws_id, aal_level=2
        )

        resp_switch = await client.post(
            f"/api/v1/workspaces/{ws2_id}/switch",
            headers={CSRF_HEADER_NAME: admin_csrf},
        )
        assert resp_switch.status_code == 200
        switch_data = resp_switch.json()
        assert switch_data["workspace_id"] == str(ws2_id)
        assert switch_data["status"] == "switched"
        assert "set-cookie" in resp_switch.headers

        # Update client cookies from response for next request
        session_cookie = resp_switch.cookies.get(SESSION_COOKIE_NAME)
        csrf_cookie = resp_switch.cookies.get(CSRF_COOKIE_NAME)
        if session_cookie:
            client.cookies.set(SESSION_COOKIE_NAME, session_cookie)
        if csrf_cookie:
            client.cookies.set(CSRF_COOKIE_NAME, csrf_cookie)

        # Verify session endpoint now reports ws2_id as active workspace
        resp_session = await client.get("/api/v1/auth/session")
        assert resp_session.status_code == 200
        assert resp_session.json()["workspace_id"] == str(ws2_id)

        # 2. Non-existent workspace -> 404
        nonexistent_ws = uuid.uuid4()
        resp_404 = await client.post(
            f"/api/v1/workspaces/{nonexistent_ws}/switch",
            headers={CSRF_HEADER_NAME: switch_data["csrf_token"]},
        )
        assert resp_404.status_code == 404
        assert "WORKSPACE_NOT_FOUND" in resp_404.text

        # 3. Regular member without membership in ws2_id tries to switch -> 403
        client.cookies.clear()
        _, member_csrf = await _login_and_elevate(
            client, session_service, db_session, member_id, ws_id, aal_level=1
        )
        resp_forbidden = await client.post(
            f"/api/v1/workspaces/{ws2_id}/switch",
            headers={CSRF_HEADER_NAME: member_csrf},
        )
        assert resp_forbidden.status_code == 403
        assert "FORBIDDEN_WORKSPACE_SWITCH" in resp_forbidden.text


@pytest.mark.asyncio
async def test_case_4_member_cross_workspace_matching_email_and_switching(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Case 4: Member with matching email in secondary workspace can list and switch."""
    ws_id, _, member_id = await _setup_workspace_and_principals(db_session)

    # Secondary workspace where member ALSO exists with same email
    ws2_id = uuid.uuid4()
    ws2_member_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Shared Dev WS')"),
        {"id": ws2_id, "slug": f"ws-{ws2_id.hex[:10]}"},
    )
    await db_session.execute(
        text(
            "SELECT register_object("
            "  'user'::object_kind, :ws_id, NULL, :ckey, 'Member In WS2', :u_id, :u_id"
            ")"
        ),
        {"ws_id": ws2_id, "ckey": f"usr-{ws2_member_id.hex[:10]}", "u_id": ws2_member_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Member User', 'ACTIVE')"
        ),
        {"id": ws2_member_id, "ws_id": ws2_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'member@example.com')"
        ),
        {"id": ws2_member_id, "ws_id": ws2_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'WORKSPACE_MEMBER', 'workspace', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws2_id, "p_id": ws2_member_id},
    )

    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        _, member_csrf = await _login_and_elevate(
            client, session_service, db_session, member_id, ws_id, aal_level=1
        )

        # 1. Listing workspaces shows both workspaces
        resp_list = await client.get("/api/v1/workspaces")
        assert resp_list.status_code == 200
        items = resp_list.json()
        ids = [i["id"] for i in items]
        assert str(ws_id) in ids
        assert str(ws2_id) in ids

        # 2. Member switches to ws2_id successfully via email resolution
        resp_switch = await client.post(
            f"/api/v1/workspaces/{ws2_id}/switch",
            headers={CSRF_HEADER_NAME: member_csrf},
        )
        assert resp_switch.status_code == 200
        assert resp_switch.json()["workspace_id"] == str(ws2_id)


@pytest.mark.asyncio
async def test_case_5_workspace_edge_cases_and_error_branches(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Case 5: Missing session factory, validation errors, and direct principal membership."""
    ws_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        _, admin_csrf = await _login_and_elevate(
            client, session_service, db_session, admin_id, ws_id, aal_level=2
        )

        # 1. Validation error: empty name -> 422
        resp_bad_name = await client.post(
            "/api/v1/workspaces",
            json={"name": "   ", "slug": "valid-slug"},
            headers={CSRF_HEADER_NAME: admin_csrf},
        )
        assert resp_bad_name.status_code == 422

        # 2. Server admin switching to target workspace (auto-provisions principal/binding)
        ws_direct = uuid.uuid4()
        await db_session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Direct WS')"),
            {"id": ws_direct, "slug": f"ws-{ws_direct.hex[:10]}"},
        )

        # Switch without session_service in app state
        app.state.session_service = None
        resp_no_svc = await client.post(
            f"/api/v1/workspaces/{ws_direct}/switch",
            headers={CSRF_HEADER_NAME: admin_csrf},
        )
        assert resp_no_svc.status_code == 200
        assert resp_no_svc.json()["status"] == "switched"
        app.state.session_service = session_service

        # 3. Validation error: invalid slug -> 422
        resp_bad_slug = await client.post(
            "/api/v1/workspaces",
            json={"name": "Bad Slug WS", "slug": "Invalid Slug!"},
            headers={CSRF_HEADER_NAME: admin_csrf},
        )
        assert resp_bad_slug.status_code == 422

        # 4. Duplicate slug creation -> 409
        resp_first_create = await client.post(
            "/api/v1/workspaces",
            json={"name": "Unique One", "slug": "unique-slug"},
            headers={CSRF_HEADER_NAME: admin_csrf},
        )
        assert resp_first_create.status_code == 201

        resp_dup = await client.post(
            "/api/v1/workspaces",
            json={"name": "Unique Two", "slug": "unique-slug"},
            headers={CSRF_HEADER_NAME: admin_csrf},
        )
        assert resp_dup.status_code == 409

        # 5. Non-existent workspace switch -> 404
        non_existent_ws = uuid.uuid4()
        resp_not_found = await client.post(
            f"/api/v1/workspaces/{non_existent_ws}/switch",
            headers={CSRF_HEADER_NAME: admin_csrf},
        )
        assert resp_not_found.status_code == 404

        # 6. Forbidden switch: regular member without access to private workspace -> 403
        _, _, member_id = await _setup_workspace_and_principals(db_session)
        client.cookies.clear()
        _, member_csrf = await _login_and_elevate(
            client, session_service, db_session, member_id, ws_id, aal_level=1
        )
        resp_forbidden = await client.post(
            f"/api/v1/workspaces/{ws_direct}/switch",
            headers={CSRF_HEADER_NAME: member_csrf},
        )
        assert resp_forbidden.status_code == 403


@pytest.mark.asyncio
async def test_case_6_coverage_direct_switch_and_fallback_cookies(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Case 6: Direct switch, localhost fallback cookies, and no-email list."""
    ws_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    # Using base_url="http://localhost" hits fallback cookies branches
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        _, admin_csrf = await _login_and_elevate(
            client, session_service, db_session, admin_id, ws_id, aal_level=2
        )

        # 1. Switch to current workspace -> hits direct_p branch and fallback cookies
        resp_switch = await client.post(
            f"/api/v1/workspaces/{ws_id}/switch",
            headers={CSRF_HEADER_NAME: admin_csrf, "Host": "localhost"},
        )
        assert resp_switch.status_code == 200
        assert resp_switch.json()["workspace_id"] == str(ws_id)
        assert "set-cookie" in resp_switch.headers

        # 2. Principal without email in users table
        no_email_pid = uuid.uuid4()
        await db_session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'AGENT', :ws_id, 'Agent Principal', 'ACTIVE')"
            ),
            {"id": no_email_pid, "ws_id": ws_id},
        )
        client.cookies.clear()
        _, agent_csrf = await _login_and_elevate(
            client, session_service, db_session, no_email_pid, ws_id, aal_level=1
        )
        resp_list_no_email = await client.get("/api/v1/workspaces")
        assert resp_list_no_email.status_code == 200
        items = resp_list_no_email.json()
        assert len(items) == 1
        assert items[0]["id"] == str(ws_id)

        # 3. Agent principal tries to switch to non-owned workspace without email
        ws_other = uuid.uuid4()
        await db_session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Other WS')"),
            {"id": ws_other, "slug": f"ws-{ws_other.hex[:10]}"},
        )
        resp_switch_no_email = await client.post(
            f"/api/v1/workspaces/{ws_other}/switch",
            headers={CSRF_HEADER_NAME: agent_csrf},
        )
        assert resp_switch_no_email.status_code == 403


@pytest.mark.asyncio
async def test_case_7_unit_coverage_direct_invocations(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Case 7: Direct endpoint invocations for fallback and error branches."""
    ws_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    caller = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        aal_level=2,
    )

    # 1. list_workspaces_endpoint fallback when session_factory is None
    req = Request(scope={"type": "http", "app": app, "path": "/api/v1/workspaces", "headers": []})
    app.state.session_factory = None
    fallback_res = await list_workspaces_endpoint(caller=caller, session=db_session, request=req)
    assert len(fallback_res) == 1
    assert fallback_res[0].id == ws_id

    # 2. create_workspace_endpoint raises ProblemException when session_factory is None
    with pytest.raises(ProblemException) as exc_info:
        await create_workspace_endpoint(
            body=CreateWorkspaceRequest(name="No Fac", slug="no-fac"),
            caller=caller,
            session=db_session,
            request=req,
        )
    assert exc_info.value.code == "INTERNAL_ERROR"

    # Restore session factory
    app.state.session_factory = factory

    # 3. Create workspace with principal not in users table (e.g. AGENT principal)
    agent_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'AGENT', :ws_id, 'Agent Maker', 'ACTIVE')"
        ),
        {"id": agent_id, "ws_id": ws_id},
    )
    agent_caller = PrincipalContext(
        principal_id=agent_id,
        workspace_id=ws_id,
        aal_level=1,
    )
    req_valid = Request(scope={"type": "http", "app": app, "headers": []})
    created = await create_workspace_endpoint(
        body=CreateWorkspaceRequest(name="Agent WS", slug=f"agent-{uuid.uuid4().hex[:8]}"),
        caller=agent_caller,
        session=db_session,
        request=req_valid,
    )
    assert created.name == "Agent WS"


@pytest.mark.asyncio
async def test_case_8_workspaces_under_kanban_app_force_rls(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Case 8: Ensure workspaces endpoints succeed under kanban_app role with FORCE RLS."""
    ws_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    issued_session = await session_service.create_after_login(
        db_session,
        principal_id=admin_id,
        workspace_id=ws_id,
        aal_level=2,
    )

    caller = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        aal_level=2,
        session_id=issued_session.session_id,
    )

    # Drop privileges to kanban_app
    await db_session.execute(text("SET LOCAL ROLE kanban_app"))

    cookie_hdr = f"{SESSION_COOKIE_NAME}={issued_session.cookie_val}".encode("latin-1")
    req = Request(
        scope={
            "type": "http",
            "app": app,
            "path": "/api/v1/workspaces",
            "headers": [(b"cookie", cookie_hdr)],
        }
    )
    req.state.session_id = issued_session.session_id

    # 1. List workspaces under kanban_app
    ws_list = await list_workspaces_endpoint(caller=caller, session=db_session, request=req)
    assert len(ws_list) >= 1
    assert any(w.id == ws_id for w in ws_list)

    # 2. Create workspace under kanban_app
    new_slug = f"ws-rls-{uuid.uuid4().hex[:8]}"
    created = await create_workspace_endpoint(
        body=CreateWorkspaceRequest(name="RLS App WS", slug=new_slug),
        caller=caller,
        session=db_session,
        request=req,
    )
    assert created.slug == new_slug
    assert created.role == "WORKSPACE_ADMIN"

    # 3. Switch workspace under kanban_app
    switched_resp = await switch_workspace_endpoint(
        workspace_id=created.id,
        caller=caller,
        session=db_session,
        request=req,
    )
    assert switched_resp.status_code == 200

    # 4. Direct update_workspace_endpoint coverage
    from kanban.api.v1.workspaces import (  # noqa: PLC0415
        UpdateWorkspaceRequest,
        WorkspaceRoleBindingRequest,
        bind_workspace_role_endpoint,
        unbind_workspace_role_endpoint,
        update_workspace_endpoint,
    )

    valid_new_slug = f"ws-rls-{uuid.uuid4().hex[:8]}"
    patched = await update_workspace_endpoint(
        workspace_id=ws_id,
        body=UpdateWorkspaceRequest(name="Updated RLS Name", slug=valid_new_slug),
        caller=caller,
        session=db_session,
    )
    assert patched.name == "Updated RLS Name"
    assert patched.slug == valid_new_slug

    # Validation errors on update_workspace_endpoint
    with pytest.raises(ProblemException) as exc_slug:
        await update_workspace_endpoint(
            workspace_id=ws_id,
            body=UpdateWorkspaceRequest(slug="Invalid Slug!"),
            caller=caller,
            session=db_session,
        )
    assert exc_slug.value.code == "VALIDATION_FAILED"

    # 5. Direct bind and unbind role endpoints
    rb_req = WorkspaceRoleBindingRequest(principal_id=caller.principal_id, role="WORKSPACE_ADMIN")
    bound = await bind_workspace_role_endpoint(
        workspace_id=ws_id,
        body=rb_req,
        caller=caller,
        session=db_session,
    )
    assert bound is not None

    unbound = await unbind_workspace_role_endpoint(
        workspace_id=ws_id,
        body=rb_req,
        caller=caller,
        session=db_session,
    )
    assert unbound is not None

    # WorkspaceRoleBindingRequest validation (empty role -> 422)
    with pytest.raises(ProblemException) as exc_rb:
        WorkspaceRoleBindingRequest(principal_id=caller.principal_id)
    assert exc_rb.value.code == "VALIDATION_FAILED"

    # WorkspaceRoleBindingRequest validation (empty role -> 422)
    with pytest.raises(ProblemException) as exc_rb:
        WorkspaceRoleBindingRequest(principal_id=caller.principal_id)
    assert exc_rb.value.code == "VALIDATION_FAILED"

    await db_session.execute(text("RESET ROLE"))


@pytest.mark.asyncio
async def test_case_9_multi_workspace_switch_roundtrip_project_creation(  # noqa: PLR0915
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Case 9: Multi-workspace switch roundtrip and project creation with stale CSRF."""
    ws_id, admin_id, member_id = await _setup_workspace_and_principals(db_session)
    await db_session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'WORKSPACE_ADMIN', 'workspace', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": member_id},
    )
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    app = _create_test_app(factory, key_material, session_service)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Member in default workspace creates project (WORKSPACE_MEMBER RBAC fix)
        _, member_csrf = await _login_and_elevate(
            client, session_service, db_session, member_id, ws_id, aal_level=1
        )
        client.cookies.set(FALLBACK_CSRF_COOKIE_NAME, "stale_fallback_csrf_val")

        resp_mem_proj = await client.post(
            "/api/v1/projects",
            json={"identifier": "MEMPRJ", "name": "Member Project"},
            headers={CSRF_HEADER_NAME: member_csrf},
        )
        assert resp_mem_proj.status_code == 201, resp_mem_proj.text
        assert resp_mem_proj.json()["identifier"] == "MEMPRJ"

        # 2. Server admin creates project in default workspace
        client.cookies.clear()
        _, admin_csrf = await _login_and_elevate(
            client, session_service, db_session, admin_id, ws_id, aal_level=2
        )
        client.cookies.set(FALLBACK_CSRF_COOKIE_NAME, "stale_fallback_csrf_val")

        resp_proj1 = await client.post(
            "/api/v1/projects",
            json={"identifier": "DEFPRJ", "name": "Default Project"},
            headers={CSRF_HEADER_NAME: admin_csrf},
        )
        assert resp_proj1.status_code == 201, resp_proj1.text
        assert resp_proj1.json()["identifier"] == "DEFPRJ"

        # 3. Create second workspace B
        ws_b_slug = f"ws-b-{uuid.uuid4().hex[:8]}"
        resp_ws_b = await client.post(
            "/api/v1/workspaces",
            json={"name": "Workspace Beta", "slug": ws_b_slug},
            headers={CSRF_HEADER_NAME: admin_csrf},
        )
        assert resp_ws_b.status_code == 201, resp_ws_b.text
        ws_b_data = resp_ws_b.json()
        ws_b_id = uuid.UUID(ws_b_data["id"])

        # 4. Switch to B
        resp_switch_b = await client.post(
            f"/api/v1/workspaces/{ws_b_id}/switch",
            headers={CSRF_HEADER_NAME: admin_csrf},
        )
        assert resp_switch_b.status_code == 200, resp_switch_b.text
        switch_b_data = resp_switch_b.json()
        assert switch_b_data["workspace_id"] == str(ws_b_id)
        csrf_b = switch_b_data["csrf_token"]

        # Update client session and csrf cookies cleanly (preventing duplicate cookie ambiguity)
        sess_cookie_b = resp_switch_b.cookies.get(SESSION_COOKIE_NAME)
        csrf_cookie_b = resp_switch_b.cookies.get(CSRF_COOKIE_NAME)
        client.cookies.delete(SESSION_COOKIE_NAME)
        client.cookies.delete(CSRF_COOKIE_NAME)
        if sess_cookie_b:
            client.cookies.set(SESSION_COOKIE_NAME, sess_cookie_b)
        if csrf_cookie_b:
            client.cookies.set(CSRF_COOKIE_NAME, csrf_cookie_b)

        # Inject stale fallback CSRF cookie to verify precedence over stale cookie
        client.cookies.set(FALLBACK_CSRF_COOKIE_NAME, "stale_csrf_cookie_in_b")

        # 5. Create project in B
        resp_proj_b = await client.post(
            "/api/v1/projects",
            json={"identifier": "BETAPRJ", "name": "Beta Project"},
            headers={CSRF_HEADER_NAME: csrf_b},
        )
        assert resp_proj_b.status_code == 201, resp_proj_b.text
        assert resp_proj_b.json()["identifier"] == "BETAPRJ"

        # 6. Switch back to default workspace A
        resp_switch_a = await client.post(
            f"/api/v1/workspaces/{ws_id}/switch",
            headers={CSRF_HEADER_NAME: csrf_b},
        )
        assert resp_switch_a.status_code == 200, resp_switch_a.text
        switch_a_data = resp_switch_a.json()
        assert switch_a_data["workspace_id"] == str(ws_id)
        csrf_a2 = switch_a_data["csrf_token"]

        sess_cookie_a = resp_switch_a.cookies.get(SESSION_COOKIE_NAME)
        csrf_cookie_a = resp_switch_a.cookies.get(CSRF_COOKIE_NAME)
        client.cookies.delete(SESSION_COOKIE_NAME)
        client.cookies.delete(CSRF_COOKIE_NAME)
        if sess_cookie_a:
            client.cookies.set(SESSION_COOKIE_NAME, sess_cookie_a)
        if csrf_cookie_a:
            client.cookies.set(CSRF_COOKIE_NAME, csrf_cookie_a)

        client.cookies.set(FALLBACK_CSRF_COOKIE_NAME, "stale_csrf_cookie_in_a")

        # 7. Create another project in A
        resp_proj_a2 = await client.post(
            "/api/v1/projects",
            json={"identifier": "ALPHAP2", "name": "Alpha Project Two"},
            headers={CSRF_HEADER_NAME: csrf_a2},
        )
        assert resp_proj_a2.status_code == 201, resp_proj_a2.text
        assert resp_proj_a2.json()["identifier"] == "ALPHAP2"

        # 8. Verify listing in A contains A's projects but not B's
        resp_list_a = await client.get("/api/v1/projects")
        assert resp_list_a.status_code == 200
        items_a = [p["identifier"] for p in resp_list_a.json()["items"]]
        assert "DEFPRJ" in items_a
        assert "MEMPRJ" in items_a
        assert "ALPHAP2" in items_a
        assert "BETAPRJ" not in items_a
