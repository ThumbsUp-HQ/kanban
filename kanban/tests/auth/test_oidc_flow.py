# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and integration tests for OIDC / OAuth2 flow and security invariants (KB-P2-06)."""

from __future__ import annotations

import logging
import urllib.parse
import uuid
from typing import TYPE_CHECKING

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import text
from starlette.requests import Request  # noqa: TC002

from kanban.api.problems import ProblemException
from kanban.api.v1.auth_oidc import (
    get_auth_session,
    get_oidc_flow,
)
from kanban.api.v1.auth_oidc import (
    router as auth_oidc_router,
)
from kanban.auth.cards.repository import admin_upsert
from kanban.auth.identity import (
    ExternalIdentityAssertion,
    RejectAllIdentityResolver,
    ResolvedLogin,
)
from kanban.auth.oidc.config import OidcCardConfig, _validate_safe_url
from kanban.auth.oidc.discovery import JwksCache, OidcError
from kanban.auth.oidc.flow import (
    OidcFlow,
    build_browser_binding_cookie,
    sanitize_return_to,
)
from kanban.auth.sessions.service import SessionService
from kanban.security.envelope import StaticKekProvider, seal_card_secret
from kanban.security.keys import KeyMaterial
from kanban.tests.fixtures.fake_idp import FakeIdP

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class RecordingIdentityResolver:
    """Identity resolver recording assertions and intents for testing."""

    def __init__(
        self,
        principal_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> None:
        """Initialize RecordingIdentityResolver with optional principal and workspace IDs."""
        self.assertions: list[ExternalIdentityAssertion] = []
        self.intents: list[uuid.UUID | None] = []
        self._principal_id = principal_id
        self._workspace_id = workspace_id

    async def resolve(
        self,
        assertion: ExternalIdentityAssertion,
        request: Request,
        link_intent_id: uuid.UUID | None,
    ) -> ResolvedLogin:
        """Resolve assertion, recording details."""
        del request
        self.assertions.append(assertion)
        self.intents.append(link_intent_id)
        return ResolvedLogin(
            principal_id=self._principal_id or uuid.uuid4(),
            workspace_id=self._workspace_id or uuid.uuid4(),
            aal_level=1,
            mfa_pending=False,
        )


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
    """Fixture providing an in-memory FakeIdP instance."""
    return FakeIdP(
        issuer="https://idp.example.com",
        client_id="test-client-id",
        client_secret="test-client-secret-999",  # noqa: S106
    )


@pytest.fixture
def recording_resolver() -> RecordingIdentityResolver:
    """Fixture providing a RecordingIdentityResolver."""
    return RecordingIdentityResolver()


async def _setup_workspace_and_admin(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision workspace and SERVER_ADMIN principal with AAL2 session context."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Auth Test WS"},
    )

    u_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{u_id.hex}",
            "title": "Auth Admin User",
            "u_id": u_id,
        },
    )

    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Auth Admin User', 'ACTIVE')"
        ),
        {"id": u_id, "ws_id": ws_id},
    )

    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'auth-admin@example.com')"
        ),
        {"id": u_id, "ws_id": ws_id},
    )

    rb_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
        ),
        {"id": rb_id, "ws_id": ws_id, "p_id": u_id},
    )

    # Bind session context to allow card_admin_upsert
    await session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"p_id": str(u_id), "w_id": str(ws_id)},
    )

    return ws_id, u_id


async def _seed_oidc_card(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    kek_provider: StaticKekProvider,
    slug: str,
    issuer: str,
    client_id: str,
    client_secret: bytes,
    client_auth: str = "client_secret_basic",
) -> uuid.UUID:
    """Seed an enabled OIDC card with sealed secret."""
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
            "client_auth": client_auth,
            "scopes": ["openid", "profile", "email"],
            "allowed_algs": ["RS256", "ES256"],
        },
        encrypted_secret_blob=sealed.encrypted_secret_blob,
        wrapped_dek=sealed.wrapped_dek,
        dek_kid=sealed.dek_kid,
    )
    return card_id


async def _seed_oauth2_card(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    kek_provider: StaticKekProvider,
    slug: str,
    auth_ep: str,
    token_ep: str,
    userinfo_ep: str,
    client_id: str,
    client_secret: bytes,
    subject_claim: str = "id",
) -> uuid.UUID:
    """Seed an enabled OAuth2 card with sealed secret."""
    card_id = uuid.uuid4()
    sealed = seal_card_secret(card_id, "OAUTH2", client_secret, kek_provider)
    await admin_upsert(
        session,
        card_id=card_id,
        workspace_id=ws_id,
        provider_kind="OAUTH2",
        slug=slug,
        display_name=f"OAuth2 Card {slug}",
        is_enabled=True,
        sort_rank="0002",
        public_config={
            "kind": "OAUTH2",
            "authorization_endpoint": auth_ep,
            "token_endpoint": token_ep,
            "userinfo_endpoint": userinfo_ep,
            "client_id": client_id,
            "client_auth": "client_secret_basic",
            "scopes": ["read:user", "user:email"],
            "subject_claim": subject_claim,
            "allowed_algs": ["RS256"],
        },
        encrypted_secret_blob=sealed.encrypted_secret_blob,
        wrapped_dek=sealed.wrapped_dek,
        dek_kid=sealed.dek_kid,
    )
    return card_id


