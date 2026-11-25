# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and integration tests for WebSudo sliding window and transparent replay.

Validates KAN-404 requirements:
- Linear DB migration and ORM parity for aal2_last_active_at
- session_touch_aal2 sliding window (900s idle, 14400s absolute cap, 30s write throttle)
- session_drop_aal2 RPC and POST /api/v1/auth/aal2/drop endpoint
- POST /api/v1/auth/aal2/touch endpoint (non-throwing 200 when inactive)
- X-KB-AAL2-Expires-At response header emission on elevated routes
- Irreversible action freshness isolation (verification_only=True)
- Session metadata and me endpoint reporting (aal2_active, aal2_expires_at)
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Final
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import text
from starlette.responses import JSONResponse

from database.models.auth import (
    AuthProviderCard,
    IdentityLinkIntent,
    LdapGroupMapping,
    LocalAdminCredential,
    OidcAuthRequest,
    RecoveryCode,
    SetupClaimToken,
    TotpFactor,
    UserIdentity,
    UserSession,
    WebauthnChallenge,
    WebauthnCredential,
)
from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.api.v1.auth_session import (
    _fetch_session_expiry,
    drop_aal2_session,
    get_session_info,
    touch_aal2_session,
)
from kanban.api.v1.schemas.custom_fields import CustomFieldApprovalApproveRequest
from kanban.auth.mfa.policy import (
    _get_enrolled_methods,
    _RequireAal2,
    assert_admin_routes_protected,
    require_aal2,
    require_admin_aal2,
)
from kanban.auth.sessions.cookies import SESSION_COOKIE_NAME
from kanban.auth.sessions.csrf import CsrfMiddleware
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import IssuedSession, SessionService
from kanban.custom_fields.approvals import CustomFieldApprovalService
from kanban.security.boundary import CredentialBoundary
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


