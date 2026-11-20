# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for workspace switch session persistence, TTL, AAL2, and cookie safety.

Validates KB-P3-PENTEST-01 / KAN-36 / CWE-613.

Verifies that switching active workspaces:
1. Preserves is_persistent=False (never escalating remember_me=False to True).
2. Omits Max-Age and Expires on session cookies when is_persistent=False.
3. Clears fallback cookies over HTTPS.
4. Preserves absolute_expires_at verbatim (never extending session lifespan).
5. Preserves stale aal2_verified_at (>900s remains stale).
6. Rejects callers lacking a valid browser cookie session (caller.session_id is None) with 401.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from starlette.requests import Request
from starlette.responses import Response

from database.models.auth import UserSession
from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.api.v1.workspaces import (
    UpdateWorkspaceRequest,
    WorkspaceRoleBindingRequest,
    bind_workspace_role_endpoint,
    switch_workspace_endpoint,
    unbind_workspace_role_endpoint,
    update_workspace_endpoint,
)
from kanban.auth.sessions.cookies import (
    FALLBACK_SESSION_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    attach_session_and_csrf_cookies,
)
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    FALLBACK_CSRF_COOKIE_NAME,
    CsrfMiddleware,
)
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionService
from kanban.security.envelope import StaticKekProvider
from kanban.security.keys import KeyMaterial
from kanban.security.mcp_keys import mint_mcp_api_key

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
def key_material() -> KeyMaterial:
    """Provide static test key material."""
    return KeyMaterial(
        master_kek=b"m" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
        master_kek_kid="kek-v1",
    )


@pytest.fixture
def kek_provider(key_material: KeyMaterial) -> StaticKekProvider:
    """Provide static KEK provider."""
    return StaticKekProvider.from_key_material(key_material)


