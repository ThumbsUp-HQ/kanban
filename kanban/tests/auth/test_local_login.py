# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: S106, S107
"""Integration tests for Local Admin login service, anti-enumeration, and rate limits (KB-P2-04)."""

from __future__ import annotations

import base64
import logging
import os
import statistics
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final

import httpx
import pytest
from argon2 import PasswordHasher, Type
from fastapi import Depends, FastAPI
from sqlalchemy import text
from starlette.responses import JSONResponse

from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext, get_principal
from kanban.api.problems import (
    ProblemException,
    problem_exception_handler,
)
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.auth.cards.repository import admin_upsert
from kanban.auth.local.hashing import (
    _normalize_and_pepper,
    hash_password_sync,
    needs_rehash,
)
from kanban.auth.local.service import LocalAdminLoginService
from kanban.auth.sessions.cookies import SESSION_COOKIE_NAME
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    CsrfMiddleware,
)
from kanban.auth.sessions.resolver import (
    SessionCookieResolver,
    require_full_session,
)
from kanban.auth.sessions.service import IssuedSession, SessionService
from kanban.security.keys import KeyMaterial
from kanban.security.ratelimit import AUTH_LOGIN_ACCOUNT, AUTH_LOGIN_IP, make_key
from kanban.security.ratelimit.pg import PgRateLimiter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

PEPPER_KEY: Final[bytes] = b"p" * 32
SESSION_HMAC_KEY: Final[bytes] = b"s" * 32


@pytest.fixture
def key_material() -> KeyMaterial:
    """Fixture providing KeyMaterial with fixed testing keys."""
    return KeyMaterial(
        master_kek=os.urandom(32),
        master_kek_kid="kek-v1",
        auth_pepper=PEPPER_KEY,
        session_hmac_key=SESSION_HMAC_KEY,
    )