async def _provision_admin_user(
    factory: RLSSessionFactory,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision workspace, admin user, role binding, and TOTP factor."""
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)
    async with factory.session(ctx) as db_session:
        await db_session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "WebSudo WS"},
        )
        await db_session.execute(
            text(
                "SELECT register_object("
                "'user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
            ),
            {"ws_id": ws_id, "ckey": f"usr-{p_id.hex}", "title": "WebSudo Admin", "u_id": p_id},
        )
        await db_session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'WebSudo Admin', 'ACTIVE')"
            ),
            {"id": p_id, "ws_id": ws_id},
        )
        await db_session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, :email)"
            ),
            {"id": p_id, "ws_id": ws_id, "email": f"adm-{ws_id.hex[:6]}@example.com"},
        )
        await db_session.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
            ),
            {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": p_id},
        )
        # Provision TOTP factor
        await db_session.execute(
            text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
            {
                "p_id": p_id,
                "blob": b"\x01" + b"\x00" * 28,
                "dek": b"\x01" + b"\x00" * 44,
            },
        )
        res = await db_session.execute(
            text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
            {"p_id": p_id},
        )
        p_row = res.mappings().first()
        if p_row:
            await db_session.execute(
                text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
                {"p_fid": p_row["id"]},
            )

    return ws_id, p_id


@pytest.mark.asyncio
async def test_websudo_sliding_window_and_touch_drop_flow(  # noqa: PLR0915
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Validate full WebSudo sliding window lifecycle and touch/drop endpoints."""
    factory = RLSSessionFactory(pg_worker_db)
    session_service = SessionService(key_material.session_hmac_key)
    rate_limiter = PgRateLimiter(pg_worker_db)

    ws_id, admin_id = await _provision_admin_user(factory)

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

    # Protected test endpoint
    @app.get("/api/v1/admin/privileged/action")
    async def privileged_action(
        principal: Annotated[PrincipalContext, Depends(require_admin_aal2)],
    ) -> JSONResponse:
        return JSONResponse(
            {"status": "privileged_ok", "principal_id": str(principal.principal_id)}
        )

    # Irreversible action endpoint requiring recent verification
    @app.delete("/api/v1/admin/irreversible/action")
    async def irreversible_action(
        _principal: Annotated[
            PrincipalContext,
            Depends(require_aal2(max_age_seconds=900, verification_only=True)),
        ],
    ) -> JSONResponse:
        return JSONResponse({"status": "deleted_ok"})

    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_middleware(RequestIdMiddleware)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        anon_ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
            token_scopes=("auth",),
            aal_level=1,
        )

        # 1. Create initial AAL1 session
        async with factory.session(anon_ctx) as session:
            sess_issued = await session_service.create_after_login(
                session,
                principal_id=admin_id,
                workspace_id=ws_id,
            )

        client.cookies.clear()
        client.cookies.update(
            {
                SESSION_COOKIE_NAME: sess_issued.cookie_val,
                "kb_csrf": sess_issued.csrf_token,
            }
        )
        csrf_headers = {"X-CSRF-Token": sess_issued.csrf_token}

        # 2. Touch while AAL1 -> returns 200 with aal2_active=False without throwing 403
        touch_resp = await client.post(
            "/api/v1/auth/aal2/touch",
            headers=csrf_headers,
        )
        assert touch_resp.status_code == 200
        touch_data = touch_resp.json()
        assert touch_data["aal2_active"] is False
        assert touch_data["aal2_expires_at"] is None

        # 3. Privileged route fails with 403 AAL2_REQUIRED
        priv_resp = await client.get("/api/v1/admin/privileged/action")
        assert priv_resp.status_code == 403
        assert priv_resp.json()["code"] == "AAL2_REQUIRED"

        # 4. Elevate session to AAL2
        async with factory.session(anon_ctx) as session:
            elevated = await session_service.elevate_aal(
                session,
                old_session_id=sess_issued.session_id,
            )
            assert elevated.aal_level == 2

        client.cookies.clear()
        client.cookies.update(
            {
                SESSION_COOKIE_NAME: elevated.cookie_val,
                "kb_csrf": elevated.csrf_token,
            }
        )
        csrf_headers = {"X-CSRF-Token": elevated.csrf_token}

        # 5. Privileged route now succeeds and emits X-KB-AAL2-Expires-At header
        priv_resp2 = await client.get("/api/v1/admin/privileged/action")
        assert priv_resp2.status_code == 200
        assert priv_resp2.json()["status"] == "privileged_ok"
        assert "x-kb-aal2-expires-at" in priv_resp2.headers

        # 6. Touch while AAL2 -> returns 200 with aal2_active=True and aal2_expires_at string
        touch_resp2 = await client.post(
            "/api/v1/auth/aal2/touch",
            headers=csrf_headers,
        )
        assert touch_resp2.status_code == 200
        touch_data2 = touch_resp2.json()
        assert touch_data2["aal2_active"] is True
        assert touch_data2["aal2_expires_at"] is not None

        # 7. GET /api/v1/auth/session reports aal2_active and aal2_expires_at
        sess_info = await client.get("/api/v1/auth/session")
        assert sess_info.status_code == 200
        info_data = sess_info.json()
        assert info_data["aal2_active"] is True
        assert info_data["aal2_expires_at"] is not None

        # 8. GET /api/v1/auth/me reports aal2_active and aal2_expires_at
        me_info = await client.get("/api/v1/auth/me")
        assert me_info.status_code == 200
        me_data = me_info.json()
        assert me_data["aal2_active"] is True
        assert me_data["aal2_expires_at"] is not None

        # 9. Irreversible action succeeds within initial verification window
        irrev_resp = await client.delete(
            "/api/v1/admin/irreversible/action",
            headers=csrf_headers,
        )
        assert irrev_resp.status_code == 200

        # 10. Drop AAL2 via POST /api/v1/auth/aal2/drop
        drop_resp = await client.post(
            "/api/v1/auth/aal2/drop",
            headers=csrf_headers,
        )
        assert drop_resp.status_code == 200
        drop_data = drop_resp.json()
        assert drop_data["ok"] is True
        assert drop_data["aal2_active"] is False

        # 11. Subsequent privileged call immediately fails with 403 AAL2_REQUIRED
        priv_resp3 = await client.get("/api/v1/admin/privileged/action")
        assert priv_resp3.status_code == 403
        assert priv_resp3.json()["code"] == "AAL2_REQUIRED"