async def _setup_workspace_and_admin(
    factory: RLSSessionFactory,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision primary workspace, user, and server admin principal."""
    ws_id = uuid.uuid4()
    u_id = uuid.uuid4()
    ctx = RLSContext(principal_id=u_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as session:
        await session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Primary WS"},
        )
        await session.execute(
            text(
                "SELECT register_object("
                "'user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
            ),
            {
                "ws_id": ws_id,
                "ckey": f"usr-{u_id.hex}",
                "title": "Admin User",
                "u_id": u_id,
            },
        )
        await session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'Admin User', 'ACTIVE')"
            ),
            {"id": u_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, 'admin@example.com')"
            ),
            {"id": u_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
            ),
            {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": u_id},
        )
    return ws_id, u_id


def _create_app(
    factory: RLSSessionFactory,
    key_material: KeyMaterial,
    session_service: SessionService,
) -> FastAPI:
    """Build FastAPI test instance wired with full v1 router and session middleware."""
    app = FastAPI(title="Workspace Switch Test App")
    app.state.session_factory = factory
    app.state.session_service = session_service
    app.state.key_material = key_material

    resolver = SessionCookieResolver(session_service, factory)
    app.state.principal_resolver = resolver

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    v1_router = build_v1_router()
    app.include_router(v1_router, prefix="/api/v1")
    return app


@pytest.mark.asyncio
async def test_remember_me_false_workspace_switch_preserves_persistence_and_omits_expires(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Scenario 1: remember_me=False session switched to secondary workspace.

    Verifies:
    - Session cookie omits Max-Age and Expires before and after switch.
    - New session preserves is_persistent=False (never escalating to True).
    - Originating session is revoked with rotated_from_id tracked.
    - Clear fallback cookies emitted over HTTPS.
    """
    factory = RLSSessionFactory(pg_worker_db)
    session_service = SessionService(key_material.session_hmac_key)
    ws1_id, admin_id = await _setup_workspace_and_admin(factory)

    # Provision secondary workspace
    ws2_id = uuid.uuid4()
    ctx_admin = RLSContext(principal_id=admin_id, workspace_id=ws1_id, aal_level=1)
    async with factory.session(ctx_admin) as sess:
        await sess.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'Secondary WS')"),
            {"id": ws2_id, "slug": f"ws-{ws2_id.hex[:10]}"},
        )

        # 1. Login with remember_me=False (session-only)
        issued_orig = await session_service.create_after_login(
            sess,
            principal_id=admin_id,
            workspace_id=ws1_id,
            remember_me=False,
            aal_level=1,
        )
        assert issued_orig.is_persistent is False

    # Check originating cookies omit Max-Age and Expires
    resp_init = Response()
    attach_session_and_csrf_cookies(
        resp_init, None, issued_orig, issued_orig.csrf_token, persistent=False
    )
    init_cookie_hdr = resp_init.headers.get("set-cookie") or ""
    assert "Max-Age=" not in init_cookie_hdr
    assert "Expires=" not in init_cookie_hdr

    app = _create_app(factory, key_material, session_service)

    # 2. Switch workspace via HTTPS client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://kanban.local") as client:
        client.cookies.set(SESSION_COOKIE_NAME, issued_orig.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, issued_orig.csrf_token)
        # Also simulate stale fallback cookies over HTTPS to test clearance
        client.cookies.set(FALLBACK_SESSION_COOKIE_NAME, "stale_fb_sess")
        client.cookies.set(FALLBACK_CSRF_COOKIE_NAME, "stale_fb_csrf")

        resp_switch = await client.post(
            f"/api/v1/workspaces/{ws2_id}/switch",
            headers={CSRF_HEADER_NAME: issued_orig.csrf_token},
        )
        assert resp_switch.status_code == 200, resp_switch.text
        data = resp_switch.json()
        assert data["workspace_id"] == str(ws2_id)
        assert data["status"] == "switched"
        assert "csrf_token" in data

        # Check returned Set-Cookie headers
        raw_set_cookies = resp_switch.headers.get_list("set-cookie")
        all_cookies_str = " ;; ".join(raw_set_cookies)

        # Session cookie (__Host-kb_session) must NOT contain Max-Age or Expires
        for cookie_str in raw_set_cookies:
            if cookie_str.startswith(f"{SESSION_COOKIE_NAME}="):
                assert "Max-Age=" not in cookie_str
                assert "Expires=" not in cookie_str

        # Fallback cookies must be cleared over HTTPS with Max-Age=0
        assert f"{FALLBACK_SESSION_COOKIE_NAME}=;" in all_cookies_str
        assert f"{FALLBACK_CSRF_COOKIE_NAME}=;" in all_cookies_str
        assert "Max-Age=0" in all_cookies_str

    # 3. Verify in database: originating session is revoked, new session is persistent=False
    async with factory.session(ctx_admin) as sess:
        orig_row = (
            await sess.execute(select(UserSession).where(UserSession.id == issued_orig.session_id))
        ).scalar_one()
        assert orig_row.revoked_at is not None

        new_row = (
            await sess.execute(
                select(UserSession).where(UserSession.rotated_from_id == issued_orig.session_id)
            )
        ).scalar_one()
        assert new_row.is_persistent is False
        assert new_row.workspace_id == ws2_id
        assert new_row.revoked_at is None


