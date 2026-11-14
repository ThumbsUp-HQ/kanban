# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: SLF001, PLR0915, S311, PLR0133, E501
"""Integration and unit tests for Auth Provider Cards Admin API (KB-P2-10)."""

from __future__ import annotations

import os
import random
import uuid
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from database.session import RLSContext, RLSSessionFactory
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.request_id import RequestIdMiddleware
from kanban.api.v1 import build_v1_router
from kanban.auth.cards.lockout import record_external_admin_handshake
from kanban.auth.cards.repository import admin_get, admin_upsert
from kanban.auth.cards.service import AuthCardAdminService
from kanban.auth.mfa.policy import assert_admin_routes_protected
from kanban.auth.sessions.cookies import SESSION_COOKIE_NAME
from kanban.auth.sessions.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, CsrfMiddleware
from kanban.auth.sessions.resolver import SessionCookieResolver
from kanban.auth.sessions.service import SessionService
from kanban.security.envelope import StaticKekProvider
from kanban.security.keys import KeyMaterial
from kanban.tests.fixtures.fake_idp import FakeIdP
from kanban.tests.fixtures.fake_ldap import FakeLdapServer, LdapTestCerts, generate_ldap_test_certs
from kanban.util.fractional_rank import initial_ranks


@pytest.fixture
def key_material() -> KeyMaterial:
    """Fixture providing testing key material."""
    return KeyMaterial(
        master_kek=b"k" * 32,
        master_kek_kid="kek-v1",
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )


@pytest.fixture
def kek_provider(key_material: KeyMaterial) -> StaticKekProvider:
    """Fixture providing StaticKekProvider with test keys."""
    return StaticKekProvider(
        keys={"kek-v1": key_material.master_kek, "kek-v2": os.urandom(32)},
        current="kek-v1",
    )


@pytest.fixture
def ldap_certs() -> LdapTestCerts:
    """Generate ephemeral LDAP CA and server certificates."""
    return generate_ldap_test_certs()


async def _setup_workspace_and_principals(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Provision workspace, SERVER_ADMIN, and PROJECT_ADMIN principals."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Admin Cards WS"},
    )

    # 1. Server Admin
    server_admin_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{server_admin_id.hex}",
            "title": "Server Admin",
            "u_id": server_admin_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Server Admin', 'ACTIVE')"
        ),
        {"id": server_admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'server-admin@example.com')"
        ),
        {"id": server_admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": server_admin_id},
    )
    await session.execute(
        text(
            "INSERT INTO local_admin_credentials (principal_id, username, password_hash) "
            "VALUES (:p_id, :username, '$argon2id$v=19$m=65536,t=3,p=4$fakehash$fakehash')"
        ),
        {"p_id": server_admin_id, "username": f"admin-{server_admin_id.hex[:8]}"},
    )

    # 2. Project Admin
    project_admin_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{project_admin_id.hex}",
            "title": "Project Admin",
            "u_id": project_admin_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Project Admin', 'ACTIVE')"
        ),
        {"id": project_admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'project-admin@example.com')"
        ),
        {"id": project_admin_id, "ws_id": ws_id},
    )

    proj_id = uuid.uuid4()
    proj_ident = f"P{proj_id.hex[:6].upper()}"
    await session.execute(
        text(
            "SELECT register_object('project'::object_kind, :ws_id, NULL, :ckey, :title, :created_by, :p_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": proj_ident,
            "title": "Test Project",
            "created_by": server_admin_id,
            "p_id": proj_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, name, identifier) "
            "VALUES (:id, :ws_id, 'Test Project', :ident)"
        ),
        {"id": proj_id, "ws_id": ws_id, "ident": proj_ident},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'PROJECT_ADMIN', 'project', :proj_id)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": project_admin_id, "proj_id": proj_id},
    )

    # Register MFA TOTP for both administrators to satisfy require_admin_aal2
    for p_id in (server_admin_id, project_admin_id):
        await session.execute(
            text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
            {
                "p_id": p_id,
                "blob": b"\x01" + b"\x00" * 28,
                "dek": b"\x01" + b"\x00" * 44,
            },
        )
        res = await session.execute(
            text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
            {"p_id": p_id},
        )
        p_row = res.mappings().first()
        if p_row:
            await session.execute(
                text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
                {"p_fid": p_row["id"]},
            )

    # Default session RLS context to server admin AAL2
    await session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"p_id": str(server_admin_id), "w_id": str(ws_id)},
    )

    return ws_id, server_admin_id, project_admin_id


