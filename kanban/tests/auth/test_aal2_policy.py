# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and integration tests for AAL2 policies and admin route audit.

Implements KB-P2-05a, Test Cases 9 and 10.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Final

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import JSONResponse

from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext
from kanban.api.problems import (
    PROBLEM_HELP_CATALOG,
    ProblemException,
    problem_exception_handler,
    resolve_problem_help,
)
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.auth.mfa.policy import (
    assert_admin_routes_protected,
    require_aal2,
    require_admin_aal2,
)
from kanban.auth.sessions.cookies import SESSION_COOKIE_NAME
from kanban.auth.sessions.csrf import CsrfMiddleware
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


async def _provision_admin_user(
    factory: RLSSessionFactory,
    *,
    is_admin: bool = True,
    enroll_totp: bool = True,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision workspace, principal, role bindings, and optional TOTP factor."""
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)
    async with factory.session(ctx) as db_session:
        await db_session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Policy WS"},
        )
        await db_session.execute(
            text(
                "SELECT register_object("
                "'user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
            ),
            {"ws_id": ws_id, "ckey": f"usr-{p_id.hex}", "title": "Admin User", "u_id": p_id},
        )
        await db_session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'Admin User', 'ACTIVE')"
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
        if is_admin:
            await db_session.execute(
                text(
                    "INSERT INTO role_bindings "
                    "(id, workspace_id, principal_id, role, scope_type, project_id) "
                    "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
                ),
                {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": p_id},
            )

        if enroll_totp:
            # Insert confirmed/active factor via kb_auth.totp_enroll and totp_confirm
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
async def test_case_9_aal2_policy_enforcement(  # noqa: PLR0915
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Test Case 9: AAL2 policy enforcement matrix.

    AAL1 admin on admin route -> 403 AAL2_REQUIRED;
    unenrolled -> 403 MFA_ENROLLMENT_REQUIRED;
    stale -> 403 AAL2_STALE.
    """
    factory = RLSSessionFactory(pg_worker_db)
    session_service = SessionService(key_material.session_hmac_key)
    rate_limiter = PgRateLimiter(pg_worker_db)

    # 1. Admin with confirmed factor
    ws_id, admin_with_factor = await _provision_admin_user(factory, is_admin=True, enroll_totp=True)

    # 2. Admin WITHOUT factor
    _, admin_no_factor = await _provision_admin_user(factory, is_admin=True, enroll_totp=False)

    # 3. Non-admin user
    _, non_admin = await _provision_admin_user(factory, is_admin=False, enroll_totp=True)

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

    # Register admin test route protected by require_admin_aal2
    @app.get("/api/v1/admin/server/settings")
    async def admin_settings(
        principal: Annotated[PrincipalContext, Depends(require_admin_aal2)],
    ) -> JSONResponse:
        return JSONResponse({"status": "ok", "principal_id": str(principal.principal_id)})

    # Register route with require_aal2(max_age_seconds=900)
    @app.get("/api/v1/sensitive/action")
    async def sensitive_action(
        principal: Annotated[PrincipalContext, Depends(require_aal2(max_age_seconds=900))],
    ) -> JSONResponse:
        return JSONResponse({"status": "fresh", "principal_id": str(principal.principal_id)})

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

        # Scenario A: Admin with factor but AAL1 session -> 403 AAL2_REQUIRED
        async with factory.session(anon_ctx) as session:
            sess_aal1 = await session_service.create_after_login(
                session,
                principal_id=admin_with_factor,
                workspace_id=ws_id,
                aal_level=1,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal1.cookie_val)
        res_a = await client.get("/api/v1/admin/server/settings")
        assert res_a.status_code == 403
        assert res_a.json()["code"] == "AAL2_REQUIRED"

        # Scenario B: Admin without factor -> 403 MFA_ENROLLMENT_REQUIRED
        async with factory.session(anon_ctx) as session:
            sess_no_mfa = await session_service.create_after_login(
                session,
                principal_id=admin_no_factor,
                workspace_id=ws_id,
                aal_level=1,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_no_mfa.cookie_val)
        res_b = await client.get("/api/v1/admin/server/settings")
        assert res_b.status_code == 403
        assert res_b.json()["code"] == "MFA_ENROLLMENT_REQUIRED"

        # Scenario C: Non-admin principal -> 403 FORBIDDEN
        async with factory.session(anon_ctx) as session:
            sess_non_admin = await session_service.create_after_login(
                session,
                principal_id=non_admin,
                workspace_id=ws_id,
                aal_level=2,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_non_admin.cookie_val)
        res_c = await client.get("/api/v1/admin/server/settings")
        assert res_c.status_code == 403
        assert res_c.json()["code"] == "FORBIDDEN"

        # Scenario D: Admin with factor and AAL2 session -> 200 OK
        async with factory.session(anon_ctx) as session:
            sess_aal2 = await session_service.create_after_login(
                session,
                principal_id=admin_with_factor,
                workspace_id=ws_id,
                aal_level=2,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal2.cookie_val)
        res_d = await client.get("/api/v1/admin/server/settings")
        assert res_d.status_code == 200
        assert res_d.json()["status"] == "ok"

        # Scenario E: require_aal2(max_age_seconds=900) fresh (< 900s) -> 200 OK
        res_e = await client.get("/api/v1/sensitive/action")
        assert res_e.status_code == 200
        assert res_e.json()["status"] == "fresh"

        # Scenario F: require_aal2(max_age_seconds=900) at 901s -> 403 AAL2_STALE
        stale_time = datetime.now(UTC) - timedelta(seconds=905)
        async with factory.session(anon_ctx) as session:
            await session.execute(
                text(
                    "UPDATE sessions SET aal2_verified_at = :stale, "
                    "aal2_last_active_at = :stale WHERE id = :id"
                ),
                {"stale": stale_time, "id": sess_aal2.session_id},
            )

        res_f = await client.get("/api/v1/sensitive/action")
        assert res_f.status_code == 403
        assert res_f.json()["code"] == "AAL2_STALE"
        res_f_admin = await client.get("/api/v1/admin/server/settings")
        assert res_f_admin.status_code == 403
        assert res_f_admin.json()["code"] == "AAL2_STALE"

        # Scenario G: AAL1 session on require_aal2 -> 403 AAL2_REQUIRED
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal1.cookie_val)
        res_g = await client.get("/api/v1/sensitive/action")
        assert res_g.status_code == 403
        assert res_g.json()["code"] == "AAL2_REQUIRED"

        # Scenario H: AAL2 session with NULL aal2_verified_at -> 403 AAL2_STALE
        async with factory.session(anon_ctx) as session:
            await session.execute(
                text("UPDATE sessions SET aal2_verified_at = NULL WHERE id = :id"),
                {"id": sess_aal2.session_id},
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal2.cookie_val)
        res_h = await client.get("/api/v1/sensitive/action")
        assert res_h.status_code == 403
        assert res_h.json()["code"] == "AAL2_STALE"
        res_h_admin = await client.get("/api/v1/admin/server/settings")
        assert res_h_admin.status_code == 403
        assert res_h_admin.json()["code"] == "AAL2_STALE"


