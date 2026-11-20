# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for public authentication cards endpoints (KB-P2-10, S4.1, S4.3)."""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from database.session import RLSSessionFactory
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.v1.auth_cards_public import (
    get_public_session,
)
from kanban.api.v1.auth_cards_public import (
    router as auth_cards_public_router,
)
from kanban.auth.cards.repository import admin_upsert
from kanban.auth.cards.schemas import AuthCardPublic
from kanban.auth.oidc.discovery import OidcError
from kanban.security.envelope import StaticKekProvider, seal_card_secret


@pytest.fixture
def kek_provider() -> StaticKekProvider:
    """Fixture providing StaticKekProvider with test keys."""
    return StaticKekProvider(
        keys={"kek-v1": os.urandom(32), "kek-v2": os.urandom(32)},
        current="kek-v1",
    )


async def _setup_workspace(session: AsyncSession) -> uuid.UUID:
    """Provision a workspace."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Public Cards WS"},
    )
    return ws_id


async def _setup_admin_principal(session: AsyncSession, ws_id: uuid.UUID) -> uuid.UUID:
    """Provision a SERVER_ADMIN principal with role bindings and AAL2 session context."""
    u_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {"ws_id": ws_id, "ckey": f"usr-{u_id.hex}", "title": "Test Admin", "u_id": u_id},
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Test Admin', 'ACTIVE')"
        ),
        {"id": u_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'admin@example.com')"
        ),
        {"id": u_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": u_id},
    )
    await session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"p_id": str(u_id), "w_id": str(ws_id)},
    )
    return u_id


@pytest.mark.asyncio
async def test_case_1_positive_crud_and_public_projection(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Case 1: Positive CRUD & public projection.

    Create OIDC, LDAP, and OAuth2 cards with secrets.
    Enable OIDC and LDAP (keep OAuth2 disabled).
    GET /api/v1/auth/cards returns only enabled cards in exact sort_rank order with
    only {id, slug, provider_kind, display_name, button_subtext, icon_preset}.
    """
    ws_id = await _setup_workspace(db_session)
    await _setup_admin_principal(db_session, ws_id)

    # 1. Create OIDC card (enabled, rank 'BGuM')
    c_oidc_id = uuid.uuid4()
    sealed_oidc = seal_card_secret(c_oidc_id, "OIDC", b"oidc-secret-test", kek_provider)
    await admin_upsert(
        db_session,
        card_id=c_oidc_id,
        workspace_id=ws_id,
        provider_kind="OIDC",
        slug="oidc-sso",
        display_name="Enterprise SSO",
        button_subtext="Sign in with OIDC",
        icon_preset="key",
        is_enabled=True,
        sort_rank="BGuM",
        auto_provision_users=True,
        allowed_email_domains=["example.com"],
        public_config={
            "issuer": "https://idp.example.com",
            "client_id": "oidc-client-123",
        },
        encrypted_secret_blob=sealed_oidc.encrypted_secret_blob,
        wrapped_dek=sealed_oidc.wrapped_dek,
        dek_kid=sealed_oidc.dek_kid,
    )

    # 2. Create LDAP card (enabled, rank 'GuMX' > 'BGuM')
    c_ldap_id = uuid.uuid4()
    sealed_ldap = seal_card_secret(c_ldap_id, "LDAP", b"ldap-bind-secret", kek_provider)
    await admin_upsert(
        db_session,
        card_id=c_ldap_id,
        workspace_id=ws_id,
        provider_kind="LDAP",
        slug="corp-directory",
        display_name="Corporate Directory",
        button_subtext="Username & password",
        icon_preset="building",
        is_enabled=True,
        sort_rank="GuMX",
        public_config={
            "url": "ldaps://ldap.example.com:636",
            "transport_mode": "ldaps",
            "base_dn": "dc=example,dc=com",
        },
        encrypted_secret_blob=sealed_ldap.encrypted_secret_blob,
        wrapped_dek=sealed_ldap.wrapped_dek,
        dek_kid=sealed_ldap.dek_kid,
    )

    # 3. Create OAuth2 card (disabled, rank '5dSB' < 'BGuM')
    c_oauth2_id = uuid.uuid4()
    sealed_oauth2 = seal_card_secret(c_oauth2_id, "OAUTH2", b"oauth2-secret", kek_provider)
    await admin_upsert(
        db_session,
        card_id=c_oauth2_id,
        workspace_id=ws_id,
        provider_kind="OAUTH2",
        slug="github-login",
        display_name="GitHub Login",
        is_enabled=False,
        sort_rank="5dSB",
        public_config={"client_id": "gh-client-456"},
        encrypted_secret_blob=sealed_oauth2.encrypted_secret_blob,
        wrapped_dek=sealed_oauth2.wrapped_dek,
        dek_kid=sealed_oauth2.dek_kid,
    )

    # Test HTTP endpoint
    app = FastAPI()
    app.state.session_factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    app.include_router(auth_cards_public_router, prefix="/api/v1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/cards")
        assert resp.status_code == 200

        data = resp.json()
        assert "cards" in data
        cards = data["cards"]

        # Only enabled cards returned (OIDC and LDAP; OAuth2 excluded)
        assert len(cards) == 2
        assert cards[0]["slug"] == "oidc-sso"
        assert cards[0]["id"] == str(c_oidc_id)
        assert cards[0]["provider_kind"] == "OIDC"
        assert cards[0]["display_name"] == "Enterprise SSO"
        assert cards[0]["button_subtext"] == "Sign in with OIDC"
        assert cards[0]["icon_preset"] == "key"

        assert cards[1]["slug"] == "corp-directory"
        assert cards[1]["id"] == str(c_ldap_id)
        assert cards[1]["provider_kind"] == "LDAP"

        # Verify strict schema projection: only permitted fields present
        expected_keys = {
            "id",
            "slug",
            "provider_kind",
            "display_name",
            "button_subtext",
            "icon_preset",
        }
        for c in cards:
            assert set(c.keys()) == expected_keys
            # Validate through Pydantic extra="forbid" schema
            AuthCardPublic.model_validate(c)


