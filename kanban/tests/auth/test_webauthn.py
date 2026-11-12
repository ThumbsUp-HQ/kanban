# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: S106, S107, PLR0915, ARG005, TRY003, EM101, PLC0415, F841, RUF059
"""Comprehensive test suite for WebAuthn and Passkeys registration and assertions (KB-P2-05b)."""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING, Any, Final

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from starlette.requests import Request

from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.api.v1.auth_webauthn import (
    _build_elevated_response,
    _get_rate_limiter,
    _get_webauthn_service,
    authenticate_options,
    authenticate_verify,
    delete_credential,
    list_credentials,
    register_options,
    register_verify,
)
from kanban.auth.cards.repository import admin_upsert
from kanban.auth.local.hashing import hash_password_sync
from kanban.auth.mfa.webauthn import WebauthnCloneDetectedError, WebauthnService
from kanban.auth.sessions.cookies import SESSION_COOKIE_NAME
from kanban.auth.sessions.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, CsrfMiddleware
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionService
from kanban.security.envelope import StaticKekProvider
from kanban.security.keys import KeyMaterial
from kanban.security.ratelimit import AUTH_MFA_VERIFY, make_key
from kanban.security.ratelimit.pg import PgRateLimiter
from kanban.settings import Settings
from kanban.tests.helpers.soft_authenticator import SoftAuthenticator

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

PEPPER_KEY: Final[bytes] = b"p" * 32
SESSION_HMAC_KEY: Final[bytes] = b"s" * 32
MASTER_KEK: Final[bytes] = b"k" * 32
ORIGIN: Final[str] = "https://kanban.example.com"
RP_ID: Final[str] = "kanban.example.com"


@pytest.fixture
def key_material() -> KeyMaterial:
    """Provide testing cryptographic keys."""
    return KeyMaterial(
        master_kek=MASTER_KEK,
        master_kek_kid="kek-v1",
        auth_pepper=PEPPER_KEY,
        session_hmac_key=SESSION_HMAC_KEY,
    )


@pytest.fixture
def webauthn_settings() -> Settings:
    """Provide settings configured for testing WebAuthn domain."""
    return Settings(
        deployment_mode="production",
        public_origin=ORIGIN,
        webauthn_rp_id=RP_ID,
        webauthn_rp_name="👍kanban",
    )


async def _setup_test_admin(
    factory: RLSSessionFactory,
    key_material: KeyMaterial,
    *,
    username: str = "superadmin",
    password: str = "AdminPassword456!",
    role: str = "SERVER_ADMIN",
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Provision workspace, local admin credential, card, and role binding in database."""
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()
    card_id = uuid.uuid4()

    pw_hash = hash_password_sync(password, key_material.auth_pepper)
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)

    async with factory.session(ctx) as session:
        await session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:8]}", "name": "Auth Test Workspace"},
        )
        await session.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', :name)"
            ),
            {"id": p_id, "ws_id": ws_id, "name": username},
        )
        await session.execute(
            text(
                "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type) "
                "VALUES (:ws_id, :p_id, :role, 'server')"
            ),
            {"ws_id": ws_id, "p_id": p_id, "role": role},
        )

        await admin_upsert(
            session,
            card_id=card_id,
            workspace_id=ws_id,
            provider_kind="LOCAL_ADMIN",
            slug=f"local-admin-{ws_id.hex[:8]}",
            display_name="Local Administrator",
            button_subtext="Username & password",
            icon_preset="shield",
            is_enabled=True,
            sort_rank="0|h00000:",
        )
        await session.execute(text("SET LOCAL app.is_setup_claim = 'true'"))
        await session.execute(
            text("SELECT kb_auth.local_admin_create(:pid, :username, :hash, 'pepper-v1')"),
            {"pid": p_id, "username": username, "hash": pw_hash},
        )

    return ws_id, p_id, card_id


def _create_app(
    factory: RLSSessionFactory,
    key_material: KeyMaterial,
    rate_limiter: PgRateLimiter,
    settings: Settings,
) -> tuple[FastAPI, SessionService]:
    """Create test FastAPI application configured with auth and WebAuthn routes."""
    session_service = SessionService(key_material.session_hmac_key)
    app = FastAPI(title="WebAuthn Test App")
    app.state.settings = settings
    app.state.session_service = session_service
    app.state.session_factory = factory
    app.state.key_material = key_material
    app.state.rate_limiter = rate_limiter
    app.state.kek_provider = StaticKekProvider(
        {key_material.master_kek_kid: key_material.master_kek},
        current=key_material.master_kek_kid,
    )
    app.state.webauthn_service = WebauthnService(
        rp_id=settings.effective_rp_id,
        rp_name=settings.webauthn_rp_name,
        expected_origin=settings.effective_origin,
    )

    resolver = SessionCookieResolver(session_service, factory)
    app.state.principal_resolver = resolver
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    v1 = build_v1_router()
    app.include_router(v1, prefix="/api/v1")

    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_middleware(RequestIdMiddleware)

    return app, session_service


def _sync_cookies(client: httpx.AsyncClient, response: httpx.Response) -> None:
    """Sync response cookies into AsyncClient cookie jar."""
    for c in response.cookies.jar:
        client.cookies.set(c.name, c.value or "")


async def _get_pre_session_csrf(client: httpx.AsyncClient) -> tuple[str, str]:
    """Retrieve pre-session CSRF token and cookie from GET /api/v1/auth/session."""
    res = await client.get("/api/v1/auth/session")
    assert res.status_code == 200
    token = str(res.json()["csrf_token"])
    csrf_cookie = str(res.cookies.get(CSRF_COOKIE_NAME, token) or token)
    _sync_cookies(client, res)
    return token, csrf_cookie


# --- 1. Positive lifecycle ---


@pytest.mark.asyncio
async def test_case_1_positive_lifecycle(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Test Case 1: Positive factor lifecycle.

    Soft authenticator registers (ES256), then asserts -> aal_level=2, session id rotated.
    """
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    _ws_id, p_id, _ = await _setup_test_admin(
        factory, key_material, username="alice", password="Password123!"
    )

    app, _ = _create_app(factory, key_material, rate_limiter, webauthn_settings)
    transport = httpx.ASGITransport(app=app)
    auth = SoftAuthenticator()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Pre-session CSRF
        pre_token, _ = await _get_pre_session_csrf(client)

        # 1. Login with local credentials -> yields initial session with mfa_pending=True
        login_res = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre_token},
            json={"username": "alice", "password": "Password123!"},
        )
        assert login_res.status_code == 200
        _sync_cookies(client, login_res)
        login_data = login_res.json()
        assert login_data["mfa_pending"] is True
        assert login_data["aal_level"] == 1
        sess_token_1 = login_data["csrf_token"]
        old_session_id = login_data["session_id"]

        # 2. First enrollment: Request registration options on mfa_pending session
        reg_opts_res = await client.post(
            "/api/v1/auth/webauthn/register/options",
            headers={CSRF_HEADER_NAME: sess_token_1},
        )
        assert reg_opts_res.status_code == 200
        reg_options = reg_opts_res.json()
        assert "challenge" in reg_options
        assert reg_options["rp"]["name"] == "👍kanban"
        assert reg_options["rp"]["id"] == RP_ID

        # 3. Soft authenticator creates registration credential
        reg_cred = auth.create_credential(reg_options, origin=ORIGIN)
        reg_cred["response"].pop("transports", None)

        # 4. Verify registration -> elevates session to AAL2 on first enrollment
        reg_verify_res = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: sess_token_1},
            json={"credential": reg_cred, "nickname": "MacBook Touch ID"},
        )
        assert reg_verify_res.status_code == 200
        _sync_cookies(client, reg_verify_res)
        reg_verify_data = reg_verify_res.json()
        assert reg_verify_data["verified"] is True
        assert reg_verify_data["aal_level"] == 2
        assert reg_verify_data["session_id"] != old_session_id
        new_sess_token = reg_verify_data["csrf_token"]

        # 5. List credentials -> should return our newly enrolled credential
        list_res = await client.get("/api/v1/auth/webauthn/credentials")
        assert list_res.status_code == 200
        creds = list_res.json()
        assert len(creds) == 1
        assert creds[0]["nickname"] == "MacBook Touch ID"

        # 6. Re-login with password -> new session with mfa_pending=True
        login_res_2 = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: new_sess_token},
            json={"username": "alice", "password": "Password123!"},
        )
        assert login_res_2.status_code == 200
        _sync_cookies(client, login_res_2)
        login_data_2 = login_res_2.json()
        assert login_data_2["mfa_pending"] is True
        sess_token_2 = login_data_2["csrf_token"]
        sess_id_2 = login_data_2["session_id"]

        # 7. Authenticate options
        auth_opts_res = await client.post(
            "/api/v1/auth/webauthn/authenticate/options",
            headers={CSRF_HEADER_NAME: sess_token_2},
        )
        assert auth_opts_res.status_code == 200
        auth_opts = auth_opts_res.json()
        assert "challenge" in auth_opts
        assert len(auth_opts["allowCredentials"]) == 1

        # 8. Soft authenticator asserts
        auth_cred = auth.get_assertion(auth_opts, origin=ORIGIN, sign_count=1)

        # 9. Verify assertion -> elevates to AAL2 and rotates session
        auth_verify_res = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: sess_token_2},
            json={"credential": auth_cred},
        )
        assert auth_verify_res.status_code == 200
        _sync_cookies(client, auth_verify_res)
        auth_verify_data = auth_verify_res.json()
        assert auth_verify_data["verified"] is True
        assert auth_verify_data["aal_level"] == 2
        assert auth_verify_data["session_id"] != sess_id_2


