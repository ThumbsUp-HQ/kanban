# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and integration tests for backup recovery codes (KB-P2-05a, Test Case 8)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Final

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from database.session import RLSContext, RLSSessionFactory
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.auth.mfa.recovery import (
    CROCKFORD_ALPHABET,
    generate_recovery_codes,
    hash_recovery_code,
    normalize_recovery_code,
)
from kanban.auth.sessions.cookies import SESSION_COOKIE_NAME
from kanban.auth.sessions.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, CsrfMiddleware
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionService
from kanban.security.keys import KeyMaterial
from kanban.security.ratelimit.pg import PgRateLimiter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

PEPPER_KEY: Final[bytes] = b"p" * 32
SESSION_HMAC_KEY: Final[bytes] = b"s" * 32


@pytest.fixture
def key_material() -> KeyMaterial:
    """Provide testing key material."""
    return KeyMaterial(
        master_kek=b"k" * 32,
        master_kek_kid="kek-v1",
        auth_pepper=PEPPER_KEY,
        session_hmac_key=SESSION_HMAC_KEY,
    )


def test_recovery_code_generation_entropy() -> None:
    """Verify generated recovery codes adhere to Crockford base32 and entropy format."""
    codes = generate_recovery_codes(10)
    assert len(codes) == 10
    assert len(set(codes)) == 10
    for code in codes:
        assert len(code) == 11
        assert code[5] == "-"
        raw = code.replace("-", "")
        assert len(raw) == 10
        assert all(c in CROCKFORD_ALPHABET for c in raw)


def test_recovery_code_normalization_and_lookalikes() -> None:
    """Verify Crockford normalization handles dashes, spaces, and lookalike characters."""
    assert normalize_recovery_code("abcdefghjk") == "ABCDEFGHJK"
    assert normalize_recovery_code("abcde-fghjk") == "ABCDEFGHJK"
    assert normalize_recovery_code(" abcde - fghjk ") == "ABCDEFGHJK"

    # Test lookalike translation: i/l -> 1, o -> 0
    assert normalize_recovery_code("iiilllooo0") == "1111110000"
    assert normalize_recovery_code("IIILLLOOO0") == "1111110000"

    # Invalid length
    with pytest.raises(ValueError, match="Invalid recovery code format"):
        normalize_recovery_code("12345")
    with pytest.raises(ValueError, match="Invalid recovery code format"):
        normalize_recovery_code("12345678901")

    # Invalid characters (e.g. U is excluded from Crockford Base32)
    with pytest.raises(ValueError, match="Invalid recovery code format"):
        normalize_recovery_code("123456789U")


def test_recovery_code_hashing() -> None:
    """Verify HMAC-SHA256 hashing produces consistent 32-byte digest."""
    h1 = hash_recovery_code("ABCDE-FGHJK", PEPPER_KEY)
    h2 = hash_recovery_code("abcde-fghjk", PEPPER_KEY)
    h3 = hash_recovery_code("ABCDEFGHJK", PEPPER_KEY)
    assert len(h1) == 32
    assert h1 == h2 == h3

    h_other_pepper = hash_recovery_code("ABCDE-FGHJK", b"q" * 32)
    assert h1 != h_other_pepper


