# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: S106, S107
"""Unit and integration tests for RFC 6238 TOTP factor lifecycle.

Covers security, replay rejection, concurrency, and hygiene (KB-P2-05a).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
import uuid
from typing import TYPE_CHECKING, Annotated, Final

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import NullPool, text
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.responses import JSONResponse

from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext  # noqa: TC001
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.auth.cards.repository import admin_upsert
from kanban.auth.local.hashing import hash_password_sync
from kanban.auth.mfa.totp import (
    TotpService,
    totp_at,
    verify_totp,
)
from kanban.auth.sessions.cookies import SESSION_COOKIE_NAME
from kanban.auth.sessions.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, CsrfMiddleware
from kanban.auth.sessions.resolver import SessionCookieResolver, require_full_session
from kanban.auth.sessions.service import SessionService
from kanban.security.envelope import StaticKekProvider
from kanban.security.keys import KeyMaterial
from kanban.security.ratelimit import AUTH_MFA_VERIFY, make_key
from kanban.security.ratelimit.pg import PgRateLimiter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

PEPPER_KEY: Final[bytes] = b"p" * 32
SESSION_HMAC_KEY: Final[bytes] = b"s" * 32
MASTER_KEK: Final[bytes] = b"k" * 32


@pytest.fixture
def key_material() -> KeyMaterial:
    """Provide testing key material."""
    return KeyMaterial(
        master_kek=MASTER_KEK,
        master_kek_kid="kek-v1",
        auth_pepper=PEPPER_KEY,
        session_hmac_key=SESSION_HMAC_KEY,
    )


def test_case_1_rfc6238_appendix_b_vectors() -> None:
    """Test Case 1: RFC 6238 Appendix B test vectors (SHA-1 seed, 6 digits)."""
    seed = b"12345678901234567890"  # 20 bytes SHA-1 seed from RFC 6238 Appendix B
    vectors = [
        (59, "287082"),
        (1111111109, "081804"),
        (1111111111, "050471"),
        (1234567890, "005924"),
        (2000000000, "279037"),
        (20000000000, "353130"),
    ]
    for timestamp, expected in vectors:
        calculated = totp_at(seed, timestamp, digits=6)
        err = f"Failed vector at timestamp {timestamp}: expected {expected}, got {calculated}"
        assert calculated == expected, err


def test_case_5_window_boundaries() -> None:
    """Test Case 5: Codes for s-1, s, s+1 accept with fresh factor; s-2, s+2 reject."""
    secret = b"12345678901234567890"
    current_time = 1234567890
    current_step = current_time // 30

    code_s_minus_2 = totp_at(secret, (current_step - 2) * 30)
    code_s_minus_1 = totp_at(secret, (current_step - 1) * 30)
    code_s = totp_at(secret, current_step * 30)
    code_s_plus_1 = totp_at(secret, (current_step + 1) * 30)
    code_s_plus_2 = totp_at(secret, (current_step + 2) * 30)

    # Acceptance window [s-1, s+1] with last_accepted_step = 0
    ok, step = verify_totp(secret, code_s_minus_1, last_accepted_step=0, timestamp=current_time)
    assert ok is True
    assert step == current_step - 1

    ok, step = verify_totp(secret, code_s, last_accepted_step=0, timestamp=current_time)
    assert ok is True
    assert step == current_step

    ok, step = verify_totp(secret, code_s_plus_1, last_accepted_step=0, timestamp=current_time)
    assert ok is True
    assert step == current_step + 1

    # Boundaries outside window reject
    ok, _ = verify_totp(secret, code_s_minus_2, last_accepted_step=0, timestamp=current_time)
    assert ok is False

    ok, _ = verify_totp(secret, code_s_plus_2, last_accepted_step=0, timestamp=current_time)
    assert ok is False


def test_case_6_format_rejection() -> None:
    """Test Case 6: Malformed formats reject immediately without HMAC computation."""
    secret = b"12345678901234567890"
    malformed_inputs = [
        "12345",
        "1234567",
        "12 3456",
        "١٢٣٤٥٦",  # Arabic-Indic digits
        "abcdef",
        "12345a",
        "",
    ]
    for inp in malformed_inputs:
        ok, step = verify_totp(secret, inp, last_accepted_step=0, timestamp=1234567890)
        assert ok is False
        assert step == 0


async def _setup_test_admin(
    factory: RLSSessionFactory,
    key_material: KeyMaterial,
    *,
    username: str = "superadmin",
    password: str = "AdminPassword456!",
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Provision workspace, local admin credential, and card in database."""
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()
    card_id = uuid.uuid4()

    pw_hash = hash_password_sync(password, key_material.auth_pepper)
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)

    async with factory.session(ctx) as session:
        # Clean up any leftover LOCAL_ADMIN cards from previous test cases:
        await session.execute(
            text(
                "UPDATE principals SET status = 'DISABLED' WHERE id IN ("
                "  SELECT principal_id FROM role_bindings WHERE role = 'SERVER_ADMIN'"
                ")"
            )
        )
        await session.execute(
            text("DELETE FROM auth_provider_cards WHERE provider_kind = 'LOCAL_ADMIN'")
        )
        await session.execute(text("DELETE FROM local_admin_credentials"))

        await session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "TOTP Admin WS"},
        )
        await session.execute(
            text(
                "SELECT register_object("
                "'user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
            ),
            {"ws_id": ws_id, "ckey": f"usr-{p_id.hex}", "title": "TOTP Admin", "u_id": p_id},
        )
        await session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'TOTP Admin', 'ACTIVE')"
            ),
            {"id": p_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, :email)"
            ),
            {"id": p_id, "ws_id": ws_id, "email": f"{username}-{ws_id.hex[:6]}@example.com"},
        )
        await session.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
            ),
            {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": p_id},
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
) -> tuple[FastAPI, SessionService]:
    """Create test FastAPI application configured with auth routes."""
    session_service = SessionService(key_material.session_hmac_key)
    app = FastAPI(title="TOTP Test App")
    app.state.session_service = session_service
    app.state.session_factory = factory
    app.state.key_material = key_material
    app.state.rate_limiter = rate_limiter
    app.state.kek_provider = StaticKekProvider(
        {key_material.master_kek_kid: key_material.master_kek},
        current=key_material.master_kek_kid,
    )

    resolver = SessionCookieResolver(session_service, factory)
    app.state.principal_resolver = resolver
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    v1 = build_v1_router()
    app.include_router(v1, prefix="/api/v1")

    # Protected view enforcing non-mfa_pending session
    @app.get("/api/v1/protected/resource")
    async def protected_resource(
        principal: Annotated[PrincipalContext, Depends(require_full_session)],
    ) -> JSONResponse:
        return JSONResponse({"status": "allowed", "principal_id": str(principal.principal_id)})

    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_middleware(RequestIdMiddleware)

    return app, session_service