# --- 2. Security: Phishing Origin ---


@pytest.mark.asyncio
async def test_case_2_security_phishing_origin(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Test Case 2: Phishing origin rejection (clientDataJSON origin=https://kanban.example.evil)."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    _, p_id, _ = await _setup_test_admin(
        factory, key_material, username="bob", password="Password123!"
    )
    app, _ = _create_app(factory, key_material, rate_limiter, webauthn_settings)
    transport = httpx.ASGITransport(app=app)
    auth = SoftAuthenticator()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        pre_token, _ = await _get_pre_session_csrf(client)
        login_res = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre_token},
            json={"username": "bob", "password": "Password123!"},
        )
        _sync_cookies(client, login_res)
        csrf = login_res.json()["csrf_token"]

        # Register valid credential
        reg_opts = (
            await client.post(
                "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        reg_cred = auth.create_credential(reg_opts, origin=ORIGIN)
        reg_res = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": reg_cred},
        )
        assert reg_res.status_code == 200
        _sync_cookies(client, reg_res)
        csrf = reg_res.json()["csrf_token"]

        # Attempt authenticate assertion with phishing origin
        auth_opts = (
            await client.post(
                "/api/v1/auth/webauthn/authenticate/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        phished_cred = auth.get_assertion(
            auth_opts, origin="https://kanban.example.evil", sign_count=1
        )

        verify_res = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": phished_cred},
        )
        assert verify_res.status_code == 401
        assert verify_res.json()["code"] == "MFA_INVALID"


# --- 3. Security: RP ID Hash ---


@pytest.mark.asyncio
async def test_case_3_security_rp_id_hash(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Test Case 3: RP ID hash mismatch (authenticatorData rpIdHash for evil.example -> 401)."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    _, p_id, _ = await _setup_test_admin(
        factory, key_material, username="charlie", password="Password123!"
    )
    app, _ = _create_app(factory, key_material, rate_limiter, webauthn_settings)
    transport = httpx.ASGITransport(app=app)
    auth = SoftAuthenticator()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        pre_token, _ = await _get_pre_session_csrf(client)
        login_res = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre_token},
            json={"username": "charlie", "password": "Password123!"},
        )
        _sync_cookies(client, login_res)
        csrf = login_res.json()["csrf_token"]

        reg_opts = (
            await client.post(
                "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        reg_cred = auth.create_credential(reg_opts, origin=ORIGIN)
        reg_res = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": reg_cred},
        )
        assert reg_res.status_code == 200
        _sync_cookies(client, reg_res)
        csrf = reg_res.json()["csrf_token"]

        auth_opts = (
            await client.post(
                "/api/v1/auth/webauthn/authenticate/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        evil_rp_hash = hashlib.sha256(b"evil.example").digest()
        evil_cred = auth.get_assertion(
            auth_opts, origin=ORIGIN, override_rp_id_hash=evil_rp_hash, sign_count=1
        )

        verify_res = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": evil_cred},
        )
        assert verify_res.status_code == 401
        assert verify_res.json()["code"] == "MFA_INVALID"


# --- 4. Security: UV Missing ---


@pytest.mark.asyncio
async def test_case_4_security_uv_missing(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Test Case 4: User Verification missing (flags with UP=1, UV=0 -> 401)."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    _, p_id, _ = await _setup_test_admin(
        factory, key_material, username="dave", password="Password123!"
    )
    app, _ = _create_app(factory, key_material, rate_limiter, webauthn_settings)
    transport = httpx.ASGITransport(app=app)
    auth = SoftAuthenticator()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        pre_token, _ = await _get_pre_session_csrf(client)
        login_res = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre_token},
            json={"username": "dave", "password": "Password123!"},
        )
        _sync_cookies(client, login_res)
        csrf = login_res.json()["csrf_token"]

        reg_opts = (
            await client.post(
                "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        # Create credential with UV=False
        no_uv_reg_cred = auth.create_credential(reg_opts, origin=ORIGIN, uv=False, up=True)
        reg_res = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": no_uv_reg_cred},
        )
        assert reg_res.status_code == 401
        assert reg_res.json()["code"] == "MFA_INVALID"

        # Now register with UV=True
        reg_opts_2 = (
            await client.post(
                "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        valid_reg_cred = auth.create_credential(reg_opts_2, origin=ORIGIN, uv=True, up=True)
        reg_ok = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": valid_reg_cred},
        )
        assert reg_ok.status_code == 200
        _sync_cookies(client, reg_ok)
        csrf = reg_ok.json()["csrf_token"]

        # Attempt assertion with UV=False
        auth_opts = (
            await client.post(
                "/api/v1/auth/webauthn/authenticate/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        no_uv_auth = auth.get_assertion(auth_opts, origin=ORIGIN, uv=False, up=True, sign_count=1)
        auth_res = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": no_uv_auth},
        )
        assert auth_res.status_code == 401
        assert auth_res.json()["code"] == "MFA_INVALID"


# --- 5. Security: Challenge Replay, Expiry, and Session Mismatch ---


@pytest.mark.asyncio
async def test_case_5_challenge_replay_and_expiry_and_session_binding(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Test Case 5: Replay rejected, challenge > 300s rejected, session mismatch rejected."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    _, p_id, _ = await _setup_test_admin(
        factory, key_material, username="eve", password="Password123!"
    )
    app, _ = _create_app(factory, key_material, rate_limiter, webauthn_settings)
    transport = httpx.ASGITransport(app=app)
    auth = SoftAuthenticator()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        pre_token, _ = await _get_pre_session_csrf(client)
        login_res = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre_token},
            json={"username": "eve", "password": "Password123!"},
        )
        _sync_cookies(client, login_res)
        csrf = login_res.json()["csrf_token"]
        session_id_a = uuid.UUID(login_res.json()["session_id"])

        # Register credential
        reg_opts = (
            await client.post(
                "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        reg_cred = auth.create_credential(reg_opts, origin=ORIGIN)
        reg_ok = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": reg_cred},
        )
        assert reg_ok.status_code == 200
        _sync_cookies(client, reg_ok)
        csrf = reg_ok.json()["csrf_token"]

        # 5a: Challenge replay rejection
        auth_opts = (
            await client.post(
                "/api/v1/auth/webauthn/authenticate/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        assertion = auth.get_assertion(auth_opts, origin=ORIGIN, sign_count=1)

        first_verify = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": assertion},
        )
        assert first_verify.status_code == 200
        _sync_cookies(client, first_verify)
        csrf = first_verify.json()["csrf_token"]

        # Replay the identical assertion
        replay_verify = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": assertion},
        )
        assert replay_verify.status_code == 401
        assert replay_verify.json()["code"] == "MFA_INVALID"

        # 5b: Challenge expired (> 300s)
        auth_opts_2 = (
            await client.post(
                "/api/v1/auth/webauthn/authenticate/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        # Expire challenge directly in database
        async with factory.session(
            RLSContext(principal_id=p_id, workspace_id=uuid.uuid4(), aal_level=2)
        ) as db_session:
            await db_session.execute(
                text(
                    "UPDATE webauthn_challenges "
                    "SET expires_at = clock_timestamp() - interval '301 seconds' "
                    "WHERE session_id = :sid AND consumed_at IS NULL"
                ),
                {"sid": uuid.UUID(first_verify.json()["session_id"])},
            )

        assertion_expired = auth.get_assertion(auth_opts_2, origin=ORIGIN, sign_count=2)
        expired_res = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": assertion_expired},
        )
        assert expired_res.status_code == 401
        assert expired_res.json()["code"] == "MFA_INVALID"

        # 5c: Challenge issued to Session A used in Session B
        # Obtain challenge for Session A
        auth_opts_3 = (
            await client.post(
                "/api/v1/auth/webauthn/authenticate/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        assertion_for_a = auth.get_assertion(auth_opts_3, origin=ORIGIN, sign_count=3)

        # Login in a second independent client to create Session B
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client_b:
            pre_b, _ = await _get_pre_session_csrf(client_b)
            login_b = await client_b.post(
                "/api/v1/auth/local/login",
                headers={CSRF_HEADER_NAME: pre_b},
                json={"username": "eve", "password": "Password123!"},
            )
            _sync_cookies(client_b, login_b)
            csrf_b = login_b.json()["csrf_token"]

            # Present assertion from Session A in Session B
            mismatch_res = await client_b.post(
                "/api/v1/auth/webauthn/authenticate/verify",
                headers={CSRF_HEADER_NAME: csrf_b},
                json={"credential": assertion_for_a},
            )
            assert mismatch_res.status_code == 401
            assert mismatch_res.json()["code"] == "MFA_INVALID"


# --- 6. Security: Credential Substitution ---


@pytest.mark.asyncio
async def test_case_6_security_credential_substitution(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Test Case 6: Principal B's valid credential used during Principal A's assertion -> 401."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    _, p_a, _ = await _setup_test_admin(
        factory, key_material, username="user_a", password="Password123!"
    )
    _, p_b, _ = await _setup_test_admin(
        factory, key_material, username="user_b", password="Password123!"
    )
    app, _ = _create_app(factory, key_material, rate_limiter, webauthn_settings)
    transport = httpx.ASGITransport(app=app)
    auth_a = SoftAuthenticator()
    auth_b = SoftAuthenticator()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Register User A
        pre, _ = await _get_pre_session_csrf(client)
        login_a = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre},
            json={"username": "user_a", "password": "Password123!"},
        )
        _sync_cookies(client, login_a)
        csrf_a = login_a.json()["csrf_token"]
        reg_opts_a = (
            await client.post(
                "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf_a}
            )
        ).json()
        reg_cred_a = auth_a.create_credential(reg_opts_a, origin=ORIGIN)
        await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf_a},
            json={"credential": reg_cred_a},
        )

        # Register User B
        pre, _ = await _get_pre_session_csrf(client)
        login_b = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre},
            json={"username": "user_b", "password": "Password123!"},
        )
        _sync_cookies(client, login_b)
        csrf_b = login_b.json()["csrf_token"]
        reg_opts_b = (
            await client.post(
                "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf_b}
            )
        ).json()
        reg_cred_b = auth_b.create_credential(reg_opts_b, origin=ORIGIN)
        await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf_b},
            json={"credential": reg_cred_b},
        )

        # User A requests assertion options
        pre, _ = await _get_pre_session_csrf(client)
        login_a_2 = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre},
            json={"username": "user_a", "password": "Password123!"},
        )
        _sync_cookies(client, login_a_2)
        csrf_a_2 = login_a_2.json()["csrf_token"]
        auth_opts_a = (
            await client.post(
                "/api/v1/auth/webauthn/authenticate/options", headers={CSRF_HEADER_NAME: csrf_a_2}
            )
        ).json()

        # Sign assertion using User B's credential
        sub_assertion = auth_b.get_assertion(auth_opts_a, origin=ORIGIN, sign_count=1)

        # Present User B's assertion in User A's session
        sub_res = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: csrf_a_2},
            json={"credential": sub_assertion},
        )
        assert sub_res.status_code == 401
        assert sub_res.json()["code"] == "MFA_INVALID"