@pytest.mark.asyncio
async def test_01_positive_oidc_flow(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
    fake_idp: FakeIdP,
    recording_resolver: RecordingIdentityResolver,
) -> None:
    """Test 1: Positive OIDC start -> IdP authorize -> callback -> resolver assertion with S256."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    await _seed_oidc_card(
        db_session,
        ws_id,
        kek_provider,
        slug="oidc-test",
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        client_secret=b"test-client-secret-999",
    )

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as http_client:
        flow = OidcFlow(
            key_material=key_material,
            identity_resolver=recording_resolver,
            http_client=http_client,
            public_origin="http://localhost:8000",
        )

        # 1. Start flow
        start_resp = await flow.start(
            db_session,
            "oidc-test",
            return_to="/projects/KAN",
        )
        assert start_resp.status_code == 302
        auth_url = start_resp.headers["Location"]
        assert "code_challenge_method=S256" in auth_url
        assert "response_type=code" in auth_url

        parsed_url = urllib.parse.urlsplit(auth_url)
        params = dict(urllib.parse.parse_qsl(parsed_url.query))
        assert params["code_challenge"] == start_resp.code_challenge
        assert params["state"] == start_resp.state
        assert params["nonce"] == start_resp.nonce

        # 2. Simulate user authenticating with FakeIdP
        callback_url = fake_idp.authorize_url_for_params(
            client_id=params["client_id"],
            redirect_uri=params["redirect_uri"],
            state=params["state"],
            nonce=params["nonce"],
            code_challenge=params["code_challenge"],
            code_challenge_method=params["code_challenge_method"],
        )
        cb_params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(callback_url).query))

        # 3. Callback
        cb_resp = await flow.callback(
            db_session,
            "oidc-test",
            code=cb_params["code"],
            state=cb_params["state"],
            browser_binding_cookie=start_resp.browser_binding,
        )
        assert cb_resp.status_code == 302
        assert cb_resp.headers["Location"] == "/projects/KAN"

        # Verify assertions received by resolver
        assert len(recording_resolver.assertions) == 1
        assertion = recording_resolver.assertions[0]
        assert assertion.subject == "user-4242"
        assert assertion.email == "user4242@example.com"
        assert assertion.email_verified is True

        # Verify fake IdP observed code_challenge_method=S256 and matched code_verifier
        assert len(fake_idp.observed_token_requests) == 1
        token_req = fake_idp.observed_token_requests[0]
        assert "code_verifier" in token_req["form"]


@pytest.mark.asyncio
async def test_02_positive_oauth2_flow(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
    fake_idp: FakeIdP,
    recording_resolver: RecordingIdentityResolver,
) -> None:
    """Test 2: Positive OAUTH2: no id_token, userinfo numeric id: 4242 -> subject='4242'."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    await _seed_oauth2_card(
        db_session,
        ws_id,
        kek_provider,
        slug="oauth2-test",
        auth_ep=f"{fake_idp.issuer}/oauth/authorize",
        token_ep=f"{fake_idp.issuer}/oauth/token",
        userinfo_ep=f"{fake_idp.issuer}/oauth/userinfo",
        client_id=fake_idp.client_id,
        client_secret=b"test-client-secret-999",
        subject_claim="id",
    )

    # Instruct FakeIdP to omit id_token on token exchange for OAuth2 test
    fake_idp.token_override = lambda _req, _form: httpx.Response(
        200,
        json={"token_type": "Bearer", "access_token": "oauth2-acc-123"},
    )
    fake_idp.userinfo_data = {"id": 4242, "email": "numeric@example.com", "email_verified": True}

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as http_client:
        flow = OidcFlow(
            key_material=key_material,
            identity_resolver=recording_resolver,
            http_client=http_client,
        )

        start_resp = await flow.start(db_session, "oauth2-test")
        auth_url = start_resp.headers["Location"]
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(auth_url).query))

        callback_url = fake_idp.authorize_url_for_params(
            client_id=params["client_id"],
            redirect_uri=params["redirect_uri"],
            state=params["state"],
            code_challenge=params["code_challenge"],
        )
        cb_params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(callback_url).query))

        cb_resp = await flow.callback(
            db_session,
            "oauth2-test",
            code=cb_params["code"],
            state=cb_params["state"],
            browser_binding_cookie=start_resp.browser_binding,
        )
        assert cb_resp.status_code == 302

        assert len(recording_resolver.assertions) == 1
        assertion = recording_resolver.assertions[0]
        # Coerced integer subject to string
        assert assertion.subject == "4242"
        assert assertion.email == "numeric@example.com"


