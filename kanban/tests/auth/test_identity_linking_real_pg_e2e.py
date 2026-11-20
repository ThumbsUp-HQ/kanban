# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Real PostgreSQL-backed end-to-end ASGI tests for OIDC identity linking lifecycle (KAN-27)."""

from __future__ import annotations

import urllib.parse
import uuid
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from database.session import RLSContext, RLSSessionFactory
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1.auth_identities import router as auth_identities_router
from kanban.api.v1.auth_oidc import router as auth_oidc_router
from kanban.auth.cards.repository import admin_upsert
from kanban.auth.identity_service import DatabaseIdentityResolver
from kanban.auth.oidc.flow import OidcFlow
from kanban.auth.sessions.csrf import (
    CSRF_HEADER_NAME,
    CsrfMiddleware,
)
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionService
from kanban.security.envelope import StaticKekProvider, seal_card_secret
from kanban.security.keys import KeyMaterial
from kanban.tests.fixtures.fake_idp import FakeIdP

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@pytest.fixture
def key_material() -> KeyMaterial:
    """Fixture providing static key material."""
    return KeyMaterial(
        master_kek=b"m" * 32,
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
        master_kek_kid="kek-v1",
    )


@pytest.fixture
def kek_provider(key_material: KeyMaterial) -> StaticKekProvider:
    """Fixture providing StaticKekProvider."""
    return StaticKekProvider.from_key_material(key_material)


@pytest.fixture
def fake_idp() -> FakeIdP:
    """Fixture providing FakeIdP instance."""
    return FakeIdP(
        issuer="https://idp.corp.example.com",
        client_id="corp-sso-client-id",
        client_secret="corp-sso-client-secret",  # noqa: S106
    )


async def _seed_oidc_card(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    kek_provider: StaticKekProvider,
    slug: str,
    issuer: str,
    client_id: str,
    client_secret: bytes,
) -> uuid.UUID:
    """Seed an enabled OIDC provider card."""
    card_id = uuid.uuid4()
    sealed = seal_card_secret(card_id, "OIDC", client_secret, kek_provider)
    await admin_upsert(
        session,
        card_id=card_id,
        workspace_id=ws_id,
        provider_kind="OIDC",
        slug=slug,
        display_name=f"OIDC Card {slug}",
        is_enabled=True,
        sort_rank="0001",
        public_config={
            "kind": "OIDC",
            "issuer": issuer,
            "client_id": client_id,
            "client_auth": "client_secret_basic",
            "scopes": ["openid", "profile", "email"],
            "allowed_algs": ["RS256", "ES256"],
        },
        encrypted_secret_blob=sealed.encrypted_secret_blob,
        wrapped_dek=sealed.wrapped_dek,
        dek_kid=sealed.dek_kid,
    )
    return card_id