# --- 7. Security: Clone Detection ---


@pytest.mark.asyncio
async def test_case_7_security_clone_detection(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Test Case 7: Sign counter clone detection (regression flags credential, 0/0 accepted)."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    ws_id, p_id, _ = await _setup_test_admin(
        factory, key_material, username="frank", password="Password123!"
    )
    app, _ = _create_app(factory, key_material, rate_limiter, webauthn_settings)
    transport = httpx.ASGITransport(app=app)
    auth = SoftAuthenticator()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        pre, _ = await _get_pre_session_csrf(client)
        login = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre},
            json={"username": "frank", "password": "Password123!"},
        )
        _sync_cookies(client, login)
        csrf = login.json()["csrf_token"]

        reg_opts = (
            await client.post(
                "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        reg_cred = auth.create_credential(reg_opts, origin=ORIGIN, sign_count=10)
        reg_ok = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": reg_cred},
        )
        assert reg_ok.status_code == 200
        _sync_cookies(client, reg_ok)
        csrf = reg_ok.json()["csrf_token"]

        # Assertion with sign_count=10 (same as stored 10) -> regression detected -> 401 MFA_INVALID
        auth_opts = (
            await client.post(
                "/api/v1/auth/webauthn/authenticate/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        clone_10 = auth.get_assertion(auth_opts, origin=ORIGIN, sign_count=10)
        verify_clone = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": clone_10},
        )
        assert verify_clone.status_code == 401
        assert verify_clone.json()["code"] == "MFA_INVALID"

        # Verify credential flagged in database and activity logged
        async with factory.session(
            RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)
        ) as db_session:
            cred_row = (
                (
                    await db_session.execute(
                        text(
                            "SELECT suspect_clone_at FROM webauthn_credentials "
                            "WHERE principal_id = :p_id"
                        ),
                        {"p_id": p_id},
                    )
                )
                .mappings()
                .first()
            )
            assert cred_row is not None
            assert cred_row["suspect_clone_at"] is not None

            act_row = (
                await db_session.execute(
                    text(
                        "SELECT event_type FROM activity_records "
                        "WHERE event_type = 'WEBAUTHN_SIGN_COUNT_REGRESSION'"
                    )
                )
            ).scalar_one_or_none()
            assert act_row == "WEBAUTHN_SIGN_COUNT_REGRESSION"

    # Test 0/0 authenticator accepted
    auth_zero = SoftAuthenticator()
    _, p_zero, _ = await _setup_test_admin(
        factory, key_material, username="zero_counter_user", password="Password123!"
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client_z:
        pre_z, _ = await _get_pre_session_csrf(client_z)
        login_z = await client_z.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre_z},
            json={"username": "zero_counter_user", "password": "Password123!"},
        )
        _sync_cookies(client_z, login_z)
        csrf_z = login_z.json()["csrf_token"]

        reg_opts_z = (
            await client_z.post(
                "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf_z}
            )
        ).json()
        reg_cred_z = auth_zero.create_credential(reg_opts_z, origin=ORIGIN, sign_count=0)
        reg_ok_z = await client_z.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf_z},
            json={"credential": reg_cred_z},
        )
        assert reg_ok_z.status_code == 200
        _sync_cookies(client_z, reg_ok_z)
        csrf_z = reg_ok_z.json()["csrf_token"]

        # Assert with 0 count -> should accept!
        auth_opts_z = (
            await client_z.post(
                "/api/v1/auth/webauthn/authenticate/options", headers={CSRF_HEADER_NAME: csrf_z}
            )
        ).json()
        auth_cred_z = auth_zero.get_assertion(auth_opts_z, origin=ORIGIN, sign_count=0)
        verify_z = await client_z.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: csrf_z},
            json={"credential": auth_cred_z},
        )
        assert verify_z.status_code == 200
        assert verify_z.json()["verified"] is True