@pytest.mark.asyncio
async def test_require_admin_aal2_missing_factory() -> None:
    """Verify require_admin_aal2 raises RuntimeError if session_factory is missing."""
    dummy_app = FastAPI()
    from starlette.requests import Request  # noqa: PLC0415

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/admin/test",
        "headers": [],
        "app": dummy_app,
    }
    req = Request(scope)
    ctx = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        aal_level=2,
    )
    with pytest.raises(RuntimeError, match="Session factory is not configured"):
        await require_admin_aal2(req, ctx)


def test_case_10_assert_admin_routes_protected() -> None:
    """Test Case 10: Verify assert_admin_routes_protected catches missing deps.

    Returns [] initially; returns path on unprotected admin route.
    """
    app = FastAPI()

    # Initial state with standard canonical v1 routes
    v1 = build_v1_router()
    app.include_router(v1, prefix="/api/v1")

    # 1. Assert initial routes are all protected (no unprotected /api/v1/admin routes)
    unprotected = assert_admin_routes_protected(app)
    assert unprotected == []

    # 2. Register an unprotected admin route
    @app.get("/api/v1/admin/x")
    async def unprotected_admin_x() -> JSONResponse:
        return JSONResponse({"status": "unprotected"})

    # 3. Assert auditor flags the unprotected admin route
    unprotected_after = assert_admin_routes_protected(app)
    assert unprotected_after == ["/api/v1/admin/x"]

    # 4. Register a properly protected admin route
    @app.get("/api/v1/admin/y", dependencies=[Depends(require_admin_aal2)])
    async def protected_admin_y() -> JSONResponse:
        return JSONResponse({"status": "protected"})

    unprotected_with_y = assert_admin_routes_protected(app)
    # y is protected, so only x should still be in unprotected
    assert unprotected_with_y == ["/api/v1/admin/x"]


@pytest.mark.asyncio
async def test_aal2_stale_human_readable_and_problem_doc_links() -> None:
    """Verify human-readable AAL2_STALE detail string, doc_href, and help_summary (KAN-393)."""
    # 1. Verify ProblemException default resolution from catalog
    detail_msg = (
        "AAL2 verification is stale (950s > 900s). Your 15-minute Admin 2FA security window "
        "(Authenticator Assurance Level 2) has expired; please re-verify with your "
        "Passkey or Authenticator app (TOTP) to continue."
    )
    exc = ProblemException(
        code="AAL2_STALE",
        status=403,
        title="AAL2 Session Stale",
        detail=detail_msg,
    )
    expected_doc, expected_summary = PROBLEM_HELP_CATALOG["AAL2_STALE"]
    assert exc.doc_href == expected_doc
    assert exc.help_summary == expected_summary
    assert "AAL2 verification is stale (950s > 900s)." in str(exc.detail)
    assert "Your 15-minute Admin 2FA security window" in str(exc.detail)

    # 2. Verify problem_exception_handler populates doc_href and help_summary
    scope = {"type": "http", "method": "GET", "path": "/api/v1/admin/test", "headers": []}
    req = Request(scope)
    res = await problem_exception_handler(req, exc)
    data = json.loads(bytes(res.body).decode("utf-8"))
    assert data["code"] == "AAL2_STALE"
    assert data["doc_href"] == expected_doc
    assert data["help_summary"] == expected_summary
    assert "AAL2 verification is stale" in data["detail"]

    # 3. Verify resolve_problem_help fallback
    doc, summary = resolve_problem_help("UNKNOWN_RANDOM_CODE")
    assert doc == "/docs/admin-diagnostics-and-link-inspector-studio"
    assert "troubleshooting steps" in summary

    doc_404, summary_404 = resolve_problem_help("NOT_FOUND", 404)
    assert doc_404 == "/docs/zero-trust-security-and-access-visibility"
    assert "requested resource was not found" in summary_404
