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
from typing import TYPE_CHECKING, Annotated, Final
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import text
from starlette.responses import JSONResponse

from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext  # noqa: TC001  # Required at runtime for FastAPI dependency analysis
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.api.v1.schemas.custom_fields import CustomFieldApprovalApproveRequest
from kanban.auth.mfa.policy import require_aal2, require_admin_aal2
from kanban.auth.sessions.cookies import SESSION_COOKIE_NAME
from kanban.auth.sessions.csrf import CsrfMiddleware
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import IssuedSession, SessionService
from kanban.custom_fields.approvals import CustomFieldApprovalService
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
        client.cookies.update({
            SESSION_COOKIE_NAME: sess_issued.cookie_val,
            "kb_csrf": sess_issued.csrf_token,
        })
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
        client.cookies.update({
            SESSION_COOKIE_NAME: elevated.cookie_val,
            "kb_csrf": elevated.csrf_token,
        })
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
