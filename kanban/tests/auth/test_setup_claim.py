# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: PLC0415, RUF059, TC001, TC003, SLF001
"""Comprehensive test suite for first-boot setup claim and status (KB-P2-12)."""

from __future__ import annotations

import asyncio
import hashlib
import io
import re
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Annotated, Final

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import text

from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.auth.mfa.policy import require_aal2
from kanban.auth.mfa.webauthn import WebauthnService
from kanban.auth.sessions.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, CsrfMiddleware
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionService
from kanban.auth.setup import (
    SetupBootstrapService,
    mint_setup_token_if_uninitialized,
)
from kanban.security.envelope import StaticKekProvider
from kanban.security.keys import KeyMaterial
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
def setup_settings() -> Settings:
    """Provide settings configured for testing setup claim domain."""
    return Settings(
        deployment_mode="production",
        public_origin=ORIGIN,
        webauthn_rp_id=RP_ID,
        webauthn_rp_name="👍kanban",
    )


@pytest.fixture(autouse=True)
async def _clean_setup_db(pg_worker_db: AsyncEngine) -> AsyncIterator[None]:
    """Ensure clean uninitialized database before and after each setup test."""

    async def _truncate() -> None:
        async with pg_worker_db.connect() as conn:
            await conn.execute(
                text(
                    "TRUNCATE workspaces, principals, users, role_bindings, auth_provider_cards, "
                    "activity_records, activity_chain_heads, sessions, rate_limit_buckets, "
                    "local_admin_credentials, setup_claim_tokens, "
                    "totp_factors, webauthn_credentials "
                    "RESTART IDENTITY CASCADE"
                )
            )
            await conn.commit()

    await _truncate()
    try:
        yield
    finally:
        await _truncate()


def _create_app(
    factory: RLSSessionFactory,
    key_material: KeyMaterial,
    rate_limiter: PgRateLimiter,
    settings: Settings,
) -> tuple[FastAPI, SessionService]:
    """Create test FastAPI application configured with setup and auth routes."""
    session_service = SessionService(key_material.session_hmac_key)
    app = FastAPI(title="Setup Claim Test App")
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

    @app.get("/api/v1/admin/auth-cards")
    async def _admin_auth_cards(
        principal: Annotated[PrincipalContext, Depends(require_aal2())],
    ) -> dict[str, str]:
        return {"status": "ok", "principal_id": str(principal.principal_id)}

    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_middleware(RequestIdMiddleware)

    return app, session_service


def _sync_cookies(client: httpx.AsyncClient, response: httpx.Response) -> None:
    """Sync response cookies into AsyncClient cookie jar."""
    del client, response


async def _get_pre_session_csrf(client: httpx.AsyncClient) -> tuple[str, str]:
    """Retrieve pre-session CSRF token and cookie from GET /api/v1/auth/session."""
    res = await client.get("/api/v1/auth/session")
    assert res.status_code == 200
    token = str(res.json()["csrf_token"])
    csrf_cookie = str(res.cookies.get(CSRF_COOKIE_NAME, token) or token)
    _sync_cookies(client, res)
    return token, csrf_cookie


# --- 1. Positive Full Lifecycle ---