# --- 8. Security: Type Confusion ---


@pytest.mark.asyncio
async def test_case_8_security_type_confusion(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Test Case 8: Type confusion rejection (clientDataJSON type=webauthn.create)."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    _, p_id, _ = await _setup_test_admin(
        factory, key_material, username="grace", password="Password123!"
    )
    app, _ = _create_app(factory, key_material, rate_limiter, webauthn_settings)
    transport = httpx.ASGITransport(app=app)
    auth = SoftAuthenticator()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        pre, _ = await _get_pre_session_csrf(client)
        login = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre},
            json={"username": "grace", "password": "Password123!"},
        )
        _sync_cookies(client, login)
        csrf = login.json()["csrf_token"]

        reg_opts = (
            await client.post(
                "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        reg_cred = auth.create_credential(reg_opts, origin=ORIGIN)
        reg_ok = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": reg_cred},
        )
        assert reg_ok.status_code == 200
        _sync_cookies(client, reg_ok)
        csrf = reg_ok.json()["csrf_token"]

        # Type confusion: send type=webauthn.create during authenticate
        auth_opts = (
            await client.post(
                "/api/v1/auth/webauthn/authenticate/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        confused_assertion = auth.get_assertion(
            auth_opts, origin=ORIGIN, sign_count=1, override_type="webauthn.create"
        )

        verify_res = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": confused_assertion},
        )
        assert verify_res.status_code == 401
        assert verify_res.json()["code"] == "MFA_INVALID"


# --- 9. Boundary: Credential Limit & Nickname Length ---


@pytest.mark.asyncio
async def test_case_9_boundary_credential_limit_and_nickname_length(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Test Case 9: 11th credential -> 409 CREDENTIAL_LIMIT; nickname 65 chars -> 422."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    _, p_id, _ = await _setup_test_admin(
        factory, key_material, username="heidi", password="Password123!"
    )
    app, _ = _create_app(factory, key_material, rate_limiter, webauthn_settings)
    transport = httpx.ASGITransport(app=app)
    auth = SoftAuthenticator()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        pre, _ = await _get_pre_session_csrf(client)
        login = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre},
            json={"username": "heidi", "password": "Password123!"},
        )
        _sync_cookies(client, login)
        csrf = login.json()["csrf_token"]

        # 9a: Nickname 65 characters -> 422
        reg_opts_1 = (
            await client.post(
                "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        cred_1 = auth.create_credential(reg_opts_1, origin=ORIGIN)
        too_long_nick = "a" * 65
        nick_res = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": cred_1, "nickname": too_long_nick},
        )
        assert nick_res.status_code == 422

        # Register first credential properly -> elevates session to AAL2
        reg_ok = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": cred_1, "nickname": "Key 1"},
        )
        assert reg_ok.status_code == 200
        _sync_cookies(client, reg_ok)
        csrf = reg_ok.json()["csrf_token"]

        limit_key = make_key(AUTH_MFA_VERIFY, str(p_id), session_hmac_key=SESSION_HMAC_KEY)

        # Register 9 more credentials (total 10)
        for i in range(2, 11):
            await rate_limiter.reset(AUTH_MFA_VERIFY, limit_key)
            opts_i = (
                await client.post(
                    "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf}
                )
            ).json()
            cred_i = auth.create_credential(opts_i, origin=ORIGIN)
            res_i = await client.post(
                "/api/v1/auth/webauthn/register/verify",
                headers={CSRF_HEADER_NAME: csrf},
                json={"credential": cred_i, "nickname": f"Key {i}"},
            )
            assert res_i.status_code == 200

        # Attempt 11th registration -> 409 CREDENTIAL_LIMIT
        await rate_limiter.reset(AUTH_MFA_VERIFY, limit_key)
        opts_11 = (
            await client.post(
                "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        cred_11 = auth.create_credential(opts_11, origin=ORIGIN)
        res_11 = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": cred_11, "nickname": "Key 11"},
        )
        assert res_11.status_code == 409
        assert res_11.json()["code"] == "CREDENTIAL_LIMIT"


# --- 10. Deletion Invariants ---


@pytest.mark.asyncio
async def test_case_10_deletion_invariants(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Test Case 10: Admin last factor -> 409 LAST_FACTOR; stale AAL2 -> 403 AAL2_STALE."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    ws_id, p_id, _ = await _setup_test_admin(
        factory,
        key_material,
        username="ivan",
        password="Password123!",
        role="SERVER_ADMIN",
    )
    app, session_service = _create_app(factory, key_material, rate_limiter, webauthn_settings)
    transport = httpx.ASGITransport(app=app)
    auth = SoftAuthenticator()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        pre, _ = await _get_pre_session_csrf(client)
        login = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre},
            json={"username": "ivan", "password": "Password123!"},
        )
        _sync_cookies(client, login)
        csrf = login.json()["csrf_token"]

        # Register 2 WebAuthn credentials
        opts_1 = (
            await client.post(
                "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        cred_1 = auth.create_credential(opts_1, origin=ORIGIN)
        reg_1 = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": cred_1, "nickname": "Key 1"},
        )
        assert reg_1.status_code == 200
        _sync_cookies(client, reg_1)
        csrf = reg_1.json()["csrf_token"]
        cred_1_id = reg_1.json()["credential_id"]

        opts_2 = (
            await client.post(
                "/api/v1/auth/webauthn/register/options", headers={CSRF_HEADER_NAME: csrf}
            )
        ).json()
        cred_2 = auth.create_credential(opts_2, origin=ORIGIN)
        reg_2 = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": cred_2, "nickname": "Key 2"},
        )
        assert reg_2.status_code == 200
        cred_2_id = reg_2.json()["credential_id"]
        sess_id = uuid.UUID(reg_1.json()["session_id"])

        # 10a: Stale AAL2 test (> 900s)
        # Age the aal2_verified_at timestamp in database to 901 seconds ago
        async with factory.session(
            RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)
        ) as db_session:
            await db_session.execute(
                text(
                    "UPDATE sessions "
                    "SET aal2_verified_at = clock_timestamp() - interval '901 seconds' "
                    "WHERE id = :sid"
                ),
                {"sid": sess_id},
            )

        stale_del = await client.delete(
            f"/api/v1/auth/webauthn/credentials/{cred_2_id}",
            headers={CSRF_HEADER_NAME: csrf},
        )
        assert stale_del.status_code == 403
        assert stale_del.json()["code"] == "AAL2_STALE"

        # Refresh AAL2 verification timestamp
        async with factory.session(
            RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)
        ) as db_session:
            await db_session.execute(
                text("UPDATE sessions SET aal2_verified_at = clock_timestamp() WHERE id = :sid"),
                {"sid": sess_id},
            )

        # 10b: Delete Key 2 (now 1 factor remaining) -> should succeed
        del_2 = await client.delete(
            f"/api/v1/auth/webauthn/credentials/{cred_2_id}",
            headers={CSRF_HEADER_NAME: csrf},
        )
        assert del_2.status_code == 200
        assert del_2.json()["deleted"] is True

        # 10c: Attempt to delete Key 1 (last factor for admin) -> 409 LAST_FACTOR
        del_1 = await client.delete(
            f"/api/v1/auth/webauthn/credentials/{cred_1_id}",
            headers={CSRF_HEADER_NAME: csrf},
        )
        assert del_1.status_code == 409
        assert del_1.json()["code"] == "LAST_FACTOR"


