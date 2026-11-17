# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for durable session persistence, remember_me policy, and cookie stability.

Part of KB-AUTH-PERSIST / KANBA-186.
"""

from __future__ import annotations

import urllib.parse
import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from starlette.responses import Response

from database.session import RLSContext, RLSSessionFactory
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1.auth_cards_public import router as auth_cards_router
from kanban.api.v1.auth_oidc import get_oidc_flow
from kanban.api.v1.auth_oidc import router as auth_oidc_router
from kanban.api.v1.auth_session import router as auth_session_router
from kanban.auth.cards.repository import admin_upsert
from kanban.auth.identity import ExternalIdentityAssertion, IdentityResolver, ResolvedLogin
from kanban.auth.oidc.flow import OidcFlow
from kanban.auth.sessions.cookies import (
    SESSION_COOKIE_NAME,
    attach_session_and_csrf_cookies,
    hash_session_token,
    parse_session_cookie,
)
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CsrfMiddleware,
)
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionPolicy, SessionService
from kanban.security.envelope import StaticKekProvider, seal_card_secret
from kanban.security.keys import KeyMaterial

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine
    from starlette.requests import Request


class RecordingIdentityResolver(IdentityResolver):
    """Stub identity resolver returning a fixed principal and workspace."""

    def __init__(self, principal_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
        """Initialize with fixed test principal and workspace."""
        self.principal_id = principal_id
        self.workspace_id = workspace_id

    async def resolve(
        self,
        assertion: ExternalIdentityAssertion,
        request: Request,
        link_intent_id: uuid.UUID | None = None,
    ) -> ResolvedLogin:
        """Return fixed test login."""
        del assertion, request, link_intent_id
        return ResolvedLogin(
            principal_id=self.principal_id,
            workspace_id=self.workspace_id,
            aal_level=2,
            mfa_pending=False,
        )


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


async def _create_test_workspace_and_admin(
    factory: RLSSessionFactory,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision workspace, user, and principal for testing."""
    ws_id = uuid.uuid4()
    u_id = uuid.uuid4()
    ctx = RLSContext(principal_id=u_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as session:
        await session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Persist WS"},
        )

        await session.execute(
            text(
                "SELECT register_object("
                "'user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
            ),
            {
                "ws_id": ws_id,
                "ckey": f"usr-{u_id.hex}",
                "title": "Persist User",
                "u_id": u_id,
            },
        )

        await session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'Persist User', 'ACTIVE')"
            ),
            {"id": u_id, "ws_id": ws_id},
        )

        await session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, 'persist@example.com')"
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


def _build_test_app(
    session_service: SessionService,
    session_factory: RLSSessionFactory,
    key_material: KeyMaterial,
) -> FastAPI:
    """Build FastAPI test instance wired with auth session router and middleware."""
    app = FastAPI(title="Persist Test App")
    app.state.session_service = session_service
    app.state.session_factory = session_factory
    app.state.key_material = key_material

    resolver = SessionCookieResolver(session_service, session_factory)
    app.state.principal_resolver = resolver

    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    app.include_router(auth_session_router, prefix="/api/v1")
    app.include_router(auth_cards_router, prefix="/api/v1")
    app.include_router(auth_oidc_router, prefix="/api/v1")

    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_middleware(RequestIdMiddleware)
    return app


@pytest.mark.asyncio
async def test_session_policy_remember_bounds() -> None:
    """Verify remember_me timeout policy defaults and validation bounds."""
    policy = SessionPolicy()
    assert policy.remember_idle_seconds == 604800  # 7 days
    assert policy.remember_absolute_seconds == 2592000  # 30 days
    assert policy.aal2_fresh_seconds == 900

    env_policy = SessionPolicy.from_env()
    assert env_policy.remember_idle_seconds == 604800
    assert env_policy.remember_absolute_seconds == 2592000

    with pytest.raises(ValueError, match="outside allowed bounds"):
        SessionPolicy(remember_absolute_seconds=3000000)


