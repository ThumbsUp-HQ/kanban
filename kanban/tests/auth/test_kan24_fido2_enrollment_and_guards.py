# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration and unit tests for KAN-24 WebAuthn and FIDO2 policy enhancements.

Verifies:
1. Hardware FIDO2 Security Key Compatibility (UV=PREFERRED, UP=True).
2. Authenticator attachment modality hint ('platform' | 'cross-platform' | null).
3. First-factor enrollment deadlock fix and automatic AAL2 elevation.
4. Second-factor registration enforcement (AAL2 freshness within 900s) with methods.
5. WORKSPACE_ADMIN and is_server_admin last-factor lockout prevention.
6. Credential metadata (aaguid, transports, suspect_clone_at) in GET and PATCH.
7. Clone detection setting suspect_clone_at on sign count regression.
8. Step-up methods discovery (totp, webauthn, recovery) in problem documents.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Final
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import JSONResponse
from webauthn.helpers.structs import AuthenticatorAttachment

from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext
from kanban.api.problems import Problem, ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1.auth_mfa import delete_totp
from kanban.api.v1.auth_mfa import router as mfa_router
from kanban.api.v1.auth_webauthn import (
    WebauthnRenameRequest,
    _assert_can_register,
    rename_credential,
)
from kanban.api.v1.auth_webauthn import (
    router as webauthn_router,
)
from kanban.auth.cards.repository import admin_upsert
from kanban.auth.local.hashing import hash_password_sync
from kanban.auth.mfa.policy import (
    _get_enrolled_methods,
    _RequireAal2,
    require_aal2,
    require_admin_aal2,
)
from kanban.auth.mfa.totp import TotpService
from kanban.auth.mfa.webauthn import (
    WebauthnService,
    _extract_client_data,
    _parse_aaguid,
)
from kanban.auth.sessions.cookies import SESSION_COOKIE_NAME
from kanban.auth.sessions.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, CsrfMiddleware
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionService
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
def webauthn_settings() -> Settings:
    """Provide settings configured for testing WebAuthn domain."""
    return Settings(
        deployment_mode="production",
        public_origin=ORIGIN,
        webauthn_rp_id=RP_ID,
        webauthn_rp_name="👍kanban",
    )