@pytest.mark.asyncio
async def test_oidc_identity_linking_real_pg_lifecycle(  # noqa: PLR0915
    pg_worker_db: AsyncEngine,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
    fake_idp: FakeIdP,
) -> None:
    """Test full zero-mock PostgreSQL lifecycle for OIDC identity linking and collision.

    Proves:
    1. Zero-factor WORKSPACE_MEMBER @alice (aal_level=1) calls
       POST /api/v1/auth/identities/link/start
       (HTTP 200, Set-Cookie: kb_oidc present, real row inserted into oidc_auth_requests AND
       identity_link_intents with zero foreign key violation error).
    2. IdP callback GET /api/v1/auth/oidc/corp-sso/callback?code=...&state=... redirects 302
       to /settings/profile?linked=corp-sso, binds external identity in PostgreSQL, and preserves
       @alice's exact session_id and aal_level == 1.
    3. Second user @admin (aal_level=2) attempting to link the same (issuer, sub) via real DB flow
       redirects cleanly to /settings/profile?link_error=IDENTITY_ALREADY_LINKED
       with zero duplicate rows.
    """
    session_factory = RLSSessionFactory(pg_worker_db)
    session_service = SessionService(session_hmac_key=key_material.session_hmac_key)

    ws_id = uuid.uuid4()
    alice_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    # 1. Provision Workspace, @alice, @admin, sessions, and OIDC card in PostgreSQL
    init_ctx = RLSContext(principal_id=uuid.uuid4(), workspace_id=ws_id, aal_level=2)
    async with session_factory.session(init_ctx) as init_sess:
        await init_sess.execute(text("RESET SESSION AUTHORIZATION"))

        # Workspace
        await init_sess.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Link Lifecycle WS"},
        )

        # @alice (WORKSPACE_MEMBER, no MFA enrolled)
        await init_sess.execute(
            text(
                "SELECT register_object("
                "'user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
            ),
            {
                "ws_id": ws_id,
                "ckey": f"usr-{alice_id.hex}",
                "title": "Alice Member",
                "u_id": alice_id,
            },
        )
        await init_sess.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'alice', 'ACTIVE')"
            ),
            {"id": alice_id, "ws_id": ws_id},
        )
        await init_sess.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, 'alice@example.com')"
            ),
            {"id": alice_id, "ws_id": ws_id},
        )
        await init_sess.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :p_id, 'WORKSPACE_MEMBER', 'workspace', NULL)"
            ),
            {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": alice_id},
        )

        # @admin (SERVER_ADMIN, aal_level=2)
        await init_sess.execute(
            text(
                "SELECT register_object("
                "'user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
            ),
            {
                "ws_id": ws_id,
                "ckey": f"usr-{admin_id.hex}",
                "title": "Admin User",
                "u_id": admin_id,
            },
        )
        await init_sess.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'admin', 'ACTIVE')"
            ),
            {"id": admin_id, "ws_id": ws_id},
        )
        await init_sess.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, 'admin@example.com')"
            ),
            {"id": admin_id, "ws_id": ws_id},
        )
        await init_sess.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
            ),
            {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": admin_id},
        )

        # Real PostgreSQL sessions
        s_alice = await session_service.create_after_login(
            init_sess,
            principal_id=alice_id,
            workspace_id=ws_id,
            aal_level=1,
            mfa_pending=False,
        )
        assert s_alice.aal_level == 1

        s_admin = await session_service.create_after_login(
            init_sess,
            principal_id=admin_id,
            workspace_id=ws_id,
            aal_level=2,
            mfa_pending=False,
        )
        assert s_admin.aal_level == 2

        # Bind session context to allow card_admin_upsert under admin_id
        await init_sess.execute(
            text(
                "SELECT set_config('app.principal_id', :p_id, true), "
                "set_config('app.workspace_id', :w_id, true), "
                "set_config('app.aal_level', '2', true)"
            ),
            {"p_id": str(admin_id), "w_id": str(ws_id)},
        )
        card_id = await _seed_oidc_card(
            init_sess,
            ws_id,
            kek_provider,
            slug="corp-sso",
            issuer=fake_idp.issuer,
            client_id=fake_idp.client_id,
            client_secret=fake_idp.client_secret.encode("utf-8"),
        )
        await init_sess.commit()

    # 2. Build Real ASGI App (MOCKING ONLY OUTBOUND HTTP TO IDP VIA MockTransport!)
    app = FastAPI(title="Real Postgres Identity Linking E2E")
    app.state.session_service = session_service
    app.state.session_factory = session_factory
    app.state.key_material = key_material
    app.state.kek_provider = kek_provider
    app.state.principal_resolver = SessionCookieResolver(session_service, session_factory)
    app.state.identity_resolver = DatabaseIdentityResolver(session_factory=session_factory)

    idp_http_client = httpx.AsyncClient(transport=fake_idp.as_transport())
    app.state.http_client = idp_http_client
    app.state.public_origin = "http://testserver"

    oidc_flow = OidcFlow(
        key_material=key_material,
        session_service=session_service,
        identity_resolver=app.state.identity_resolver,
        http_client=idp_http_client,
        public_origin="http://testserver",
    )
    app.state.oidc_flow = oidc_flow

    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    app.include_router(auth_identities_router, prefix="/api/v1")
    app.include_router(auth_oidc_router, prefix="/api/v1")
    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_middleware(RequestIdMiddleware)

    # 3. Lifecycle Step 1: Zero-factor @alice links corp-sso
    asgi_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client:
        client.cookies.set("kb_session", s_alice.cookie_val)
        client.cookies.set("kb_csrf", s_alice.csrf_token)
        client.cookies.set("__Host-kb_csrf", s_alice.csrf_token)

        # 3a. Call POST /api/v1/auth/identities/link/start
        link_start_resp = await client.post(
            "/api/v1/auth/identities/link/start",
            headers={CSRF_HEADER_NAME: s_alice.csrf_token},
            json={"card_slug": "corp-sso"},
        )
        assert link_start_resp.status_code == 200
        start_payload = link_start_resp.json()
        assert start_payload["mode"] == "redirect"
        assert "authorize_url" in start_payload

        # Extract browser binding cookie
        set_cookies = link_start_resp.headers.get_list("set-cookie")
        oidc_cookie_val = ""
        for cookie_str in set_cookies:
            for part in cookie_str.split(";"):
                part_clean = part.strip()
                if part_clean.startswith("__Host-kb_oidc=") or (
                    not oidc_cookie_val and part_clean.startswith("kb_oidc=")
                ):
                    oidc_cookie_val = part_clean.split("=", 1)[1]

        assert len(oidc_cookie_val) > 0

        # Assert Real Rows Inserted into PostgreSQL with ZERO FK error
        check_ctx = RLSContext(principal_id=alice_id, workspace_id=ws_id, aal_level=1)
        async with session_factory.session(check_ctx) as verify_sess:
            await verify_sess.execute(text("RESET SESSION AUTHORIZATION"))
            intent_row = (
                (
                    await verify_sess.execute(
                        text(
                            "SELECT id, principal_id, session_id, target_card_id, consumed_at "
                            "FROM identity_link_intents WHERE principal_id = :p_id"
                        ),
                        {"p_id": alice_id},
                    )
                )
                .mappings()
                .first()
            )
            assert intent_row is not None
            assert intent_row["principal_id"] == alice_id
            assert intent_row["session_id"] == s_alice.session_id
            assert intent_row["target_card_id"] == card_id
            assert intent_row["consumed_at"] is None

            auth_req_row = (
                (
                    await verify_sess.execute(
                        text(
                            "SELECT id, card_id, link_intent_id, consumed_at "
                            "FROM oidc_auth_requests WHERE link_intent_id = :intent_id"
                        ),
                        {"intent_id": intent_row["id"]},
                    )
                )
                .mappings()
                .first()
            )
            assert auth_req_row is not None
            assert auth_req_row["link_intent_id"] == intent_row["id"]
            assert auth_req_row["consumed_at"] is None

        # 3b. Authenticate against FakeIdP and invoke callback
        auth_url = start_payload["authorize_url"]
        auth_params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(auth_url).query))
        cb_url = fake_idp.authorize_url_for_params(
            client_id=auth_params["client_id"],
            redirect_uri=auth_params["redirect_uri"],
            state=auth_params["state"],
            nonce=auth_params["nonce"],
            code_challenge=auth_params["code_challenge"],
            code_challenge_method=auth_params["code_challenge_method"],
        )
        cb_params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url).query))

        client.cookies.set("kb_oidc", oidc_cookie_val)
        client.cookies.set("__Host-kb_oidc", oidc_cookie_val)

        cb_resp = await client.get(
            f"/api/v1/auth/oidc/corp-sso/callback?code={cb_params['code']}&state={cb_params['state']}",
            follow_redirects=False,
        )
        assert cb_resp.status_code == 302
        assert cb_resp.headers["location"] == "/settings/profile?linked=corp-sso"

        # 3c. Verify external identity bound in PostgreSQL and @alice session preserved
        async with session_factory.session(check_ctx) as verify_sess:
            await verify_sess.execute(text("RESET SESSION AUTHORIZATION"))
            ident_row = (
                (
                    await verify_sess.execute(
                        text(
                            "SELECT id, principal_id, auth_card_id, immutable_subject_id "
                            "FROM user_identities WHERE principal_id = :p_id"
                        ),
                        {"p_id": alice_id},
                    )
                )
                .mappings()
                .first()
            )
            assert ident_row is not None
            assert ident_row["principal_id"] == alice_id
            assert ident_row["auth_card_id"] == card_id
            assert ident_row["immutable_subject_id"] == "user-4242"

            # Verify @alice exact session_id and aal_level == 1 preserved
            sess_row = (
                (
                    await verify_sess.execute(
                        text("SELECT id, principal_id, aal_level FROM sessions WHERE id = :s_id"),
                        {"s_id": s_alice.session_id},
                    )
                )
                .mappings()
                .first()
            )
            assert sess_row is not None
            assert sess_row["principal_id"] == alice_id
            assert sess_row["aal_level"] == 1

            # Verify link intent and auth request consumed
            consumed_intent = await verify_sess.scalar(
                text("SELECT consumed_at FROM identity_link_intents WHERE id = :id"),
                {"id": intent_row["id"]},
            )
            assert consumed_intent is not None

            consumed_req = await verify_sess.scalar(
                text("SELECT consumed_at FROM oidc_auth_requests WHERE id = :id"),
                {"id": auth_req_row["id"]},
            )
            assert consumed_req is not None

    # 4. Lifecycle Step 2: Second user @admin attempts to link the same (issuer, sub)
    async with httpx.AsyncClient(
        transport=asgi_transport, base_url="http://testserver"
    ) as admin_client:
        admin_client.cookies.set("kb_session", s_admin.cookie_val)
        admin_client.cookies.set("kb_csrf", s_admin.csrf_token)
        admin_client.cookies.set("__Host-kb_csrf", s_admin.csrf_token)

        # 4a. Admin calls POST /api/v1/auth/identities/link/start
        admin_start_resp = await admin_client.post(
            "/api/v1/auth/identities/link/start",
            headers={CSRF_HEADER_NAME: s_admin.csrf_token},
            json={"card_slug": "corp-sso"},
        )
        assert admin_start_resp.status_code == 200
        admin_start_payload = admin_start_resp.json()
        assert admin_start_payload["mode"] == "redirect"

        admin_oidc_cookie_val = ""
        for cookie_str in admin_start_resp.headers.get_list("set-cookie"):
            for part in cookie_str.split(";"):
                part_clean = part.strip()
                if part_clean.startswith("__Host-kb_oidc=") or (
                    not admin_oidc_cookie_val and part_clean.startswith("kb_oidc=")
                ):
                    admin_oidc_cookie_val = part_clean.split("=", 1)[1]

        assert len(admin_oidc_cookie_val) > 0

        # 4b. IdP returns code for the SAME subject (user-4242)
        admin_auth_url = admin_start_payload["authorize_url"]
        admin_query = urllib.parse.urlsplit(admin_auth_url).query
        admin_auth_params = dict(urllib.parse.parse_qsl(admin_query))
        admin_cb_url = fake_idp.authorize_url_for_params(
            client_id=admin_auth_params["client_id"],
            redirect_uri=admin_auth_params["redirect_uri"],
            state=admin_auth_params["state"],
            nonce=admin_auth_params["nonce"],
            code_challenge=admin_auth_params["code_challenge"],
            code_challenge_method=admin_auth_params["code_challenge_method"],
        )
        admin_cb_params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(admin_cb_url).query))

        admin_client.cookies.set("kb_oidc", admin_oidc_cookie_val)
        admin_client.cookies.set("__Host-kb_oidc", admin_oidc_cookie_val)

        # 4c. Callback fails with IDENTITY_ALREADY_LINKED redirect
        cb_path = (
            f"/api/v1/auth/oidc/corp-sso/callback"
            f"?code={admin_cb_params['code']}&state={admin_cb_params['state']}"
        )
        admin_cb_resp = await admin_client.get(cb_path, follow_redirects=False)
        assert admin_cb_resp.status_code == 302
        expected_loc = "/settings/profile?link_error=IDENTITY_ALREADY_LINKED"
        assert admin_cb_resp.headers["location"] == expected_loc

        # 4d. Verify PostgreSQL still has 0 identities for @admin, and @alice identity is untouched
        admin_check_ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=2)
        async with session_factory.session(admin_check_ctx) as verify_sess:
            await verify_sess.execute(text("RESET SESSION AUTHORIZATION"))
            admin_ident_count = await verify_sess.scalar(
                text("SELECT COUNT(*) FROM user_identities WHERE principal_id = :p_id"),
                {"p_id": admin_id},
            )
            assert admin_ident_count == 0

            alice_ident_count = await verify_sess.scalar(
                text("SELECT COUNT(*) FROM user_identities WHERE principal_id = :p_id"),
                {"p_id": alice_id},
            )
            assert alice_ident_count == 1

    await idp_http_client.aclose()