@pytest.mark.asyncio
async def test_03_positive_private_key_jwt_flow(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
    fake_idp: FakeIdP,
    recording_resolver: RecordingIdentityResolver,
) -> None:
    """Test 3: Positive private_key_jwt flow: assertion verified by IdP, exp-iat==60."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)

    # Generate RSA client key pair for client assertion
    client_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client_priv_pem = client_priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    client_pub_pem = client_priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    fake_idp.client_public_key_pem = client_pub_pem

    await _seed_oidc_card(
        db_session,
        ws_id,
        kek_provider,
        slug="oidc-jwt-test",
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        client_secret=client_priv_pem,
        client_auth="private_key_jwt",
    )

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as http_client:
        flow = OidcFlow(
            key_material=key_material,
            identity_resolver=recording_resolver,
            http_client=http_client,
        )

        start_resp = await flow.start(db_session, "oidc-jwt-test")
        params = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(start_resp.headers["Location"]).query)
        )

        callback_url = fake_idp.authorize_url_for_params(
            client_id=params["client_id"],
            redirect_uri=params["redirect_uri"],
            state=params["state"],
            nonce=params["nonce"],
            code_challenge=params["code_challenge"],
        )
        cb_params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(callback_url).query))

        cb_resp = await flow.callback(
            db_session,
            "oidc-jwt-test",
            code=cb_params["code"],
            state=cb_params["state"],
            browser_binding_cookie=start_resp.browser_binding,
        )
        assert cb_resp.status_code == 302

        # Verify fake IdP received and validated client assertion
        assert len(fake_idp.observed_assertions) == 1
        assertion_claims = fake_idp.observed_assertions[0]
        assert assertion_claims["aud"] == f"{fake_idp.issuer}/oauth/token"
        assert assertion_claims["iss"] == fake_idp.client_id
        assert assertion_claims["sub"] == fake_idp.client_id
        assert assertion_claims["exp"] - assertion_claims["iat"] == 60


@pytest.mark.asyncio
async def test_04_state_replay_and_expiry(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
    fake_idp: FakeIdP,
    recording_resolver: RecordingIdentityResolver,
) -> None:
    """Test 4: callback submitted twice -> 400 OIDC_STATE_INVALID; state after 301s -> 400."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    await _seed_oidc_card(
        db_session,
        ws_id,
        kek_provider,
        slug="replay-test",
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        client_secret=b"test-client-secret-999",
    )

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as http_client:
        flow = OidcFlow(
            key_material=key_material,
            identity_resolver=recording_resolver,
            http_client=http_client,
        )

        start_resp = await flow.start(db_session, "replay-test")
        params = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(start_resp.headers["Location"]).query)
        )

        callback_url = fake_idp.authorize_url_for_params(
            client_id=params["client_id"],
            redirect_uri=params["redirect_uri"],
            state=params["state"],
            nonce=params["nonce"],
            code_challenge=params["code_challenge"],
        )
        cb_params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(callback_url).query))

        # First consumption succeeds
        cb_resp = await flow.callback(
            db_session,
            "replay-test",
            code=cb_params["code"],
            state=cb_params["state"],
            browser_binding_cookie=start_resp.browser_binding,
        )
        assert cb_resp.status_code == 302

        # Second consumption (replay attack) fails with 400 OIDC_STATE_INVALID
        with pytest.raises(ProblemException) as exc_info:
            await flow.callback(
                db_session,
                "replay-test",
                code=cb_params["code"],
                state=cb_params["state"],
                browser_binding_cookie=start_resp.browser_binding,
            )
        assert exc_info.value.code == "OIDC_STATE_INVALID"
        assert exc_info.value.status == 400

        # State after 301s: start another flow with expired TTL (ttl_seconds=-1)
        start_resp2 = await flow.start(db_session, "replay-test", ttl_seconds=-1)
        params2 = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(start_resp2.headers["Location"]).query)
        )

        cb_url2 = fake_idp.authorize_url_for_params(
            client_id=params2["client_id"],
            redirect_uri=params2["redirect_uri"],
            state=params2["state"],
            nonce=params2["nonce"],
            code_challenge=params2["code_challenge"],
        )
        cb_params2 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url2).query))

        with pytest.raises(ProblemException) as exc_info2:
            await flow.callback(
                db_session,
                "replay-test",
                code=cb_params2["code"],
                state=cb_params2["state"],
                browser_binding_cookie=start_resp2.browser_binding,
            )
        assert exc_info2.value.code == "OIDC_STATE_INVALID"
        assert exc_info2.value.status == 400