def _create_test_app(
    factory: RLSSessionFactory,
    service: AuthCardAdminService,
    key_material: KeyMaterial,
    session_service: SessionService,
) -> FastAPI:
    """Instantiate configured FastAPI application with test dependencies."""
    app = FastAPI()
    app.state.session_factory = factory
    app.state.session_service = session_service
    app.state.key_material = key_material
    app.state.auth_card_admin_service = service
    app.state.principal_resolver = SessionCookieResolver(session_service, factory)

    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    v1 = build_v1_router()
    app.include_router(v1, prefix="/api/v1")

    app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
    app.add_middleware(RequestIdMiddleware)
    return app


@pytest.mark.asyncio
async def test_case_2_security_zero_secret_leakage(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
) -> None:
    """Case 2: Security (zero config/secret leakage).

    Inspect raw JSON of GET, POST, PATCH, and activity_records for canary secret.
    Canary secret must have 0 hits everywhere.
    """
    ws_id, server_admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    service = AuthCardAdminService(kek_provider=kek_provider)
    app = _create_test_app(factory, service, key_material, session_service)

    canary_secret = "s3cr3t-canary-p2-10"

    # Create AAL2 session for SERVER_ADMIN
    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)
    async with factory.session(anon_ctx) as sess:
        sess_aal2 = await session_service.create_after_login(
            sess,
            principal_id=server_admin_id,
            workspace_id=ws_id,
            aal_level=2,
            mfa_pending=False,
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal2.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_aal2.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_aal2.csrf_token

        # 1. POST /api/v1/admin/auth-cards with canary secret
        create_payload = {
            "provider_kind": "OIDC",
            "slug": "leak-test-card",
            "display_name": "Leak Test Card",
            "is_enabled": False,
            "public_config": {
                "issuer": "https://idp.example.com",
                "client_id": "test-client-id",
            },
            "secret": canary_secret,
        }
        res_post = await client.post("/api/v1/admin/auth-cards", json=create_payload)
        assert res_post.status_code == 201
        assert canary_secret not in res_post.text
        assert res_post.json()["has_secret"] is True

        # 2. GET /api/v1/admin/auth-cards
        res_list = await client.get("/api/v1/admin/auth-cards")
        assert res_list.status_code == 200
        assert canary_secret not in res_list.text

        # 3. GET /api/v1/admin/auth-cards/leak-test-card
        res_get = await client.get("/api/v1/admin/auth-cards/leak-test-card")
        assert res_get.status_code == 200
        assert canary_secret not in res_get.text

        # 4. PATCH /api/v1/admin/auth-cards/leak-test-card with new canary
        new_canary = "s3cr3t-canary-updated-99"
        res_patch = await client.patch(
            "/api/v1/admin/auth-cards/leak-test-card",
            json={"secret": new_canary, "display_name": "Updated Display"},
        )
        assert res_patch.status_code == 200
        assert new_canary not in res_patch.text
        assert canary_secret not in res_patch.text

        # 5. Check activity_records table for canary leak
        stmt = text(
            "SELECT payload::text FROM activity_records WHERE payload::text LIKE :c1 OR payload::text LIKE :c2"
        )
        records = (
            await db_session.execute(stmt, {"c1": f"%{canary_secret}%", "c2": f"%{new_canary}%"})
        ).fetchall()
        assert len(records) == 0


@pytest.mark.asyncio
async def test_case_3_fractional_rank_collate_c(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
) -> None:
    """Case 3: Fractional rank (COLLATE "C") and 200 random moves in DB.

    Verifies Python byte order matches PostgreSQL COLLATE "C" ('Z' < 'a'),
    and 200 random move operations maintain exact list order until rebalance.
    """
    ws_id, server_admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    service = AuthCardAdminService(kek_provider=kek_provider)
    app = _create_test_app(factory, service, key_material, session_service)

    # 1. Assert case check: 'Z' < 'a' holds identically in Python and Postgres COLLATE "C"
    assert "Z" < "a"
    pg_res = (await db_session.execute(text("SELECT ('Z' < 'a' COLLATE \"C\")"))).scalar_one()
    assert pg_res is True

    # 2. Seed 6 initial cards
    seeded_slugs = [f"card-{i:02d}" for i in range(6)]
    current_order = list(seeded_slugs)
    ranks = initial_ranks(len(seeded_slugs))

    for i, slug in enumerate(seeded_slugs):
        await admin_upsert(
            db_session,
            workspace_id=ws_id,
            provider_kind="LOCAL_ADMIN" if i == 0 else "OIDC",
            slug=slug,
            display_name=f"Card {i}",
            is_enabled=False,
            sort_rank=ranks[i],
        )

    # Create AAL2 session for reorder requests
    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)
    async with factory.session(anon_ctx) as sess:
        sess_aal2 = await session_service.create_after_login(
            sess,
            principal_id=server_admin_id,
            workspace_id=ws_id,
            aal_level=2,
            mfa_pending=False,
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal2.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_aal2.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_aal2.csrf_token

        # Initial rebalance to establish clean ranks
        await client.post(
            f"/api/v1/admin/auth-cards/{seeded_slugs[0]}/reorder", json={"after": None}
        )

        rng = random.Random(1337)

        # 3. Perform 200 random move operations
        for _ in range(200):
            # Pick a card to move
            move_idx = rng.randint(0, len(current_order) - 1)
            target_slug = current_order.pop(move_idx)

            # Pick destination
            dest_pos = rng.randint(0, len(current_order))
            after_slug = current_order[dest_pos - 1] if dest_pos > 0 else None
            current_order.insert(dest_pos, target_slug)

            # Execute reorder request
            reorder_res = await client.post(
                f"/api/v1/admin/auth-cards/{target_slug}/reorder",
                json={"after": after_slug},
            )
            assert reorder_res.status_code == 200

            # Verify PostgreSQL ORDER BY sort_rank COLLATE "C" matches current_order
            rows = (
                (
                    await db_session.execute(
                        text(
                            "SELECT slug FROM auth_provider_cards "
                            "WHERE workspace_id = :ws_id "
                            'ORDER BY sort_rank COLLATE "C" ASC, id ASC'
                        ),
                        {"ws_id": ws_id},
                    )
                )
                .scalars()
                .all()
            )
            assert list(rows) == current_order


@pytest.mark.asyncio
async def test_case_4_handshake_probe_diagnostics(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
    ldap_certs: LdapTestCerts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 4: Handshake probe diagnostics.

    - OIDC card against fake_idp -> ok=True, last_health_status="OK";
    - fake_idp with mismatched issuer -> ok=False, error_code="ISSUER_MISMATCH", last_health_status="FAILED:ISSUER_MISMATCH";
    - LDAP card with mismatched SPKI pin -> ok=False, error_code="SPKI_PIN_MISMATCH";
    - Modifying public_config via PATCH resets last_health_status to "UNVERIFIED".
    """
    monkeypatch.setenv("KANBAN_AUTH_EGRESS_ALLOW_PRIVATE", "true")
    ws_id, server_admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)

    fake_idp = FakeIdP(issuer="https://idp.example.com", client_id="test-client")
    mock_http_client = httpx.AsyncClient(transport=fake_idp.as_transport())

    service = AuthCardAdminService(
        kek_provider=kek_provider,
        http_client=mock_http_client,
    )
    app = _create_test_app(factory, service, key_material, session_service)

    # 1. Valid OIDC card
    c_oidc_id = uuid.uuid4()
    await admin_upsert(
        db_session,
        card_id=c_oidc_id,
        workspace_id=ws_id,
        provider_kind="OIDC",
        slug="oidc-probe-card",
        display_name="OIDC Probe Card",
        is_enabled=True,
        sort_rank="A",
        public_config={
            "issuer": fake_idp.issuer,
            "client_id": fake_idp.client_id,
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO user_identities ("
            "  workspace_id, auth_card_id, principal_id, "
            "  immutable_subject_id, subject_email_at_link"
            ") VALUES (:ws_id, :cid, :pid, 'oidc-probe-sub', 'server-admin@example.com')"
        ),
        {"ws_id": ws_id, "cid": c_oidc_id, "pid": server_admin_id},
    )

    # Create AAL2 session
    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)
    async with factory.session(anon_ctx) as sess:
        sess_aal2 = await session_service.create_after_login(
            sess,
            principal_id=server_admin_id,
            workspace_id=ws_id,
            aal_level=2,
            mfa_pending=False,
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal2.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_aal2.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_aal2.csrf_token

        # Probe valid OIDC card -> OK
        res_oidc_ok = await client.post("/api/v1/admin/auth-cards/oidc-probe-card/test-handshake")
        assert res_oidc_ok.status_code == 200
        probe_data = res_oidc_ok.json()
        assert probe_data["ok"] is True
        assert probe_data["status"] == "OK"
        assert probe_data["error_code"] is None
        assert probe_data["latency_ms"] >= 0

        card_db = await admin_get(db_session, c_oidc_id)
        assert card_db is not None
        assert card_db.last_health_status == "OK"

        # 2. OIDC card with mismatched issuer -> ISSUER_MISMATCH
        fake_idp_bad = FakeIdP(issuer="https://idp.example.com")
        # In discovery response, returned issuer is https://different-issuer.example.com
        fake_idp_bad.discovery_override = lambda _req: httpx.Response(
            200,
            json={
                "issuer": "https://different-issuer.example.com",
                "authorization_endpoint": "https://idp.example.com/auth",
                "token_endpoint": "https://idp.example.com/token",
                "jwks_uri": "https://idp.example.com/jwks",
            },
        )
        bad_http_client = httpx.AsyncClient(transport=fake_idp_bad.as_transport())
        service._http_client = bad_http_client

        res_oidc_bad = await client.post("/api/v1/admin/auth-cards/oidc-probe-card/test-handshake")
        assert res_oidc_bad.status_code == 200
        bad_probe = res_oidc_bad.json()
        assert bad_probe["ok"] is False
        assert bad_probe["error_code"] == "ISSUER_MISMATCH"
        assert bad_probe["status"] == "FAILED:ISSUER_MISMATCH"

        card_bad_db = await admin_get(db_session, c_oidc_id)
        assert card_bad_db is not None
        assert card_bad_db.last_health_status == "FAILED:ISSUER_MISMATCH"

        # 3. LDAP card with mismatched SPKI pin
        async with FakeLdapServer(ldap_certs, mode="ldaps", use_mismatched_cert=True) as server:
            service._ldap_unix_socket_path = server.sock_path
            c_ldap_id = uuid.uuid4()
            await admin_upsert(
                db_session,
                card_id=c_ldap_id,
                workspace_id=ws_id,
                provider_kind="LDAP",
                slug="ldap-probe-card",
                display_name="LDAP Probe Card",
                is_enabled=False,
                sort_rank="B",
                public_config={
                    "kind": "LDAP",
                    "url": "ldaps://localhost:636",
                    "transport_mode": "ldaps",
                    "ca_cert_pem": ldap_certs.ca_pem,
                    "spki_sha256_pins": [ldap_certs.spki_sha256],
                    "base_dn": "dc=example,dc=com",
                },
            )

            res_ldap = await client.post("/api/v1/admin/auth-cards/ldap-probe-card/test-handshake")
            assert res_ldap.status_code == 200
            ldap_probe = res_ldap.json()
            assert ldap_probe["ok"] is False
            assert ldap_probe["error_code"] == "SPKI_PIN_MISMATCH"
            assert ldap_probe["status"] == "FAILED:SPKI_PIN_MISMATCH"

        # 4. Modifying public_config via PATCH resets last_health_status to "UNVERIFIED"
        res_patch = await client.patch(
            "/api/v1/admin/auth-cards/oidc-probe-card",
            json={
                "public_config": {"issuer": "https://idp.example.com", "client_id": "new-client"}
            },
        )
        assert res_patch.status_code == 200
        assert res_patch.json()["last_health_status"] == "UNVERIFIED"


@pytest.mark.asyncio
async def test_case_5_lockout_enforcement_over_http(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
) -> None:
    """Case 5: Lockout enforcement over HTTP.

    - Disabling sole admin-capable card returns 409 LOCKOUT_PREVENTED with layer="db_trigger";
    - Disabling LOCAL_ADMIN without recent external admin login returns 409 LOCKOUT_PREVENTED
      with layer="handshake_probe_15m" (even after running synthetic /test-handshake!);
    - Live external admin login handshake permits disabling LOCAL_ADMIN.
    """
    ws_id, server_admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    service = AuthCardAdminService(kek_provider=kek_provider)
    app = _create_test_app(factory, service, key_material, session_service)

    # 1. Create sole enabled card: LOCAL_ADMIN
    c_local_id = uuid.uuid4()
    await admin_upsert(
        db_session,
        card_id=c_local_id,
        workspace_id=ws_id,
        provider_kind="LOCAL_ADMIN",
        slug="sole-local-admin",
        display_name="Local Admin",
        is_enabled=True,
        sort_rank="A",
    )

    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)
    async with factory.session(anon_ctx) as sess:
        sess_aal2 = await session_service.create_after_login(
            sess,
            principal_id=server_admin_id,
            workspace_id=ws_id,
            aal_level=2,
            mfa_pending=False,
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal2.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_aal2.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_aal2.csrf_token

        # Attempt to disable sole card -> 409 LOCKOUT_PREVENTED (db_trigger or handshake_probe_15m)
        res_sole_disable = await client.post("/api/v1/admin/auth-cards/sole-local-admin/disable")
        assert res_sole_disable.status_code == 409
        sole_prob = res_sole_disable.json()
        assert sole_prob["code"] == "LOCKOUT_PREVENTED"
        assert sole_prob["layer"] in ("db_trigger", "handshake_probe_15m")

        # 2. Add an enabled external card (OIDC) with NO recent login handshake
        c_oidc_id = uuid.uuid4()
        await admin_upsert(
            db_session,
            card_id=c_oidc_id,
            workspace_id=ws_id,
            provider_kind="OIDC",
            slug="ext-oidc-card",
            display_name="External OIDC",
            is_enabled=True,
            sort_rank="B",
            public_config={"issuer": "https://idp.example.com", "client_id": "test"},
        )
        await db_session.execute(
            text(
                "INSERT INTO user_identities ("
                "  workspace_id, auth_card_id, principal_id, "
                "  immutable_subject_id, subject_email_at_link"
                ") VALUES (:ws_id, :cid, :pid, 'oidc-admin-sub', 'server-admin@example.com')"
            ),
            {"ws_id": ws_id, "cid": c_oidc_id, "pid": server_admin_id},
        )

        # Run synthetic /test-handshake on ext-oidc-card
        fake_idp = FakeIdP(issuer="https://idp.example.com", client_id="test")
        service._http_client = httpx.AsyncClient(transport=fake_idp.as_transport())
        res_test_hs = await client.post("/api/v1/admin/auth-cards/ext-oidc-card/test-handshake")
        assert res_test_hs.status_code == 200

        # Attempt to disable LOCAL_ADMIN -> must fail with layer="handshake_probe_15m"
        # because synthetic /test-handshake does NOT satisfy the 15-minute live external admin login requirement!
        res_disable_local = await client.post("/api/v1/admin/auth-cards/sole-local-admin/disable")
        assert res_disable_local.status_code == 409
        prob_local = res_disable_local.json()
        assert prob_local["code"] == "LOCKOUT_PREVENTED"
        assert prob_local["layer"] == "handshake_probe_15m"

        # 3. Record a verified external admin login handshake
        await record_external_admin_handshake(db_session, c_oidc_id)

        # Now disabling LOCAL_ADMIN succeeds!
        res_disable_success = await client.post("/api/v1/admin/auth-cards/sole-local-admin/disable")
        assert res_disable_success.status_code == 200
        assert res_disable_success.json()["is_enabled"] is False

        # Attempting to disable the remaining external card now fails with layer="db_trigger" (leaving 0 enabled cards)
        res_disable_ext = await client.post("/api/v1/admin/auth-cards/ext-oidc-card/disable")
        assert res_disable_ext.status_code == 409
        prob_ext = res_disable_ext.json()
        assert prob_ext["code"] == "LOCKOUT_PREVENTED"
        assert prob_ext["layer"] == "db_trigger"


@pytest.mark.asyncio
async def test_case_6_delete_confirmation(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
) -> None:
    """Case 6: Delete confirmation phrase and removal.

    - DELETE with mismatched or missing confirm_slug -> 422 CONFIRM_PHRASE_MISMATCH;
    - DELETE with exact confirm_slug on unused disabled card -> 204.
    """
    ws_id, server_admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    service = AuthCardAdminService(kek_provider=kek_provider)
    app = _create_test_app(factory, service, key_material, session_service)

    card_id = uuid.uuid4()
    await admin_upsert(
        db_session,
        card_id=card_id,
        workspace_id=ws_id,
        provider_kind="OIDC",
        slug="card-to-delete",
        display_name="Card to Delete",
        is_enabled=False,
        sort_rank="A",
    )

    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)
    async with factory.session(anon_ctx) as sess:
        sess_aal2 = await session_service.create_after_login(
            sess,
            principal_id=server_admin_id,
            workspace_id=ws_id,
            aal_level=2,
            mfa_pending=False,
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal2.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_aal2.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_aal2.csrf_token

        # 1. DELETE with wrong confirm_slug -> 422 CONFIRM_PHRASE_MISMATCH
        r_mismatch = await client.request(
            "DELETE",
            "/api/v1/admin/auth-cards/card-to-delete",
            json={"confirm_slug": "wrong-phrase"},
        )
        assert r_mismatch.status_code == 422
        assert r_mismatch.json()["code"] == "CONFIRM_PHRASE_MISMATCH"

        # 2. DELETE with matching confirm_slug -> 204 NO_CONTENT
        r_ok = await client.request(
            "DELETE",
            "/api/v1/admin/auth-cards/card-to-delete",
            json={"confirm_slug": "card-to-delete"},
        )
        assert r_ok.status_code == 204

        # Card is deleted from DB
        deleted = await admin_get(db_session, card_id)
        assert deleted is None


@pytest.mark.asyncio
async def test_case_7_authz_and_aal2_wall(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
) -> None:
    """Case 7: AuthZ and AAL2 wall.

    - Unauthenticated -> 401;
    - AAL1 SERVER_ADMIN -> 403 AAL2_REQUIRED;
    - AAL2 PROJECT_ADMIN (not SERVER_ADMIN) -> 403 INSUFFICIENT_CAPABILITY;
    - assert_admin_routes_protected(app) returns [].
    """
    ws_id, server_admin_id, project_admin_id = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    service = AuthCardAdminService(kek_provider=kek_provider)
    app = _create_test_app(factory, service, key_material, session_service)

    # Route audit: assert all admin routes require require_admin_aal2
    unprotected = assert_admin_routes_protected(app)
    assert unprotected == []

    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unauthenticated -> 401
        res_anon = await client.get("/api/v1/admin/auth-cards")
        assert res_anon.status_code == 401

        # 2. AAL1 SERVER_ADMIN -> 403 AAL2_REQUIRED
        async with factory.session(anon_ctx) as sess:
            sess_aal1 = await session_service.create_after_login(
                sess,
                principal_id=server_admin_id,
                workspace_id=ws_id,
                aal_level=1,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal1.cookie_val)
        res_aal1 = await client.get("/api/v1/admin/auth-cards")
        assert res_aal1.status_code == 403
        assert res_aal1.json()["code"] == "AAL2_REQUIRED"

        # 3. AAL2 PROJECT_ADMIN -> 403 INSUFFICIENT_CAPABILITY
        async with factory.session(anon_ctx) as sess:
            sess_proj_admin = await session_service.create_after_login(
                sess,
                principal_id=project_admin_id,
                workspace_id=ws_id,
                aal_level=2,
                mfa_pending=False,
            )
        client.cookies.set(SESSION_COOKIE_NAME, sess_proj_admin.cookie_val)
        res_proj = await client.get("/api/v1/admin/auth-cards")
        assert res_proj.status_code == 403
        assert res_proj.json()["code"] == "INSUFFICIENT_CAPABILITY"


@pytest.mark.asyncio
async def test_case_8_validation_boundaries(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
) -> None:
    """Case 8: Validation boundaries.

    - 51 allowed_email_domains -> 422;
    - Second LOCAL_ADMIN card in workspace -> 409 LOCAL_ADMIN_CARD_EXISTS;
    - Invalid OIDC http:// URL -> 422.
    """
    ws_id, server_admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    session_service = SessionService(key_material.session_hmac_key)
    service = AuthCardAdminService(kek_provider=kek_provider)
    app = _create_test_app(factory, service, key_material, session_service)

    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)
    async with factory.session(anon_ctx) as sess:
        sess_aal2 = await session_service.create_after_login(
            sess,
            principal_id=server_admin_id,
            workspace_id=ws_id,
            aal_level=2,
            mfa_pending=False,
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal2.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_aal2.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_aal2.csrf_token

        # 1. 51 allowed_email_domains -> 422
        domains_51 = [f"domain{i}.com" for i in range(51)]
        res_domains = await client.post(
            "/api/v1/admin/auth-cards",
            json={
                "provider_kind": "OIDC",
                "slug": "too-many-domains",
                "display_name": "Too Many Domains",
                "allowed_email_domains": domains_51,
                "public_config": {"issuer": "https://idp.example.com", "client_id": "test"},
            },
        )
        assert res_domains.status_code == 422

        # 2. Second LOCAL_ADMIN card in workspace -> 409 LOCAL_ADMIN_CARD_EXISTS
        res_local1 = await client.post(
            "/api/v1/admin/auth-cards",
            json={
                "provider_kind": "LOCAL_ADMIN",
                "slug": "local-admin-first",
                "display_name": "First Local Admin",
            },
        )
        assert res_local1.status_code == 201

        res_local2 = await client.post(
            "/api/v1/admin/auth-cards",
            json={
                "provider_kind": "LOCAL_ADMIN",
                "slug": "local-admin-second",
                "display_name": "Second Local Admin",
            },
        )
        assert res_local2.status_code == 409
        assert res_local2.json()["code"] == "LOCAL_ADMIN_CARD_EXISTS"

        # 3. Invalid OIDC http:// URL -> 422
        res_insecure_oidc = await client.post(
            "/api/v1/admin/auth-cards",
            json={
                "provider_kind": "OIDC",
                "slug": "insecure-oidc",
                "display_name": "Insecure OIDC",
                "public_config": {"issuer": "http://insecure-idp.example.com", "client_id": "test"},
            },
        )
        assert res_insecure_oidc.status_code == 422