async def _get_pre_session_csrf(client: httpx.AsyncClient) -> tuple[str, str]:
    """Retrieve pre-session CSRF token and cookie from GET /api/v1/auth/session."""
    res = await client.get("/api/v1/auth/session")
    assert res.status_code == 200
    token = str(res.json()["csrf_token"])
    csrf_cookie = str(res.cookies.get(CSRF_COOKIE_NAME, token) or token)
    return token, csrf_cookie


@pytest.mark.asyncio
async def test_case_2_positive_lifecycle(  # noqa: PLR0915
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 2: Positive factor lifecycle.

    enroll -> confirm -> logout -> local login -> verify TOTP -> session rotated,
    aal_level=2, mfa_pending=FALSE.
    """
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    _ws_id, _p_id, _ = await _setup_test_admin(
        factory, key_material, username="alice", password="Password123!"
    )

    app, _session_service = _create_app(factory, key_material, rate_limiter)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Pre-session CSRF
        pre_token, pre_cookie = await _get_pre_session_csrf(client)
        client.cookies.set(CSRF_COOKIE_NAME, pre_cookie)

        # 1. Login with local credentials -> yields initial session
        login_res = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre_token},
            json={"username": "alice", "password": "Password123!"},
        )
        assert login_res.status_code == 200, login_res.text
        login_data = login_res.json()
        assert login_data["authenticated"] is True
        login_data["session_id"]
        csrf_token = login_data["csrf_token"]
        client.cookies.set(CSRF_COOKIE_NAME, csrf_token)
        if SESSION_COOKIE_NAME in login_res.cookies:
            client.cookies.set(SESSION_COOKIE_NAME, login_res.cookies[SESSION_COOKIE_NAME])
        headers = {CSRF_HEADER_NAME: csrf_token}

        # 2. Enroll TOTP factor
        enroll_res = await client.post("/api/v1/auth/mfa/totp/enroll", headers=headers)
        assert enroll_res.status_code == 200, enroll_res.text
        enroll_data = enroll_res.json()
        secret_b32 = enroll_data["secret"]
        secret_bytes = base64.b32decode(secret_b32)
        assert len(secret_bytes) == 20

        # 3. Confirm pending factor with current code
        now_ts = int(time.time())
        valid_code = totp_at(secret_bytes, now_ts)
        confirm_res = await client.post(
            "/api/v1/auth/mfa/totp/confirm",
            headers=headers,
            json={"code": valid_code},
        )
        assert confirm_res.status_code == 200, confirm_res.text
        assert confirm_res.json()["confirmed"] is True

        # 4. Logout
        logout_res = await client.post("/api/v1/auth/logout", headers=headers)
        assert logout_res.status_code == 200

        # 5. Local login again -> produces mfa_pending=True session
        pre_tok2, pre_cook2 = await _get_pre_session_csrf(client)
        client.cookies.set(CSRF_COOKIE_NAME, pre_cook2)
        login_res2 = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: pre_tok2},
            json={"username": "alice", "password": "Password123!"},
        )
        assert login_res2.status_code == 200
        l2_data = login_res2.json()
        assert l2_data["mfa_pending"] is True
        assert l2_data["aal_level"] == 1
        pending_session_id = l2_data["session_id"]
        csrf2 = l2_data["csrf_token"]
        client.cookies.set(CSRF_COOKIE_NAME, csrf2)
        if SESSION_COOKIE_NAME in login_res2.cookies:
            client.cookies.set(SESSION_COOKIE_NAME, login_res2.cookies[SESSION_COOKIE_NAME])
        headers2 = {CSRF_HEADER_NAME: csrf2}

        # Protected resource rejects mfa_pending session
        prot_res = await client.get("/api/v1/protected/resource", headers=headers2)
        assert prot_res.status_code == 403
        assert prot_res.json()["code"] == "MFA_REQUIRED"

        # 6. Verify TOTP factor -> elevates session to AAL2, clears mfa_pending, rotates session id
        now_ts2 = int(time.time()) + 30
        verify_code = totp_at(secret_bytes, now_ts2)
        v_res = await client.post(
            "/api/v1/auth/mfa/verify",
            headers=headers2,
            json={"method": "totp", "code": verify_code},
        )
        assert v_res.status_code == 200, v_res.text
        v_data = v_res.json()
        assert v_data["verified"] is True
        assert v_data["aal_level"] == 2
        assert v_data["session_id"] != pending_session_id

        # Update cookies and CSRF from verification response
        client.cookies.clear()
        for c in v_res.cookies.jar:
            client.cookies.set(c.name, c.value or "")
        elevated_headers = {CSRF_HEADER_NAME: v_data["csrf_token"]}

        # 7. Protected resource now permits access with elevated AAL2 session
        prot_res2 = await client.get("/api/v1/protected/resource", headers=elevated_headers)
        assert prot_res2.status_code == 200
        assert prot_res2.json()["status"] == "allowed"


@pytest.mark.asyncio
async def test_case_3_replay_rejection(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 3: Replay rejection.

    Same code submitted twice within its 30s step -> second 401 MFA_INVALID;
    s-1 after s -> 401.
    """
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    _ws_id, _p_id, _ = await _setup_test_admin(
        factory, key_material, username="bob", password="Password123!"
    )

    app, _session_service = _create_app(factory, key_material, rate_limiter)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Login and enroll
        tok1, cook1 = await _get_pre_session_csrf(client)
        client.cookies.set(CSRF_COOKIE_NAME, cook1)
        l_res = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: tok1},
            json={"username": "bob", "password": "Password123!"},
        )
        assert l_res.status_code == 200, l_res.text
        csrf = l_res.json()["csrf_token"]
        client.cookies.set(CSRF_COOKIE_NAME, csrf)
        if SESSION_COOKIE_NAME in l_res.cookies:
            client.cookies.set(SESSION_COOKIE_NAME, l_res.cookies[SESSION_COOKIE_NAME])
        headers = {CSRF_HEADER_NAME: csrf}

        en_res = await client.post("/api/v1/auth/mfa/totp/enroll", headers=headers)
        assert en_res.status_code == 200, en_res.text
        secret_bytes = base64.b32decode(en_res.json()["secret"])

        now_ts = int(time.time())
        conf_code = totp_at(secret_bytes, now_ts)
        await client.post(
            "/api/v1/auth/mfa/totp/confirm",
            headers=headers,
            json={"code": conf_code},
        )

        # Login to get mfa_pending session
        tok2, cook2 = await _get_pre_session_csrf(client)
        client.cookies.set(CSRF_COOKIE_NAME, cook2)
        l_res2 = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: tok2},
            json={"username": "bob", "password": "Password123!"},
        )
        assert l_res2.status_code == 200, l_res2.text
        csrf2 = l_res2.json()["csrf_token"]
        client.cookies.set(CSRF_COOKIE_NAME, csrf2)
        if SESSION_COOKIE_NAME in l_res2.cookies:
            client.cookies.set(SESSION_COOKIE_NAME, l_res2.cookies[SESSION_COOKIE_NAME])
        headers2 = {CSRF_HEADER_NAME: csrf2}

        # Step s
        step_s_ts = now_ts + 30
        code_s = totp_at(secret_bytes, step_s_ts)

        # First verification succeeds
        v1 = await client.post(
            "/api/v1/auth/mfa/verify",
            headers=headers2,
            json={"method": "totp", "code": code_s},
        )
        assert v1.status_code == 200

        # Update cookies and CSRF from v1
        for c in v1.cookies.jar:
            client.cookies.set(c.name, c.value or "")
        elevated_headers = {CSRF_HEADER_NAME: v1.json()["csrf_token"]}

        # Second verification with exact same code (same step) rejected as replay
        v2 = await client.post(
            "/api/v1/auth/mfa/verify",
            headers=elevated_headers,
            json={"method": "totp", "code": code_s},
        )
        assert v2.status_code == 401
        assert v2.json()["code"] == "MFA_INVALID"

        # Verification with step s-1 after step s has been accepted is also rejected
        code_s_minus_1 = totp_at(secret_bytes, step_s_ts - 30)
        v3 = await client.post(
            "/api/v1/auth/mfa/verify",
            headers=elevated_headers,
            json={"method": "totp", "code": code_s_minus_1},
        )
        assert v3.status_code == 401
        assert v3.json()["code"] == "MFA_INVALID"