async def _provision_user(
    factory: RLSSessionFactory,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision workspace and principal in database."""
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)
    async with factory.session(ctx) as db_session:
        await db_session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Recovery WS"},
        )
        await db_session.execute(
            text(
                "SELECT register_object("
                "'user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
            ),
            {"ws_id": ws_id, "ckey": f"usr-{p_id.hex}", "title": "Recovery User", "u_id": p_id},
        )
        await db_session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'Recovery User', 'ACTIVE')"
            ),
            {"id": p_id, "ws_id": ws_id},
        )
        await db_session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, :email)"
            ),
            {"id": p_id, "ws_id": ws_id, "email": f"rec-{ws_id.hex[:6]}@example.com"},
        )
    return ws_id, p_id


@pytest.mark.asyncio
async def test_case_8_recovery_lifecycle_and_db_hygiene(  # noqa: PLR0915
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 8: Code consumed once; 2nd use 401; regenerate invalidates.

    Also asserts raw code is absent from DB dump.
    """
    factory = RLSSessionFactory(pg_worker_db)
    ws_id, p_id = await _provision_user(factory)

    session_service = SessionService(key_material.session_hmac_key)
    rate_limiter = PgRateLimiter(pg_worker_db)

    app = FastAPI()
    app.state.session_service = session_service
    app.state.session_factory = factory
    app.state.key_material = key_material
    app.state.rate_limiter = rate_limiter

    resolver = SessionCookieResolver(session_service, factory)
    app.state.principal_resolver = resolver
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    v1 = build_v1_router()
    app.include_router(v1, prefix="/api/v1")
    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_middleware(RequestIdMiddleware)

    # 1. Create active AAL2 session to authorize regenerate endpoint
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
            aal_level=2,
            mfa_pending=False,
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, issued.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, issued.csrf_token)
        headers = {CSRF_HEADER_NAME: issued.csrf_token}

        # 2. Regenerate recovery codes
        regen_res = await client.post("/api/v1/auth/mfa/recovery/regenerate", headers=headers)
        assert regen_res.status_code == 200, regen_res.text
        data = regen_res.json()
        codes = data["recovery_codes"]
        assert len(codes) == 10

        # 3. DB dump check: ensure raw codes are NEVER stored in plaintext in the database
        async with factory.session(anon_ctx) as session:
            rows = await session.execute(
                text("SELECT code_hmac FROM recovery_codes WHERE principal_id = :p_id"),
                {"p_id": p_id},
            )
            stored_hmacs = [r[0] for r in rows.all()]
            assert len(stored_hmacs) == 10

            for code in codes:
                raw_bytes = code.encode("utf-8")
                raw_norm_bytes = normalize_recovery_code(code).encode("ascii")
                for stored in stored_hmacs:
                    assert raw_bytes not in stored
                    assert raw_norm_bytes not in stored

        # 4. Now simulate an mfa_pending session for verification
        async with factory.session(anon_ctx) as session:
            pending_issued = await session_service.create_after_login(
                session,
                principal_id=p_id,
                workspace_id=ws_id,
                aal_level=1,
                mfa_pending=True,
            )

        client.cookies.set(SESSION_COOKIE_NAME, pending_issued.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, pending_issued.csrf_token)
        headers = {CSRF_HEADER_NAME: pending_issued.csrf_token}

        # 5. Verify first recovery code -> succeeds and session is elevated
        first_code = codes[0]
        v_res = await client.post(
            "/api/v1/auth/mfa/verify",
            headers=headers,
            json={"method": "recovery", "code": first_code},
        )
        assert v_res.status_code == 200, v_res.text
        v_data = v_res.json()
        assert v_data["verified"] is True
        assert v_data["aal_level"] == 2
        assert v_data["session_id"] != str(pending_issued.session_id)

        # Update cookies for elevated session
        client.cookies.clear()
        for cookie_item in v_res.cookies.jar:
            client.cookies.set(cookie_item.name, cookie_item.value or "")
        elevated_csrf = v_data["csrf_token"]
        headers = {CSRF_HEADER_NAME: elevated_csrf}

        # 6. Replay: second use of first_code -> fails 401 MFA_INVALID
        replay_res = await client.post(
            "/api/v1/auth/mfa/verify",
            headers=headers,
            json={"method": "recovery", "code": first_code},
        )
        assert replay_res.status_code == 401
        assert replay_res.json()["code"] == "MFA_INVALID"

        # 7. Regenerate again -> invalidates all prior remaining 9 codes
        regen_res2 = await client.post("/api/v1/auth/mfa/recovery/regenerate", headers=headers)
        assert regen_res2.status_code == 200
        new_codes = regen_res2.json()["recovery_codes"]
        assert new_codes != codes

        # Old code 1 (from first batch) was unused, but regeneration must invalidate it
        old_code_1 = codes[1]
        old_res = await client.post(
            "/api/v1/auth/mfa/verify",
            headers=headers,
            json={"method": "recovery", "code": old_code_1},
        )
        assert old_res.status_code == 401
        assert old_res.json()["code"] == "MFA_INVALID"

        # New code from second batch works
        new_res = await client.post(
            "/api/v1/auth/mfa/verify",
            headers=headers,
            json={"method": "recovery", "code": new_codes[0]},
        )
        assert new_res.status_code == 200
        assert new_res.json()["verified"] is True

        client.cookies.clear()
        for cookie_item in new_res.cookies.jar:
            client.cookies.set(cookie_item.name, cookie_item.value or "")
        post_headers = {CSRF_HEADER_NAME: new_res.json()["csrf_token"]}

        # Malformed recovery code returns 401 MFA_INVALID
        bad_res = await client.post(
            "/api/v1/auth/mfa/verify",
            headers=post_headers,
            json={"method": "recovery", "code": "malformed-code!"},
        )
        assert bad_res.status_code == 401
        assert bad_res.json()["code"] == "MFA_INVALID"