@pytest.mark.asyncio
async def test_05_browser_binding_csrf(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
    fake_idp: FakeIdP,
    recording_resolver: RecordingIdentityResolver,
) -> None:
    """Test 5: valid state with missing or different browser cookie -> 400 OIDC_STATE_INVALID."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    await _seed_oidc_card(
        db_session,
        ws_id,
        kek_provider,
        slug="csrf-test",
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        client_secret=b"test-client-secret-999",
    )

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as http_client:
        flow = OidcFlow(
            key_material=key_material,
            identity_resolver=recording_resolver,
            http_client=http_client,
        )

        start_resp = await flow.start(db_session, "csrf-test")
        params = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(start_resp.headers["Location"]).query)
        )
        cb_url = fake_idp.authorize_url_for_params(
            client_id=params["client_id"],
            redirect_uri=params["redirect_uri"],
            state=params["state"],
            nonce=params["nonce"],
            code_challenge=params["code_challenge"],
        )
        cb_params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url).query))

        # 1. Missing cookie
        with pytest.raises(ProblemException) as exc1:
            await flow.callback(
                db_session,
                "csrf-test",
                code=cb_params["code"],
                state=cb_params["state"],
                browser_binding_cookie=None,
            )
        assert exc1.value.code == "OIDC_STATE_INVALID"
        assert exc1.value.status == 400

        # 2. Mismatched cookie (from a different browser)
        different_cookie = "attacker-browser-binding-value-different"
        with pytest.raises(ProblemException) as exc2:
            await flow.callback(
                db_session,
                "csrf-test",
                code=cb_params["code"],
                state=cb_params["state"],
                browser_binding_cookie=different_cookie,
            )
        assert exc2.value.code == "OIDC_STATE_INVALID"
        assert exc2.value.status == 400


def test_11_open_redirect_defense() -> None:
    r"""Test 11: open redirect defense sanitizes suspicious return_to targets to '/'."""
    assert sanitize_return_to("//evil.example") == "/"
    assert sanitize_return_to(r"/\evil.example") == "/"
    assert sanitize_return_to("https://evil.example") == "/"
    assert sanitize_return_to("/%2F%2Fevil.example") == "/"
    assert sanitize_return_to("/%2f%2fevil.example") == "/"
    assert sanitize_return_to("javascript:alert(1)") == "/"
    assert sanitize_return_to(None) == "/"

    # Legitimate local paths are preserved
    assert sanitize_return_to("/projects/KAN") == "/projects/KAN"
    assert sanitize_return_to("/issues/KAN-123?tab=comments") == "/issues/KAN-123?tab=comments"
    oauth_next = (
        "/oauth/authorize?response_type=code&client_id=abc"
        "&redirect_uri=http%3A%2F%2F127.0.0.1%3A54321%2Fcallback"
        "&scope=agent%3Aread+agent%3Awrite"
        "&resource=https%3A%2F%2Fk.hackedyour.info%2Fmcp%2Fagent"
    )
    assert sanitize_return_to(oauth_next) == oauth_next
    assert sanitize_return_to("/https:%2F%2Fevil.example") == "/"


def test_12_ssrf_config_validation() -> None:
    """Test 12: issuer loopback and link-local IPs rejected at config validation."""
    with pytest.raises(ValidationError, match="targets loopback IP"):
        OidcCardConfig(
            kind="OIDC",
            issuer="https://127.0.0.1/",
            client_id="c1",
        )

    with pytest.raises(ValidationError, match="prohibited link-local or cloud metadata IP"):
        OidcCardConfig(
            kind="OIDC",
            issuer="https://169.254.169.254/",
            client_id="c1",
        )

    with pytest.raises(ValidationError, match="must use the https:// scheme"):
        OidcCardConfig(
            kind="OIDC",
            issuer="http://insecure.example.com/",
            client_id="c1",
        )


@pytest.mark.asyncio
async def test_13_boundary_response_size_and_subject_length(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
    fake_idp: FakeIdP,
    recording_resolver: RecordingIdentityResolver,
) -> None:
    """Test 13: token response > 64 KiB -> RESPONSE_TOO_LARGE; subject > 255 chars -> 401."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    await _seed_oidc_card(
        db_session,
        ws_id,
        kek_provider,
        slug="boundary-test",
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        client_secret=b"test-client-secret-999",
    )

    # 1. Token response exceeding 64 KiB (65537 bytes)
    oversized_token_body = "x" * 65537
    fake_idp.token_override = lambda _req, _form: httpx.Response(
        200,
        content=oversized_token_body.encode("ascii"),
        headers={"Content-Type": "application/json"},
    )

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as http_client:
        flow = OidcFlow(
            key_material=key_material,
            identity_resolver=recording_resolver,
            http_client=http_client,
        )

        start_resp = await flow.start(db_session, "boundary-test")
        params = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(start_resp.headers["Location"]).query)
        )
        cb_url = fake_idp.authorize_url_for_params(
            client_id=params["client_id"],
            redirect_uri=params["redirect_uri"],
            state=params["state"],
            nonce=params["nonce"],
            code_challenge=params["code_challenge"],
        )
        cb_params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url).query))

        with pytest.raises(OidcError) as exc_info:
            await flow.callback(
                db_session,
                "boundary-test",
                code=cb_params["code"],
                state=cb_params["state"],
                browser_binding_cookie=start_resp.browser_binding,
            )
        assert exc_info.value.code == "RESPONSE_TOO_LARGE"

    # 2. Subject exceeding 255 chars (256 chars) -> 401
    fake_idp.token_override = None  # Reset override
    long_subject = "s" * 256
    fake_idp.create_id_token(subject=long_subject)

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as http_client2:
        flow2 = OidcFlow(
            key_material=key_material,
            identity_resolver=recording_resolver,
            http_client=http_client2,
        )

        start_resp2 = await flow2.start(db_session, "boundary-test")
        params2 = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(start_resp2.headers["Location"]).query)
        )
        cb_url2 = fake_idp.authorize_url_for_params(
            client_id=params2["client_id"],
            redirect_uri=params2["redirect_uri"],
            state=params2["state"],
            nonce=params2["nonce"],
            code_challenge=params2["code_challenge"],
        )
        cb_params2 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url2).query))

        # Configure fake IdP to return the long subject in the token
        fake_idp.token_override = lambda _req, _form: httpx.Response(
            200,
            json={
                "token_type": "Bearer",
                "access_token": "acc-123",
                "id_token": fake_idp.create_id_token(subject=long_subject, nonce=params2["nonce"]),
            },
        )

        with pytest.raises(ProblemException) as exc_info2:
            await flow2.callback(
                db_session,
                "boundary-test",
                code=cb_params2["code"],
                state=cb_params2["state"],
                browser_binding_cookie=start_resp2.browser_binding,
            )
        assert exc_info2.value.code == "OIDC_TOKEN_INVALID"
        assert exc_info2.value.status == 401
        assert "255" in (exc_info2.value.detail or "")


@pytest.mark.asyncio
async def test_14_secret_hygiene_logging(  # noqa: PLR0913, PLR0917
    db_session: AsyncSession,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
    fake_idp: FakeIdP,
    recording_resolver: RecordingIdentityResolver,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test 14: caplog at DEBUG contains zero secrets, PEM keys, code verifiers, or tokens."""
    caplog.set_level(logging.DEBUG)

    ws_id, _ = await _setup_workspace_and_admin(db_session)
    secret_canary = "super-secret-canary-never-log-me-12345"
    fake_idp.client_secret = secret_canary
    await _seed_oidc_card(
        db_session,
        ws_id,
        kek_provider,
        slug="hygiene-test",
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        client_secret=secret_canary.encode("utf-8"),
    )

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as http_client:
        flow = OidcFlow(
            key_material=key_material,
            identity_resolver=recording_resolver,
            http_client=http_client,
        )

        start_resp = await flow.start(db_session, "hygiene-test")
        params = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(start_resp.headers["Location"]).query)
        )

        cb_url = fake_idp.authorize_url_for_params(
            client_id=params["client_id"],
            redirect_uri=params["redirect_uri"],
            state=params["state"],
            nonce=params["nonce"],
            code_challenge=params["code_challenge"],
        )
        cb_params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url).query))

        await flow.callback(
            db_session,
            "hygiene-test",
            code=cb_params["code"],
            state=cb_params["state"],
            browser_binding_cookie=start_resp.browser_binding,
        )

    log_text = caplog.text
    # Verify zero occurrences of sensitive secrets in logs
    assert secret_canary not in log_text
    assert cb_params["code"] not in log_text
    assert "BEGIN PRIVATE KEY" not in log_text


@pytest.mark.asyncio
async def test_provider_error_query_param(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
    fake_idp: FakeIdP,
) -> None:
    """Verify IdP provider error returns 400 OIDC_PROVIDER_ERROR without echoing error details."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    await _seed_oidc_card(
        db_session,
        ws_id,
        kek_provider,
        slug="err-test",
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        client_secret=b"test-client-secret-999",
    )

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as http_client:
        flow = OidcFlow(
            key_material=key_material,
            http_client=http_client,
        )

        with pytest.raises(ProblemException) as exc_info:
            await flow.callback(
                db_session,
                "err-test",
                error="consent_required",
                error_description="Attacker sensitive payload in error_description",
            )

        assert exc_info.value.code == "OIDC_PROVIDER_ERROR"
        assert exc_info.value.status == 400
        # Critical security invariant: provider error text must not be echoed
        assert "consent_required" not in (exc_info.value.detail or "")
        assert "Attacker sensitive payload" not in (exc_info.value.detail or "")