@pytest.mark.committed_db
@pytest.mark.usefixtures("committed_db_session")
@pytest.mark.asyncio
async def test_case_4_concurrency_race(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 4: 10 concurrent verifies with the same valid code -> exactly 1 success."""
    # Use NullPool engine for concurrent client connections
    concurrency_engine = create_async_engine(pg_worker_db.url, poolclass=NullPool)
    factory = RLSSessionFactory(concurrency_engine)
    PgRateLimiter(concurrency_engine)
    SessionService(key_material.session_hmac_key)

    _ws_id, p_id, _ = await _setup_test_admin(
        factory, key_material, username="charlie", password="Password123!"
    )

    totp_service = TotpService(
        StaticKekProvider(
            {key_material.master_kek_kid: key_material.master_kek},
            current=key_material.master_kek_kid,
        )
    )

    anon_ctx = RLSContext(
        principal_id=uuid.UUID(int=0),
        workspace_id=uuid.UUID(int=0),
        token_scopes=("auth",),
        aal_level=1,
    )
    async with factory.session(anon_ctx) as session:
        _uri, secret_b32 = await totp_service.enroll(session, p_id, "charlie")
        secret_bytes = base64.b32decode(secret_b32)
        now_ts = int(time.time())
        conf_code = totp_at(secret_bytes, now_ts)
        confirmed = await totp_service.confirm(session, p_id, conf_code, timestamp=now_ts)
        assert confirmed is True

    # Pre-generate valid code for step s+1
    target_time = now_ts + 60
    target_code = totp_at(secret_bytes, target_time)

    # Run 10 concurrent verify calls directly against the service in parallel transactions
    async def _try_verify() -> bool:
        async with factory.session(anon_ctx) as session:
            return await totp_service.verify(session, p_id, target_code, timestamp=target_time)

    results = await asyncio.gather(*[_try_verify() for _ in range(10)])
    await concurrency_engine.dispose()

    success_count = sum(1 for r in results if r is True)
    failure_count = sum(1 for r in results if r is False)
    assert success_count == 1, f"Expected exactly 1 success, got {success_count}"
    assert failure_count == 9, f"Expected 9 failures, got {failure_count}"


@pytest.mark.asyncio
async def test_case_7_brute_force_rate_limit(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 7: 6th verify attempt in 300s -> 429 RATE_LIMITED."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    ws_id, p_id, _ = await _setup_test_admin(
        factory, key_material, username="david", password="Password123!"
    )

    app, session_service = _create_app(factory, key_material, rate_limiter)
    transport = httpx.ASGITransport(app=app)

    # Reset rate limit key for clean test start
    limit_key = make_key(
        AUTH_MFA_VERIFY,
        str(p_id),
        session_hmac_key=session_service.session_hmac_key,
    )
    await rate_limiter.reset(AUTH_MFA_VERIFY, limit_key)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create mfa_pending session
        anon_ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
            token_scopes=("auth",),
            aal_level=1,
        )
        async with factory.session(anon_ctx) as session:
            issued = await session_service.create_after_login(
                session,
                principal_id=p_id,
                workspace_id=ws_id,
                aal_level=1,
                mfa_pending=True,
            )

        client.cookies.set(SESSION_COOKIE_NAME, issued.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, issued.csrf_token)
        headers = {CSRF_HEADER_NAME: issued.csrf_token}

        # 5 invalid verify attempts consume the quota
        for idx in range(5):
            res = await client.post(
                "/api/v1/auth/mfa/verify",
                headers=headers,
                json={"method": "totp", "code": "000000"},
            )
            assert res.status_code == 401, f"Attempt {idx + 1} expected 401, got {res.status_code}"

        # 6th attempt triggers 429 RATE_LIMITED
        rate_res = await client.post(
            "/api/v1/auth/mfa/verify",
            headers=headers,
            json={"method": "totp", "code": "000000"},
        )
        assert rate_res.status_code == 429
        assert rate_res.json()["code"] == "RATE_LIMITED"
        assert "Retry-After" in rate_res.headers


@pytest.mark.asyncio
async def test_case_11_secret_hygiene_and_blob_tampering(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test Case 11: Secret hygiene and tampering defense.

    Secret absent from responses/caplog; bit-flip on blob -> verify fails closed (401).
    """
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    _ws_id, p_id, _ = await _setup_test_admin(
        factory, key_material, username="eve", password="Password123!"
    )

    app, _session_service = _create_app(factory, key_material, rate_limiter)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        tok, cook = await _get_pre_session_csrf(client)
        client.cookies.set(CSRF_COOKIE_NAME, cook)
        l_res = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: tok},
            json={"username": "eve", "password": "Password123!"},
        )
        assert l_res.status_code == 200, l_res.text
        csrf = l_res.json()["csrf_token"]
        client.cookies.set(CSRF_COOKIE_NAME, csrf)
        if SESSION_COOKIE_NAME in l_res.cookies:
            client.cookies.set(SESSION_COOKIE_NAME, l_res.cookies[SESSION_COOKIE_NAME])
        headers = {CSRF_HEADER_NAME: csrf}

        with caplog.at_level(logging.DEBUG):
            # 1. Enroll
            en_res = await client.post("/api/v1/auth/mfa/totp/enroll", headers=headers)
            secret_b32 = en_res.json()["secret"]

            # 2. Confirm
            valid_code = totp_at(base64.b32decode(secret_b32), int(time.time()))
            conf_res = await client.post(
                "/api/v1/auth/mfa/totp/confirm",
                headers=headers,
                json={"code": valid_code},
            )
            assert conf_res.status_code == 200
            # Ensure secret is absent from confirm response
            assert secret_b32 not in conf_res.text

            # 3. Verify with next step within acceptance window
            next_code = totp_at(base64.b32decode(secret_b32), int(time.time()) + 30)
            v_res = await client.post(
                "/api/v1/auth/mfa/verify",
                headers=headers,
                json={"method": "totp", "code": next_code},
            )
            assert v_res.status_code == 200, v_res.text
            # Ensure secret is absent from verify response
            assert secret_b32 not in v_res.text
            for c in v_res.cookies.jar:
                client.cookies.set(c.name, c.value or "")
            headers = {CSRF_HEADER_NAME: v_res.json()["csrf_token"]}

            # 4. Check caplog: raw secret or secret_b32 must never appear in logs
            for record in caplog.records:
                assert secret_b32 not in record.message
                assert "kanban/totp/v1" not in record.message

        # 5. Bit-flip tampering: flip a byte in encrypted_secret_blob
        anon_ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
            token_scopes=("auth",),
            aal_level=1,
        )
        async with factory.session(anon_ctx) as session:
            await session.execute(
                text(
                    "UPDATE totp_factors "
                    "SET encrypted_secret_blob = set_byte(encrypted_secret_blob, 10, 255) "
                    "WHERE principal_id = :p_id"
                ),
                {"p_id": p_id},
            )

        # 6. Verify now fails closed with 401 MFA_INVALID
        tampered_code = totp_at(base64.b32decode(secret_b32), int(time.time()) + 60)
        tampered_res = await client.post(
            "/api/v1/auth/mfa/verify",
            headers=headers,
            json={"method": "totp", "code": tampered_code},
        )
        assert tampered_res.status_code == 401
        assert tampered_res.json()["code"] == "MFA_INVALID"