# --- 11. Configuration Validation ---


def test_case_11_configuration_validation() -> None:
    """Test Case 11: RP ID mismatch fails startup; http outside standalone fails startup."""
    # 11a: RP ID not a suffix of origin host
    with pytest.raises(ValueError, match="is not a valid suffix of origin host"):
        Settings(
            deployment_mode="production",
            public_origin="https://kanban.other.org",
            webauthn_rp_id="example.com",
        )

    # 11b: http:// origin outside standalone
    with pytest.raises(ValueError, match="forbidden outside standalone mode"):
        Settings(
            deployment_mode="production",
            public_origin="http://kanban.example.com",
            webauthn_rp_id="kanban.example.com",
        )

    # 11c: http:// in standalone mode permitted
    s_standalone = Settings(
        deployment_mode="standalone",
        public_origin="http://localhost:8080",
        webauthn_rp_id="localhost",
    )
    assert s_standalone.effective_rp_id == "localhost"
    assert s_standalone.effective_origin == "http://localhost:8080"


# --- Additional branch coverage tests for WebAuthn API and Service ---


def test_helpers_fallback_branches() -> None:
    """Test helper functions fallback branches in auth_webauthn."""
    # 1. _get_webauthn_service with settings present
    app1 = FastAPI()
    app1.state.settings = Settings(
        deployment_mode="production",
        public_origin=ORIGIN,
        webauthn_rp_id=RP_ID,
        webauthn_rp_name="Test RP",
    )
    req1 = Request({"type": "http", "app": app1})
    svc1 = _get_webauthn_service(req1)
    assert svc1.rp_id == RP_ID
    assert svc1.rp_name == "Test RP"
    # Cached service branch
    assert _get_webauthn_service(req1) is svc1

    # 2. _get_webauthn_service with settings None
    app2 = FastAPI()
    req2 = Request({"type": "http", "app": app2})
    svc2 = _get_webauthn_service(req2)
    assert svc2.rp_name == "👍kanban"

    # 3. _get_rate_limiter caching and fallback
    limiter = _get_rate_limiter(req2)
    assert limiter is not None
    assert _get_rate_limiter(req2) is limiter

    app3 = FastAPI()
    app3.state.session_factory = type("DummyFactory", (), {"engine": None})()
    req3 = Request({"type": "http", "app": app3})
    rl3 = _get_rate_limiter(req3)
    assert rl3 is not None

    # 4. _build_elevated_response with elevated is None
    resp = _build_elevated_response(None, uuid.uuid4(), {"extra": 123})
    assert b"set-cookie" not in [h[0] for h in resp.raw_headers]
    resp_none = _build_elevated_response(None, uuid.uuid4(), None)
    assert resp_none.status_code == 200