async def _setup_principal_with_role(
    factory: RLSSessionFactory,
    key_material: KeyMaterial,
    *,
    username: str,
    role: str = "WORKSPACE_ADMIN",
    scope_type: str = "workspace",
) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision workspace, principal, local credential, and role binding."""
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()
    card_id = uuid.uuid4()
    pw_hash = hash_password_sync("Password123!", key_material.auth_pepper)
    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)

    async with factory.session(ctx) as session:
        await session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:8]}", "name": f"Workspace {username}"},
        )
        await session.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', :name)"
            ),
            {"id": p_id, "ws_id": ws_id, "name": f"Display {username}"},
        )
        # Always insert SERVER_ADMIN initially so card_admin_upsert succeeds under RLS
        await session.execute(
            text(
                "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type) "
                "VALUES (:ws_id, :p_id, 'SERVER_ADMIN', 'server')"
            ),
            {"ws_id": ws_id, "p_id": p_id},
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
        # Update role binding to requested role and scope
        if role != "SERVER_ADMIN" or scope_type != "server":
            await session.execute(
                text(
                    "UPDATE role_bindings SET role = :role, scope_type = :scope_type "
                    "WHERE workspace_id = :ws_id AND principal_id = :p_id"
                ),
                {"ws_id": ws_id, "p_id": p_id, "role": role, "scope_type": scope_type},
            )

    return ws_id, p_id


def _build_test_app(
    factory: RLSSessionFactory,
    key_material: KeyMaterial,
    rate_limiter: PgRateLimiter,
    settings: Settings,
) -> tuple[FastAPI, SessionService]:
    """Create test application mounted with auth WebAuthn and MFA routers."""
    session_service = SessionService(key_material.session_hmac_key)
    app = FastAPI(title="👍kanban API")
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
    app.state.totp_service = TotpService(app.state.kek_provider)

    resolver = SessionCookieResolver(session_service, factory)
    app.state.principal_resolver = resolver
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]

    app.include_router(webauthn_router, prefix="/api/v1")
    app.include_router(mfa_router, prefix="/api/v1")

    # Test routes for AAL2 enforcement policies
    @app.get("/api/v1/test/sensitive")
    async def test_sensitive(
        principal: Annotated[PrincipalContext, Depends(require_aal2(max_age_seconds=900))],
    ) -> JSONResponse:
        return JSONResponse({"status": "ok", "user": str(principal.principal_id)})

    @app.get("/api/v1/admin/test/route")
    async def test_admin_route(
        principal: Annotated[PrincipalContext, Depends(require_admin_aal2)],
    ) -> JSONResponse:
        return JSONResponse({"status": "admin_ok", "user": str(principal.principal_id)})

    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_middleware(RequestIdMiddleware)
    return app, session_service


def _sync_cookies(client: httpx.AsyncClient, response: httpx.Response) -> None:
    """Sync response cookies into AsyncClient cookie jar."""
    for c in response.cookies.jar:
        client.cookies.set(c.name, c.value or "")


@pytest.mark.asyncio
async def test_kan24_hardware_fido2_key_up_only_compatibility(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Verify hardware security keys with UP=True, UV=False register and authenticate."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    ws_id, p_id = await _setup_principal_with_role(
        factory, key_material, username="hw_user_1", role="WORKSPACE_MEMBER"
    )
    app, session_service = _build_test_app(factory, key_material, rate_limiter, webauthn_settings)
    auth = SoftAuthenticator()

    async with factory.session(RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)) as s:
        sess = await session_service.create_after_login(
            s, principal_id=p_id, workspace_id=ws_id, aal_level=1, mfa_pending=False
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(SESSION_COOKIE_NAME, sess.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess.csrf_token)

        # 1. Registration options with attachment hint 'cross-platform'
        opt_res = await client.post(
            "/api/v1/auth/webauthn/register/options",
            headers={CSRF_HEADER_NAME: sess.csrf_token},
            json={"authenticator_attachment": "cross-platform"},
        )
        assert opt_res.status_code == 200
        opts = opt_res.json()
        assert opts["authenticatorSelection"]["authenticatorAttachment"] == "cross-platform"
        assert opts["authenticatorSelection"]["userVerification"] == "preferred"
        assert opts["authenticatorSelection"]["residentKey"] == "preferred"
        assert opts["user"]["displayName"] == "Display hw_user_1"

        # 2. Register credential with UP=True, UV=False (hardware key touch without PIN)
        cred_up_only = auth.create_credential(opts, origin=ORIGIN, uv=False, up=True)
        reg_res = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: sess.csrf_token},
            json={"credential": cred_up_only, "nickname": "USB Hardware Key"},
        )
        assert reg_res.status_code == 200
        reg_data = reg_res.json()
        assert reg_data["nickname"] == "USB Hardware Key"

        # Session was elevated to AAL2 upon first enrollment
        cookies = {c.name: c.value for c in reg_res.cookies.jar}
        new_sess_token = cookies.get(SESSION_COOKIE_NAME)
        assert new_sess_token is not None
        new_csrf = reg_data["csrf_token"]
        client.cookies.set(SESSION_COOKIE_NAME, new_sess_token)
        client.cookies.set(CSRF_COOKIE_NAME, new_csrf)

        # 3. Authenticate with UP=True, UV=False
        auth_opt_res = await client.post(
            "/api/v1/auth/webauthn/authenticate/options",
            headers={CSRF_HEADER_NAME: new_csrf},
        )
        assert auth_opt_res.status_code == 200
        auth_opts = auth_opt_res.json()
        assert auth_opts["userVerification"] == "preferred"

        assert_cred = auth.get_assertion(auth_opts, origin=ORIGIN, uv=False, up=True, sign_count=1)
        auth_res = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: new_csrf},
            json={"credential": assert_cred},
        )
        assert auth_res.status_code == 200

        # Update cookies after elevation
        auth_cookies = {c.name: c.value for c in auth_res.cookies.jar}
        sess_token_val = auth_cookies.get(SESSION_COOKIE_NAME)
        assert sess_token_val is not None
        client.cookies.set(SESSION_COOKIE_NAME, sess_token_val)
        fresh_csrf = auth_res.json()["csrf_token"]
        client.cookies.set(CSRF_COOKIE_NAME, fresh_csrf)

        # 4. User Presence missing (UP=False) -> 401 MFA_INVALID on registration and assertion
        reg_opts_2 = (
            await client.post(
                "/api/v1/auth/webauthn/register/options",
                headers={CSRF_HEADER_NAME: fresh_csrf},
            )
        ).json()
        no_up_cred = auth.create_credential(reg_opts_2, origin=ORIGIN, uv=False, up=False)
        no_up_reg_res = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: fresh_csrf},
            json={"credential": no_up_cred},
        )
        assert no_up_reg_res.status_code == 401
        assert no_up_reg_res.json()["code"] == "MFA_INVALID"


@pytest.mark.asyncio
async def test_kan24_first_factor_deadlock_and_second_factor_staleness(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Verify first-factor enrollment succeeds for AAL1 user and enforces AAL2 freshness."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    ws_id, p_id = await _setup_principal_with_role(
        factory, key_material, username="fresh_user", role="WORKSPACE_MEMBER"
    )
    app, session_service = _build_test_app(factory, key_material, rate_limiter, webauthn_settings)
    auth = SoftAuthenticator()

    # User starts with zero factors and AAL1 session (mfa_pending=False)
    async with factory.session(RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)) as s:
        sess_aal1 = await session_service.create_after_login(
            s, principal_id=p_id, workspace_id=ws_id, aal_level=1, mfa_pending=False
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal1.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_aal1.csrf_token)

        # First factor enrollment allowed without deadlock
        opts = (
            await client.post(
                "/api/v1/auth/webauthn/register/options",
                headers={CSRF_HEADER_NAME: sess_aal1.csrf_token},
            )
        ).json()

        # Enroll factor 1
        cred1 = auth.create_credential(opts, origin=ORIGIN, uv=True, up=True)
        reg1_res = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: sess_aal1.csrf_token},
            json={"credential": cred1, "nickname": "Passkey 1"},
        )
        assert reg1_res.status_code == 200
        cookies1 = {c.name: c.value for c in reg1_res.cookies.jar}
        aal2_session_token = cookies1.get(SESSION_COOKIE_NAME)
        assert aal2_session_token is not None
        aal2_csrf = reg1_res.json()["csrf_token"]

        # Now attempt to register factor 2 using an AAL1 session for the user -> 403 AAL2_REQUIRED
        async with factory.session(
            RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=1)
        ) as s:
            sess_aal1_second = await session_service.create_after_login(
                s, principal_id=p_id, workspace_id=ws_id, aal_level=1, mfa_pending=False
            )
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal1_second.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_aal1_second.csrf_token)
        second_opts_res = await client.post(
            "/api/v1/auth/webauthn/register/options",
            headers={CSRF_HEADER_NAME: sess_aal1_second.csrf_token},
        )
        assert second_opts_res.status_code == 403
        prob = second_opts_res.json()
        assert prob["code"] == "AAL2_REQUIRED"
        assert prob["methods"] == ["webauthn"]

        # Switch to the AAL2 session: register options succeeds
        client.cookies.clear()
        _sync_cookies(client, reg1_res)
        aal2_csrf = reg1_res.json()["csrf_token"]
        opts2_res = await client.post(
            "/api/v1/auth/webauthn/register/options",
            headers={CSRF_HEADER_NAME: aal2_csrf},
        )
        assert opts2_res.status_code == 200

        # Make the AAL2 session stale (> 900 seconds old)
        stale_time = datetime.now(UTC) - timedelta(seconds=905)
        async with factory.session(
            RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)
        ) as s:
            await s.execute(
                text("UPDATE sessions SET aal2_verified_at = :stale WHERE principal_id = :p_id"),
                {"stale": stale_time, "p_id": p_id},
            )

        # With stale AAL2 session -> 403 AAL2_STALE with methods
        stale_res = await client.post(
            "/api/v1/auth/webauthn/register/options",
            headers={CSRF_HEADER_NAME: aal2_csrf},
        )
        assert stale_res.status_code == 403
        stale_prob = stale_res.json()
        assert stale_prob["code"] == "AAL2_STALE"
        assert stale_prob["methods"] == ["webauthn"]

        # Also test with missing aal2_verified_at (None)
        async with factory.session(
            RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)
        ) as s:
            await s.execute(
                text("UPDATE sessions SET aal2_verified_at = NULL WHERE principal_id = :p_id"),
                {"p_id": p_id},
            )
        none_verified_res = await client.post(
            "/api/v1/auth/webauthn/register/options",
            headers={CSRF_HEADER_NAME: aal2_csrf},
        )
        assert none_verified_res.status_code == 403
        assert none_verified_res.json()["code"] == "AAL2_STALE"
        assert none_verified_res.json()["methods"] == ["webauthn"]


@pytest.mark.asyncio
async def test_kan24_workspace_admin_and_server_admin_last_factor_lockout(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Verify WORKSPACE_ADMIN and is_server_admin are protected by LAST_FACTOR lockout guards."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    ws_id, p_id = await _setup_principal_with_role(
        factory, key_material, username="ws_admin_guard", role="WORKSPACE_ADMIN"
    )
    app, session_service = _build_test_app(factory, key_material, rate_limiter, webauthn_settings)
    auth = SoftAuthenticator()

    async with factory.session(RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)) as s:
        sess = await session_service.create_after_login(
            s, principal_id=p_id, workspace_id=ws_id, aal_level=2, mfa_pending=False
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(SESSION_COOKIE_NAME, sess.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess.csrf_token)

        # 1. Register a WebAuthn factor
        opts = (
            await client.post(
                "/api/v1/auth/webauthn/register/options",
                headers={CSRF_HEADER_NAME: sess.csrf_token},
            )
        ).json()
        cred = auth.create_credential(opts, origin=ORIGIN)
        reg_res = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: sess.csrf_token},
            json={"credential": cred, "nickname": "Admin Key"},
        )
        assert reg_res.status_code == 200
        _sync_cookies(client, reg_res)
        admin_csrf = reg_res.json()["csrf_token"]
        cred_uuid = reg_res.json()["credential_id"]

        # 2. WORKSPACE_ADMIN attempts to delete their only factor -> 409 LAST_FACTOR
        del_res = await client.delete(
            f"/api/v1/auth/webauthn/credentials/{cred_uuid}",
            headers={CSRF_HEADER_NAME: admin_csrf},
        )
        assert del_res.status_code == 409
        assert del_res.json()["code"] == "LAST_FACTOR"

        # 3. Enroll a TOTP factor for the WORKSPACE_ADMIN
        async with factory.session(
            RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)
        ) as s:
            await s.execute(
                text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
                {
                    "p_id": p_id,
                    "blob": b"\x01" + b"\x00" * 28,
                    "dek": b"\x01" + b"\x00" * 44,
                },
            )
            p_res = await s.execute(
                text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
                {"p_id": p_id},
            )
            p_row = p_res.mappings().first()
            assert p_row is not None
            await s.execute(
                text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
                {"p_fid": p_row["id"]},
            )

        # Now has 2 factors (WebAuthn + TOTP). Deleting TOTP succeeds because WebAuthn remains.
        del_totp_res = await client.delete(
            "/api/v1/auth/mfa/totp",
            headers={CSRF_HEADER_NAME: admin_csrf},
        )
        assert del_totp_res.status_code == 200
        assert del_totp_res.json() == {"revoked": True}

        # Now only WebAuthn remains: deleting WebAuthn fails with 409 LAST_FACTOR
        del_res_again = await client.delete(
            f"/api/v1/auth/webauthn/credentials/{cred_uuid}",
            headers={CSRF_HEADER_NAME: admin_csrf},
        )
        assert del_res_again.status_code == 409
        assert del_res_again.json()["code"] == "LAST_FACTOR"


@pytest.mark.asyncio
async def test_kan24_credential_metadata_and_clone_detection(  # noqa: PLR0915
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Verify GET and PATCH credential metadata, transports, and suspect_clone_at on regression."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    ws_id, p_id = await _setup_principal_with_role(
        factory, key_material, username="clone_test_user", role="WORKSPACE_MEMBER"
    )
    app, session_service = _build_test_app(factory, key_material, rate_limiter, webauthn_settings)
    auth = SoftAuthenticator()

    async with factory.session(RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)) as s:
        sess = await session_service.create_after_login(
            s, principal_id=p_id, workspace_id=ws_id, aal_level=2, mfa_pending=False
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(SESSION_COOKIE_NAME, sess.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess.csrf_token)

        # Register credential
        opts = (
            await client.post(
                "/api/v1/auth/webauthn/register/options",
                headers={CSRF_HEADER_NAME: sess.csrf_token},
                json={"authenticator_attachment": "platform"},
            )
        ).json()
        cred = auth.create_credential(opts, origin=ORIGIN, sign_count=5)
        reg_res = await client.post(
            "/api/v1/auth/webauthn/register/verify",
            headers={CSRF_HEADER_NAME: sess.csrf_token},
            json={"credential": cred, "nickname": "MacBook TouchID"},
        )
        assert reg_res.status_code == 200
        _sync_cookies(client, reg_res)
        cred_csrf = reg_res.json()["csrf_token"]
        cred_uuid = reg_res.json()["credential_id"]

        # GET /credentials should include aaguid, transports, and suspect_clone_at
        list_res = await client.get("/api/v1/auth/webauthn/credentials")
        assert list_res.status_code == 200
        creds = list_res.json()
        assert len(creds) == 1
        c0 = creds[0]
        assert c0["id"] == cred_uuid
        assert c0["nickname"] == "MacBook TouchID"
        assert c0["sign_count"] == 5
        assert "aaguid" in c0
        assert "transports" in c0
        assert c0["transports"] == ["internal"]
        assert c0["suspect_clone_at"] is None

        # PATCH /credentials/{credential_id} to rename
        patch_res = await client.patch(
            f"/api/v1/auth/webauthn/credentials/{cred_uuid}",
            headers={CSRF_HEADER_NAME: cred_csrf},
            json={"nickname": "Work MacBook Pro"},
        )
        assert patch_res.status_code == 200
        patched = patch_res.json()
        assert patched["id"] == cred_uuid
        assert patched["nickname"] == "Work MacBook Pro"
        assert "aaguid" in patched
        assert "transports" in patched
        assert patched["transports"] == ["internal"]
        assert patched["suspect_clone_at"] is None

        # Authenticate successfully with advancing counter (sign_count = 10)
        auth_opts = (
            await client.post(
                "/api/v1/auth/webauthn/authenticate/options",
                headers={CSRF_HEADER_NAME: cred_csrf},
            )
        ).json()
        valid_auth = auth.get_assertion(auth_opts, origin=ORIGIN, sign_count=10)
        auth_res = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: cred_csrf},
            json={"credential": valid_auth},
        )
        assert auth_res.status_code == 200
        auth_cookies = {c.name: c.value for c in auth_res.cookies.jar}
        auth_sess_tok = auth_cookies.get(SESSION_COOKIE_NAME)
        assert auth_sess_tok is not None
        client.cookies.set(SESSION_COOKIE_NAME, auth_sess_tok)
        fresh_csrf = auth_res.json()["csrf_token"]
        client.cookies.set(CSRF_COOKIE_NAME, fresh_csrf)

        # Authenticate with REGRESSED counter (sign_count = 8 <= 10) -> 401 MFA_INVALID
        auth_opts_2 = (
            await client.post(
                "/api/v1/auth/webauthn/authenticate/options",
                headers={CSRF_HEADER_NAME: fresh_csrf},
            )
        ).json()
        cloned_auth = auth.get_assertion(auth_opts_2, origin=ORIGIN, sign_count=8)
        clone_res = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: fresh_csrf},
            json={"credential": cloned_auth},
        )
        assert clone_res.status_code == 401
        assert clone_res.json()["code"] == "MFA_INVALID"

        # Now GET /credentials reveals suspect_clone_at timestamp is populated!
        list_res_after = await client.get("/api/v1/auth/webauthn/credentials")
        assert list_res_after.status_code == 200
        c_after = list_res_after.json()[0]
        assert c_after["suspect_clone_at"] is not None

        # PATCH /credentials/{credential_id} also includes the populated suspect_clone_at
        patch_res_after = await client.patch(
            f"/api/v1/auth/webauthn/credentials/{cred_uuid}",
            headers={CSRF_HEADER_NAME: fresh_csrf},
            json={"nickname": "Compromised Cloned Key"},
        )
        assert patch_res_after.status_code == 200
        assert patch_res_after.json()["suspect_clone_at"] is not None

        # Subsequent authentication attempts with suspect credential fail immediately
        auth_opts_3 = (
            await client.post(
                "/api/v1/auth/webauthn/authenticate/options",
                headers={CSRF_HEADER_NAME: fresh_csrf},
            )
        ).json()
        adv_auth = auth.get_assertion(auth_opts_3, origin=ORIGIN, sign_count=20)
        auth_res_3 = await client.post(
            "/api/v1/auth/webauthn/authenticate/verify",
            headers={CSRF_HEADER_NAME: fresh_csrf},
            json={"credential": adv_auth},
        )
        assert auth_res_3.status_code == 401
        assert auth_res_3.json()["code"] == "MFA_INVALID"


@pytest.mark.asyncio
async def test_kan24_step_up_methods_discovery(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    webauthn_settings: Settings,
) -> None:
    """Verify enrolled methods ('totp', 'webauthn', 'recovery') populated in problem documents."""
    factory = RLSSessionFactory(pg_worker_db)
    rate_limiter = PgRateLimiter(pg_worker_db)
    ws_id, p_id = await _setup_principal_with_role(
        factory, key_material, username="stepup_user", role="SERVER_ADMIN", scope_type="server"
    )
    app, session_service = _build_test_app(factory, key_material, rate_limiter, webauthn_settings)

    # Enroll TOTP factor, recovery codes, and WebAuthn credential for principal
    async with factory.session(RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)) as s:
        # 1. TOTP
        await s.execute(
            text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
            {
                "p_id": p_id,
                "blob": b"\x01" + b"\x00" * 28,
                "dek": b"\x01" + b"\x00" * 44,
            },
        )
        p_res = await s.execute(
            text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
            {"p_id": p_id},
        )
        p_row = p_res.mappings().first()
        assert p_row is not None
        await s.execute(text("SELECT kb_auth.totp_confirm(:p_fid, 100)"), {"p_fid": p_row["id"]})

        # 2. Recovery code
        await s.execute(
            text("SELECT kb_auth.recovery_codes_replace(:p_id, ARRAY[:hmac]::BYTEA[])"),
            {"p_id": p_id, "hmac": b"h" * 32},
        )

        # 3. WebAuthn credential
        cred_bytes = b"\xaa" * 32
        await s.execute(
            text(
                "SELECT kb_auth.webauthn_credential_create("
                "  :p_id, :cred_id, :pub_key, 0, NULL, ARRAY['internal']::TEXT[], 'Passkey'"
                ")"
            ),
            {"p_id": p_id, "cred_id": cred_bytes, "pub_key": b"\xbb" * 64},
        )

        # Create AAL1 session for step-up test
        sess_aal1 = await session_service.create_after_login(
            s, principal_id=p_id, workspace_id=ws_id, aal_level=1, mfa_pending=False
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal1.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_aal1.csrf_token)

        # 1. require_aal2 route with AAL1 session -> 403 AAL2_REQUIRED with all enrolled methods
        res_sens = await client.get("/api/v1/test/sensitive")
        assert res_sens.status_code == 403
        prob_sens = res_sens.json()
        assert prob_sens["code"] == "AAL2_REQUIRED"
        assert set(prob_sens["methods"]) == {"totp", "webauthn", "recovery"}

        # 2. require_admin_aal2 route with AAL1 session -> 403 AAL2_REQUIRED with enrolled methods
        res_adm = await client.get("/api/v1/admin/test/route")
        assert res_adm.status_code == 403
        prob_adm = res_adm.json()
        assert prob_adm["code"] == "AAL2_REQUIRED"
        assert set(prob_adm["methods"]) == {"totp", "webauthn", "recovery"}

        # 3. require_aal2 route with stale AAL2 session -> 403 AAL2_STALE with methods
        async with factory.session(
            RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)
        ) as s:
            sess_stale = await session_service.create_after_login(
                s, principal_id=p_id, workspace_id=ws_id, aal_level=2, mfa_pending=False
            )
            stale_time = datetime.now(UTC) - timedelta(seconds=950)
            await s.execute(
                text("UPDATE sessions SET aal2_verified_at = :stale WHERE id = :id"),
                {"stale": stale_time, "id": sess_stale.session_id},
            )

        client.cookies.set(SESSION_COOKIE_NAME, sess_stale.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_stale.csrf_token)

        res_stale = await client.get("/api/v1/test/sensitive")
        assert res_stale.status_code == 403
        prob_stale = res_stale.json()
        assert prob_stale["code"] == "AAL2_STALE"
        assert set(prob_stale["methods"]) == {"totp", "webauthn", "recovery"}


@pytest.mark.asyncio
async def test_kan24_service_and_policy_direct_unit_branches(  # noqa: PLR0915
    pg_worker_db: AsyncEngine,
    webauthn_settings: Settings,
) -> None:
    """Exercise direct branch conditions on WebauthnService, _assert_can_register, and policy."""
    factory = RLSSessionFactory(pg_worker_db)
    service = WebauthnService(
        rp_id=webauthn_settings.effective_rp_id,
        rp_name=webauthn_settings.webauthn_rp_name,
        expected_origin=webauthn_settings.effective_origin,
    )
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()
    sess_id = uuid.uuid4()

    async with factory.session(RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)) as s:
        await s.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:8]}", "name": "Direct Unit WS"},
        )
        await s.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', 'Direct User')"
            ),
            {"id": p_id, "ws_id": ws_id},
        )
        await s.execute(
            text(
                "INSERT INTO sessions (id, token_sha256, principal_id, workspace_id, aal_level, "
                "last_seen_at, idle_expires_at, absolute_expires_at) "
                "VALUES (:id, :tok, :p_id, :ws_id, 2, now(), "
                "now() + interval '1 hour', now() + interval '1 day')"
            ),
            {"id": sess_id, "tok": b"t" * 32, "p_id": p_id, "ws_id": ws_id},
        )

        # 1. registration_options with AuthenticatorAttachment enum
        opts_enum = await service.registration_options(
            s,
            session_id=sess_id,
            principal_id=p_id,
            username="direct_user",
            display_name="Direct Display",
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
        )
        assert opts_enum["authenticatorSelection"]["authenticatorAttachment"] == "platform"

        # 2. registration_options with string modality
        opts_str = await service.registration_options(
            s,
            session_id=sess_id,
            principal_id=p_id,
            username="direct_user",
            authenticator_attachment="cross-platform",
        )
        assert opts_str["authenticatorSelection"]["authenticatorAttachment"] == "cross-platform"

        # 3. _assert_can_register with principal.is_server_admin
        principal_fresh = PrincipalContext(
            principal_id=p_id,
            workspace_id=ws_id,
            aal_level=2,
            session_id=sess_id,
            aal2_verified_at=datetime.now(UTC),
            is_server_admin=True,
        )
        can_reg = await _assert_can_register(s, principal_fresh)
        assert can_reg is True

        # Now create 1 factor in DB
        cred_res = await s.execute(
            text(
                "SELECT kb_auth.webauthn_credential_create("
                "  :p_id, :cred_id, :pub_key, 0, NULL, ARRAY['internal']::TEXT[], 'Key'"
                ")"
            ),
            {"p_id": p_id, "cred_id": b"\x11" * 32, "pub_key": b"\x22" * 64},
        )
        created_cred_id = cred_res.scalar_one()
        # With 1 factor and fresh AAL2 -> returns False
        can_reg_second = await _assert_can_register(s, principal_fresh)
        assert can_reg_second is False

        # With 1 factor and AAL1 -> raises AAL2_REQUIRED
        principal_aal1 = PrincipalContext(
            principal_id=p_id,
            workspace_id=ws_id,
            aal_level=1,
            session_id=sess_id,
            is_server_admin=True,
        )
        with pytest.raises(ProblemException) as exc_req:
            await _assert_can_register(s, principal_aal1)
        assert exc_req.value.code == "AAL2_REQUIRED"
        assert exc_req.value.methods == ["webauthn"]

        # With 1 factor and stale AAL2 -> raises AAL2_STALE
        principal_stale = PrincipalContext(
            principal_id=p_id,
            workspace_id=ws_id,
            aal_level=2,
            session_id=sess_id,
            aal2_verified_at=datetime.now(UTC) - timedelta(seconds=1000),
            is_server_admin=True,
        )
        with pytest.raises(ProblemException) as exc_stale:
            await _assert_can_register(s, principal_stale)
        assert exc_stale.value.code == "AAL2_STALE"
        assert exc_stale.value.methods == ["webauthn"]

        # With 1 factor and missing aal2_verified_at -> raises AAL2_STALE
        principal_none_ver = PrincipalContext(
            principal_id=p_id,
            workspace_id=ws_id,
            aal_level=2,
            session_id=sess_id,
            aal2_verified_at=None,
            is_server_admin=True,
        )
        with pytest.raises(ProblemException) as exc_none_ver:
            await _assert_can_register(s, principal_none_ver)
        assert exc_none_ver.value.code == "AAL2_STALE"
        assert exc_none_ver.value.methods == ["webauthn"]

    # 4. _get_enrolled_methods with app without session_factory
    app_no_factory = FastAPI()
    req_no_factory = Request({"type": "http", "app": app_no_factory})
    methods_empty = await _get_enrolled_methods(req_no_factory, principal_fresh)
    assert methods_empty == []

    # 5. _parse_aaguid and _extract_client_data unit branches
    assert _parse_aaguid(None) is None
    assert _parse_aaguid("") is None
    assert _parse_aaguid("not-a-uuid") is None
    valid_u = uuid.uuid4()
    assert _parse_aaguid(str(valid_u)) == valid_u

    # _extract_client_data errors
    with pytest.raises(ProblemException) as exc_nd:
        _extract_client_data(12345, expected_type="webauthn.get")
    assert exc_nd.value.code == "MFA_INVALID"

    with pytest.raises(ProblemException) as exc_mc:
        _extract_client_data({"response": {}}, expected_type="webauthn.get")
    assert exc_mc.value.code == "MFA_INVALID"

    arr_b64 = base64.urlsafe_b64encode(b"[1, 2, 3]").decode("ascii").rstrip("=")
    with pytest.raises(ProblemException) as exc_cd_arr:
        _extract_client_data({"clientDataJSON": arr_b64}, expected_type="webauthn.get")
    assert exc_cd_arr.value.code == "MFA_INVALID"

    nochal_b64 = base64.urlsafe_b64encode(b'{"type": "webauthn.get"}').decode("ascii").rstrip("=")
    with pytest.raises(ProblemException) as exc_nc:
        _extract_client_data({"clientDataJSON": nochal_b64}, expected_type="webauthn.get")
    assert exc_nc.value.code == "MFA_INVALID"

    bad_chal_b64 = (
        base64.urlsafe_b64encode(b'{"type": "webauthn.get", "challenge": "1"}')
        .decode("ascii")
        .rstrip("=")
    )
    with pytest.raises(ProblemException) as exc_bad_ch:
        _extract_client_data({"clientDataJSON": bad_chal_b64}, expected_type="webauthn.get")
    assert exc_bad_ch.value.code == "MFA_INVALID"

    wrong_type_b64 = (
        base64.urlsafe_b64encode(b'{"type": "webauthn.create", "challenge": "YWFh"}')
        .decode("ascii")
        .rstrip("=")
    )
    with pytest.raises(ProblemException) as exc_tc:
        _extract_client_data({"clientDataJSON": wrong_type_b64}, expected_type="webauthn.get")
    assert exc_tc.value.code == "MFA_INVALID"

    # 6. Naive datetime for verified_at in _assert_can_register
    async with factory.session(RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)) as s:
        principal_naive = PrincipalContext(
            principal_id=p_id,
            workspace_id=ws_id,
            aal_level=2,
            session_id=sess_id,
            aal2_verified_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1000),
            is_server_admin=True,
        )
        with pytest.raises(ProblemException) as exc_naive:
            await _assert_can_register(s, principal_naive)
        assert exc_naive.value.code == "AAL2_STALE"

    # 7. record_activity exception logging in WebauthnService
    ctx_aal2 = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)
    with patch(
        "kanban.auth.mfa.webauthn.record_activity",
        side_effect=RuntimeError("activity failure"),
    ):
        async with factory.session(ctx_aal2) as s:
            await service.delete_credential(
                s,
                principal_id=p_id,
                credential_id=created_cred_id,
                is_admin=False,
                workspace_id=ws_id,
            )

    # 8. rename_credential when not found or session_factory is None
    app_missing_sf = FastAPI()
    req_missing_sf = Request({"type": "http", "app": app_missing_sf})
    with pytest.raises(RuntimeError) as exc_sf:
        await rename_credential(
            uuid.uuid4(),
            WebauthnRenameRequest(nickname="New Nickname"),
            req_missing_sf,
            principal_fresh,
        )
    assert "Session factory is not configured" in str(exc_sf.value)

    test_app = FastAPI()
    test_app.state.session_factory = factory
    test_app.state.webauthn_service = service
    req_test_app = Request({"type": "http", "app": test_app})
    with pytest.raises(ProblemException) as exc_nf:
        await rename_credential(
            uuid.uuid4(),
            WebauthnRenameRequest(nickname="New Nickname"),
            req_test_app,
            principal_fresh,
        )
    assert exc_nf.value.code == "NOT_FOUND"

    # 9. _RequireAal2 with AAL1 principal -> raises AAL2_REQUIRED
    req_policy_app = Request({"type": "http", "app": test_app})
    principal_aal1_req = PrincipalContext(
        principal_id=p_id,
        workspace_id=ws_id,
        aal_level=1,
        session_id=sess_id,
    )
    with pytest.raises(ProblemException) as exc_req_p:
        await _RequireAal2(max_age_seconds=900)(req_policy_app, principal_aal1_req)
    assert exc_req_p.value.code == "AAL2_REQUIRED"

    # With AAL2 but verified_at=None -> raises AAL2_STALE
    principal_no_ver = PrincipalContext(
        principal_id=p_id,
        workspace_id=ws_id,
        aal_level=2,
        session_id=sess_id,
        aal2_verified_at=None,
    )
    with pytest.raises(ProblemException) as exc_stale_p:
        await _RequireAal2(max_age_seconds=900)(req_policy_app, principal_no_ver)
    assert exc_stale_p.value.code == "AAL2_STALE"

    # 10. _get_enrolled_methods when status_row is None
    mock_session = AsyncMock()
    mock_mappings = MagicMock()
    mock_mappings.first.return_value = None
    mock_exec = MagicMock()
    mock_exec.mappings.return_value = mock_mappings
    mock_session.execute.return_value = mock_exec

    class MockSessionFactory:
        def session(self, _ctx: object) -> object:
            class SessionCtx:
                async def __aenter__(self) -> AsyncMock:
                    return mock_session

                async def __aexit__(self, *args: object) -> None:
                    pass

            return SessionCtx()

    app_mock_sf = FastAPI()
    app_mock_sf.state.session_factory = MockSessionFactory()
    req_mock_sf = Request({"type": "http", "app": app_mock_sf})
    methods_none_row = await _get_enrolled_methods(req_mock_sf, principal_fresh)
    assert methods_none_row == []


@pytest.mark.asyncio
async def test_kan24_delete_totp_role_lockout_branches(
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
) -> None:
    """Verify delete_totp lockout guard across is_server_admin, WORKSPACE_ADMIN, and non-admin."""
    factory = RLSSessionFactory(pg_worker_db)
    app = FastAPI()
    app.state.session_factory = factory
    app.state.kek_provider = StaticKekProvider(
        {key_material.master_kek_kid: key_material.master_kek},
        current=key_material.master_kek_kid,
    )
    req = Request({"type": "http", "app": app})
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()

    async with factory.session(RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)) as s:
        await s.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:8]}", "name": "TOTP Guard WS"},
        )
        await s.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', 'TOTP Guard User')"
            ),
            {"id": p_id, "ws_id": ws_id},
        )
        # Enroll 1 TOTP factor
        await s.execute(
            text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
            {
                "p_id": p_id,
                "blob": b"\x01" + b"\x00" * 28,
                "dek": b"\x01" + b"\x00" * 44,
            },
        )
        p_res = await s.execute(
            text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
            {"p_id": p_id},
        )
        p_row = p_res.mappings().first()
        assert p_row is not None
        await s.execute(text("SELECT kb_auth.totp_confirm(:p_fid, 100)"), {"p_fid": p_row["id"]})

    # Case 1: is_server_admin=True with only TOTP factor -> 409 LAST_FACTOR
    p_srv = PrincipalContext(
        principal_id=p_id,
        workspace_id=ws_id,
        aal_level=2,
        session_id=uuid.uuid4(),
        is_server_admin=True,
    )
    with pytest.raises(ProblemException) as exc_srv:
        await delete_totp(req, p_srv)
    assert exc_srv.value.code == "LAST_FACTOR"

    # Case 2: role='WORKSPACE_ADMIN' with only TOTP factor -> 409 LAST_FACTOR
    async with factory.session(RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)) as s:
        await s.execute(
            text(
                "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type) "
                "VALUES (:ws_id, :p_id, 'WORKSPACE_ADMIN', 'workspace')"
            ),
            {"ws_id": ws_id, "p_id": p_id},
        )
    p_ws = PrincipalContext(
        principal_id=p_id,
        workspace_id=ws_id,
        aal_level=2,
        session_id=uuid.uuid4(),
        is_server_admin=False,
    )
    with pytest.raises(ProblemException) as exc_ws:
        await delete_totp(req, p_ws)
    assert exc_ws.value.code == "LAST_FACTOR"

    # Case 3: role='WORKSPACE_MEMBER' (non-admin) with only TOTP factor -> successfully deleted
    async with factory.session(RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)) as s:
        await s.execute(
            text("UPDATE role_bindings SET role = 'WORKSPACE_MEMBER' WHERE principal_id = :p_id"),
            {"p_id": p_id},
        )
    del_res = await delete_totp(req, p_ws)
    assert del_res.status_code == 200


@pytest.mark.asyncio
async def test_kan24_problems_methods_serialization() -> None:
    """Verify methods parameter is serialized in Problem and handled in handler."""
    prob = Problem(
        type="https://api.kanban.example/errors/aal2-required",
        title="AAL2 Required",
        status=403,
        detail="AAL2 required.",
        code="AAL2_REQUIRED",
        request_id="req-123",
        methods=["totp", "webauthn"],
    )
    assert prob.methods == ["totp", "webauthn"]
    dumped = prob.model_dump(exclude_none=True)
    assert dumped["methods"] == ["totp", "webauthn"]

    exc = ProblemException(
        status=403,
        title="AAL2 Required",
        detail="AAL2 required.",
        code="AAL2_REQUIRED",
        methods=["totp", "webauthn"],
    )
    assert exc.methods == ["totp", "webauthn"]

    req = Request({"type": "http", "method": "GET", "path": "/test", "headers": []})
    resp = await problem_exception_handler(req, exc)
    data = json.loads(bytes(resp.body).decode("utf-8"))
    assert data["code"] == "AAL2_REQUIRED"
    assert data["methods"] == ["totp", "webauthn"]