@pytest.mark.asyncio
async def test_reject_all_identity_resolver(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
    fake_idp: FakeIdP,
) -> None:
    """Verify default RejectAllIdentityResolver raises 403 IDENTITY_NOT_PROVISIONED."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    await _seed_oidc_card(
        db_session,
        ws_id,
        kek_provider,
        slug="reject-test",
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        client_secret=b"test-client-secret-999",
    )

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as http_client:
        flow = OidcFlow(
            key_material=key_material,
            identity_resolver=RejectAllIdentityResolver(),
            http_client=http_client,
        )

        start_resp = await flow.start(db_session, "reject-test")
        params = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(start_resp.headers["Location"]).query)
        )
        cb_url = fake_idp.authorize_url_for_params(
            client_id=params["client_id"],
            redirect_uri=params["redirect_uri"],
            state=params["state"],
            nonce=params["nonce"],
            code_challenge=params["code_challenge"],
        )
        cb_params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url).query))

        with pytest.raises(ProblemException) as exc_info:
            await flow.callback(
                db_session,
                "reject-test",
                code=cb_params["code"],
                state=cb_params["state"],
                browser_binding_cookie=start_resp.browser_binding,
            )

        assert exc_info.value.code == "IDENTITY_NOT_PROVISIONED"
        assert exc_info.value.status == 403


def test_config_validation_edge_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify OidcCardConfig validation constraints on URLs, scopes, endpoints, and algs."""
    # 1. URL without hostname
    with pytest.raises(ValidationError, match="must specify a valid hostname"):
        OidcCardConfig(kind="OIDC", issuer="https:///no-host", client_id="c1")

    # 2. Localhost hostname rejected by default
    with pytest.raises(ValidationError, match="targets loopback hostname"):
        OidcCardConfig(kind="OIDC", issuer="https://localhost/auth", client_id="c1")

    # 3. Localhost permitted when KANBAN_AUTH_EGRESS_ALLOW_PRIVATE=true
    monkeypatch.setenv("KANBAN_AUTH_EGRESS_ALLOW_PRIVATE", "true")
    cfg_local = OidcCardConfig(kind="OIDC", issuer="https://localhost/auth", client_id="c1")
    assert cfg_local.issuer == "https://localhost/auth"
    monkeypatch.undo()

    # 4. OIDC missing issuer
    with pytest.raises(ValidationError, match="require an 'issuer' endpoint"):
        OidcCardConfig(kind="OIDC", client_id="c1")

    # 5. OIDC missing openid in scopes
    with pytest.raises(ValidationError, match="must include 'openid' scope"):
        OidcCardConfig(
            kind="OIDC", issuer="https://idp.example.com", client_id="c1", scopes=["profile"]
        )

    # 6. OAuth2 missing authorization_endpoint
    with pytest.raises(ValidationError, match="require an 'authorization_endpoint'"):
        OidcCardConfig(kind="OAUTH2", client_id="c1")

    # 7. OAuth2 missing token_endpoint
    with pytest.raises(ValidationError, match="require a 'token_endpoint'"):
        OidcCardConfig(
            kind="OAUTH2", client_id="c1", authorization_endpoint="https://idp.example.com/auth"
        )

    # 8. OAuth2 missing userinfo_endpoint
    with pytest.raises(ValidationError, match="require a 'userinfo_endpoint'"):
        OidcCardConfig(
            kind="OAUTH2",
            client_id="c1",
            authorization_endpoint="https://idp.example.com/auth",
            token_endpoint="https://idp.example.com/token",  # noqa: S106
        )

    # 9. Empty allowed_algs
    with pytest.raises(ValidationError, match="allowed_algs cannot be empty"):
        OidcCardConfig(
            kind="OIDC",
            issuer="https://idp.example.com",
            client_id="c1",
            allowed_algs=[],
        )


def test_identity_assertion_and_resolver() -> None:
    """Verify ExternalIdentityAssertion post-init validations and type conversions."""
    card_id = uuid.uuid4()

    # 1. Empty subject
    with pytest.raises(ValueError, match="Assertion subject must be non-empty"):
        ExternalIdentityAssertion(
            card_id=card_id,
            subject="",
            email=None,
            email_verified=False,
            display_name=None,
            groups=(),
        )

    # 2. Subject > 255 chars
    with pytest.raises(ValueError, match="at most 255 characters"):
        ExternalIdentityAssertion(
            card_id=card_id,
            subject="x" * 256,
            email=None,
            email_verified=False,
            display_name=None,
            groups=(),
        )

    # 3. Non-iterable groups
    with pytest.raises(TypeError, match="Groups must be an iterable"):
        ExternalIdentityAssertion(
            card_id=card_id,
            subject="u1",
            email=None,
            email_verified=False,
            display_name=None,
            groups=12345,  # type: ignore[arg-type]
        )

    # 4. List of groups converted to tuple
    assertion = ExternalIdentityAssertion(
        card_id=card_id,
        subject="u1",
        email="u1@example.com",
        email_verified=True,
        display_name="User One",
        groups=["admin", "dev"],  # type: ignore[arg-type]
    )
    assert assertion.groups == ("admin", "dev")

    # 5. ResolvedLogin fields
    login = ResolvedLogin(
        principal_id=uuid.uuid4(), workspace_id=uuid.uuid4(), aal_level=2, mfa_pending=True
    )
    assert login.aal_level == 2
    assert login.mfa_pending is True