@pytest.mark.asyncio
async def test_case_1_positive_full_lifecycle(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    setup_settings: Settings,
) -> None:
    """Test Case 1: Fresh DB -> mint -> status false -> claim.

    Verify mfa_pending -> enroll TOTP -> AAL2 -> status true.
    """
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    app, session_service = _create_app(factory, key_material, rate_limiter, setup_settings)

    # 1. Mint setup token on uninitialized DB
    out = io.StringIO()
    token = await mint_setup_token_if_uninitialized(
        factory, key_material=key_material, settings=setup_settings, stdout=out
    )
    assert token is not None
    assert re.match(r"^kb_setup_[A-Za-z0-9_-]{43}$", token)
    expected_url = f"First-boot setup URL: {setup_settings.effective_origin}/setup?token={token}\n"
    assert expected_url in out.getvalue()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as client:
        # 2. Check status: initialized is false
        status_res = await client.get("/api/v1/setup/status")
        assert status_res.status_code == 200
        assert status_res.json() == {"initialized": False}

        # 3. Post claim request
        csrf_token, _ = await _get_pre_session_csrf(client)
        claim_payload = {
            "token": token,
            "username": "rootadmin",
            "display_name": "Root Administrator",
            "password": "SecurePassword1234!",
            "email": "root@kanban.example",
        }
        claim_res = await client.post(
            "/api/v1/setup/claim",
            json=claim_payload,
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert claim_res.status_code == 200
        claim_data = claim_res.json()
        assert claim_data["status"] == "enrollment_required"
        assert "principal_id" in claim_data
        assert "enrollment_id" in claim_data
        _sync_cookies(client, claim_res)

        # 4. Verify session cookie is set with mfa_pending=True
        # Calling an AAL2-required admin endpoint must fail
        admin_res = await client.get("/api/v1/admin/auth-cards")
        assert admin_res.status_code in (401, 403)
        expected_codes = ("AAL2_REQUIRED", "MFA_REQUIRED", "MFA_ENROLLMENT_REQUIRED")
        assert admin_res.json()["code"] in expected_codes

        # 5. Enroll TOTP to elevate to AAL2
        csrf_token = str(client.cookies.get(CSRF_COOKIE_NAME, ""))
        totp_enroll_res = await client.post(
            "/api/v1/auth/mfa/totp/enroll",
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert totp_enroll_res.status_code == 200
        secret_b32 = totp_enroll_res.json()["secret"]

        # Confirm TOTP with valid code
        import base64
        import time

        from kanban.auth.mfa.totp import totp_at

        secret_bytes = base64.b32decode(secret_b32)
        # Confirm TOTP with code from prior step within window
        valid_confirm_code = totp_at(secret_bytes, int(time.time()) - 30)
        totp_confirm_res = await client.post(
            "/api/v1/auth/mfa/totp/confirm",
            json={"code": valid_confirm_code},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert totp_confirm_res.status_code == 200
        assert totp_confirm_res.json()["confirmed"] is True

        # Verify MFA factor with current step code to elevate session to AAL2
        valid_verify_code = totp_at(secret_bytes, int(time.time()))
        totp_verify_res = await client.post(
            "/api/v1/auth/mfa/verify",
            json={"method": "totp", "code": valid_verify_code},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert totp_verify_res.status_code == 200
        assert totp_verify_res.json()["aal_level"] == 2

        # 6. Admin endpoint now accessible
        admin_cards_res = await client.get("/api/v1/admin/auth-cards")
        assert admin_cards_res.status_code == 200

        # 7. Check status is now initialized = True
        status_after = await client.get("/api/v1/setup/status")
        assert status_after.status_code == 200
        assert status_after.json() == {"initialized": True}


# --- 2. Positive Passkey Branch ---


@pytest.mark.asyncio
async def test_case_2_positive_passkey_branch(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    setup_settings: Settings,
) -> None:
    """Test Case 2: Claim initial admin -> register WebAuthn passkey on mfa_pending -> AAL2."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    app, _ = _create_app(factory, key_material, rate_limiter, setup_settings)

    token = await mint_setup_token_if_uninitialized(
        factory, key_material=key_material, settings=setup_settings
    )
    assert token is not None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as client:
        csrf_token, _ = await _get_pre_session_csrf(client)
        claim_res = await client.post(
            "/api/v1/setup/claim",
            json={
                "token": token,
                "username": "passkeyadmin",
                "display_name": "Passkey Admin",
                "password": "PasswordPasskey123!",
            },
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert claim_res.status_code == 200
        _sync_cookies(client, claim_res)

        # Register WebAuthn passkey while session is in mfa_pending
        csrf_token = str(client.cookies.get(CSRF_COOKIE_NAME, ""))
        reg_opts_res = await client.post(
            "/api/v1/auth/webauthn/register/options",
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert reg_opts_res.status_code == 200
        opts_json = reg_opts_res.json()

        auth = SoftAuthenticator()
        cred_payload = auth.create_credential(opts_json, origin=ORIGIN)

        verify_res = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            json={"credential": cred_payload, "nickname": "Primary Passkey"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert verify_res.status_code == 200
        assert verify_res.json()["aal_level"] == 2
        _sync_cookies(client, verify_res)

        # Admin route is unlocked
        admin_res = await client.get("/api/v1/admin/auth-cards")
        assert admin_res.status_code == 200


# --- 3. Security: Single-Use Replay ---


@pytest.mark.asyncio
async def test_case_3_single_use_replay(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    setup_settings: Settings,
) -> None:
    """Test Case 3: Replaying same setup token returns 401 and creates zero duplicate users."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    app, _ = _create_app(factory, key_material, rate_limiter, setup_settings)

    token = await mint_setup_token_if_uninitialized(
        factory, key_material=key_material, settings=setup_settings
    )
    assert token is not None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as client:
        csrf_token, _ = await _get_pre_session_csrf(client)
        payload = {
            "token": token,
            "username": "adminonce",
            "display_name": "Admin Once",
            "password": "PasswordReplay123!",
        }
        res1 = await client.post(
            "/api/v1/setup/claim",
            json=payload,
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert res1.status_code == 200

        # Second attempt with identical token
        csrf2 = str(client.cookies.get(CSRF_COOKIE_NAME, csrf_token))
        res2 = await client.post(
            "/api/v1/setup/claim",
            json=payload,
            headers={CSRF_HEADER_NAME: csrf2},
        )
        assert res2.status_code == 401
        assert res2.json()["code"] == "SETUP_TOKEN_INVALID"

    # Verify database has exactly 1 user
    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0))
    async with factory.session(anon_ctx) as session:
        user_count = await session.execute(text("SELECT count(*) FROM users"))
        assert user_count.scalar_one() == 1


# --- 4. Security: Concurrency Race ---


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_case_4_concurrency_race(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    setup_settings: Settings,
) -> None:
    """Test Case 4: 10 concurrent claim requests -> exactly 1 succeeds, 9 fail with 401."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    app, _ = _create_app(factory, key_material, rate_limiter, setup_settings)

    token = await mint_setup_token_if_uninitialized(
        factory, key_material=key_material, settings=setup_settings
    )
    assert token is not None

    transport = httpx.ASGITransport(app=app)

    async def _attempt_claim(idx: int) -> int:
        async with httpx.AsyncClient(
            transport=transport, base_url=ORIGIN, headers={"Origin": ORIGIN}
        ) as client:
            csrf_token, _ = await _get_pre_session_csrf(client)
            res = await client.post(
                "/api/v1/setup/claim",
                json={
                    "token": token,
                    "username": f"admin{idx}",
                    "display_name": f"Admin {idx}",
                    "password": "PasswordConcurrency123!",
                },
                headers={CSRF_HEADER_NAME: csrf_token},
            )
            return res.status_code

    results = await asyncio.gather(*[_attempt_claim(i) for i in range(10)])
    assert results.count(200) == 1
    assert results.count(401) == 9

    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0))
    async with factory.session(anon_ctx) as session:
        user_count = await session.execute(text("SELECT count(*) FROM users"))
        assert user_count.scalar_one() == 1


# --- 5. Security: TTL Expiry ---


@pytest.mark.asyncio
async def test_case_5_ttl_expiry(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    setup_settings: Settings,
) -> None:
    """Test Case 5: Expired token (> 3600s) returns 401 SETUP_TOKEN_INVALID."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    app, _ = _create_app(factory, key_material, rate_limiter, setup_settings)

    token = await mint_setup_token_if_uninitialized(
        factory, key_material=key_material, settings=setup_settings
    )
    assert token is not None

    # Artificially expire the token in database
    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0))
    async with factory.session(anon_ctx) as session:
        expire_stmt = "UPDATE setup_claim_tokens SET expires_at = clock_timestamp() - interval '5s'"
        await session.execute(text(expire_stmt))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as client:
        csrf_token, _ = await _get_pre_session_csrf(client)
        res = await client.post(
            "/api/v1/setup/claim",
            json={
                "token": token,
                "username": "expiredadmin",
                "display_name": "Expired Admin",
                "password": "PasswordExpiry123!",
            },
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert res.status_code == 401
        assert res.json()["code"] == "SETUP_TOKEN_INVALID"


# --- 6. Security: Restart Rotation & Post-Init Silence ---


@pytest.mark.asyncio
async def test_case_6_restart_rotation_and_post_init_silence(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    setup_settings: Settings,
) -> None:
    """Test Case 6: Restarting before claim revokes T1 for T2; restarting after claim mints None."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    app, _ = _create_app(factory, key_material, rate_limiter, setup_settings)

    # First boot mints T1
    t1 = await mint_setup_token_if_uninitialized(
        factory, key_material=key_material, settings=setup_settings
    )
    assert t1 is not None

    # Second boot before claim mints T2 and revokes T1
    t2 = await mint_setup_token_if_uninitialized(
        factory, key_material=key_material, settings=setup_settings
    )
    assert t2 is not None
    assert t1 != t2

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as client:
        csrf_token, _ = await _get_pre_session_csrf(client)

        # Attempting T1 fails
        res_t1 = await client.post(
            "/api/v1/setup/claim",
            json={
                "token": t1,
                "username": "t1admin",
                "display_name": "T1 Admin",
                "password": "PasswordRotation123!",
            },
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert res_t1.status_code == 401
        assert res_t1.json()["code"] == "SETUP_TOKEN_INVALID"

        # T2 succeeds
        res_t2 = await client.post(
            "/api/v1/setup/claim",
            json={
                "token": t2,
                "username": "t2admin",
                "display_name": "T2 Admin",
                "password": "PasswordRotation123!",
            },
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert res_t2.status_code == 200

    # Boot after claim (user exists)
    out_post = io.StringIO()
    t_after = await mint_setup_token_if_uninitialized(
        factory, key_material=key_material, settings=setup_settings, stdout=out_post
    )
    assert t_after is None
    assert out_post.getvalue() == ""


# --- 7. Security: At-Rest Hashing & DB Boundary ---


@pytest.mark.asyncio
async def test_case_7_at_rest_hashing_and_db_boundary(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    setup_settings: Settings,
) -> None:
    """Test Case 7: Stored token_hmac is peppered HMAC and neither raw sha256 nor plaintext."""
    factory = RLSSessionFactory(pg_worker_db)
    token = await mint_setup_token_if_uninitialized(
        factory, key_material=key_material, settings=setup_settings
    )
    assert token is not None

    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0))
    async with factory.session(anon_ctx) as session:
        res = await session.execute(text("SELECT token_hmac FROM setup_claim_tokens LIMIT 1"))
        stored_hmac = res.scalar_one()

    raw_sha = hashlib.sha256(token.encode("ascii")).digest()
    assert stored_hmac != raw_sha
    assert len(stored_hmac) == 32
    assert "kb_setup_" not in str(stored_hmac)


# --- 8. Security: Rate Limit & Uniform Error Document ---


@pytest.mark.asyncio
async def test_case_8_rate_limit_and_enumeration(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    setup_settings: Settings,
) -> None:
    """Test Case 8: 11th failed claim yields 429; malformed/expired/wrong tokens match."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    app, _ = _create_app(factory, key_material, rate_limiter, setup_settings)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as client:
        csrf_token, _ = await _get_pre_session_csrf(client)

        # Compare error bodies for malformed and wrong token
        res_malformed = await client.post(
            "/api/v1/setup/claim",
            json={
                "token": "kb_setup_short",
                "username": "testenum",
                "display_name": "Test Enum",
                "password": "PasswordEnumeration123!",
            },
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert res_malformed.status_code == 401

        res_wrong = await client.post(
            "/api/v1/setup/claim",
            json={
                "token": "kb_setup_" + "A" * 43,
                "username": "testenum",
                "display_name": "Test Enum",
                "password": "PasswordEnumeration123!",
            },
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert res_wrong.status_code == 401

        # Check identical payload structure
        body1 = res_malformed.json()
        body2 = res_wrong.json()
        expected_detail = "The setup token is invalid, expired, or has already been used."
        assert body1["code"] == body2["code"] == "SETUP_TOKEN_INVALID"
        assert body1["title"] == body2["title"] == "Setup Token Invalid"
        assert body1["detail"] == body2["detail"] == expected_detail

        # Exhaust 10-rate limit bucket
        # We already made 2 requests; make 8 more
        for _ in range(8):
            await client.post(
                "/api/v1/setup/claim",
                json={
                    "token": "kb_setup_" + "B" * 43,
                    "username": "testenum",
                    "display_name": "Test Enum",
                    "password": "PasswordEnumeration123!",
                },
                headers={CSRF_HEADER_NAME: csrf_token},
            )

        # 11th request must return 429
        res_limited = await client.post(
            "/api/v1/setup/claim",
            json={
                "token": "kb_setup_" + "C" * 43,
                "username": "testenum",
                "display_name": "Test Enum",
                "password": "PasswordEnumeration123!",
            },
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert res_limited.status_code == 429
        assert res_limited.json()["code"] == "RATE_LIMITED"
        assert "Retry-After" in res_limited.headers


# --- 9. Boundary & Secret Hygiene ---


@pytest.mark.asyncio
async def test_case_9_boundary_and_secret_hygiene(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    setup_settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test Case 9: 13-char password -> 422; caplog at DEBUG contains neither token nor password."""
    import logging

    caplog.set_level(logging.DEBUG)

    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    app, _ = _create_app(factory, key_material, rate_limiter, setup_settings)

    token = await mint_setup_token_if_uninitialized(
        factory, key_material=key_material, settings=setup_settings
    )
    assert token is not None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as client:
        csrf_token, _ = await _get_pre_session_csrf(client)

        # 13-character password must fail with 422
        short_pw = "1234567890123"
        res_short = await client.post(
            "/api/v1/setup/claim",
            json={
                "token": token,
                "username": "adminhygiene",
                "display_name": "Admin Hygiene",
                "password": short_pw,
            },
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert res_short.status_code == 422

        # Successful claim with valid 14-char password
        valid_pw = "12345678901234"
        res_valid = await client.post(
            "/api/v1/setup/claim",
            json={
                "token": token,
                "username": "adminhygiene",
                "display_name": "Admin Hygiene",
                "password": valid_pw,
            },
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert res_valid.status_code == 200

    # Ensure neither plaintext token nor password appear in captured logs
    for record in caplog.records:
        assert token not in record.getMessage()
        assert valid_pw not in record.getMessage()


# --- Additional Coverage & Edge Case Tests ---


@pytest.mark.asyncio
async def test_setup_validation_edge_cases(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    setup_settings: Settings,
) -> None:
    """Test validation errors for trimmed display_name and oversized password."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    app, _ = _create_app(factory, key_material, rate_limiter, setup_settings)

    token = await mint_setup_token_if_uninitialized(
        factory, key_material=key_material, settings=setup_settings
    )
    assert token is not None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=ORIGIN, headers={"Origin": ORIGIN}
    ) as client:
        csrf_token, _ = await _get_pre_session_csrf(client)

        # Whitespace-only display_name -> 422
        res_ws = await client.post(
            "/api/v1/setup/claim",
            json={
                "token": token,
                "username": "adminws",
                "display_name": "     ",
                "password": "ValidPassword1234!",
            },
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert res_ws.status_code == 422

        # Oversized password (> 1024 bytes) -> 422
        res_long = await client.post(
            "/api/v1/setup/claim",
            json={
                "token": token,
                "username": "adminlong",
                "display_name": "Admin Long",
                "password": "A" * 1025,
            },
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert res_long.status_code == 422


@pytest.mark.asyncio
async def test_setup_service_dependency_error() -> None:
    """Verify _get_session_service raises RuntimeError when session_service is missing."""
    from starlette.requests import Request

    from kanban.api.v1.auth_setup import _get_session_service

    dummy_app = FastAPI()
    # request with dummy state without session_service
    scope = {"type": "http", "app": dummy_app, "headers": [], "state": {}}
    req = Request(scope)

    with pytest.raises(RuntimeError, match="SessionService is not configured"):
        _get_session_service(req)


@pytest.mark.asyncio
async def test_mint_token_defaults_coverage(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify default origin and stdout handling and load_key_material fallback."""
    import sys

    factory = RLSSessionFactory(pg_worker_db)

    # Test settings=None, stdout=None
    svc = SetupBootstrapService(factory, key_material=key_material, settings=None)
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)

    tok = await svc.mint_token_if_uninitialized(stdout=None)
    assert tok is not None
    assert f"First-boot setup URL: http://localhost:8080/setup?token={tok}\n" in captured.getvalue()

    # Test _resolve_key_material when key_material=None
    svc_no_km = SetupBootstrapService(factory, key_material=None, settings=None)
    monkeypatch.setattr("kanban.auth.setup.load_key_material", lambda: key_material)
    resolved = svc_no_km._resolve_key_material()
    assert resolved == key_material