async def _create_test_admin_and_card(  # noqa: PLR0913
    factory: RLSSessionFactory,
    key_material: KeyMaterial,
    *,
    is_card_enabled: bool = True,
    status: str = "ACTIVE",
    username: str = "admin",
    password: str = "CorrectPassword123",
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Provision workspace, principal, local admin card, and credential."""
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()
    card_id = uuid.uuid4()

    pw_hash = hash_password_sync(password, key_material.auth_pepper)

    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)
    async with factory.session(ctx) as db_session:
        # Clean up any leftover LOCAL_ADMIN cards from previous test cases:
        # First deactivate existing server admins so lockout guard permits cleanup
        await db_session.execute(
            text(
                "UPDATE principals SET status = 'DISABLED' WHERE id IN ("
                "  SELECT principal_id FROM role_bindings WHERE role = 'SERVER_ADMIN'"
                ")"
            )
        )
        await db_session.execute(
            text("DELETE FROM auth_provider_cards WHERE provider_kind = 'LOCAL_ADMIN'")
        )
        await db_session.execute(text("DELETE FROM local_admin_credentials"))

        # Create workspace
        await db_session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Local Admin WS"},
        )
        # Register user object in spine
        await db_session.execute(
            text(
                "SELECT register_object("
                "'user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
            ),
            {"ws_id": ws_id, "ckey": f"usr-{p_id.hex}", "title": "Admin User", "u_id": p_id},
        )
        # Insert principal
        await db_session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'Admin Principal', :status)"
            ),
            {"id": p_id, "ws_id": ws_id, "status": status},
        )
        # Insert users record
        await db_session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, :email)"
            ),
            {"id": p_id, "ws_id": ws_id, "email": f"{username}-{ws_id.hex[:6]}@example.com"},
        )
        # Bind SERVER_ADMIN role for admin_upsert authorization
        await db_session.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
            ),
            {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": p_id},
        )
        # Upsert LOCAL_ADMIN card with unique slug to prevent test collision
        await admin_upsert(
            db_session,
            card_id=card_id,
            workspace_id=ws_id,
            provider_kind="LOCAL_ADMIN",
            slug=f"local-admin-{ws_id.hex[:8]}",
            display_name="Local Administrator",
            button_subtext="Username & password",
            icon_preset="shield",
            is_enabled=is_card_enabled,
            sort_rank="0|h00000:",
        )
        # Create credential via setup_claim
        await db_session.execute(text("SET LOCAL app.is_setup_claim = 'true'"))
        await db_session.execute(
            text("SELECT kb_auth.local_admin_create(:pid, :username, :hash, 'pepper-v1')"),
            {"pid": p_id, "username": username, "hash": pw_hash},
        )

    return ws_id, p_id, card_id


def _build_test_app(
    session_service: SessionService,
    session_factory: RLSSessionFactory,
    key_material: KeyMaterial,
    rate_limiter: PgRateLimiter,
) -> FastAPI:
    """Build FastAPI test instance wired with auth routes and middlewares."""
    app = FastAPI(title="Local Admin Test App")
    app.state.session_service = session_service
    app.state.session_factory = session_factory
    app.state.key_material = key_material
    app.state.rate_limiter = rate_limiter

    resolver = SessionCookieResolver(session_service, session_factory)
    app.state.principal_resolver = resolver

    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    # Mount v1 router tree
    v1 = build_v1_router()
    app.include_router(v1, prefix="/api/v1")

    # Sample route enforcing AAL2 (rejects mfa_pending)
    @app.get("/api/v1/protected/admin-only")
    async def admin_only_view(
        principal: Annotated[PrincipalContext, Depends(require_full_session)],
    ) -> JSONResponse:
        return JSONResponse({"status": "ok", "principal_id": str(principal.principal_id)})

    # Sample route permitting mfa_pending
    @app.get("/api/v1/mfa/status")
    async def mfa_status_view(
        principal: Annotated[PrincipalContext, Depends(get_principal)],
    ) -> JSONResponse:
        return JSONResponse({"status": "mfa_pending", "mfa_pending": principal.mfa_pending})

    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_middleware(RequestIdMiddleware)

    return app


async def _get_pre_session_csrf(client: httpx.AsyncClient) -> tuple[str, str]:
    """Retrieve pre-session CSRF token and cookie from GET /api/v1/auth/session."""
    res = await client.get("/api/v1/auth/session")
    assert res.status_code == 200
    token = str(res.json()["csrf_token"])
    csrf_cookie = str(res.cookies.get(CSRF_COOKIE_NAME, token) or token)
    return token, csrf_cookie


@pytest.mark.asyncio
async def test_case_1_positive_login(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 1: Correct credentials return 200, session cookie, mfa_pending=True, aal=1."""
    factory = RLSSessionFactory(pg_worker_db)
    service = SessionService(key_material.session_hmac_key)
    limiter = PgRateLimiter(pg_worker_db)

    await _create_test_admin_and_card(factory, key_material)

    app = _build_test_app(service, factory, key_material, limiter)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        csrf_token, csrf_cookie = await _get_pre_session_csrf(client)

        res = await client.post(
            "/api/v1/auth/local/login",
            json={"username": "admin", "password": "CorrectPassword123"},
            headers={CSRF_HEADER_NAME: csrf_token},
            cookies={CSRF_COOKIE_NAME: csrf_cookie},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["authenticated"] is True
        assert data["aal_level"] == 1
        assert data["mfa_pending"] is True
        assert "session_id" in data
        assert "csrf_token" in data

        # Check Set-Cookie headers
        raw_set_cookies = res.headers.get_list("set-cookie")
        assert any(SESSION_COOKIE_NAME in h for h in raw_set_cookies)
        assert any(CSRF_COOKIE_NAME in h for h in raw_set_cookies)

        session_cookie = res.cookies[SESSION_COOKIE_NAME]
        assert session_cookie is not None

        # Verify mfa_pending state on session resolver
        mfa_res = await client.get(
            "/api/v1/mfa/status",
            cookies={SESSION_COOKIE_NAME: session_cookie},
        )
        assert mfa_res.status_code == 200
        assert mfa_res.json()["mfa_pending"] is True

        # Verify access to require_full_session is denied with MFA_REQUIRED
        deny_res = await client.get(
            "/api/v1/protected/admin-only",
            cookies={SESSION_COOKIE_NAME: session_cookie},
        )
        assert deny_res.status_code == 403
        assert deny_res.json()["code"] == "MFA_REQUIRED"


@pytest.mark.asyncio
async def test_case_4_and_5_enumeration_body_and_work_equality(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Cases 4 & 5: Byte-identical 401 bodies and exactly 1 Argon2 verify.

    Asserts all failure scenarios yield byte-identical problem bodies and 1 verify.
    """
    factory = RLSSessionFactory(pg_worker_db)
    service = SessionService(key_material.session_hmac_key)
    limiter = PgRateLimiter(pg_worker_db)

    ws_id, p_id, _card_id = await _create_test_admin_and_card(factory, key_material)

    # Provision disabled card and suspended principal for scenario testing
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)
    async with factory.session(ctx) as db_session:
        # Create suspended principal
        susp_id = uuid.uuid4()
        await db_session.execute(
            text(
                "SELECT register_object("
                "'user'::object_kind, :ws_id, NULL, :ckey, 'Susp', :u_id, :u_id)"
            ),
            {"ws_id": ws_id, "ckey": f"usr-{susp_id.hex}", "u_id": susp_id},
        )
        await db_session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'Suspended Admin', 'DISABLED')"
            ),
            {"id": susp_id, "ws_id": ws_id},
        )
        await db_session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, 'suspended@example.com')"
            ),
            {"id": susp_id, "ws_id": ws_id},
        )
        await db_session.execute(text("SET LOCAL app.is_setup_claim = 'true'"))
        await db_session.execute(
            text("SELECT kb_auth.local_admin_create(:pid, 'suspended', :hash, 'pepper-v1')"),
            {
                "pid": susp_id,
                "hash": hash_password_sync("CorrectPassword123", key_material.auth_pepper),
            },
        )

    app = _build_test_app(service, factory, key_material, limiter)
    transport = httpx.ASGITransport(app=app)

    # Set up spy on PasswordHasher.verify to assert exactly 1 invocation
    verify_calls: list[str] = []
    real_verify = PasswordHasher.verify

    def spy_verify(self: PasswordHasher, stored_hash: str, password: str) -> bool:
        verify_calls.append(stored_hash[:20])
        return real_verify(self, stored_hash, password)

    monkeypatch.setattr(PasswordHasher, "verify", spy_verify)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        csrf_token, csrf_cookie = await _get_pre_session_csrf(client)
        headers = {CSRF_HEADER_NAME: csrf_token}
        cookies = {CSRF_COOKIE_NAME: csrf_cookie}

        test_scenarios = [
            ("unknown_user", "nonexistent_admin", "CorrectPassword123"),
            ("wrong_password", "admin", "CompletelyWrongPassword999"),
            ("suspended_user", "suspended", "CorrectPassword123"),
            ("empty_user", "", "CorrectPassword123"),
            ("oversize_user", "x" * 65, "CorrectPassword123"),
            ("short_password", "admin", "1234567"),
            ("long_password", "admin", "x" * 1025),
        ]

        responses: list[dict[str, object]] = []

        for name, username, password in test_scenarios:
            verify_calls.clear()
            res = await client.post(
                "/api/v1/auth/local/login",
                json={"username": username, "password": password},
                headers=headers,
                cookies=cookies,
            )
            assert res.status_code == 401, f"Scenario {name} expected 401, got {res.status_code}"
            assert len(verify_calls) == 1, (
                f"Scenario {name} expected exactly 1 verify call, got {len(verify_calls)}"
            )

            body = res.json()
            assert body["code"] == "INVALID_CREDENTIALS"
            assert body["status"] == 401
            assert body["title"] == "Invalid Credentials"
            assert body["detail"] == "Invalid username or password"

            # Strip dynamic request_id
            scrubbed = {k: v for k, v in body.items() if k != "request_id"}
            responses.append(scrubbed)

        # Test disabled card scenario
        async with factory.session(ctx) as db_session:
            # Temporarily deactivate principal so lockout trigger allows disabling the card
            await db_session.execute(
                text("UPDATE principals SET status = 'DISABLED' WHERE id = :p_id"),
                {"p_id": p_id},
            )
            await db_session.execute(
                text(
                    "UPDATE auth_provider_cards SET is_enabled = FALSE "
                    "WHERE provider_kind = 'LOCAL_ADMIN'"
                )
            )
            # Re-activate principal so we test login with disabled card (not disabled principal)
            await db_session.execute(
                text("UPDATE principals SET status = 'ACTIVE' WHERE id = :p_id"),
                {"p_id": p_id},
            )

        verify_calls.clear()
        res_disabled = await client.post(
            "/api/v1/auth/local/login",
            json={"username": "admin", "password": "CorrectPassword123"},
            headers=headers,
            cookies=cookies,
        )
        assert res_disabled.status_code == 401
        assert len(verify_calls) == 1
        responses.append({k: v for k, v in res_disabled.json().items() if k != "request_id"})

        # Assert all failure bodies (excluding request_id) are byte-identical
        first = responses[0]
        for idx, resp in enumerate(responses[1:], start=1):
            assert resp == first, f"Scenario index {idx} response body diverged from first failure"


@pytest.mark.asyncio
async def test_case_6_enumeration_timing_bounded(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 6: 50 unknown vs 50 wrong-password attempts; abs(median delta) <= 15ms."""
    factory = RLSSessionFactory(pg_worker_db)
    service = SessionService(key_material.session_hmac_key)
    limiter = PgRateLimiter(pg_worker_db)

    ws_id, _p_id, _ = await _create_test_admin_and_card(factory, key_material)

    login_service = LocalAdminLoginService(
        session_service=service,
        rate_limiter=limiter,
        session_hmac_key=key_material.session_hmac_key,
        auth_pepper=key_material.auth_pepper,
    )

    anon_ctx = RLSContext(
        principal_id=uuid.UUID(int=0),
        workspace_id=ws_id,
        token_scopes=("auth",),
        aal_level=1,
    )

    durations_unknown: list[float] = []
    durations_wrong: list[float] = []

    account_key = make_key(
        AUTH_LOGIN_ACCOUNT, "admin", session_hmac_key=key_material.session_hmac_key
    )

    # 50 iterations: unknown user
    for i in range(50):
        ip = f"10.0.1.{i % 250 + 1}"
        async with factory.session(anon_ctx) as db_sess:
            t0 = time.perf_counter()
            with pytest.raises(ProblemException):
                await login_service.login(
                    db_sess,
                    username=f"unknown_user_{i}",
                    password="SomePassword123!",
                    client_ip=ip,
                    workspace_id=ws_id,
                )
            durations_unknown.append((time.perf_counter() - t0) * 1000.0)

    # 50 iterations: wrong password on known user (resetting account limit counter each iteration)
    for i in range(50):
        ip = f"10.0.2.{i % 250 + 1}"
        await limiter.reset(AUTH_LOGIN_ACCOUNT, account_key)
        async with factory.session(anon_ctx) as db_sess:
            t0 = time.perf_counter()
            with pytest.raises(ProblemException):
                await login_service.login(
                    db_sess,
                    username="admin",
                    password="WrongPassword999!",
                    client_ip=ip,
                    workspace_id=ws_id,
                )
            durations_wrong.append((time.perf_counter() - t0) * 1000.0)

    median_unknown = statistics.median(durations_unknown)
    median_wrong = statistics.median(durations_wrong)
    p95_unknown = sorted(durations_unknown)[int(len(durations_unknown) * 0.95)]
    p95_wrong = sorted(durations_wrong)[int(len(durations_wrong) * 0.95)]
    delta_ms = abs(median_unknown - median_wrong)

    # Write proof report to docs/qa/KANBA-72/enumeration-timing.txt
    proof_dir = Path("docs/qa/KANBA-72")
    proof_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
    timing_file = proof_dir / "enumeration-timing.txt"
    report = (
        "Timing Side-Channel Analysis Report (KB-P2-04 / KANBA-72)\n"
        "========================================================\n"
        f"Unknown-User Sample Count: {len(durations_unknown)}\n"
        f"Unknown-User Median Latency: {median_unknown:.2f} ms\n"
        f"Unknown-User P95 Latency: {p95_unknown:.2f} ms\n"
        f"Wrong-Password Sample Count: {len(durations_wrong)}\n"
        f"Wrong-Password Median Latency: {median_wrong:.2f} ms\n"
        f"Wrong-Password P95 Latency: {p95_wrong:.2f} ms\n"
        f"Median Delta: {delta_ms:.2f} ms (Maximum Allowed: 15.00 ms)\n"
        f"Evaluation Result: {'PASS' if delta_ms <= 15.0 else 'FAIL'}\n"
    )
    timing_file.write_text(report, encoding="utf-8")

    assert delta_ms <= 15.0, (
        f"Median delta {delta_ms:.2f}ms exceeds allowed 15.0ms threshold "
        f"(unknown={median_unknown:.2f}ms, wrong={median_wrong:.2f}ms)"
    )


@pytest.mark.asyncio
async def test_case_7_security_rate_limits(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 7: 6th account failure -> 429; 21st IP failure -> 429; success resets bucket."""
    factory = RLSSessionFactory(pg_worker_db)
    service = SessionService(key_material.session_hmac_key)
    limiter = PgRateLimiter(pg_worker_db)

    ws_id, _, _ = await _create_test_admin_and_card(factory, key_material)

    login_service = LocalAdminLoginService(
        session_service=service,
        rate_limiter=limiter,
        session_hmac_key=key_material.session_hmac_key,
        auth_pepper=key_material.auth_pepper,
    )

    anon_ctx = RLSContext(
        principal_id=uuid.UUID(int=0),
        workspace_id=ws_id,
        token_scopes=("auth",),
        aal_level=1,
    )

    # Part A: 5 failed attempts on one account succeed, 6th attempt is throttled (429)
    account_ip = "198.51.100.1"
    account_key = make_key(
        AUTH_LOGIN_ACCOUNT, "admin", session_hmac_key=key_material.session_hmac_key
    )
    ip_key = make_key(AUTH_LOGIN_IP, account_ip, session_hmac_key=key_material.session_hmac_key)
    await limiter.reset(AUTH_LOGIN_ACCOUNT, account_key)
    await limiter.reset(AUTH_LOGIN_IP, ip_key)
    for i in range(1, 6):
        async with factory.session(anon_ctx) as db_sess:
            with pytest.raises(ProblemException) as exc_info:
                await login_service.login(
                    db_sess,
                    username="admin",
                    password=f"WrongPassword{i}",
                    client_ip=account_ip,
                    workspace_id=ws_id,
                )
            assert exc_info.value.status == 401

    # 6th attempt breaches limit -> 429 RATE_LIMITED
    async with factory.session(anon_ctx) as db_sess:
        with pytest.raises(ProblemException) as exc_info:
            await login_service.login(
                db_sess,
                username="admin",
                password="WrongPassword6",
                client_ip=account_ip,
                workspace_id=ws_id,
            )
        assert exc_info.value.status == 429
        assert exc_info.value.code == "RATE_LIMITED"
        assert exc_info.value.headers is not None
        assert "Retry-After" in exc_info.value.headers

    # Part B: Reset account bucket and verify successful login resets counter
    account_key = make_key(
        AUTH_LOGIN_ACCOUNT, "admin", session_hmac_key=key_material.session_hmac_key
    )
    await limiter.reset(AUTH_LOGIN_ACCOUNT, account_key)

    # 4 failed attempts
    for i in range(1, 5):
        async with factory.session(anon_ctx) as db_sess:
            with pytest.raises(ProblemException):
                await login_service.login(
                    db_sess,
                    username="admin",
                    password=f"WrongPassword{i}",
                    client_ip="198.51.100.2",
                    workspace_id=ws_id,
                )

    # 5th attempt is successful -> resets account bucket!
    async with factory.session(anon_ctx) as db_sess:
        issued = await login_service.login(
            db_sess,
            username="admin",
            password="CorrectPassword123",
            client_ip="198.51.100.2",
            workspace_id=ws_id,
        )
        assert isinstance(issued, IssuedSession)

    # Next 5 failed attempts succeed without 429 because counter was reset!
    for i in range(1, 6):
        async with factory.session(anon_ctx) as db_sess:
            with pytest.raises(ProblemException) as exc_info:
                await login_service.login(
                    db_sess,
                    username="admin",
                    password=f"WrongPasswordAfterReset{i}",
                    client_ip=f"198.51.100.{i + 10}",
                    workspace_id=ws_id,
                )
            assert exc_info.value.status == 401

    # Part C: IP rate limit (20 distinct accounts from same IP allowed, 21st throttled)
    shared_ip = "203.0.113.88"
    shared_ip_key = make_key(
        AUTH_LOGIN_IP, shared_ip, session_hmac_key=key_material.session_hmac_key
    )
    await limiter.reset(AUTH_LOGIN_IP, shared_ip_key)
    for i in range(1, 21):
        async with factory.session(anon_ctx) as db_sess:
            with pytest.raises(ProblemException) as exc_info:
                await login_service.login(
                    db_sess,
                    username=f"user_{i}",
                    password="SomePassword123",
                    client_ip=shared_ip,
                    workspace_id=ws_id,
                )
            assert exc_info.value.status == 401

    # 21st attempt from shared_ip raises 429
    async with factory.session(anon_ctx) as db_sess:
        with pytest.raises(ProblemException) as exc_info:
            await login_service.login(
                db_sess,
                username="user_21",
                password="SomePassword123",
                client_ip=shared_ip,
                workspace_id=ws_id,
            )
        assert exc_info.value.status == 429
        assert exc_info.value.code == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_case_11_secret_hygiene(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test Case 11: Neither password nor failed username appear in debug logs or activity rows."""
    factory = RLSSessionFactory(pg_worker_db)
    service = SessionService(key_material.session_hmac_key)
    limiter = PgRateLimiter(pg_worker_db)

    ws_id, _, _ = await _create_test_admin_and_card(factory, key_material)

    login_service = LocalAdminLoginService(
        session_service=service,
        rate_limiter=limiter,
        session_hmac_key=key_material.session_hmac_key,
        auth_pepper=key_material.auth_pepper,
    )

    anon_ctx = RLSContext(
        principal_id=uuid.UUID(int=0),
        workspace_id=ws_id,
        token_scopes=("auth",),
        aal_level=1,
    )

    caplog.set_level(logging.DEBUG)

    sensitive_username = "secret_admin_user"
    sensitive_password = "SuperSecretPasswordP@ss999"

    async with factory.session(anon_ctx) as db_sess:
        with pytest.raises(ProblemException):
            await login_service.login(
                db_sess,
                username=sensitive_username,
                password=sensitive_password,
                client_ip="192.0.2.1",
                workspace_id=ws_id,
            )

    # 1. Assert secrets never leak in application logs
    assert sensitive_password not in caplog.text
    assert sensitive_username not in caplog.text

    # 2. Assert secrets never leak in activity ledger payloads
    async with factory.session(anon_ctx) as db_sess:
        rows = await db_sess.execute(
            text(
                "SELECT payload::text FROM activity_records "
                "WHERE event_type = 'LOCAL_ADMIN_LOGIN_FAILED'"
            )
        )
        for row in rows.all():
            payload_str = row[0]
            assert sensitive_password not in payload_str
            assert sensitive_username not in payload_str


@pytest.mark.asyncio
async def test_case_10_login_rehash_and_resilience(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Case 10: Rehash t=2 -> t=3 on login, fallback pepper resolution, and resilience."""
    factory = RLSSessionFactory(pg_worker_db)
    service = SessionService(key_material.session_hmac_key)
    limiter = PgRateLimiter(pg_worker_db)

    # 1. Create legacy hash with t=2
    hasher_t2 = PasswordHasher(
        time_cost=2,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        salt_len=16,
        type=Type.ID,
    )
    pw = "RehashLoginPassword123"
    b64_mac = _normalize_and_pepper(pw, key_material.auth_pepper)
    legacy_hash = hasher_t2.hash(b64_mac)
    assert legacy_hash.startswith("$argon2id$v=19$m=65536,t=2,p=4$")

    ws_id, p_id, _ = await _create_test_admin_and_card(
        factory,
        key_material,
        username="rehash_admin",
        password=pw,
    )

    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)
    # Set legacy hash in database
    async with factory.session(ctx) as db_sess:
        await db_sess.execute(
            text("SELECT kb_auth.local_set_password_hash(:pid, :hash)"),
            {"pid": p_id, "hash": legacy_hash},
        )

    # Test _get_pepper() resolution path when auth_pepper is None
    b64_pepper = base64.urlsafe_b64encode(key_material.auth_pepper).decode("ascii")
    monkeypatch.setenv("KB_AUTH_PEPPER", b64_pepper)

    login_service = LocalAdminLoginService(
        session_service=service,
        rate_limiter=limiter,
        session_hmac_key=key_material.session_hmac_key,
        auth_pepper=None,
    )

    anon_ctx = RLSContext(
        principal_id=uuid.UUID(int=0),
        workspace_id=ws_id,
        token_scopes=("auth",),
        aal_level=1,
    )

    # Test login with t=2 hash -> succeeds and rehashes to t=3
    async with factory.session(anon_ctx) as db_sess:
        issued = await login_service.login(
            db_sess,
            username="rehash_admin",
            password=pw,
            client_ip="198.51.100.99",
            workspace_id=ws_id,
        )
        assert isinstance(issued, IssuedSession)

    # Check updated hash in DB
    async with factory.session(ctx) as db_sess:
        res = await db_sess.execute(
            text("SELECT password_hash FROM local_admin_credentials WHERE principal_id = :pid"),
            {"pid": p_id},
        )
        new_hash = res.scalar_one()
        assert new_hash.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
        assert needs_rehash(new_hash) is False

    # Test resilience: record_activity failure does not break login or error paths
    async def failing_record_activity(*_args: object, **_kwargs: object) -> None:
        msg = "Simulated activity audit ledger failure"
        raise RuntimeError(msg)

    monkeypatch.setattr("kanban.auth.local.service.record_activity", failing_record_activity)

    # Positive login with failing activity logging
    async with factory.session(anon_ctx) as db_sess:
        issued2 = await login_service.login(
            db_sess,
            username="rehash_admin",
            password=pw,
            client_ip="198.51.100.99",
            workspace_id=ws_id,
        )
        assert isinstance(issued2, IssuedSession)

    # Failed login with failing activity logging
    async with factory.session(anon_ctx) as db_sess:
        with pytest.raises(ProblemException) as exc_info:
            await login_service.login(
                db_sess,
                username="rehash_admin",
                password="WrongPassword999",
                client_ip="198.51.100.99",
                workspace_id=ws_id,
            )
        assert exc_info.value.status == 401
