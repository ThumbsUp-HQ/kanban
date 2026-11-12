# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and integration tests for session lifecycle, rotation, timeouts, and MFA (KB-P2-02)."""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING, Annotated

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import JSONResponse

from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext, get_principal
from kanban.api.problems import (
    ProblemException,
    problem_exception_handler,
)
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1.auth_session import router as auth_session_router
from kanban.auth.sessions.cookies import (
    SESSION_COOKIE_NAME,
    build_set_cookie_header,
    encode_session_cookie,
    generate_session_token,
    hash_session_token,
)
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    CsrfMiddleware,
    validate_csrf_token,
)
from kanban.auth.sessions.resolver import (
    SessionCookieResolver,
    require_full_session,
)
from kanban.auth.sessions.service import (
    IssuedSession,
    SessionPolicy,
    SessionService,
)
from kanban.security.keys import KeyMaterial

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
def hmac_key() -> bytes:
    """Fixture providing a fixed 32-byte session HMAC key."""
    return os.urandom(32)


@pytest.fixture
def key_material(hmac_key: bytes) -> KeyMaterial:
    """Fixture providing KeyMaterial with current session HMAC key."""
    return KeyMaterial(
        master_kek=os.urandom(32),
        master_kek_kid="kek-v1",
        auth_pepper=os.urandom(32),
        session_hmac_key=hmac_key,
    )