@pytest.mark.asyncio
async def test_case_12_pending_factor_expiry(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 12: Unconfirmed factor older than 600s cannot be confirmed."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    _ws_id, p_id, _ = await _setup_test_admin(
        factory, key_material, username="frank", password="Password123!"
    )

    app, _session_service = _create_app(factory, key_material, rate_limiter)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        tok, cook = await _get_pre_session_csrf(client)
        client.cookies.set(CSRF_COOKIE_NAME, cook)
        l_res = await client.post(
            "/api/v1/auth/local/login",
            headers={CSRF_HEADER_NAME: tok},
            json={"username": "frank", "password": "Password123!"},
        )
        assert l_res.status_code == 200, l_res.text
        csrf = l_res.json()["csrf_token"]
        client.cookies.set(CSRF_COOKIE_NAME, csrf)
        if SESSION_COOKIE_NAME in l_res.cookies:
            client.cookies.set(SESSION_COOKIE_NAME, l_res.cookies[SESSION_COOKIE_NAME])
        headers = {CSRF_HEADER_NAME: csrf}

        # Enroll factor
        en_res = await client.post("/api/v1/auth/mfa/totp/enroll", headers=headers)
        secret_bytes = base64.b32decode(en_res.json()["secret"])

        # Attempt to confirm with wrong code -> fails 401 MFA_INVALID
        wrong_conf = await client.post(
            "/api/v1/auth/mfa/totp/confirm",
            headers=headers,
            json={"code": "000000"},
        )
        assert wrong_conf.status_code == 401
        assert wrong_conf.json()["code"] == "MFA_INVALID"

        # Backdate the factor by 605 seconds (> 600s expiry threshold)
        anon_ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
            token_scopes=("auth",),
            aal_level=1,
        )
        async with factory.session(anon_ctx) as session:
            await session.execute(
                text(
                    "UPDATE totp_factors "
                    "SET created_at = clock_timestamp() - interval '605 seconds' "
                    "WHERE principal_id = :p_id AND status = 'PENDING'"
                ),
                {"p_id": p_id},
            )

        # Attempt to confirm with a valid code -> fails 401 MFA_INVALID
        valid_code = totp_at(secret_bytes, int(time.time()))
        conf_res = await client.post(
            "/api/v1/auth/mfa/totp/confirm",
            headers=headers,
            json={"code": valid_code},
        )
        assert conf_res.status_code == 401
        assert conf_res.json()["code"] == "MFA_INVALID"