@pytest.mark.asyncio
async def test_auth_webauthn_endpoint_guard_branches(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Test session null guards and missing state errors in endpoint handlers."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    app, session_service = _create_app(factory, key_material, rate_limiter, webauthn_settings)

    req_valid = Request({"type": "http", "app": app})
    app_no_factory = FastAPI()
    app_no_factory.state.session_service = session_service
    app_no_factory.state.rate_limiter = rate_limiter
    req_no_factory = Request({"type": "http", "app": app_no_factory})

    app_no_service = FastAPI()
    app_no_service.state.session_factory = factory
    app_no_service.state.rate_limiter = rate_limiter
    req_no_service = Request({"type": "http", "app": app_no_service})

    p_no_sess = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        aal_level=2,
        session_id=None,
    )
    p_with_sess = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        aal_level=2,
        session_id=uuid.uuid4(),
    )

    # 1. register_options guards
    with pytest.raises(ProblemException) as exc:
        await register_options(req_valid, p_no_sess)
    assert exc.value.status == 401
    assert exc.value.code == "UNAUTHENTICATED"

    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await register_options(req_no_factory, p_with_sess)

    # 2. register_verify guards
    with pytest.raises(ProblemException) as exc:
        await register_verify(req_valid, p_no_sess)
    assert exc.value.status == 401

    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await register_verify(req_no_factory, p_with_sess)

    with pytest.raises(RuntimeError, match="Session service is not configured"):
        await register_verify(req_no_service, p_with_sess)

    # 3. authenticate_options guards
    with pytest.raises(ProblemException) as exc:
        await authenticate_options(req_valid, p_no_sess)
    assert exc.value.status == 401

    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await authenticate_options(req_no_factory, p_with_sess)

    # 4. authenticate_verify guards
    with pytest.raises(ProblemException) as exc:
        await authenticate_verify(req_valid, p_no_sess)
    assert exc.value.status == 401

    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await authenticate_verify(req_no_factory, p_with_sess)

    with pytest.raises(RuntimeError, match="Session service is not configured"):
        await authenticate_verify(req_no_service, p_with_sess)

    # 5. list_credentials guard
    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await list_credentials(req_no_factory, p_with_sess)

    # 6. delete_credential guard
    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await delete_credential(uuid.uuid4(), req_no_factory, p_with_sess)