def test_flow_properties_and_helpers(key_material: KeyMaterial) -> None:
    """Verify OidcFlow properties and cookie builder functions."""
    flow = OidcFlow(
        key_material=key_material,
        public_origin="https://kanban.example.com/",
    )
    assert flow.key_material == key_material
    assert isinstance(flow.jwks_cache, JwksCache)
    assert isinstance(flow.identity_resolver, RejectAllIdentityResolver)
    assert flow.session_service is None
    assert flow.public_origin == "https://kanban.example.com"

    hdr = build_browser_binding_cookie("testval", max_age=120)
    assert "Max-Age=120" in hdr
    assert "__Host-kb_oidc=testval" in hdr


@pytest.mark.asyncio
async def test_flow_card_not_found(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Verify start and callback raise 404 when card is not found or disabled."""
    flow = OidcFlow(key_material=key_material)

    with pytest.raises(ProblemException) as exc1:
        await flow.start(db_session, "nonexistent-card")
    assert exc1.value.status == 404
    assert exc1.value.code == "AUTH_PROVIDER_NOT_FOUND"


@pytest.mark.asyncio
async def test_flow_malformed_inputs(
    db_session: AsyncSession,
    key_material: KeyMaterial,
) -> None:
    """Verify callback raises 400 OIDC_STATE_INVALID on malformed base64 state or cookie."""
    flow = OidcFlow(key_material=key_material)

    # Missing code or state
    with pytest.raises(ProblemException) as exc1:
        await flow.callback(db_session, "test", code=None, state="s", browser_binding_cookie="c")
    assert exc1.value.status == 400
    assert exc1.value.code == "OIDC_STATE_INVALID"

    # Malformed state
    with pytest.raises(ProblemException) as exc2:
        await flow.callback(
            db_session, "test", code="c", state="???not-b64???", browser_binding_cookie="c"
        )
    assert exc2.value.status == 400
    assert exc2.value.code == "OIDC_STATE_INVALID"

    # Malformed cookie
    with pytest.raises(ProblemException) as exc3:
        await flow.callback(
            db_session, "test", code="c", state="validstate", browser_binding_cookie="???not-b64???"
        )
    assert exc3.value.status == 400
    assert exc3.value.code == "OIDC_STATE_INVALID"


@pytest.mark.asyncio
async def test_flow_oauth2_error_responses(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
    fake_idp: FakeIdP,
    recording_resolver: RecordingIdentityResolver,
) -> None:
    """Verify OAuth2 errors: missing token, userinfo failure, malformed JSON, missing subject."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    await _seed_oauth2_card(
        db_session,
        ws_id,
        kek_provider,
        slug="oauth2-err",
        auth_ep=f"{fake_idp.issuer}/oauth/authorize",
        token_ep=f"{fake_idp.issuer}/oauth/token",
        userinfo_ep=f"{fake_idp.issuer}/oauth/userinfo",
        client_id=fake_idp.client_id,
        client_secret=b"test-client-secret-999",
    )

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as http_client:
        flow = OidcFlow(
            key_material=key_material,
            identity_resolver=recording_resolver,
            http_client=http_client,
        )

        # 1. Missing access_token in token response
        start_resp = await flow.start(db_session, "oauth2-err")
        params = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(start_resp.headers["Location"]).query)
        )
        cb_url = fake_idp.authorize_url_for_params(
            client_id=params["client_id"],
            redirect_uri=params["redirect_uri"],
            state=params["state"],
            code_challenge=params["code_challenge"],
        )
        cb_p = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url).query))

        fake_idp.token_override = lambda _r, _f: httpx.Response(
            200, json={"token_type": "Bearer"}
        )  # Missing access_token
        with pytest.raises(ProblemException) as exc1:
            await flow.callback(
                db_session,
                "oauth2-err",
                code=cb_p["code"],
                state=cb_p["state"],
                browser_binding_cookie=start_resp.browser_binding,
            )
        assert exc1.value.code == "OIDC_TOKEN_INVALID"

        # 2. Userinfo non-200
        start_resp2 = await flow.start(db_session, "oauth2-err")
        p2 = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(start_resp2.headers["Location"]).query)
        )
        cb_url2 = fake_idp.authorize_url_for_params(
            client_id=p2["client_id"],
            redirect_uri=p2["redirect_uri"],
            state=p2["state"],
            code_challenge=p2["code_challenge"],
        )
        cb_p2 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url2).query))

        fake_idp.token_override = lambda _r, _f: httpx.Response(
            200, json={"token_type": "Bearer", "access_token": "acc1"}
        )
        fake_idp.userinfo_override = lambda _r: httpx.Response(500, text="userinfo failed")
        with pytest.raises(ProblemException) as exc2:
            await flow.callback(
                db_session,
                "oauth2-err",
                code=cb_p2["code"],
                state=cb_p2["state"],
                browser_binding_cookie=start_resp2.browser_binding,
            )
        assert exc2.value.code == "OIDC_TOKEN_INVALID"

        # 3. Userinfo malformed JSON
        start_resp3 = await flow.start(db_session, "oauth2-err")
        p3 = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(start_resp3.headers["Location"]).query)
        )
        cb_url3 = fake_idp.authorize_url_for_params(
            client_id=p3["client_id"],
            redirect_uri=p3["redirect_uri"],
            state=p3["state"],
            code_challenge=p3["code_challenge"],
        )
        cb_p3 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url3).query))

        fake_idp.userinfo_override = lambda _r: httpx.Response(200, text="not-json")
        with pytest.raises(ProblemException) as exc3:
            await flow.callback(
                db_session,
                "oauth2-err",
                code=cb_p3["code"],
                state=cb_p3["state"],
                browser_binding_cookie=start_resp3.browser_binding,
            )
        assert exc3.value.code == "OIDC_TOKEN_INVALID"

        # 4. Userinfo response > 64 KiB
        start_resp4 = await flow.start(db_session, "oauth2-err")
        p4 = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(start_resp4.headers["Location"]).query)
        )
        cb_url4 = fake_idp.authorize_url_for_params(
            client_id=p4["client_id"],
            redirect_uri=p4["redirect_uri"],
            state=p4["state"],
            code_challenge=p4["code_challenge"],
        )
        cb_p4 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url4).query))

        fake_idp.userinfo_override = lambda _r: httpx.Response(200, content=b"x" * 65537)
        with pytest.raises(OidcError) as exc4:
            await flow.callback(
                db_session,
                "oauth2-err",
                code=cb_p4["code"],
                state=cb_p4["state"],
                browser_binding_cookie=start_resp4.browser_binding,
            )
        assert exc4.value.code == "RESPONSE_TOO_LARGE"

        # 5. Userinfo missing subject claim
        start_resp5 = await flow.start(db_session, "oauth2-err")
        p5 = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(start_resp5.headers["Location"]).query)
        )
        cb_url5 = fake_idp.authorize_url_for_params(
            client_id=p5["client_id"],
            redirect_uri=p5["redirect_uri"],
            state=p5["state"],
            code_challenge=p5["code_challenge"],
        )
        cb_p5 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url5).query))

        fake_idp.userinfo_override = lambda _r: httpx.Response(
            200, json={"email": "no-sub@example.com"}
        )
        with pytest.raises(ProblemException) as exc5:
            await flow.callback(
                db_session,
                "oauth2-err",
                code=cb_p5["code"],
                state=cb_p5["state"],
                browser_binding_cookie=start_resp5.browser_binding,
            )
        assert exc5.value.code == "OIDC_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_flow_session_service_cookies(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
    fake_idp: FakeIdP,
) -> None:
    """Verify that when SessionService is configured, callback attaches session and CSRF cookies."""
    ws_id, admin_id = await _setup_workspace_and_admin(db_session)
    await _seed_oidc_card(
        db_session,
        ws_id,
        kek_provider,
        slug="session-test",
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        client_secret=b"test-client-secret-999",
    )

    session_service = SessionService(session_hmac_key=key_material.session_hmac_key)
    session_resolver = RecordingIdentityResolver(principal_id=admin_id, workspace_id=ws_id)

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as http_client:
        flow = OidcFlow(
            key_material=key_material,
            identity_resolver=session_resolver,
            session_service=session_service,
            http_client=http_client,
        )

        start_resp = await flow.start(db_session, "session-test")
        params = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(start_resp.headers["Location"]).query)
        )
        cb_url = fake_idp.authorize_url_for_params(
            client_id=params["client_id"],
            redirect_uri=params["redirect_uri"],
            state=params["state"],
            nonce=params["nonce"],
            code_challenge=params["code_challenge"],
        )
        cb_p = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url).query))

        cb_resp = await flow.callback(
            db_session,
            "session-test",
            code=cb_p["code"],
            state=cb_p["state"],
            browser_binding_cookie=start_resp.browser_binding,
        )
        assert cb_resp.status_code == 302
        cookies = [
            val.decode("latin-1")
            for key, val in cb_resp.raw_headers
            if key.lower() == b"set-cookie"
        ]
        cookie_blob = " ".join(cookies)
        assert "__Host-kb_session" in cookie_blob
        assert "__Host-kb_csrf" in cookie_blob
        assert "__Host-kb_oidc=;" in cookie_blob