@pytest.mark.asyncio
async def test_delete_totp_factor(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Verify DELETE /api/v1/auth/mfa/totp revokes active factor."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    ws_id, p_id, _ = await _setup_test_admin(
        factory, key_material, username="grace", password="Password123!"
    )

    app, session_service = _create_app(factory, key_material, rate_limiter)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create AAL2 session directly
        anon_ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
            token_scopes=("auth",),
            aal_level=1,
        )
        async with factory.session(anon_ctx) as session:
            # Seed backup WebAuthn credential so admin retains at least one AAL2 factor
            await session.execute(
                text(
                    "INSERT INTO webauthn_credentials "
                    "(id, principal_id, credential_id, public_key, sign_count) "
                    "VALUES (:id, :p_id, :cred_id, :pub_key, 0)"
                ),
                {
                    "id": uuid.uuid4(),
                    "p_id": p_id,
                    "cred_id": b"grace_cred_backup_16b",
                    "pub_key": b"pk",
                },
            )
            issued = await session_service.create_after_login(
                session,
                principal_id=p_id,
                workspace_id=ws_id,
                aal_level=2,
                mfa_pending=False,
            )

        client.cookies.set(SESSION_COOKIE_NAME, issued.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, issued.csrf_token)
        headers = {CSRF_HEADER_NAME: issued.csrf_token}

        # Enroll and confirm factor
        en_res = await client.post("/api/v1/auth/mfa/totp/enroll", headers=headers)
        secret_bytes = base64.b32decode(en_res.json()["secret"])
        code = totp_at(secret_bytes, int(time.time()))
        await client.post(
            "/api/v1/auth/mfa/totp/confirm",
            headers=headers,
            json={"code": code},
        )

        # Revoke via DELETE /api/v1/auth/mfa/totp
        del_res = await client.delete("/api/v1/auth/mfa/totp", headers=headers)
        assert del_res.status_code == 200
        assert del_res.json()["revoked"] is True

        # Subsequent verification returns 401 MFA_INVALID
        next_code = totp_at(secret_bytes, int(time.time()) + 30)
        v_res = await client.post(
            "/api/v1/auth/mfa/verify",
            headers=headers,
            json={"method": "totp", "code": next_code},
        )
        assert v_res.status_code == 401
        assert v_res.json()["code"] == "MFA_INVALID"