@pytest.mark.asyncio
async def test_remember_me_cookie_and_rotation_persistence(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Verify remember_me=True emits Max-Age + Expires and preserves persistence on rotation."""
    factory = RLSSessionFactory(pg_worker_db)
    session_service = SessionService(key_material.session_hmac_key)
    ws_id, p_id = await _create_test_workspace_and_admin(factory)

    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as session:
        # 1. Login with remember_me=True
        issued_persist = await session_service.create_after_login(
            session,
            principal_id=p_id,
            workspace_id=ws_id,
            remember_me=True,
        )
        assert issued_persist.is_persistent is True

        # Check cookie formatting
        resp1 = Response()
        attach_session_and_csrf_cookies(
            resp1, None, issued_persist, issued_persist.csrf_token, persistent=True
        )
        cookie_hdr1 = resp1.headers.get("set-cookie") or ""
        assert "Max-Age=" in cookie_hdr1
        assert "Expires=" in cookie_hdr1

        # 2. Login with remember_me=False
        issued_session_only = await session_service.create_after_login(
            session,
            principal_id=p_id,
            workspace_id=ws_id,
            remember_me=False,
        )
        assert issued_session_only.is_persistent is False

        resp2 = Response()
        attach_session_and_csrf_cookies(
            resp2, None, issued_session_only, issued_session_only.csrf_token, persistent=False
        )
        cookie_hdr2 = resp2.headers.get("set-cookie") or ""
        assert "Max-Age=" not in cookie_hdr2
        assert "Expires=" not in cookie_hdr2

        # 3. Elevate AAL on persistent session -> preserves is_persistent=True
        elevated = await session_service.elevate_aal(
            session,
            old_session_id=issued_persist.session_id,
            new_aal=2,
        )
        assert elevated.is_persistent is True


@pytest.mark.asyncio
async def test_csrf_stability_and_session_status(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Verify GET /api/v1/auth/session reuses existing valid CSRF cookies without rotating."""
    factory = RLSSessionFactory(pg_worker_db)
    session_service = SessionService(key_material.session_hmac_key)
    ws_id, admin_id = await _create_test_workspace_and_admin(factory)

    app = _build_test_app(session_service, factory, key_material)

    anon_ctx = RLSContext(
        principal_id=uuid.UUID(int=0),
        workspace_id=uuid.UUID(int=0),
        token_scopes=("session",),
        aal_level=1,
    )
    async with factory.session(anon_ctx) as sess:
        issued = await session_service.create_after_login(
            sess,
            principal_id=admin_id,
            workspace_id=ws_id,
            remember_me=True,
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        # First request: unauthenticated / fresh pre-session CSRF
        r1 = await client.get("/api/v1/auth/session")
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["authenticated"] is False
        csrf1 = d1["csrf_token"]
        assert csrf1

        # Second request with existing CSRF cookie:
        # must reuse same CSRF token and emit NO Set-Cookie
        r2 = await client.get(
            "/api/v1/auth/session",
            cookies={CSRF_COOKIE_NAME: csrf1},
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["csrf_token"] == csrf1
        # No Set-Cookie header emitted when CSRF token is reused
        assert "set-cookie" not in r2.headers

        # Third request with valid authenticated session cookie & valid CSRF
        valid_csrf_for_sess = issued.csrf_token
        r3 = await client.get(
            "/api/v1/auth/session",
            cookies={
                SESSION_COOKIE_NAME: issued.cookie_val,
                CSRF_COOKIE_NAME: valid_csrf_for_sess,
            },
        )
        assert r3.status_code == 200
        d3 = r3.json()
        assert d3["authenticated"] is True
        assert d3["principal_id"] == str(admin_id)
        assert d3["csrf_token"] == valid_csrf_for_sess
        assert d3["remember_me"] is True
        assert d3["idle_expires_at"] is not None
        assert d3["absolute_expires_at"] is not None
        assert "set-cookie" not in r3.headers


@pytest.mark.asyncio
async def test_oidc_callback_commits_session_and_survives_reload(  # noqa: PLR0915
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
) -> None:
    """Verify OIDC callback commits session to DB and emits fallback cookies on plain HTTP."""
    factory = RLSSessionFactory(pg_worker_db)
    session_service = SessionService(key_material.session_hmac_key)
    ws_id, admin_id = await _create_test_workspace_and_admin(factory)

    # 1. Seed an OIDC card
    async with factory.session(
        RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=2)
    ) as sess:
        card_id = uuid.uuid4()
        sealed = seal_card_secret(card_id, "OAUTH2", b"test-secret-1234", kek_provider)
        await admin_upsert(
            sess,
            card_id=card_id,
            workspace_id=ws_id,
            provider_kind="OAUTH2",
            slug="google-persist-test",
            display_name="Google Persist Test",
            is_enabled=True,
            sort_rank="0001",
            public_config={
                "kind": "OAUTH2",
                "authorization_endpoint": "https://accounts.google.com/o/oauth2/auth",
                "token_endpoint": "https://oauth2.googleapis.com/token",
                "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
                "client_id": "test-client-id.apps.googleusercontent.com",
                "client_auth": "client_secret_basic",
                "scopes": ["openid", "profile", "email"],
                "subject_claim": "sub",
                "allowed_algs": ["RS256"],
            },
            encrypted_secret_blob=sealed.encrypted_secret_blob,
            wrapped_dek=sealed.wrapped_dek,
            dek_kid=sealed.dek_kid,
        )

    app = _build_test_app(session_service, factory, key_material)

    recording_resolver = RecordingIdentityResolver(principal_id=admin_id, workspace_id=ws_id)
    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_discovery_resp = httpx.Response(
        200,
        json={
            "issuer": "https://accounts.google.com",
            "authorization_endpoint": "https://accounts.google.com/o/oauth2/auth",
            "token_endpoint": "https://oauth2.googleapis.com/token",
            "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
            "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
        },
        request=httpx.Request(
            "GET", "https://accounts.google.com/.well-known/openid-configuration"
        ),
    )
    mock_token_resp = httpx.Response(
        200,
        json={"access_token": "fake-access-token", "token_type": "Bearer"},
        request=httpx.Request("POST", "https://oauth2.googleapis.com/token"),
    )
    mock_userinfo_resp = httpx.Response(
        200,
        json={
            "sub": "google-user-12345",
            "email": "persist-user@example.com",
            "email_verified": True,
            "name": "Persist User",
        },
        request=httpx.Request("GET", "https://openidconnect.googleapis.com/v1/userinfo"),
    )
    mock_http_client.post.return_value = mock_token_resp

    async def _mock_get(url: object, *args: object, **kwargs: object) -> httpx.Response:
        del args, kwargs
        if "openid-configuration" in str(url):
            return mock_discovery_resp
        return mock_userinfo_resp

    mock_http_client.get.side_effect = _mock_get

    flow = OidcFlow(
        key_material=key_material,
        identity_resolver=recording_resolver,
        session_service=session_service,
        http_client=mock_http_client,
    )
    app.state.oidc_flow = flow
    app.dependency_overrides[get_oidc_flow] = lambda: flow

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        # Start auth with remember_me=1
        start_res = await client.get(
            "/api/v1/auth/cards/google-persist-test/start?return_to=/&remember_me=1",
            follow_redirects=False,
        )
        assert start_res.status_code == 302
        start_loc = start_res.headers["Location"]
        start_params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(start_loc).query))

        # Extract browser binding cookie
        binding_val = ""
        for cookie_hdr in start_res.headers.get_list("set-cookie"):
            if "kb_oidc=" in cookie_hdr:
                binding_val = cookie_hdr.split(";")[0].split("=")[1].strip()

        client.cookies.set("kb_oidc", binding_val)

        # Execute callback over plain HTTP (http://127.0.0.1)
        cb_res = await client.get(
            f"/api/v1/auth/oidc/google-persist-test/callback?code=mock-code&state={start_params['state']}",
            follow_redirects=False,
        )
        assert cb_res.status_code == 302
        assert cb_res.headers["Location"] == "/"

        # Inspect Set-Cookie headers
        cb_cookies = cb_res.headers.get_list("set-cookie")
        # Must have __Host-kb_session with Max-Age and Expires
        host_sess_hdr = next((c for c in cb_cookies if "__Host-kb_session=" in c), None)
        assert host_sess_hdr is not None
        assert "Max-Age=" in host_sess_hdr
        assert "Expires=" in host_sess_hdr

        # Must have fallback kb_session on plain HTTP
        fallback_sess_hdr = next(
            (c for c in cb_cookies if "kb_session=" in c and "__Host-" not in c), None
        )
        assert fallback_sess_hdr is not None

        # Extract session token from cookie
        cookie_val = host_sess_hdr.split(";")[0].split("=")[1].strip()
        parsed_token = parse_session_cookie(cookie_val, key_material.session_hmac_key)
        assert parsed_token is not None
        token_sha = hash_session_token(parsed_token)

        # 3. VERIFY SESSION ROW DURABLY COMMITTED IN POSTGRESQL (FRESH SESSION)
        anon_ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
            token_scopes=("session",),
            aal_level=1,
        )
        async with factory.session(anon_ctx) as verify_session:
            user_session = await session_service.resolve_session(verify_session, token_sha)
            assert user_session is not None
            assert user_session.principal_id == admin_id
            assert user_session.is_persistent is True

        # 4. Subsequent requests using the issued cookies in a fresh client return 200 authenticated
        client.cookies.set(SESSION_COOKIE_NAME, cookie_val)
        me_res = await client.get("/api/v1/auth/me")
        assert me_res.status_code == 200
        assert me_res.json()["principal_id"] == str(admin_id)

        session_res = await client.get("/api/v1/auth/session")
        assert session_res.status_code == 200
        assert session_res.json()["authenticated"] is True
        assert session_res.json()["remember_me"] is True