@pytest.mark.asyncio
async def test_websudo_idle_expiry_and_absolute_cap(  # noqa: PLR0915
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Validate idle timeout (900s) and absolute cap (14400s) enforcement."""
    factory = RLSSessionFactory(pg_worker_db)
    session_service = SessionService(key_material.session_hmac_key)
    rate_limiter = PgRateLimiter(pg_worker_db)

    ws_id, admin_id = await _provision_admin_user(factory)

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

    @app.get("/api/v1/admin/privileged/check")
    async def privileged_check(
        _principal: Annotated[PrincipalContext, Depends(require_admin_aal2)],
    ) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.delete("/api/v1/admin/irreversible/check")
    async def irreversible_check(
        _principal: Annotated[
            PrincipalContext,
            Depends(require_aal2(max_age_seconds=900, verification_only=True)),
        ],
    ) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_middleware(RequestIdMiddleware)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        anon_ctx = RLSContext(
            principal_id=uuid.UUID(int=0),
            workspace_id=uuid.UUID(int=0),
            token_scopes=("auth",),
            aal_level=1,
        )

        # Helper to create an active AAL2 session
        async def create_aal2_session() -> tuple[IssuedSession, dict[str, str], dict[str, str]]:
            async with factory.session(anon_ctx) as session:
                init_sess = await session_service.create_after_login(
                    session,
                    principal_id=admin_id,
                    workspace_id=ws_id,
                )
                elev = await session_service.elevate_aal(
                    session,
                    old_session_id=init_sess.session_id,
                )
            sess_cookies = {
                SESSION_COOKIE_NAME: elev.cookie_val,
                "kb_csrf": elev.csrf_token,
            }
            sess_headers = {"X-CSRF-Token": elev.csrf_token}
            return elev, sess_cookies, sess_headers

        # Case A: Idle expiration (> 900s inactive)
        sess_a, cookies_a, _ = await create_aal2_session()
        async with factory.session(anon_ctx) as session:
            await session.execute(
                text(
                    "UPDATE sessions SET aal2_last_active_at = now() - interval '950 seconds' "
                    "WHERE id = :id"
                ),
                {"id": sess_a.session_id},
            )

        client.cookies.clear()
        client.cookies.update(cookies_a)
        idle_resp = await client.get("/api/v1/admin/privileged/check")
        assert idle_resp.status_code == 403
        assert idle_resp.json()["code"] == "AAL2_STALE"

        # Case B: Absolute cap exceeded (> 14400s / 4 hours since verified)
        sess_b, cookies_b, _ = await create_aal2_session()
        async with factory.session(anon_ctx) as session:
            await session.execute(
                text(
                    "UPDATE sessions SET "
                    "aal2_verified_at = now() - interval '14500 seconds', "
                    "aal2_last_active_at = now() "
                    "WHERE id = :id"
                ),
                {"id": sess_b.session_id},
            )

        client.cookies.clear()
        client.cookies.update(cookies_b)
        cap_resp = await client.get("/api/v1/admin/privileged/check")
        assert cap_resp.status_code == 403
        assert cap_resp.json()["code"] == "AAL2_STALE"

        # Case C: Irreversible action isolation
        # Within absolute cap and idle window (verified 1000s ago, active now)
        sess_c, cookies_c, headers_c = await create_aal2_session()
        async with factory.session(anon_ctx) as session:
            await session.execute(
                text(
                    "UPDATE sessions SET "
                    "aal2_verified_at = now() - interval '1000 seconds', "
                    "aal2_last_active_at = now() "
                    "WHERE id = :id"
                ),
                {"id": sess_c.session_id},
            )

        client.cookies.clear()
        client.cookies.update(cookies_c)
        priv_ok = await client.get("/api/v1/admin/privileged/check")
        assert priv_ok.status_code == 200

        irrev_stale = await client.delete(
            "/api/v1/admin/irreversible/check",
            headers=headers_c,
        )
        assert irrev_stale.status_code == 403
        assert irrev_stale.json()["code"] == "AAL2_STALE"


@pytest.mark.asyncio
async def test_websudo_session_and_me_do_not_advance_sliding_window(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Validate session and me endpoints do not advance aal2_last_active_at."""
    factory = RLSSessionFactory(pg_worker_db)
    session_service = SessionService(key_material.session_hmac_key)
    rate_limiter = PgRateLimiter(pg_worker_db)

    ws_id, admin_id = await _provision_admin_user(factory)

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

    anon_ctx = RLSContext(
        principal_id=uuid.UUID(int=0),
        workspace_id=uuid.UUID(int=0),
        token_scopes=("auth",),
        aal_level=1,
    )

    async with factory.session(anon_ctx) as session:
        init_sess = await session_service.create_after_login(
            session,
            principal_id=admin_id,
            workspace_id=ws_id,
        )
        elev = await session_service.elevate_aal(
            session,
            old_session_id=init_sess.session_id,
        )
        # Set aal2_last_active_at to 120s ago
        await session.execute(
            text(
                "UPDATE sessions SET aal2_last_active_at = now() - interval '120 seconds' "
                "WHERE id = :id"
            ),
            {"id": elev.session_id},
        )
        res = await session.execute(
            text("SELECT aal2_last_active_at FROM sessions WHERE id = :id"),
            {"id": elev.session_id},
        )
        initial_active_at = res.scalar_one()

    cookies = {
        SESSION_COOKIE_NAME: elev.cookie_val,
        "kb_csrf": elev.csrf_token,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.clear()
        client.cookies.update(cookies)
        # 1. GET /api/v1/auth/session
        r1 = await client.get("/api/v1/auth/session")
        assert r1.status_code == 200
        assert r1.json()["aal2_active"] is True

        # 2. GET /api/v1/auth/me
        r2 = await client.get("/api/v1/auth/me")
        assert r2.status_code == 200
        assert r2.json()["aal2_active"] is True

    # 3. Verify in DB that aal2_last_active_at did NOT change
    async with factory.session(anon_ctx) as session:
        res = await session.execute(
            text("SELECT aal2_last_active_at FROM sessions WHERE id = :id"),
            {"id": elev.session_id},
        )
        after_active_at = res.scalar_one()
        assert after_active_at == initial_active_at


@pytest.mark.asyncio
async def test_websudo_db_write_throttling_30s(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Validate 30s write throttle (<= 1 write per 30s) in kb_auth.session_touch_aal2."""
    factory = RLSSessionFactory(pg_worker_db)
    session_service = SessionService(key_material.session_hmac_key)

    ws_id, admin_id = await _provision_admin_user(factory)

    anon_ctx = RLSContext(
        principal_id=uuid.UUID(int=0),
        workspace_id=uuid.UUID(int=0),
        token_scopes=("auth",),
        aal_level=1,
    )

    async with factory.session(anon_ctx) as session:
        init_sess = await session_service.create_after_login(
            session,
            principal_id=admin_id,
            workspace_id=ws_id,
        )
        elev = await session_service.elevate_aal(
            session,
            old_session_id=init_sess.session_id,
        )

        # Set aal2_last_active_at to 10 seconds ago (< 30s)
        await session.execute(
            text(
                "UPDATE sessions SET aal2_last_active_at = now() - interval '10 seconds' "
                "WHERE id = :id"
            ),
            {"id": elev.session_id},
        )
        res = await session.execute(
            text("SELECT aal2_last_active_at FROM sessions WHERE id = :id"),
            {"id": elev.session_id},
        )
        active_at_10s = res.scalar_one()

        # Call session_touch_aal2 without force -> throttled, no write
        t1 = await session.execute(
            text("SELECT * FROM kb_auth.session_touch_aal2(:id, 900, 14400, FALSE)"),
            {"id": elev.session_id},
        )
        row1 = t1.mappings().one()
        assert row1["aal2_active"] is True

        res2 = await session.execute(
            text("SELECT aal2_last_active_at FROM sessions WHERE id = :id"),
            {"id": elev.session_id},
        )
        assert res2.scalar_one() == active_at_10s

        # Now set aal2_last_active_at to 35 seconds ago (> 30s)
        await session.execute(
            text(
                "UPDATE sessions SET aal2_last_active_at = now() - interval '35 seconds' "
                "WHERE id = :id"
            ),
            {"id": elev.session_id},
        )

        # Call session_touch_aal2 without force -> unthrottled, updates timestamp
        t2 = await session.execute(
            text("SELECT * FROM kb_auth.session_touch_aal2(:id, 900, 14400, FALSE)"),
            {"id": elev.session_id},
        )
        row2 = t2.mappings().one()
        assert row2["aal2_active"] is True

        res3 = await session.execute(
            text("SELECT aal2_last_active_at FROM sessions WHERE id = :id"),
            {"id": elev.session_id},
        )
        assert res3.scalar_one() > active_at_10s


@pytest.mark.asyncio
async def test_approvals_strictly_rejects_none_aal2_verified_at() -> None:
    """Validate approvals rejects none aal2_verified_at with 403."""
    mock_session = AsyncMock()

    caller = MagicMock()
    caller.aal_level = 2
    caller.aal2_verified_at = None

    payload = CustomFieldApprovalApproveRequest(
        manifest_sha256="00" * 32,
        sp_warning_acknowledged=True,
    )

    with pytest.raises(ProblemException) as exc_info:
        await CustomFieldApprovalService.approve(
            session=mock_session,
            caller=caller,
            approval_id=uuid.uuid4(),
            payload=payload,
        )

    assert exc_info.value.status == 403
    assert exc_info.value.code == "AAL2_REQUIRED"
    assert "AAL2 verification is required" in (exc_info.value.detail or "")


def test_auth_models_repr_and_str() -> None:
    """Test __repr__ and __str__ for all 12 auth model classes (database.models.auth)."""
    now = datetime.now(UTC)
    u1 = uuid.uuid4()

    m1 = AuthProviderCard(
        id=u1,
        slug="google",
        provider_kind="OIDC",
        is_enabled=True,
        sort_rank=10,
        dek_kid="k1",
    )
    assert "AuthProviderCard" in repr(m1)
    assert str(m1) == repr(m1)

    m2 = UserSession(
        id=u1,
        principal_id=u1,
        workspace_id=u1,
        aal_level=2,
        mfa_pending=False,
        idle_expires_at=now,
        absolute_expires_at=now,
        revoked_at=None,
    )
    assert "UserSession" in repr(m2)
    assert str(m2) == repr(m2)

    m3 = LocalAdminCredential(
        principal_id=u1,
        username="admin",
        pepper_kid="p1",
        password_hash="hash",  # noqa: S106
    )
    assert "LocalAdminCredential" in repr(m3)
    assert str(m3) == repr(m3)

    m4 = OidcAuthRequest(id=u1, card_id=u1, state_hash=b"s" * 32, nonce="n", expires_at=now)
    assert "OidcAuthRequest" in repr(m4)
    assert str(m4) == repr(m4)

    m5 = TotpFactor(id=u1, principal_id=u1, status="ACTIVE", dek_kid="d1")
    assert "TotpFactor" in repr(m5)
    assert str(m5) == repr(m5)

    m6 = RecoveryCode(id=u1, principal_id=u1, code_hmac=b"h" * 32)
    assert "RecoveryCode" in repr(m6)
    assert str(m6) == repr(m6)

    m7 = LdapGroupMapping(id=u1, card_id=u1, workspace_id=u1, ldap_dn="cn=adm", group_name="adm")
    assert "LdapGroupMapping" in repr(m7)
    assert str(m7) == repr(m7)

    m8 = WebauthnCredential(id=u1, principal_id=u1, credential_id=b"cid", nickname="key")
    assert "WebauthnCredential" in repr(m8)
    assert str(m8) == repr(m8)

    m9 = WebauthnChallenge(id=u1, session_id=u1, purpose="auth", challenge=b"ch", expires_at=now)
    assert "WebauthnChallenge" in repr(m9)
    assert str(m9) == repr(m9)

    m10 = UserIdentity(
        id=u1,
        workspace_id=u1,
        principal_id=u1,
        auth_card_id=u1,
        immutable_subject_id="sub1",
    )
    assert "UserIdentity" in repr(m10)
    assert str(m10) == repr(m10)

    m11 = IdentityLinkIntent(
        id=u1,
        principal_id=u1,
        session_id=u1,
        target_card_id=u1,
        expires_at=now,
    )
    assert "IdentityLinkIntent" in repr(m11)
    assert str(m11) == repr(m11)

    m12 = SetupClaimToken(id=u1, token_hmac=b"h" * 32, expires_at=now)
    assert "SetupClaimToken" in repr(m12)
    assert str(m12) == repr(m12)


@pytest.mark.asyncio
async def test_aal2_policy_coverage_edges() -> None:  # noqa: PLR0915
    """Validate policy edge cases in kanban.auth.mfa.policy."""
    req = MagicMock()
    req.app.state.session_factory = None

    p = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        aal_level=1,
        token_scopes=("read",),
        aal2_verified_at=None,
    )

    # 1. _get_enrolled_methods when session_factory is None
    methods = await _get_enrolled_methods(req, p)
    assert methods == []

    # 2. _RequireAal2 verification_only with verified_at = None
    req.state = MagicMock()
    req.app.state.session_factory = None
    dep_vo = _RequireAal2(verification_only=True)
    elev_p = replace(p, aal_level=2, aal2_verified_at=None)
    with pytest.raises(ProblemException) as exc:
        await dep_vo(req, elev_p)
    assert exc.value.code == "AAL2_STALE"

    # 3. _RequireAal2 verification_only with naive datetime (no tzinfo)
    naive_dt = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=10)
    elev_p_naive = replace(p, aal_level=2, aal2_verified_at=naive_dt)
    res_p = await dep_vo(req, elev_p_naive)
    assert res_p.aal_level == 2

    # 4. _RequireAal2 max_age_seconds with verified_at = None
    dep_age = _RequireAal2(max_age_seconds=300)
    with pytest.raises(ProblemException) as exc:
        await dep_age(req, elev_p)
    assert exc.value.code == "AAL2_STALE"

    # 5. _RequireAal2 max_age_seconds expired (> 300s)
    stale_dt = datetime.now(UTC) - timedelta(seconds=400)
    elev_p_stale = replace(p, aal_level=2, aal2_verified_at=stale_dt)
    with pytest.raises(ProblemException) as exc:
        await dep_age(req, elev_p_stale)
    assert exc.value.code == "AAL2_STALE"

    # 6. require_admin_aal2 with MCP credential lacking admin surface
    mcp_p = replace(
        p,
        is_mcp_credential=True,
        credential_boundary=CredentialBoundary(surface="agent", has_aal2_provenance=False),
    )
    with pytest.raises(ProblemException) as exc:
        await require_admin_aal2(req, mcp_p)
    assert exc.value.code == "AAL2_REQUIRED"

    # require_admin_aal2 when session_factory is None -> RuntimeError
    with pytest.raises(RuntimeError):
        await require_admin_aal2(req, p)

    # Now configure mock session factory on req.app.state
    mock_db = AsyncMock()
    req.app.state.session_factory = MagicMock()
    req.app.state.session_factory.session.return_value.__aenter__.return_value = mock_db

    # Non-admin principal (is_admin is False) -> FORBIDDEN
    mock_role_res = MagicMock()
    mock_role_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_role_res
    non_admin_p = replace(p, token_scopes=("viewer",), aal_level=2)
    with pytest.raises(ProblemException) as exc:
        await require_admin_aal2(req, non_admin_p)
    assert exc.value.code == "FORBIDDEN"

    # Admin role is present
    mock_role_res.scalar_one_or_none.return_value = 1

    # Status returns factors
    mock_status_res = MagicMock()
    mock_status_res.mappings.return_value.first.return_value = {
        "webauthn_credential_count": 1,
        "has_active_totp": True,
        "unused_recovery_codes": 2,
    }
    mock_db.execute.side_effect = [mock_role_res, mock_status_res]
    admin_p = replace(p, token_scopes=("server:admin",), aal_level=1)
    with pytest.raises(ProblemException) as exc:
        await require_admin_aal2(req, admin_p)
    assert exc.value.code == "AAL2_REQUIRED"
    assert exc.value.methods is not None
    assert "webauthn" in exc.value.methods
    assert "totp" in exc.value.methods
    assert "recovery" in exc.value.methods

    # Admin with 0 factors enrolled and no admin key -> MFA_ENROLLMENT_REQUIRED
    mock_status_res_none = MagicMock()
    mock_status_res_none.mappings.return_value.first.return_value = {
        "webauthn_credential_count": 0,
        "has_active_totp": False,
        "unused_recovery_codes": 0,
    }
    mock_db.execute.side_effect = [mock_role_res, mock_status_res_none]
    with pytest.raises(ProblemException) as exc:
        await require_admin_aal2(req, admin_p)
    assert exc.value.code == "MFA_ENROLLMENT_REQUIRED"

    # MCP credential with admin surface, AAL2 provenance, admin role,
    # 0 factors (bypassed) and session_id=None
    mock_db.execute.side_effect = [mock_role_res, mock_status_res_none]
    mcp_admin_ok = replace(
        p,
        token_scopes=("server:admin",),
        aal_level=2,
        session_id=None,
        is_mcp_credential=True,
        credential_boundary=CredentialBoundary(surface="admin", has_aal2_provenance=True),
    )
    mcp_out = await require_admin_aal2(req, mcp_admin_ok)
    assert mcp_out.aal_level == 2

    # Verification only expired (> max_age_seconds)
    mock_db.execute.side_effect = None
    mock_db.execute.return_value = mock_status_res
    stale_vo_dt = datetime.now(UTC) - timedelta(seconds=1000)
    elev_p_vo_stale = replace(p, aal_level=2, aal2_verified_at=stale_vo_dt)
    with pytest.raises(ProblemException) as exc:
        await dep_vo(req, elev_p_vo_stale)
    assert exc.value.code == "AAL2_STALE"

    # require_aal2 helper function
    dep_helper = require_aal2(max_age_seconds=60, verification_only=True)
    assert isinstance(dep_helper, _RequireAal2)
    assert dep_helper.max_age_seconds == 60

    # Empty status row in _get_enrolled_methods
    mock_res_empty = MagicMock()
    mock_res_empty.mappings.return_value.first.return_value = None
    mock_db.execute.side_effect = None
    mock_db.execute.return_value = mock_res_empty
    methods_empty = await _get_enrolled_methods(req, admin_p)
    assert methods_empty == []

    # 8. assert_admin_routes_protected on app with both unprotected and protected routes
    class SimpleRoute:
        def __init__(self, path: str, *, protected: bool = False) -> None:
            self.path = path
            self.dependant = MagicMock()
            if protected:
                self.dependant.call = require_admin_aal2
                self.dependant.dependencies = []
            else:
                self.dependant.call = None
                self.dependant.dependencies = []

    class ComplexRoute:
        def __init__(self, path: str) -> None:
            self.ctx = SimpleRoute(path, protected=False)

        def effective_route_contexts(self) -> list[SimpleRoute]:
            return [self.ctx]

    mock_app = MagicMock()
    mock_app.routes = [
        SimpleRoute("/api/v1/admin/unprotected_simple", protected=False),
        SimpleRoute("/api/v1/admin/protected_simple", protected=True),
        ComplexRoute("/api/v1/admin/unprotected_complex"),
        SimpleRoute("/api/v1/public/home", protected=False),
    ]
    unprot = assert_admin_routes_protected(mock_app)
    assert "/api/v1/admin/unprotected_simple" in unprot
    assert "/api/v1/admin/unprotected_complex" in unprot
    assert "/api/v1/admin/protected_simple" not in unprot
    assert "/api/v1/public/home" not in unprot


@pytest.mark.asyncio
async def test_auth_session_endpoints_coverage_edges(  # noqa: PLR0915
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Validate session and logout endpoint edge cases in kanban.api.v1.auth_session."""
    factory = RLSSessionFactory(pg_worker_db)
    session_service = SessionService(key_material.session_hmac_key)
    ws_id, admin_id = await _provision_admin_user(factory)

    anon_ctx = RLSContext(
        principal_id=uuid.UUID(int=0),
        workspace_id=uuid.UUID(int=0),
        token_scopes=("auth",),
        aal_level=1,
    )
    async with factory.session(anon_ctx) as s:
        issued = await session_service.create_after_login(
            s,
            principal_id=admin_id,
            workspace_id=ws_id,
        )

    req = MagicMock()
    req.state = MagicMock()
    req.state.user_session = None
    req.app.state.session_factory = factory
    p_ctx = MagicMock()
    p_ctx.session_id = issued.session_id
    idle, abs_exp, _is_p = await _fetch_session_expiry(req, p_ctx)
    assert idle is not None
    assert abs_exp is not None

    # Line 63-69: _fetch_session_expiry with cached user_session on request.state
    cached_sess = MagicMock()
    cached_sess.id = issued.session_id
    cached_sess.idle_expires_at = datetime.now(UTC) + timedelta(minutes=15)
    cached_sess.absolute_expires_at = datetime.now(UTC) + timedelta(hours=24)
    cached_sess.is_persistent = True
    req.state.user_session = cached_sess
    c_idle, _c_abs, c_p = await _fetch_session_expiry(req, p_ctx)
    assert c_p is True
    assert c_idle == cached_sess.idle_expires_at

    # Line 92: _fetch_session_expiry when session_factory is None
    req.state.user_session = None
    req.app.state.session_factory = None
    idle_none, _, _ = await _fetch_session_expiry(req, p_ctx)
    assert idle_none is None

    # Test API endpoints
    app = FastAPI()
    app.state.session_service = session_service
    app.state.session_factory = factory
    app.state.key_material = key_material
    resolver = SessionCookieResolver(session_service, factory)
    app.state.principal_resolver = resolver
    v1 = build_v1_router()
    app.include_router(v1, prefix="/api/v1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Unauthenticated session check
        res_anon = await client.get("/api/v1/auth/session")
        assert res_anon.status_code == 200
        assert res_anon.json()["authenticated"] is False

        # 2. Dead session cookie (triggers clear cookie header)
        res_dead = await client.get(
            "/api/v1/auth/session",
            headers={"Cookie": f"{SESSION_COOKIE_NAME}=dead_cookie_value;"},
        )
        assert res_dead.status_code == 200
        assert res_dead.json()["authenticated"] is False

        # Set valid cookies on client for authenticated checks
        client.cookies.set(SESSION_COOKIE_NAME, issued.cookie_val)
        client.cookies.set("kb_csrf", issued.csrf_token)
        headers = {
            "Host": "localhost",
            "X-Forwarded-Proto": "http",
            "X-CSRF-Token": issued.csrf_token,
        }

        # 3. Authenticated session check (AAL1)
        res_auth1 = await client.get("/api/v1/auth/session", headers=headers)
        assert res_auth1.status_code == 200
        assert res_auth1.json()["authenticated"] is True
        assert res_auth1.json()["aal2_active"] is False

        # 4. Touch at AAL1 returns 200 with aal2_active=False
        res_touch_aal1 = await client.post("/api/v1/auth/aal2/touch", headers=headers)
        assert res_touch_aal1.status_code == 200
        assert res_touch_aal1.json()["aal2_active"] is False

        # 5. Elevate session to AAL2 in DB
        async with factory.session(anon_ctx) as s:
            await s.execute(
                text(
                    "UPDATE sessions SET "
                    "aal_level = 2, "
                    "aal2_verified_at = now() - interval '60 seconds', "
                    "aal2_last_active_at = now() - interval '30 seconds' "
                    "WHERE id = :id"
                ),
                {"id": issued.session_id},
            )

        # 6. Authenticated session check at AAL2
        res_auth2 = await client.get("/api/v1/auth/session", headers=headers)
        assert res_auth2.status_code == 200
        assert res_auth2.json()["authenticated"] is True
        assert res_auth2.json()["aal2_active"] is True
        assert res_auth2.json()["aal2_expires_at"] is not None

        # 7. Touch at AAL2 succeeds and returns header
        res_touch_aal2 = await client.post("/api/v1/auth/aal2/touch", headers=headers)
        assert res_touch_aal2.status_code == 200
        assert res_touch_aal2.json()["aal2_active"] is True
        assert "X-KB-AAL2-Expires-At" in res_touch_aal2.headers

        # 8. Touch when session_factory is None
        app.state.session_factory = None
        res_touch_no_fact = await client.post("/api/v1/auth/aal2/touch", headers=headers)
        assert res_touch_no_fact.status_code == 200
        assert res_touch_no_fact.json()["aal2_active"] is False
        app.state.session_factory = factory

        # 9. GET /me profile endpoint
        res_me = await client.get("/api/v1/auth/me", headers=headers)
        assert res_me.status_code == 200

        # 10. Drop AAL2 elevation
        res_drop = await client.post("/api/v1/auth/aal2/drop", headers=headers)
        assert res_drop.status_code == 200
        assert res_drop.json()["aal2_active"] is False

        # 11. Drop when session_factory is None
        app.state.session_factory = None
        res_drop_no_fact = await client.post("/api/v1/auth/aal2/drop", headers=headers)
        assert res_drop_no_fact.status_code == 200
        app.state.session_factory = factory

        # 12. Test compatibility aliases with mocked handlers
        with (
            patch("kanban.api.v1.auth_session.enroll_totp", new_callable=AsyncMock) as m_enroll,
            patch("kanban.api.v1.auth_session.confirm_totp", new_callable=AsyncMock) as m_confirm,
            patch("kanban.api.v1.auth_session.verify_mfa", new_callable=AsyncMock) as m_verify,
        ):
            m_enroll.return_value = JSONResponse({"enrolled": True})
            m_confirm.return_value = JSONResponse({"confirmed": True})
            m_verify.return_value = JSONResponse({"verified": True})

            res_enroll = await client.post("/api/v1/auth/totp/enroll", headers=headers)
            assert res_enroll.status_code == 200

            res_confirm = await client.post(
                "/api/v1/auth/totp/enroll/verify", json={"code": "123456"}, headers=headers
            )
            assert res_confirm.status_code == 200

            res_totp_v = await client.post(
                "/api/v1/auth/totp/verify", json={"code": "123456"}, headers=headers
            )
            assert res_totp_v.status_code == 200

            res_rec_v = await client.post(
                "/api/v1/auth/recovery/verify", json={"code": "123456"}, headers=headers
            )
            assert res_rec_v.status_code == 200

        # 13. Logout with active session
        res_logout = await client.post("/api/v1/auth/logout", headers=headers)
        assert res_logout.status_code == 200
        assert res_logout.json()["status"] == "logged_out"

        # 14. Logout when already unauthenticated
        client.cookies.clear()
        res_logout_unauth = await client.post(
            "/api/v1/auth/logout",
            headers={"Host": "localhost", "X-Forwarded-Proto": "http"},
        )
        assert res_logout_unauth.status_code == 200
        assert res_logout_unauth.json()["status"] == "logged_out"

    # 15. Directly test get_session_info with fallback verification timestamp
    mock_req = MagicMock()
    mock_req.app.state.key_material = key_material
    mock_req.app.state.session_factory = factory
    now_utc = datetime.now(UTC)
    mock_p_fallback = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        session_id=issued.session_id,
        token_scopes=("auth",),
        aal_level=2,
        aal2_expires_at=None,
        aal2_verified_at=now_utc - timedelta(seconds=60),
        aal2_last_active_at=now_utc - timedelta(seconds=30),
    )
    mock_req.state.principal = mock_p_fallback
    mock_req.headers = {}
    resp_fallback = await get_session_info(mock_req)
    assert resp_fallback.status_code == 200

    # Naive datetimes (no tzinfo)
    mock_p_naive = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        session_id=issued.session_id,
        token_scopes=("auth",),
        aal_level=2,
        aal2_expires_at=None,
        aal2_verified_at=(now_utc - timedelta(seconds=60)).replace(tzinfo=None),
        aal2_last_active_at=(now_utc - timedelta(seconds=30)).replace(tzinfo=None),
    )
    mock_req.state.principal = mock_p_naive
    resp_naive = await get_session_info(mock_req)
    assert resp_naive.status_code == 200

    # Fallback when aal2_last_active_at is None
    mock_p_no_active = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        session_id=issued.session_id,
        token_scopes=("auth",),
        aal_level=2,
        aal2_expires_at=None,
        aal2_verified_at=now_utc - timedelta(seconds=60),
        aal2_last_active_at=None,
    )
    mock_req.state.principal = mock_p_no_active
    resp_no_act = await get_session_info(mock_req)
    assert resp_no_act.status_code == 200

    # aal2_expires_at is expired when current time is past expiration timestamp
    mock_p_exp = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        session_id=issued.session_id,
        token_scopes=("auth",),
        aal_level=2,
        aal2_expires_at=now_utc - timedelta(seconds=10),
        aal2_verified_at=now_utc - timedelta(seconds=100),
    )
    mock_req.state.principal = mock_p_exp
    resp_exp = await get_session_info(mock_req)
    assert resp_exp.status_code == 200

    # touch_aal2_session when session_touch_aal2 returns inactive
    mock_db_inactive = AsyncMock()
    mock_row_inactive = MagicMock()
    mock_row_inactive.mappings.return_value.first.return_value = {
        "aal2_active": False,
        "aal2_expires_at": None,
    }
    mock_db_inactive.execute.return_value = mock_row_inactive
    mock_factory_inactive = MagicMock()
    mock_factory_inactive.session.return_value.__aenter__.return_value = mock_db_inactive
    mock_req.app.state.session_factory = mock_factory_inactive
    res_touch_inactive = await touch_aal2_session(mock_req, mock_p_fallback)
    assert res_touch_inactive.status_code == 200

    # drop_aal2_session when session_id is None
    mock_p_no_sid = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        session_id=None,
        token_scopes=("auth",),
        aal_level=1,
    )
    res_drop_no_sid = await drop_aal2_session(mock_req, mock_p_no_sid)
    assert res_drop_no_sid.status_code == 200