@pytest.mark.asyncio
async def test_auth_webauthn_authorization_and_validation_branches(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Test AAL2 authorization checks, request validation errors, and display_name fallback."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    ws_id, p_id, _ = await _setup_test_admin(
        factory, key_material, username="bob_admin", password="Password123!"
    )
    app, session_service = _create_app(factory, key_material, rate_limiter, webauthn_settings)

    # Create session for Bob
    async with factory.session(RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)) as s:
        issued_mfa_pending = await session_service.create_after_login(
            s,
            principal_id=p_id,
            workspace_id=ws_id,
            aal_level=1,
            mfa_pending=True,
        )
        issued_aal1 = await session_service.create_after_login(
            s,
            principal_id=p_id,
            workspace_id=ws_id,
            aal_level=1,
            mfa_pending=False,
        )

    # 1. Non-mfa_pending AAL1 user attempting register_options -> 403 AAL2_REQUIRED
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(SESSION_COOKIE_NAME, issued_aal1.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, issued_aal1.csrf_token)
        res_opts = await client.post(
            "/api/v1/auth/webauthn/register/options",
            headers={CSRF_HEADER_NAME: issued_aal1.csrf_token},
        )
        assert res_opts.status_code == 403
        assert res_opts.json()["code"] == "AAL2_REQUIRED"

        # Non-mfa_pending AAL1 user attempting register_verify -> 403 AAL2_REQUIRED
        res_ver = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: issued_aal1.csrf_token},
            json={"credential": {}},
        )
        assert res_ver.status_code == 403
        assert res_ver.json()["code"] == "AAL2_REQUIRED"

    # 2. Display name fallback for principal without local_admin_credentials
    non_local_p_id = uuid.uuid4()
    async with factory.session(
        RLSContext(principal_id=non_local_p_id, workspace_id=ws_id, aal_level=2)
    ) as s:
        await s.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', 'OAuth User')"
            ),
            {"id": non_local_p_id, "ws_id": ws_id},
        )
        issued_non_local = await session_service.create_after_login(
            s,
            principal_id=non_local_p_id,
            workspace_id=ws_id,
            aal_level=2,
            mfa_pending=False,
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(SESSION_COOKIE_NAME, issued_non_local.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, issued_non_local.csrf_token)
        res = await client.post(
            "/api/v1/auth/webauthn/register/options",
            headers={CSRF_HEADER_NAME: issued_non_local.csrf_token},
        )
        assert res.status_code == 200
        assert res.json()["user"]["name"] == "OAuth User"

    # 3. Enrolled principal attempting 2nd factor while mfa_pending -> 403 AAL2_REQUIRED
    # Bob enrolls 1st credential:
    auth = SoftAuthenticator()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(SESSION_COOKIE_NAME, issued_mfa_pending.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, issued_mfa_pending.csrf_token)
        opts = (
            await client.post(
                "/api/v1/auth/webauthn/register/options",
                headers={CSRF_HEADER_NAME: issued_mfa_pending.csrf_token},
            )
        ).json()
        cred = auth.create_credential(opts, origin=ORIGIN)
        reg = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: issued_mfa_pending.csrf_token},
            json={"credential": cred},
        )
        assert reg.status_code == 200

        # Now Bob creates another mfa_pending session (e.g. logging in again)
        async with factory.session(
            RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)
        ) as s:
            bob_pending_2 = await session_service.create_after_login(
                s,
                principal_id=p_id,
                workspace_id=ws_id,
                aal_level=1,
                mfa_pending=True,
            )

        client.cookies.set(SESSION_COOKIE_NAME, bob_pending_2.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, bob_pending_2.csrf_token)
        # Attempt register_options with mfa_pending when already has credential -> 403 AAL2_REQUIRED
        opts_fail = await client.post(
            "/api/v1/auth/webauthn/register/options",
            headers={CSRF_HEADER_NAME: bob_pending_2.csrf_token},
        )
        assert opts_fail.status_code == 403
        assert opts_fail.json()["code"] == "AAL2_REQUIRED"

        # Attempt register_verify with mfa_pending when already has credential -> 403 AAL2_REQUIRED
        ver_fail = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: bob_pending_2.csrf_token},
            json={"credential": {}},
        )
        assert ver_fail.status_code == 403
        assert ver_fail.json()["code"] == "AAL2_REQUIRED"

    # 4. Request validation error branches in register_verify and authenticate_verify
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(SESSION_COOKIE_NAME, issued_non_local.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, issued_non_local.csrf_token)
        csrf = issued_non_local.csrf_token

        # Register verify: Malformed JSON body
        bad_json = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf, "Content-Type": "application/json"},
            content=b"{not valid json",
        )
        assert bad_json.status_code == 422
        assert bad_json.json()["code"] == "VALIDATION_ERROR"

        # Register verify: Body not a dict (e.g. JSON array)
        array_body = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json=[1, 2, 3],
        )
        assert array_body.status_code == 422
        assert array_body.json()["code"] == "VALIDATION_ERROR"

        # Register verify: Credential payload not a dict
        bad_cred = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": "not-a-dict"},
        )
        assert bad_cred.status_code == 422

        # Authenticate verify: Malformed JSON body
        bad_json_auth = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: csrf, "Content-Type": "application/json"},
            content=b"{not valid json",
        )
        assert bad_json_auth.status_code == 422

        # Authenticate verify: Body not a dict
        array_auth = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json=[1, 2, 3],
        )
        assert array_auth.status_code == 422

        # Reset limiter before checking credential payload validation
        limit_key = make_key(
            AUTH_MFA_VERIFY,
            str(non_local_p_id),
            session_hmac_key=session_service.session_hmac_key,
        )
        await rate_limiter.reset(AUTH_MFA_VERIFY, limit_key)

        # Authenticate verify: Credential payload not a dict
        bad_cred_auth = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": "not-a-dict"},
        )
        assert bad_cred_auth.status_code == 422

        # 5. Rate limit hit branches on register_verify and authenticate_verify
        # Saturate rate limiter for non_local_p_id
        for _ in range(5):
            await rate_limiter.hit(AUTH_MFA_VERIFY, limit_key)

        rl_reg = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": {}},
        )
        assert rl_reg.status_code == 429
        assert rl_reg.json()["code"] == "RATE_LIMITED"

        rl_auth = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: csrf},
            json={"credential": {}},
        )
        assert rl_auth.status_code == 429
        assert rl_auth.json()["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_auth_webauthn_service_direct_edge_cases(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test service error branches: missing client data, invalid types, bad base64, missing keys."""
    import base64
    import json

    factory = RLSSessionFactory(pg_worker_db)
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()
    sess_id = uuid.uuid4()
    svc = WebauthnService(
        rp_id=webauthn_settings.effective_rp_id,
        rp_name=webauthn_settings.webauthn_rp_name,
        expected_origin=webauthn_settings.effective_origin,
    )

    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)
    async with factory.session(ctx) as session:
        await session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:8]}", "name": "Direct Test WS"},
        )
        await session.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', 'Direct User')"
            ),
            {"id": p_id, "ws_id": ws_id},
        )
        session_service = SessionService(key_material.session_hmac_key)
        issued = await session_service.create_after_login(
            session,
            principal_id=p_id,
            workspace_id=ws_id,
            aal_level=2,
            mfa_pending=False,
        )
        sess_id = issued.session_id

        # Positive registration and authentication without workspace_id
        opts = await svc.registration_options(
            session,
            session_id=sess_id,
            principal_id=p_id,
            username="direct_user",
        )
        auth = SoftAuthenticator()
        reg_cred_no_ws = auth.create_credential(opts, origin=ORIGIN)
        rec = await svc.verify_registration(
            session,
            session_id=sess_id,
            principal_id=p_id,
            credential_payload=reg_cred_no_ws,
            workspace_id=None,
        )
        assert rec is not None

        auth_opts = await svc.authentication_options(
            session,
            session_id=sess_id,
            principal_id=p_id,
        )
        assert_cred_no_ws = auth.get_assertion(
            auth_opts,
            credential_id=rec.credential_id,
            origin=ORIGIN,
            sign_count=1,
        )
        rec_auth, sc = await svc.verify_authentication(
            session,
            session_id=sess_id,
            principal_id=p_id,
            credential_payload=assert_cred_no_ws,
            workspace_id=None,
        )
        assert rec_auth is not None
        assert sc == 1

        # Test clone detection with workspace_id=None
        auth_opts_clone = await svc.authentication_options(
            session,
            session_id=sess_id,
            principal_id=p_id,
        )
        assert_cred_clone = auth.get_assertion(
            auth_opts_clone,
            credential_id=rec.credential_id,
            origin=ORIGIN,
            sign_count=1,
        )
        with pytest.raises(WebauthnCloneDetectedError):
            await svc.verify_authentication(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload=assert_cred_clone,
                workspace_id=None,
            )

        # Test aaguid invalid UUID branch in verify_registration
        from unittest.mock import MagicMock

        mock_verified = MagicMock()
        mock_verified.credential_id = b"mock_cred_id_32b_length_val_pad"
        mock_verified.credential_public_key = b"mock_pub_key"
        mock_verified.sign_count = 0
        mock_verified.aaguid = "invalid-uuid-string"

        opts_m = await svc.registration_options(
            session, session_id=sess_id, principal_id=p_id, username="direct_user"
        )
        reg_cred_m = auth.create_credential(opts_m, origin=ORIGIN)
        monkeypatch.setattr(
            "kanban.auth.mfa.webauthn.verify_registration_response",
            lambda **kw: mock_verified,
        )
        rec_m = await svc.verify_registration(
            session,
            session_id=sess_id,
            principal_id=p_id,
            credential_payload=reg_cred_m,
            workspace_id=None,
        )
        assert rec_m.aaguid is None
        monkeypatch.undo()

        # Test unexpected DB exception re-raise in verify_registration
        opts_err = await svc.registration_options(
            session, session_id=sess_id, principal_id=p_id, username="direct_user"
        )
        reg_cred_err = auth.create_credential(opts_err, origin=ORIGIN)
        orig_execute = session.execute

        async def mock_execute(
            statement: Any,  # noqa: ANN401
            params: Any = None,  # noqa: ANN401
            *args: Any,  # noqa: ANN401
            **kwargs: Any,  # noqa: ANN401
        ) -> Any:  # noqa: ANN401
            if "webauthn_credential_create" in str(statement):
                raise RuntimeError("Unexpected DB failure")
            return await orig_execute(statement, params, *args, **kwargs)

        monkeypatch.setattr(session, "execute", mock_execute)
        with pytest.raises(RuntimeError, match="Unexpected DB failure"):
            await svc.verify_registration(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload=reg_cred_err,
                workspace_id=None,
            )
        monkeypatch.undo()

        # 1. verify_registration: nickname length check directly on service
        with pytest.raises(ProblemException) as exc:
            await svc.verify_registration(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={},
                nickname="n" * 65,
            )
        assert exc.value.status == 422

        # 2. verify_registration: missing response dict
        with pytest.raises(ProblemException) as exc:
            await svc.verify_registration(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={},
            )
        assert exc.value.status == 401

        # 3. verify_registration: missing clientDataJSON
        with pytest.raises(ProblemException) as exc:
            await svc.verify_registration(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={"response": {}},
            )
        assert exc.value.status == 401

        # 4. verify_registration: invalid clientDataJSON (malformed json / missing challenge)
        with pytest.raises(ProblemException) as exc:
            await svc.verify_registration(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={"response": {"clientDataJSON": "bm90LWpzb24"}},  # "not-json"
            )
        assert exc.value.status == 401

        # 5. verify_registration: non-existent challenge in database (already consumed or missing)
        dummy_client_data = (
            base64.urlsafe_b64encode(
                json.dumps({"type": "webauthn.create", "challenge": "dGVzdC1jaGFsbGVuZ2U"}).encode()
            )
            .decode()
            .rstrip("=")
        )
        with pytest.raises(ProblemException) as exc:
            await svc.verify_registration(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={"response": {"clientDataJSON": dummy_client_data}},
            )
        assert exc.value.status == 401

        # 5b. verify_registration: missing challenge in clientDataJSON
        no_chal_reg = (
            base64.urlsafe_b64encode(json.dumps({"type": "webauthn.create"}).encode())
            .decode()
            .rstrip("=")
        )
        with pytest.raises(ProblemException) as exc:
            await svc.verify_registration(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={"response": {"clientDataJSON": no_chal_reg}},
            )
        assert exc.value.status == 401

        # 5c. verify_registration: type confusion in clientDataJSON
        wrong_type_reg = (
            base64.urlsafe_b64encode(
                json.dumps({"type": "webauthn.get", "challenge": "dGVzdC1jaGFsbGVuZ2U"}).encode()
            )
            .decode()
            .rstrip("=")
        )
        with pytest.raises(ProblemException) as exc:
            await svc.verify_registration(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={"response": {"clientDataJSON": wrong_type_reg}},
            )
        assert exc.value.status == 401

        # 6. verify_authentication: missing response dict
        with pytest.raises(ProblemException) as exc:
            await svc.verify_authentication(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={},
            )
        assert exc.value.status == 401

        # 7. verify_authentication: missing clientDataJSON
        with pytest.raises(ProblemException) as exc:
            await svc.verify_authentication(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={"response": {}},
            )
        assert exc.value.status == 401

        # 8. verify_authentication: malformed clientDataJSON
        with pytest.raises(ProblemException) as exc:
            await svc.verify_authentication(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={"response": {"clientDataJSON": "bm90LWpzb24"}},
            )
        assert exc.value.status == 401

        # 8b. verify_authentication: missing challenge in clientDataJSON
        no_chal_auth = (
            base64.urlsafe_b64encode(json.dumps({"type": "webauthn.get"}).encode())
            .decode()
            .rstrip("=")
        )
        with pytest.raises(ProblemException) as exc:
            await svc.verify_authentication(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={"response": {"clientDataJSON": no_chal_auth}},
            )
        assert exc.value.status == 401

        # 9. verify_authentication: missing challenge in db
        auth_client_data = (
            base64.urlsafe_b64encode(
                json.dumps({"type": "webauthn.get", "challenge": "dGVzdC1jaGFsbGVuZ2U"}).encode()
            )
            .decode()
            .rstrip("=")
        )
        with pytest.raises(ProblemException) as exc:
            await svc.verify_authentication(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={"response": {"clientDataJSON": auth_client_data}},
            )
        assert exc.value.status == 401

        # 10. verify_authentication: missing credential id
        chal_bytes_32 = b"c" * 32
        await session.execute(
            text("SELECT kb_auth.webauthn_challenge_create(:sid, 'authenticate', :chal)"),
            {"sid": sess_id, "chal": chal_bytes_32},
        )
        chal_b64 = base64.urlsafe_b64encode(chal_bytes_32).decode().rstrip("=")
        valid_chal_client_data = (
            base64.urlsafe_b64encode(
                json.dumps({"type": "webauthn.get", "challenge": chal_b64}).encode()
            )
            .decode()
            .rstrip("=")
        )

        with pytest.raises(ProblemException) as exc:
            await svc.verify_authentication(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={"response": {"clientDataJSON": valid_chal_client_data}},
            )
        assert exc.value.status == 401

        # 10b. verify_authentication: invalid base64 in rawId
        await session.execute(
            text("SELECT kb_auth.webauthn_challenge_create(:sid, 'authenticate', :chal)"),
            {"sid": sess_id, "chal": chal_bytes_32},
        )
        with pytest.raises(ProblemException) as exc:
            await svc.verify_authentication(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={
                    "id": "a",
                    "response": {"clientDataJSON": valid_chal_client_data},
                },
            )
        assert exc.value.status == 401

        # 10c. verify_authentication: suspect clone already flagged
        cred_uuid = uuid.uuid4()
        raw_cred_bytes = b"k" * 32
        raw_cred_b64 = base64.urlsafe_b64encode(raw_cred_bytes).decode().rstrip("=")
        await session.execute(
            text(
                "INSERT INTO webauthn_credentials "
                "(id, principal_id, credential_id, public_key, sign_count, suspect_clone_at) "
                "VALUES (:id, :p_id, :cred_id, :pub_key, 5, clock_timestamp())"
            ),
            {
                "id": cred_uuid,
                "p_id": p_id,
                "cred_id": raw_cred_bytes,
                "pub_key": b"pk",
            },
        )
        await session.execute(
            text("SELECT kb_auth.webauthn_challenge_create(:sid, 'authenticate', :chal)"),
            {"sid": sess_id, "chal": chal_bytes_32},
        )
        with pytest.raises(ProblemException) as exc:
            await svc.verify_authentication(
                session,
                session_id=sess_id,
                principal_id=p_id,
                credential_payload={
                    "id": raw_cred_b64,
                    "response": {"clientDataJSON": valid_chal_client_data},
                },
            )
        assert exc.value.status == 401

        # 11. delete_credential: not found
        with pytest.raises(ProblemException) as exc:
            await svc.delete_credential(
                session,
                principal_id=p_id,
                credential_id=uuid.uuid4(),
                is_admin=False,
            )
        assert exc.value.status == 404
        assert exc.value.code == "NOT_FOUND"

        # 11b. delete_credential: non-admin deleting single credential succeeds
        non_admin_cred_id = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO webauthn_credentials "
                "(id, principal_id, credential_id, public_key, sign_count) "
                "VALUES (:id, :p_id, :cred_id, :pub_key, 0)"
            ),
            {
                "id": non_admin_cred_id,
                "p_id": p_id,
                "cred_id": b"na" * 16,
                "pub_key": b"pk",
            },
        )
        await svc.delete_credential(
            session,
            principal_id=p_id,
            credential_id=non_admin_cred_id,
            is_admin=False,
            workspace_id=ws_id,
        )
        count = await session.execute(
            text("SELECT count(*) FROM webauthn_credentials WHERE id = :id"),
            {"id": non_admin_cred_id},
        )
        assert count.scalar_one() == 0

        # 11c. delete_credential without workspace_id
        non_admin_cred_id2 = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO webauthn_credentials "
                "(id, principal_id, credential_id, public_key, sign_count) "
                "VALUES (:id, :p_id, :cred_id, :pub_key, 0)"
            ),
            {
                "id": non_admin_cred_id2,
                "p_id": p_id,
                "cred_id": b"na2" * 10,
                "pub_key": b"pk",
            },
        )
        await svc.delete_credential(
            session,
            principal_id=p_id,
            credential_id=non_admin_cred_id2,
            is_admin=False,
            workspace_id=None,
        )
        count2 = await session.execute(
            text("SELECT count(*) FROM webauthn_credentials WHERE id = :id"),
            {"id": non_admin_cred_id2},
        )
        assert count2.scalar_one() == 0