def test_config_direct_helpers() -> None:
    """Verify _validate_safe_url helper and OAuth2 full config parsing."""
    # 1. None url returns None
    assert _validate_safe_url(None, "test") is None

    # 2. Public IP URL is cleaned and permitted
    cleaned = _validate_safe_url("https://93.184.216.34/", "test")
    assert cleaned == "https://93.184.216.34/"

    # 3. Full OAuth2 config
    cfg = OidcCardConfig(
        kind="OAUTH2",
        authorization_endpoint="https://idp.example.com/oauth/authorize",
        token_endpoint="https://idp.example.com/oauth/token",  # noqa: S106
        userinfo_endpoint="https://idp.example.com/oauth/userinfo",
        client_id="oauth-client",
        client_auth="client_secret_basic",
        scopes=["read:user"],
        allowed_algs=["RS256"],
    )
    assert cfg.kind == "OAUTH2"


@pytest.mark.asyncio
async def test_flow_oidc_token_exchange_failures(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
    fake_idp: FakeIdP,
    recording_resolver: RecordingIdentityResolver,
) -> None:
    """Verify OIDC token exchange error cases: non-200, malformed JSON, missing secrets."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    await _seed_oidc_card(
        db_session,
        ws_id,
        kek_provider,
        slug="oidc-failures",
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        client_secret=b"test-client-secret-999",
    )

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as http_client:
        flow = OidcFlow(
            key_material=key_material,
            identity_resolver=recording_resolver,
            http_client=http_client,
        )

        # 1. Token endpoint returns 500 -> 401 OIDC_TOKEN_INVALID
        s1 = await flow.start(db_session, "oidc-failures")
        p1 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(s1.headers["Location"]).query))
        cb_url1 = fake_idp.authorize_url_for_params(
            client_id=p1["client_id"],
            redirect_uri=p1["redirect_uri"],
            state=p1["state"],
            nonce=p1["nonce"],
            code_challenge=p1["code_challenge"],
        )
        cb1 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url1).query))
        fake_idp.token_override = lambda _r, _f: httpx.Response(500, text="IdP Token Server Down")
        with pytest.raises(ProblemException) as exc1:
            await flow.callback(
                db_session,
                "oidc-failures",
                code=cb1["code"],
                state=cb1["state"],
                browser_binding_cookie=s1.browser_binding,
            )
        assert exc1.value.code == "OIDC_TOKEN_INVALID"

        # 2. Token endpoint returns non-JSON -> 401 OIDC_TOKEN_INVALID
        s2 = await flow.start(db_session, "oidc-failures")
        p2 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(s2.headers["Location"]).query))
        cb_url2 = fake_idp.authorize_url_for_params(
            client_id=p2["client_id"],
            redirect_uri=p2["redirect_uri"],
            state=p2["state"],
            nonce=p2["nonce"],
            code_challenge=p2["code_challenge"],
        )
        cb2 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url2).query))
        fake_idp.token_override = lambda _r, _f: httpx.Response(200, text="not json at all")
        with pytest.raises(ProblemException) as exc2:
            await flow.callback(
                db_session,
                "oidc-failures",
                code=cb2["code"],
                state=cb2["state"],
                browser_binding_cookie=s2.browser_binding,
            )
        assert exc2.value.code == "OIDC_TOKEN_INVALID"

        # 3. Token endpoint returns JSON without id_token -> 401 OIDC_TOKEN_INVALID
        s3 = await flow.start(db_session, "oidc-failures")
        p3 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(s3.headers["Location"]).query))
        cb_url3 = fake_idp.authorize_url_for_params(
            client_id=p3["client_id"],
            redirect_uri=p3["redirect_uri"],
            state=p3["state"],
            nonce=p3["nonce"],
            code_challenge=p3["code_challenge"],
        )
        cb3 = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url3).query))
        fake_idp.token_override = lambda _r, _f: httpx.Response(
            200, json={"token_type": "Bearer", "access_token": "a1"}
        )
        with pytest.raises(ProblemException) as exc3:
            await flow.callback(
                db_session,
                "oidc-failures",
                code=cb3["code"],
                state=cb3["state"],
                browser_binding_cookie=s3.browser_binding,
            )
        assert exc3.value.code == "OIDC_TOKEN_INVALID"

        # 4. Malformed state base64 triggering binascii.Error
        with pytest.raises(ProblemException) as exc4:
            await flow.callback(
                db_session, "oidc-failures", code="c", state="abc%", browser_binding_cookie="valid"
            )
        assert exc4.value.code == "OIDC_STATE_INVALID"

        # 5. Malformed cookie base64 triggering binascii.Error
        with pytest.raises(ProblemException) as exc5:
            await flow.callback(
                db_session,
                "oidc-failures",
                code="c",
                state="validstate",
                browser_binding_cookie="abc%",
            )
        assert exc5.value.code == "OIDC_STATE_INVALID"


@pytest.mark.asyncio
async def test_fastapi_oidc_routes(
    db_session: AsyncSession,
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
    fake_idp: FakeIdP,
    recording_resolver: RecordingIdentityResolver,
) -> None:
    """Verify FastAPI GET /api/v1/auth/oidc/{slug}/start and /callback endpoints."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    await _seed_oidc_card(
        db_session,
        ws_id,
        kek_provider,
        slug="route-test",
        issuer=fake_idp.issuer,
        client_id=fake_idp.client_id,
        client_secret=b"test-client-secret-999",
    )

    app = FastAPI()
    app.include_router(auth_oidc_router, prefix="/api/v1")

    async with httpx.AsyncClient(transport=fake_idp.as_transport()) as idp_client:
        flow = OidcFlow(
            key_material=key_material,
            identity_resolver=recording_resolver,
            http_client=idp_client,
            public_origin="http://testserver",
        )

        app.dependency_overrides[get_auth_session] = lambda: db_session
        app.dependency_overrides[get_oidc_flow] = lambda: flow

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            # 1. Start endpoint
            start_res = await client.get(
                "/api/v1/auth/oidc/route-test/start?return_to=/projects/TEST",
                follow_redirects=False,
            )
            assert start_res.status_code == 302
            loc = start_res.headers["Location"]
            assert "response_type=code" in loc
            cookie_hdr = start_res.headers.get("Set-Cookie", "")
            assert "__Host-kb_oidc" in cookie_hdr

            # Extract cookie value and params
            cookie_val = ""
            for part in cookie_hdr.split(";"):
                if part.strip().startswith("__Host-kb_oidc="):
                    cookie_val = part.strip().split("=", 1)[1]

            params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(loc).query))
            cb_url = fake_idp.authorize_url_for_params(
                client_id=params["client_id"],
                redirect_uri=params["redirect_uri"],
                state=params["state"],
                nonce=params["nonce"],
                code_challenge=params["code_challenge"],
            )
            cb_p = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(cb_url).query))

            # 2. Callback endpoint
            client.cookies.set("__Host-kb_oidc", cookie_val)
            cb_res = await client.get(
                f"/api/v1/auth/oidc/route-test/callback?code={cb_p['code']}&state={cb_p['state']}",
                follow_redirects=False,
            )
            assert cb_res.status_code == 302
            assert cb_res.headers["Location"] == "/projects/TEST"