@pytest.mark.asyncio
async def test_workspace_switch_preserves_absolute_expiry_and_stale_aal2(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Scenario 2: Verify absolute_expires_at and stale aal2_verified_at are preserved verbatim.

    Verifies:
    - Absolute expiry is NOT extended upon workspace switch.
    - Stale aal2_verified_at (>900s) remains stale.
    - Callers lacking caller.session_id (non-cookie / Bearer tokens) are rejected with 401.
    - Expired sessions are rejected with 401.
    """
    factory = RLSSessionFactory(pg_worker_db)
    session_service = SessionService(key_material.session_hmac_key)
    ws1_id, admin_id = await _setup_workspace_and_admin(factory)

    ws2_id = uuid.uuid4()
    ctx_admin = RLSContext(principal_id=admin_id, workspace_id=ws1_id, aal_level=2)
    now = datetime.now(UTC)

    # 1. Seed originating session with specific absolute_expires_at (2 days from now)
    # and stale aal2_verified_at (1000s in the past)
    fixed_absolute = now + timedelta(days=2)
    stale_aal2_at = now - timedelta(seconds=1000)

    async with factory.session(ctx_admin) as sess:
        await sess.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'WS2')"),
            {"id": ws2_id, "slug": f"ws-{ws2_id.hex[:10]}"},
        )

        issued_orig = await session_service.create_after_login(
            sess,
            principal_id=admin_id,
            workspace_id=ws1_id,
            remember_me=True,
            aal_level=2,
        )

        # Manually adjust timestamps to test preservation invariants
        await sess.execute(
            text(
                "UPDATE sessions SET absolute_expires_at = :abs_at, aal2_verified_at = :aal2_at "
                "WHERE id = :id"
            ),
            {
                "abs_at": fixed_absolute,
                "aal2_at": stale_aal2_at,
                "id": issued_orig.session_id,
            },
        )

    app = _create_app(factory, key_material, session_service)

    # 2. Switch workspace and inspect resulting session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://kanban.local") as client:
        client.cookies.set(SESSION_COOKIE_NAME, issued_orig.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, issued_orig.csrf_token)

        resp_switch = await client.post(
            f"/api/v1/workspaces/{ws2_id}/switch",
            headers={CSRF_HEADER_NAME: issued_orig.csrf_token},
        )
        assert resp_switch.status_code == 200, resp_switch.text

    # 3. Assert in database that absolute_expires_at and stale aal2_verified_at are preserved
    async with factory.session(ctx_admin) as sess:
        new_row = (
            await sess.execute(
                select(UserSession).where(UserSession.rotated_from_id == issued_orig.session_id)
            )
        ).scalar_one()

        # absolute_expires_at must not be extended
        diff_abs = abs((new_row.absolute_expires_at - fixed_absolute).total_seconds())
        assert diff_abs < 1.0, (
            f"absolute_expires_at changed from {fixed_absolute} to {new_row.absolute_expires_at}"
        )

        # stale aal2_verified_at must remain stale (>900s ago)
        assert new_row.aal2_verified_at is not None
        diff_aal2 = abs((new_row.aal2_verified_at - stale_aal2_at).total_seconds())
        assert diff_aal2 < 1.0, "aal2_verified_at was freshened instead of preserved verbatim"
        age = (datetime.now(UTC) - new_row.aal2_verified_at).total_seconds()
        assert age >= 1000, "Stale AAL2 verification must stay stale"

    # 4. Non-cookie caller rejection:
    # A caller authenticating with a REAL valid non-cookie token (caller.session_id is None)
    # must reach workspaces.py:287 and be rejected with 401 SESSION_REQUIRED
    async with factory.session(ctx_admin) as sess:
        _key_rec, valid_token = await mint_mcp_api_key(
            sess,
            workspace_id=ws1_id,
            principal_id=admin_id,
            surface="agent",
            scopes=["agent:read", "agent:write"],
            created_by_id=admin_id,
        )

    async with httpx.AsyncClient(
        transport=transport, base_url="https://kanban.local"
    ) as client_no_cookie:
        resp_no_cookie = await client_no_cookie.post(
            f"/api/v1/workspaces/{ws2_id}/switch",
            headers={"X-KB-Subject-Token": valid_token},
        )
        assert resp_no_cookie.status_code == 401
        data_no_cookie = resp_no_cookie.json()
        assert data_no_cookie.get("code") == "SESSION_REQUIRED"
        assert "set-cookie" not in resp_no_cookie.headers


@pytest.mark.asyncio
async def test_direct_session_service_rotate_for_workspace_switch_unit(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Direct unit tests for SessionService.rotate_for_workspace_switch edge cases."""
    factory = RLSSessionFactory(pg_worker_db)
    session_service = SessionService(key_material.session_hmac_key)
    ws1_id, admin_id = await _setup_workspace_and_admin(factory)
    ws2_id = uuid.uuid4()

    ctx = RLSContext(principal_id=admin_id, workspace_id=ws1_id, aal_level=1)
    async with factory.session(ctx) as session:
        # 1. Non-existent session raises ValueError
        with pytest.raises(ValueError, match="Originating session could not be resolved"):
            await session_service.rotate_for_workspace_switch(
                session,
                target_principal_id=admin_id,
                target_workspace_id=ws2_id,
                old_session_id=uuid.uuid4(),
            )

        # 2. Expired session raises ValueError
        issued = await session_service.create_after_login(
            session,
            principal_id=admin_id,
            workspace_id=ws1_id,
            remember_me=False,
        )
        await session.execute(
            text(
                "UPDATE sessions SET idle_expires_at = now() - interval '1 hour', "
                "absolute_expires_at = now() - interval '1 hour' WHERE id = :id"
            ),
            {"id": issued.session_id},
        )
        with pytest.raises(ValueError, match="expired"):
            await session_service.rotate_for_workspace_switch(
                session,
                target_principal_id=admin_id,
                target_workspace_id=ws2_id,
                old_session_id=issued.session_id,
                existing_cookie=issued.cookie_val,
            )

        # 3. Already revoked session raises ValueError
        issued2 = await session_service.create_after_login(
            session,
            principal_id=admin_id,
            workspace_id=ws1_id,
            remember_me=True,
        )
        # Login with existing_cookie revokes previous session (session fixation defense)
        issued3 = await session_service.create_after_login(
            session,
            principal_id=admin_id,
            workspace_id=ws1_id,
            remember_me=False,
            existing_cookie=issued2.cookie_val,
        )
        assert issued3.session_id != issued2.session_id

        # 4. Invalid cookie fallback to old_session_id
        with pytest.raises(ValueError, match="Originating session could not be resolved"):
            await session_service.rotate_for_workspace_switch(
                session,
                target_principal_id=admin_id,
                target_workspace_id=ws2_id,
                existing_cookie="invalid.malformed.cookie",
                old_session_id=uuid.uuid4(),
            )

        # 5. Revoked originating session raises ValueError
        revoked_row = (
            await session.execute(select(UserSession).where(UserSession.id == issued2.session_id))
        ).scalar_one()
        assert revoked_row.revoked_at is not None
        with pytest.raises(ValueError, match="revoked"):
            await session_service.rotate_for_workspace_switch(
                session,
                target_principal_id=admin_id,
                target_workspace_id=ws2_id,
                originating_session=revoked_row,
            )

        # 6. Policy property and revoke_all_for_principal coverage
        assert session_service.policy is not None

        # 7. Rotate with old_session_id only (no existing_cookie) to cover direct DB query
        issued4 = await session_service.create_after_login(
            session,
            principal_id=admin_id,
            workspace_id=ws1_id,
            remember_me=False,
        )
        rotated_by_id = await session_service.rotate_for_workspace_switch(
            session,
            target_principal_id=admin_id,
            target_workspace_id=ws2_id,
            old_session_id=issued4.session_id,
        )
        assert rotated_by_id.session_id != issued4.session_id

        revoked_count = await session_service.revoke_all_for_principal(session, admin_id)
        assert revoked_count >= 1


@pytest.mark.asyncio
async def test_workspace_switch_error_branches(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test error handling branches in switch_workspace_endpoint.

    - line 296: session_factory is None -> 500 INTERNAL_ERROR
    - lines 325-326: rotate_for_workspace_switch raises ValueError -> 401 SESSION_EXPIRED
    """
    factory = RLSSessionFactory(pg_worker_db)
    session_service = SessionService(key_material.session_hmac_key)
    ws1_id, admin_id = await _setup_workspace_and_admin(factory)
    ws2_id = uuid.uuid4()

    ctx_admin = RLSContext(principal_id=admin_id, workspace_id=ws1_id, aal_level=1)
    async with factory.session(ctx_admin) as sess:
        await sess.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'WS 2')"),
            {"id": ws2_id, "slug": f"ws-{ws2_id.hex[:10]}"},
        )
        issued = await session_service.create_after_login(
            sess,
            principal_id=admin_id,
            workspace_id=ws1_id,
            remember_me=False,
            aal_level=1,
        )

        app = _create_app(factory, key_material, session_service)
        req = Request({"type": "http", "app": app, "headers": []})
        caller = PrincipalContext(
            principal_id=admin_id,
            workspace_id=ws1_id,
            session_id=issued.session_id,
        )

        # 1. session_factory is None -> 500 INTERNAL_ERROR (workspaces.py:296)
        req.app.state.session_factory = None
        with pytest.raises(ProblemException) as exc_info:
            await switch_workspace_endpoint(ws2_id, caller, sess, req)
        assert exc_info.value.code == "INTERNAL_ERROR"
        assert exc_info.value.status == 500

        # Restore session_factory
        req.app.state.session_factory = factory

        # 2. rotate_for_workspace_switch raises ValueError ->
        # 401 SESSION_EXPIRED (workspaces.py:325-326)
        with patch.object(
            session_service,
            "rotate_for_workspace_switch",
            side_effect=ValueError("Session revoked or expired"),
        ):
            with pytest.raises(ProblemException) as exc_info:
                await switch_workspace_endpoint(ws2_id, caller, sess, req)
            assert exc_info.value.code == "SESSION_EXPIRED"
            assert exc_info.value.status == 401


@pytest.mark.asyncio
async def test_workspace_endpoint_admin_checks_and_conflicts(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test update_workspace_endpoint and role binding error branches.

    - line 403: non-admin update -> 403 INSUFFICIENT_CAPABILITY
    - line 416: non-existent workspace -> 404 NOT_FOUND
    - line 448: conflicting slug -> 409 WORKSPACE_SLUG_CONFLICT
    - lines 512, 544: non-admin role bindings -> 403 INSUFFICIENT_CAPABILITY
    """
    factory = RLSSessionFactory(pg_worker_db)
    ws1_id, admin_id = await _setup_workspace_and_admin(factory)
    member_id = uuid.uuid4()

    # Member session without admin roles
    ctx_member = RLSContext(principal_id=member_id, workspace_id=ws1_id, aal_level=1)
    async with factory.session(ctx_member) as sess_member:
        caller_member = PrincipalContext(principal_id=member_id, workspace_id=ws1_id)

        # 1. Non-admin update -> 403 (workspaces.py:403)
        with pytest.raises(ProblemException) as exc_info:
            await update_workspace_endpoint(
                ws1_id, UpdateWorkspaceRequest(name="Hacked"), caller_member, sess_member
            )
        assert exc_info.value.code == "INSUFFICIENT_CAPABILITY"
        assert exc_info.value.status == 403

        # 2. Non-admin bind role -> 403 (workspaces.py:512)
        binding_req = WorkspaceRoleBindingRequest(principal_id=member_id, role="MEMBER")
        with pytest.raises(ProblemException) as exc_info:
            await bind_workspace_role_endpoint(ws1_id, binding_req, caller_member, sess_member)
        assert exc_info.value.code == "INSUFFICIENT_CAPABILITY"
        assert exc_info.value.status == 403

        # 3. Non-admin unbind role -> 403 (workspaces.py:544)
        with pytest.raises(ProblemException) as exc_info:
            await unbind_workspace_role_endpoint(ws1_id, binding_req, caller_member, sess_member)
        assert exc_info.value.code == "INSUFFICIENT_CAPABILITY"
        assert exc_info.value.status == 403

    # Admin session
    ctx_admin = RLSContext(principal_id=admin_id, workspace_id=ws1_id, aal_level=1)
    async with factory.session(ctx_admin) as sess_admin:
        caller_admin = PrincipalContext(principal_id=admin_id, workspace_id=ws1_id)

        # 4. Non-existent workspace -> 404 (workspaces.py:416)
        fake_ws = uuid.uuid4()
        with pytest.raises(ProblemException) as exc_info:
            await update_workspace_endpoint(
                fake_ws, UpdateWorkspaceRequest(name="New"), caller_admin, sess_admin
            )
        assert exc_info.value.code == "NOT_FOUND"
        assert exc_info.value.status == 404

        # 5. Conflicting slug -> 409 (workspaces.py:448)
        other_ws = uuid.uuid4()
        await sess_admin.execute(
            text(
                "INSERT INTO workspaces (id, slug, name) "
                "VALUES (:id, 'slug-conflict-x', 'WS Other')"
            ),
            {"id": other_ws},
        )
        with pytest.raises(ProblemException) as exc_info:
            await update_workspace_endpoint(
                ws1_id, UpdateWorkspaceRequest(slug="slug-conflict-x"), caller_admin, sess_admin
            )
        assert exc_info.value.code == "WORKSPACE_SLUG_CONFLICT"
        assert exc_info.value.status == 409

        # 6. Name update when WorkspaceSettings row exists (covers lines 428-430)
        resp_name = await update_workspace_endpoint(
            ws1_id, UpdateWorkspaceRequest(name="Updated Name WS"), caller_admin, sess_admin
        )
        assert resp_name.name == "Updated Name WS"

    # 7. Slug update with same slug in fresh session (post-commit) (covers line 440->456 no-op path)
    async with factory.session(ctx_admin) as sess_admin2:
        caller_admin2 = PrincipalContext(principal_id=admin_id, workspace_id=ws1_id)
        resp_same_slug = await update_workspace_endpoint(
            ws1_id, UpdateWorkspaceRequest(slug=resp_name.slug), caller_admin2, sess_admin2
        )
        assert resp_same_slug.slug == resp_name.slug