async def _create_test_principal(factory: RLSSessionFactory) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision workspace, principal, and user records."""
    ws_id = uuid.uuid4()
    u_id = uuid.uuid4()
    ctx = RLSContext(principal_id=u_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as db_session:
        await db_session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Session WS"},
        )

        await db_session.execute(
            text(
                "SELECT register_object("
                "'user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
            ),
            {
                "ws_id": ws_id,
                "ckey": f"usr-{u_id.hex}",
                "title": "Session Test User",
                "u_id": u_id,
            },
        )

        await db_session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'Session User', 'ACTIVE')"
            ),
            {"id": u_id, "ws_id": ws_id},
        )

        await db_session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, 'session@example.com')"
            ),
            {"id": u_id, "ws_id": ws_id},
        )

    return ws_id, u_id


def _build_test_app(
    session_service: SessionService,
    session_factory: RLSSessionFactory,
    key_material: KeyMaterial,
) -> FastAPI:
    """Build FastAPI test instance wired with auth session router and middleware."""
    app = FastAPI(title="Session Test App")
    app.state.session_service = session_service
    app.state.session_factory = session_factory
    app.state.key_material = key_material

    resolver = SessionCookieResolver(session_service, session_factory)
    app.state.principal_resolver = resolver

    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    # Mount auth session routes under /api/v1/auth
    app.include_router(auth_session_router, prefix="/api/v1")

    # Protected sample route requiring full session (rejects mfa_pending)
    @app.get("/api/v1/protected/resource")
    async def protected_resource(
        principal: Annotated[PrincipalContext, Depends(require_full_session)],
    ) -> JSONResponse:
        return JSONResponse({"status": "ok", "principal_id": str(principal.principal_id)})

    # Route permitting mfa_pending
    @app.get("/api/v1/mfa/verify-view")
    async def mfa_view(
        principal: Annotated[PrincipalContext, Depends(get_principal)],
    ) -> JSONResponse:
        return JSONResponse({"status": "mfa_portal", "mfa_pending": principal.mfa_pending})

    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_middleware(RequestIdMiddleware)

    return app


@pytest.mark.asyncio
async def test_case_1_positive_login_and_cookie_attributes(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 1: positive login sets __Host-kb_session and returns CSRF."""
    factory = RLSSessionFactory(pg_worker_db)
    service = SessionService(key_material.session_hmac_key)

    ws_id, p_id = await _create_test_principal(factory)
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as db_session:
        issued: IssuedSession = await service.create_after_login(
            db_session,
            principal_id=p_id,
            workspace_id=ws_id,
            aal_level=1,
        )

    # Validate cookie header attributes
    cookie_hdr = build_set_cookie_header(issued.cookie_val, issued.absolute_expires_at)
    assert f"{SESSION_COOKIE_NAME}={issued.cookie_val}" in cookie_hdr
    assert "Secure" in cookie_hdr
    assert "HttpOnly" in cookie_hdr
    assert "SameSite=Lax" in cookie_hdr
    assert "Path=/" in cookie_hdr
    assert "Domain=" not in cookie_hdr
    assert "Expires=" in cookie_hdr

    # Verify GET /api/v1/auth/session returns principal id and CSRF token
    app = _build_test_app(service, factory, key_material)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get(
            "/api/v1/auth/session",
            cookies={SESSION_COOKIE_NAME: issued.cookie_val},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["authenticated"] is True
        assert data["principal_id"] == str(p_id)
        assert data["workspace_id"] == str(ws_id)
        assert data["aal_level"] == 1
        assert "csrf_token" in data
        assert validate_csrf_token(
            data["csrf_token"], issued.session_id, key_material.session_hmac_key
        )


@pytest.mark.asyncio
async def test_case_2_session_fixation_defense(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 2: Presenting pre-login cookie C0 revokes C0 and issues fresh C1."""
    factory = RLSSessionFactory(pg_worker_db)
    service = SessionService(key_material.session_hmac_key)

    ws_id, p_id = await _create_test_principal(factory)
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as db_session:
        # Attacker obtains pre-login session C0
        c0: IssuedSession = await service.create_after_login(
            db_session,
            principal_id=p_id,
            workspace_id=ws_id,
        )

        # Victim logs in presenting C0 as existing_cookie
        c1: IssuedSession = await service.create_after_login(
            db_session,
            principal_id=p_id,
            workspace_id=ws_id,
            existing_cookie_val=c0.cookie_val,
        )

        # C1 is a fresh session
        assert c1.session_id != c0.session_id
        assert c1.cookie_val != c0.cookie_val

        # C0 is revoked and resolves to None
        c0_sha = hash_session_token(c0.token)
        c0_resolved = await service.resolve_session(db_session, c0_sha)
        assert c0_resolved is None

        # C1 resolves cleanly
        c1_sha = hash_session_token(c1.token)
        c1_resolved = await service.resolve_session(db_session, c1_sha)
        assert c1_resolved is not None
        assert c1_resolved.id == c1.session_id


@pytest.mark.asyncio
async def test_case_5_rotation_on_aal_elevation(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 5: elevate_aal returns new id, revokes old token, preserves absolute_expires_at."""
    factory = RLSSessionFactory(pg_worker_db)
    service = SessionService(key_material.session_hmac_key)

    ws_id, p_id = await _create_test_principal(factory)
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as db_session:
        s1 = await service.create_after_login(
            db_session,
            principal_id=p_id,
            workspace_id=ws_id,
            aal_level=1,
        )

        s2 = await service.elevate_aal(
            db_session,
            old_session_id=s1.session_id,
            new_aal=2,
        )

        assert s2.session_id != s1.session_id
        assert s2.aal_level == 2

        # Old token resolves to None (revoked)
        s1_sha = hash_session_token(s1.token)
        assert await service.resolve_session(db_session, s1_sha) is None

        # New token resolves to active session with rotated_from_id pointing to s1
        s2_sha = hash_session_token(s2.token)
        s2_resolved = await service.resolve_session(db_session, s2_sha)
        assert s2_resolved is not None
        assert s2_resolved.id == s2.session_id
        assert s2_resolved.rotated_from_id == s1.session_id
        assert s2_resolved.aal_level == 2
        assert s2_resolved.aal2_verified_at is not None

        # Absolute expiration is preserved from original session
        assert abs((s2_resolved.absolute_expires_at - s1.absolute_expires_at).total_seconds()) < 1.0


@pytest.mark.asyncio
async def test_case_6_idle_and_absolute_timeouts(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 6: Idle and absolute boundary expirations."""
    factory = RLSSessionFactory(pg_worker_db)
    service = SessionService(key_material.session_hmac_key)

    ws_id, p_id = await _create_test_principal(factory)
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as db_session:
        # 1. Idle expiration: advance idle_expires_at past clock_timestamp()
        s_idle = await service.create_after_login(db_session, principal_id=p_id, workspace_id=ws_id)
        token_sha = hash_session_token(s_idle.token)

        # Still valid right now
        assert await service.resolve_session(db_session, token_sha) is not None

        # Advance idle past now
        await db_session.execute(
            text(
                "UPDATE sessions SET idle_expires_at = clock_timestamp() - interval '1 second' "
                "WHERE id = :id"
            ),
            {"id": s_idle.session_id},
        )
        assert await service.resolve_session(db_session, token_sha) is None

        # 2. Absolute expiration: absolute past now
        s_abs = await service.create_after_login(db_session, principal_id=p_id, workspace_id=ws_id)
        abs_sha = hash_session_token(s_abs.token)
        await db_session.execute(
            text(
                "UPDATE sessions SET absolute_expires_at = clock_timestamp() - interval '1 second' "
                "WHERE id = :id"
            ),
            {"id": s_abs.session_id},
        )
        assert await service.resolve_session(db_session, abs_sha) is None


@pytest.mark.asyncio
async def test_case_9_security_logout(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 9: Logout revokes session in DB and clears both cookies with Max-Age=0."""
    factory = RLSSessionFactory(pg_worker_db)
    service = SessionService(key_material.session_hmac_key)

    ws_id, p_id = await _create_test_principal(factory)
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as db_session:
        s = await service.create_after_login(db_session, principal_id=p_id, workspace_id=ws_id)

    app = _build_test_app(service, factory, key_material)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Perform logout POST with valid CSRF
        res = await client.post(
            "/api/v1/auth/logout",
            headers={
                "host": "testserver",
                "origin": "http://testserver",
                CSRF_HEADER_NAME: s.csrf_token,
            },
            cookies={
                SESSION_COOKIE_NAME: s.cookie_val,
                CSRF_COOKIE_NAME: s.csrf_token,
            },
        )
        assert res.status_code == 200
        assert res.json() == {"status": "logged_out"}

        # Verify Set-Cookie headers cleared both cookies
        set_cookies = res.headers.get_list("set-cookie")
        session_clear = any(SESSION_COOKIE_NAME in c and "Max-Age=0" in c for c in set_cookies)
        csrf_clear = any(CSRF_COOKIE_NAME in c and "Max-Age=0" in c for c in set_cookies)
        assert session_clear is True
        assert csrf_clear is True

        # Subsequent request with old cookie yields unauthenticated
        res2 = await client.get(
            "/api/v1/auth/session",
            cookies={SESSION_COOKIE_NAME: s.cookie_val},
        )
        assert res2.json()["authenticated"] is False


@pytest.mark.asyncio
async def test_case_10_mfa_pending_enforcement(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 10: Session with mfa_pending=True rejected by require_full_session with 403."""
    factory = RLSSessionFactory(pg_worker_db)
    service = SessionService(key_material.session_hmac_key)

    ws_id, p_id = await _create_test_principal(factory)
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as db_session:
        s_mfa = await service.create_after_login(
            db_session,
            principal_id=p_id,
            workspace_id=ws_id,
            mfa_pending=True,
        )

    app = _build_test_app(service, factory, key_material)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Normal protected route rejects with 403 MFA_REQUIRED
        res1 = await client.get(
            "/api/v1/protected/resource",
            cookies={SESSION_COOKIE_NAME: s_mfa.cookie_val},
        )
        assert res1.status_code == 403
        data1 = res1.json()
        assert data1["code"] == "MFA_REQUIRED"

        # MFA portal route permits mfa_pending
        res2 = await client.get(
            "/api/v1/mfa/verify-view",
            cookies={SESSION_COOKIE_NAME: s_mfa.cookie_val},
        )
        assert res2.status_code == 200
        assert res2.json()["mfa_pending"] is True


def test_case_12_config_timeout_bounds_validation() -> None:
    """Test Case 12: Startup ValueError raised for policy values outside [300, 2592000]."""
    # Valid default
    policy = SessionPolicy()
    assert policy.idle_seconds == 28800

    # Values below 300s rejected
    with pytest.raises(ValueError, match="outside allowed bounds"):
        SessionPolicy(idle_seconds=10)

    # Values above 30 days rejected
    with pytest.raises(ValueError, match="outside allowed bounds"):
        SessionPolicy(absolute_seconds=3000000)

    with pytest.raises(ValueError, match="outside allowed bounds"):
        SessionPolicy(aal2_fresh_seconds=50)


@pytest.mark.asyncio
async def test_resolver_direct_unit(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Verify direct resolution: missing cookie, invalid token, DB lookup, and state."""
    factory = RLSSessionFactory(pg_worker_db)
    service = SessionService(key_material.session_hmac_key)
    resolver = SessionCookieResolver(service, factory)

    # 1. No cookie header
    req_no_cookie = Request({"type": "http", "headers": []})
    assert await resolver.resolve(req_no_cookie) is None

    # 2. Invalid cookie signature
    bad_cookie = "bad.cookie"
    req_bad_cookie = Request(
        {
            "type": "http",
            "headers": [(b"cookie", f"{SESSION_COOKIE_NAME}={bad_cookie}".encode())],
        }
    )
    assert await resolver.resolve(req_bad_cookie) is None

    # 3. Valid cookie for non-existent session
    dummy_tok = generate_session_token()
    dummy_cookie = encode_session_cookie(dummy_tok, key_material.session_hmac_key)
    req_nonexistent = Request(
        {
            "type": "http",
            "headers": [(b"cookie", f"{SESSION_COOKIE_NAME}={dummy_cookie}".encode())],
        }
    )
    assert await resolver.resolve(req_nonexistent) is None

    # 4. Valid cookie for active session
    ws_id, p_id = await _create_test_principal(factory)
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as db_sess:
        issued = await service.create_after_login(
            db_sess, principal_id=p_id, workspace_id=ws_id, aal_level=1
        )

    req_valid = Request(
        {
            "type": "http",
            "headers": [(b"cookie", f"{SESSION_COOKIE_NAME}={issued.cookie_val}".encode())],
        }
    )
    resolved_ctx = await resolver.resolve(req_valid)
    assert resolved_ctx is not None
    assert resolved_ctx.principal_id == p_id
    assert resolved_ctx.workspace_id == ws_id
    assert resolved_ctx.session_id == issued.session_id
    assert req_valid.state.session_id == issued.session_id


@pytest.mark.asyncio
async def test_require_full_session_direct_unit() -> None:
    """Verify require_full_session pass, fail, and bypass branches."""
    # 1. Principal with mfa_pending=False passes
    p_ok = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        mfa_pending=False,
    )
    req_ok = Request({"type": "http", "headers": []})
    assert await require_full_session(req_ok, p_ok) is p_ok

    # 2. Principal with mfa_pending=True rejected with 403
    p_mfa = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        mfa_pending=True,
    )
    req_mfa = Request({"type": "http", "headers": []})
    with pytest.raises(ProblemException) as exc:
        await require_full_session(req_mfa, p_mfa)
    assert exc.value.status == 403
    assert exc.value.code == "MFA_REQUIRED"

    # 3. Principal with mfa_pending=True allowed when endpoint has allow_mfa_pending
    def endpoint_fn() -> None:
        pass

    endpoint_fn.allow_mfa_pending = True  # type: ignore[attr-defined]
    req_allow = Request({"type": "http", "headers": [], "endpoint": endpoint_fn})
    assert await require_full_session(req_allow, p_mfa) is p_mfa


@pytest.mark.asyncio
async def test_service_policy_and_revocations(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Verify SessionService policy getter, bulk revocations, and logout."""
    factory = RLSSessionFactory(pg_worker_db)
    service = SessionService(key_material.session_hmac_key)
    assert service.policy.idle_seconds == 28800

    ws_id, p_id = await _create_test_principal(factory)
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as db_sess:
        # Create 2 sessions
        await service.create_after_login(db_sess, principal_id=p_id, workspace_id=ws_id)
        await service.create_after_login(db_sess, principal_id=p_id, workspace_id=ws_id)

        # Revoke all for principal via service
        count = await service.revoke_all_for_principal(db_sess, p_id)
        assert count == 2

        # Individual logout
        s3 = await service.create_after_login(db_sess, principal_id=p_id, workspace_id=ws_id)
        assert await service.logout(db_sess, s3.session_id) is True