@pytest.mark.asyncio
async def test_case_2_public_zero_leakage(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Case 2: Security (zero config/secret leakage on public endpoint).

    Verify canary secret and IdP internal configs do not appear anywhere in public JSON.
    """
    ws_id = await _setup_workspace(db_session)
    await _setup_admin_principal(db_session, ws_id)

    canary = "s3cr3t-canary-p2-10"
    canary_bytes = canary.encode("utf-8")
    issuer_url = "https://sensitive-idp.internal.example.com"
    client_id = "sensitive-client-id-xyz"

    card_id = uuid.uuid4()
    sealed = seal_card_secret(card_id, "OIDC", canary_bytes, kek_provider)
    await admin_upsert(
        db_session,
        card_id=card_id,
        workspace_id=ws_id,
        provider_kind="OIDC",
        slug="canary-sso",
        display_name="Canary SSO",
        is_enabled=True,
        sort_rank="V",
        allowed_email_domains=["secret-domain.internal"],
        public_config={"issuer": issuer_url, "client_id": client_id},
        encrypted_secret_blob=sealed.encrypted_secret_blob,
        wrapped_dek=sealed.wrapped_dek,
        dek_kid=sealed.dek_kid,
    )

    app = FastAPI()
    app.state.session_factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    app.include_router(auth_cards_public_router, prefix="/api/v1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/cards")
        raw_text = resp.text

        # Canary secret must be 0 hits
        assert canary not in raw_text

        # Private metadata and configs must be 0 hits
        assert issuer_url not in raw_text
        assert client_id not in raw_text
        assert "secret-domain.internal" not in raw_text
        assert "allowed_email_domains" not in raw_text
        assert "public_config" not in raw_text
        assert "encrypted_secret_blob" not in raw_text
        assert "wrapped_dek" not in raw_text
        assert "dek_kid" not in raw_text
        assert "last_health_status" not in raw_text


@pytest.mark.asyncio
async def test_public_start_endpoint_routing(
    db_session: AsyncSession,
) -> None:
    """Verify /auth/cards/{slug}/start returns 404 for disabled, non-OIDC, or missing cards."""
    ws_id = await _setup_workspace(db_session)
    await _setup_admin_principal(db_session, ws_id)

    # 1. Disabled OIDC card
    c_disabled = uuid.uuid4()
    await admin_upsert(
        db_session,
        card_id=c_disabled,
        workspace_id=ws_id,
        provider_kind="OIDC",
        slug="disabled-oidc",
        display_name="Disabled OIDC",
        is_enabled=False,
        sort_rank="A",
    )

    # 2. Enabled LDAP card (not OIDC/OAuth2)
    c_ldap = uuid.uuid4()
    await admin_upsert(
        db_session,
        card_id=c_ldap,
        workspace_id=ws_id,
        provider_kind="LDAP",
        slug="ldap-card",
        display_name="LDAP",
        is_enabled=True,
        sort_rank="B",
    )

    app = FastAPI()
    app.state.session_factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    app.include_router(auth_cards_public_router, prefix="/api/v1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Disabled card -> 404
        r_disabled = await client.get("/api/v1/auth/cards/disabled-oidc/start")
        assert r_disabled.status_code == 404

        # LDAP card -> 404
        r_ldap = await client.get("/api/v1/auth/cards/ldap-card/start")
        assert r_ldap.status_code == 404

        # Nonexistent card -> 404
        r_missing = await client.get("/api/v1/auth/cards/nonexistent/start")
        assert r_missing.status_code == 404


@pytest.mark.asyncio
async def test_public_start_endpoint_success_and_oidc_errors(
    db_session: AsyncSession,
) -> None:
    """Verify /auth/cards/{slug}/start delegates to OidcFlow and handles OidcError."""
    ws_id = await _setup_workspace(db_session)
    await _setup_admin_principal(db_session, ws_id)

    c_oidc = uuid.uuid4()
    await admin_upsert(
        db_session,
        card_id=c_oidc,
        workspace_id=ws_id,
        provider_kind="OIDC",
        slug="active-oidc",
        display_name="Active OIDC",
        is_enabled=True,
        sort_rank="A",
    )

    app = FastAPI()
    app.state.session_factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    app.add_exception_handler(ProblemException, problem_exception_handler)  # type: ignore[arg-type]
    app.include_router(auth_cards_public_router, prefix="/api/v1")

    # 1. Missing session_factory raises RuntimeError
    req_dummy = MagicMock()
    req_dummy.app.state = MagicMock()
    req_dummy.app.state.session_factory = None
    with pytest.raises(RuntimeError, match="No session_factory configured"):
        async for _ in get_public_session(req_dummy):
            pass

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        mock_flow = AsyncMock()
        mock_flow.start = AsyncMock(
            return_value=RedirectResponse("https://idp.example.com/auth", status_code=302)
        )

        with patch("kanban.api.v1.auth_cards_public.get_oidc_flow", return_value=mock_flow):
            # Success with ?next=
            r_next = await client.get("/api/v1/auth/cards/active-oidc/start?next=/dashboard")
            assert r_next.status_code == 302
            assert r_next.headers["location"] == "https://idp.example.com/auth"
            assert mock_flow.start.call_args[1]["return_to"] == "/dashboard"

            # Verify unauthenticated link_intent_id query param is ignored / rejected
            intent_id = uuid.uuid4()
            r_intent = await client.get(
                f"/api/v1/auth/cards/active-oidc/start?return_to=/profile&link_intent_id={intent_id}"
            )
            assert r_intent.status_code == 302
            assert mock_flow.start.call_args[1]["return_to"] == "/profile"
            assert mock_flow.start.call_args[1].get("link_intent_id") is None

            # OidcError with DISCOVERY_FAILED -> 502
            mock_flow.start.side_effect = OidcError("DISCOVERY_FAILED", "IdP unreachable")
            r_502 = await client.get("/api/v1/auth/cards/active-oidc/start")
            assert r_502.status_code == 502
            assert r_502.json()["code"] == "OIDC_DISCOVERY_FAILED"

            # OidcError with BAD_REQUEST -> 400
            mock_flow.start.side_effect = OidcError("BAD_STATE", "Invalid state")
            r_400 = await client.get("/api/v1/auth/cards/active-oidc/start")
            assert r_400.status_code == 400
            assert r_400.json()["code"] == "OIDC_BAD_STATE"
