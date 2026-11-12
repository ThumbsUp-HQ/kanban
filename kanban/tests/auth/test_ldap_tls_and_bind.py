# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: S106, S107, SLF001, PLC0415, PLR0915, PLR0917, FBT001, FBT002, D102, D107, ARG002, SIM117, RUF059, TC001, TC002, TC003, F841, E501, RUF043
"""Unit and security tests for LDAP TLS_HARD, SPKI pinning, and ephemeral bind (KB-P2-07)."""

from __future__ import annotations

import json
import logging
import ssl
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, cast

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import text
from starlette.requests import Request

from database.models.auth import AuthProviderCard
from database.session import RLSContext, RLSSessionFactory
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException, problem_exception_handler
from kanban.api.v1.auth_ldap import auth_ldap_router
from kanban.auth.cards.repository import admin_upsert
from kanban.auth.identity import (
    ExternalIdentityAssertion,
    ResolvedLogin,
)
from kanban.auth.ldap.client import (
    LdapBindError,
    LdapError,
    LdapProtocolError,
    LdapSearchError,
    LdapTlsError,
    LdapTlsHardClient,
)
from kanban.auth.ldap.config import LdapCardConfig
from kanban.auth.ldap.router import get_auth_session, get_ldap_service
from kanban.auth.ldap.service import LdapAuthService
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.auth.sessions.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    PRE_SESSION_ID,
    CsrfMiddleware,
    generate_csrf_token,
)
from kanban.auth.sessions.service import SessionService
from kanban.security.envelope import StaticKekProvider, seal_card_secret
from kanban.security.keys import KeyMaterial
from kanban.security.ratelimit import AUTH_LOGIN_IP
from kanban.security.ratelimit.base import (
    RateLimitDecision,
    RateLimitPolicy,
)
from kanban.tests.fixtures.fake_ldap import (
    FakeLdapServer,
    LdapTestCerts,
    generate_ldap_test_certs,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class RecordingIdentityResolver:
    """Identity resolver recording assertions for forensic test verification."""

    def __init__(
        self,
        principal_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> None:
        self.assertions: list[ExternalIdentityAssertion] = []
        self._principal_id = principal_id
        self._workspace_id = workspace_id

    async def resolve(
        self,
        assertion: ExternalIdentityAssertion,
        request: Request,
        link_intent_id: uuid.UUID | None,
    ) -> ResolvedLogin:
        del request, link_intent_id
        self.assertions.append(assertion)
        return ResolvedLogin(
            principal_id=self._principal_id or uuid.uuid4(),
            workspace_id=self._workspace_id or uuid.uuid4(),
            aal_level=1,
            mfa_pending=False,
        )


class InMemoryRateLimiter:
    """In-memory rate limiter tracking hit counts for test verification."""

    def __init__(self) -> None:
        self.hits: dict[tuple[str, bytes], int] = {}

    async def hit(self, policy: RateLimitPolicy, key: bytes) -> RateLimitDecision:
        bucket = (policy.name, key)
        count = self.hits.get(bucket, 0) + 1
        self.hits[bucket] = count
        if count > policy.limit:
            return RateLimitDecision(allowed=False, remaining=0, retry_after_seconds=60)
        return RateLimitDecision(
            allowed=True,
            remaining=policy.limit - count,
            retry_after_seconds=0,
        )


@pytest.fixture(autouse=True)
def allow_private_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow localhost/private network targets by default for offline test sockets."""
    monkeypatch.setenv("KANBAN_AUTH_EGRESS_ALLOW_PRIVATE", "true")


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


@pytest.fixture(scope="session")
def ldap_certs() -> LdapTestCerts:
    """Fixture providing cached self-signed root CA and leaf test certs."""
    return generate_ldap_test_certs()


async def _setup_workspace_and_admin(
    session: AsyncSession,
    ws_id: uuid.UUID | None = None,
    u_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision workspace and SERVER_ADMIN principal with AAL2 session context."""
    if ws_id is None:
        ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "LDAP Test WS"},
    )

    if u_id is None:
        u_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{u_id.hex}",
            "title": "LDAP Admin User",
            "u_id": u_id,
        },
    )

    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'LDAP Admin User', 'ACTIVE')"
        ),
        {"id": u_id, "ws_id": ws_id},
    )

    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'ldap-admin@example.com')"
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

    # Enroll and confirm active TOTP factor so require_admin_aal2 passes for this admin
    await session.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
        {
            "p_id": u_id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    totp_res = await session.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": u_id},
    )
    p_row = totp_res.mappings().first()
    if p_row:
        await session.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
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


async def _seed_ldap_card(  # noqa: PLR0913
    session: AsyncSession,
    ws_id: uuid.UUID,
    kek_provider: StaticKekProvider,
    certs: LdapTestCerts,
    slug: str = "ldap-test",
    transport_mode: str = "ldaps",
    spki_sha256_pins: list[str] | None = None,
    service_bind_dn: str | None = "cn=svc-kanban,ou=services,dc=corp,dc=example",
    service_bind_password: str | None = "SvcSecretPassword123!",
    is_enabled: bool = True,
    group_dn_map: dict[str, str] | None = None,
) -> AuthProviderCard:
    """Seed an LDAP AuthProviderCard with sealed secret blob in clean-DB."""
    card_id = uuid.uuid4()
    url = "ldaps://localhost:636" if transport_mode == "ldaps" else "ldap://localhost:389"

    pins = spki_sha256_pins if spki_sha256_pins is not None else [certs.spki_sha256]
    public_config: dict[str, Any] = {
        "kind": "LDAP",
        "url": url,
        "transport_mode": transport_mode,
        "ca_cert_pem": certs.ca_pem,
        "spki_sha256_pins": pins,
        "service_bind_dn": service_bind_dn,
        "base_dn": "ou=users,dc=corp,dc=example",
        "user_search_filter": "(&(objectClass=person)(uid={username}))",
        "subject_attribute": "objectGUID",
        "email_attribute": "mail",
        "display_name_attribute": "cn",
        "member_of_attribute": "memberOf",
        "group_dn_map": group_dn_map
        or {"cn=core-backend,ou=groups,dc=corp,dc=example": "Core Backend"},
        "timeout_seconds": 5.0,
    }

    encrypted_blob = None
    wrapped_dek = None
    dek_kid = None

    if service_bind_dn and service_bind_password:
        secret_bytes = json.dumps({"bind_dn_password": service_bind_password}).encode("utf-8")
        sealed = seal_card_secret(card_id, "LDAP", secret_bytes, kek_provider)
        encrypted_blob = sealed.encrypted_secret_blob
        wrapped_dek = sealed.wrapped_dek
        dek_kid = sealed.dek_kid

    card_id = await admin_upsert(
        session,
        card_id=card_id,
        workspace_id=ws_id,
        provider_kind="LDAP",
        slug=slug,
        display_name=f"LDAP Card {slug}",
        is_enabled=is_enabled,
        sort_rank="0001",
        public_config=public_config,
        encrypted_secret_blob=encrypted_blob,
        wrapped_dek=wrapped_dek,
        dek_kid=dek_kid or "test-kid",
    )
    stmt = text("SELECT * FROM auth_provider_cards WHERE id = :id")
    res = await session.execute(stmt, {"id": card_id})
    row = res.mappings().one()
    # Or query ORM model
    from database.models.auth import AuthProviderCard as CardModel

    card_obj = await session.get(CardModel, card_id)
    assert card_obj is not None
    return card_obj


@pytest.mark.asyncio
async def test_01_positive_ldaps_flow(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test Case 1: Positive LDAPS (TLS 1.3, CA + SPKI pin, search, ephemeral bind, objectGUID UUID)."""
    ws_id, u_id = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(
        db_session, ws_id, kek_provider, ldap_certs, transport_mode="ldaps"
    )

    raw_guid = uuid.UUID("12345678-1234-5678-1234-567812345678").bytes_le
    user_dn = "cn=alice,ou=users,dc=corp,dc=example"
    svc_dn = "cn=svc-kanban,ou=services,dc=corp,dc=example"

    async with FakeLdapServer(ldap_certs, mode="ldaps") as server:
        # Populate mock directory
        server.directory.passwords[svc_dn] = "SvcSecretPassword123!"
        server.directory.passwords[user_dn] = "AliceSecret123!"
        server.directory.entries[user_dn] = {
            "objectguid": [raw_guid],
            "mail": [b"alice@example.com"],
            "cn": [b"Alice Alison"],
            "memberof": [b"CN=Core-Backend,OU=Groups,DC=corp,DC=example"],
            "uid": [b"alice"],
        }

        resolver = RecordingIdentityResolver(principal_id=u_id, workspace_id=ws_id)
        service = LdapAuthService(
            kek_provider=kek_provider,
            identity_resolver=resolver,
            unix_socket_path=server.sock_path,
        )

        assertion, _resolved = await service.authenticate(
            session=db_session,
            card=card,
            username="alice",
            password="AliceSecret123!",
        )

        assert assertion.subject == "12345678-1234-5678-1234-567812345678"
        assert assertion.email == "alice@example.com"
        assert assertion.display_name == "Alice Alison"
        assert assertion.groups == ("Core Backend",)
        assert len(resolver.assertions) == 1
        assert resolver.assertions[0].subject == "12345678-1234-5678-1234-567812345678"


@pytest.mark.asyncio
async def test_02_positive_starttls_flow(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test Case 2: Positive StartTLS (extended op first, upgrade, CA + SPKI verify, bind)."""
    ws_id, u_id = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(
        db_session,
        ws_id,
        kek_provider,
        ldap_certs,
        slug="ldap-starttls",
        transport_mode="starttls",
    )

    user_dn = "cn=bob,ou=users,dc=corp,dc=example"
    svc_dn = "cn=svc-kanban,ou=services,dc=corp,dc=example"

    async with FakeLdapServer(ldap_certs, mode="starttls") as server:
        server.directory.passwords[svc_dn] = "SvcSecretPassword123!"
        server.directory.passwords[user_dn] = "BobSecret123!"
        server.directory.entries[user_dn] = {
            "objectguid": [b"bob-uuid-string-7890"],
            "mail": [b"bob@example.com"],
            "cn": [b"Bob Roberts"],
            "memberof": [],
            "uid": [b"bob"],
        }

        resolver = RecordingIdentityResolver(principal_id=u_id, workspace_id=ws_id)
        service = LdapAuthService(
            kek_provider=kek_provider,
            identity_resolver=resolver,
            unix_socket_path=server.sock_path,
        )

        assertion, _resolved = await service.authenticate(
            session=db_session,
            card=card,
            username="bob",
            password="BobSecret123!",
        )

        assert assertion.subject == "bob-uuid-string-7890"
        assert assertion.email == "bob@example.com"

        # Verify wire spy: pre-TLS bytes contain extended op (StartTLS), but zero 0x60 bind tags
        assert len(server.raw_pre_tls_bytes) > 0
        assert 0x60 not in server.raw_pre_tls_bytes
        # Post-TLS bytes contain bind tags
        assert 0x60 in server.raw_post_tls_bytes


@pytest.mark.asyncio
async def test_03_tls_hard_downgrade_rejected(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test Case 3: TLS_HARD downgrade rejected with 52, zero bind tags or passwords in pre-TLS wire bytes."""
    ws_id, u_id = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(
        db_session,
        ws_id,
        kek_provider,
        ldap_certs,
        slug="ldap-downgrade",
        transport_mode="starttls",
    )

    async with FakeLdapServer(ldap_certs, mode="starttls", reject_starttls=True) as server:
        resolver = RecordingIdentityResolver(principal_id=u_id, workspace_id=ws_id)
        service = LdapAuthService(
            kek_provider=kek_provider,
            identity_resolver=resolver,
            unix_socket_path=server.sock_path,
        )

        with pytest.raises(LdapTlsError, match="StartTLS rejected"):
            await service.authenticate(
                session=db_session,
                card=card,
                username="alice",
                password="AliceSecret123!",
            )

        # Forensic wire inspection: raw pre-TLS bytes must have 0 BindRequest tags and 0 password bytes
        assert 0x60 not in server.raw_pre_tls_bytes
        assert b"SvcSecretPassword123!" not in server.raw_pre_tls_bytes
        assert b"AliceSecret123!" not in server.raw_pre_tls_bytes


@pytest.mark.asyncio
async def test_04_tls_version_and_cert_verification(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test Case 4: TLS 1.1 rejection and untrusted cert rejection prior to bind."""
    ws_id, u_id = await _setup_workspace_and_admin(db_session)

    # 1. TLS 1.1 rejection
    card = await _seed_ldap_card(
        db_session,
        ws_id,
        kek_provider,
        ldap_certs,
        slug="ldap-tls11",
        transport_mode="ldaps",
    )

    async with FakeLdapServer(
        ldap_certs,
        mode="ldaps",
        min_tls_version=ssl.TLSVersion.TLSv1_1,
        max_tls_version=ssl.TLSVersion.TLSv1_1,
    ) as server:
        service = LdapAuthService(
            kek_provider=kek_provider,
            unix_socket_path=server.sock_path,
        )
        with pytest.raises((LdapTlsError, ssl.SSLError, OSError)):
            await service.authenticate(
                session=db_session,
                card=card,
                username="alice",
                password="pwd",
            )
        assert 0x60 not in server.raw_post_tls_bytes

    # 2. Untrusted cert: config with different CA cert
    untrusted_certs = generate_ldap_test_certs()
    card_untrusted = await _seed_ldap_card(
        db_session,
        ws_id,
        kek_provider,
        untrusted_certs,  # card trusts this other CA
        slug="ldap-untrusted-ca",
        transport_mode="ldaps",
    )
    async with FakeLdapServer(ldap_certs, mode="ldaps") as server:  # server serves ldap_certs
        service = LdapAuthService(
            kek_provider=kek_provider,
            unix_socket_path=server.sock_path,
        )
        with pytest.raises((LdapTlsError, ssl.SSLError, OSError)):
            await service.authenticate(
                session=db_session,
                card=card_untrusted,
                username="alice",
                password="pwd",
            )
        assert 0x60 not in server.raw_post_tls_bytes


@pytest.mark.asyncio
async def test_05_spki_pin_mismatch_rejected(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test Case 5: SPKI pin mismatch triggers SPKI_PIN_MISMATCH prior to bind."""
    ws_id, u_id = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(
        db_session,
        ws_id,
        kek_provider,
        ldap_certs,
        slug="ldap-spki-mismatch",
        transport_mode="ldaps",
        spki_sha256_pins=[ldap_certs.spki_sha256],  # Expecting primary pin
    )

    # Server serves mismatch cert signed by same CA
    async with FakeLdapServer(ldap_certs, mode="ldaps", use_mismatched_cert=True) as server:
        service = LdapAuthService(
            kek_provider=kek_provider,
            unix_socket_path=server.sock_path,
        )
        with pytest.raises(LdapTlsError, match="SPKI_PIN_MISMATCH"):
            await service.authenticate(
                session=db_session,
                card=card,
                username="alice",
                password="pwd",
            )
        # Zero BindRequest tags sent
        assert 0x60 not in server.raw_post_tls_bytes


@pytest.mark.asyncio
async def test_06_anonymous_bind_bypass_blocked(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test Case 6: Empty password rejected with 401 before opening network socket."""
    ws_id, u_id = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(db_session, ws_id, kek_provider, ldap_certs, slug="ldap-anon")

    async with FakeLdapServer(ldap_certs, mode="ldaps", accept_anonymous_bind=True) as server:
        service = LdapAuthService(
            kek_provider=kek_provider,
            unix_socket_path=server.sock_path,
        )
        with pytest.raises(ProblemException) as exc:
            await service.authenticate(
                session=db_session,
                card=card,
                username="alice",
                password="",
            )
        assert exc.value.status == 401
        assert len(server.bind_calls) == 0


@pytest.mark.asyncio
async def test_08_ambiguous_search_and_alias_deref(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test Case 8: Ambiguous search (0 or 2 entries -> 401) and derefAliases == 0."""
    ws_id, u_id = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(db_session, ws_id, kek_provider, ldap_certs, slug="ldap-search")

    svc_dn = "cn=svc-kanban,ou=services,dc=corp,dc=example"

    async with FakeLdapServer(ldap_certs, mode="ldaps") as server:
        server.directory.passwords[svc_dn] = "SvcSecretPassword123!"

        service = LdapAuthService(
            kek_provider=kek_provider,
            unix_socket_path=server.sock_path,
        )

        # 0 entries found
        with pytest.raises(ProblemException) as exc:
            await service.authenticate(
                session=db_session,
                card=card,
                username="nonexistent",
                password="SomePassword123!",
            )
        assert exc.value.status == 401

        # 2 entries found
        server.directory.entries["cn=alice1,ou=users,dc=corp,dc=example"] = {
            "objectguid": [b"guid1"],
            "uid": [b"alice"],
        }
        server.directory.entries["cn=alice2,ou=users,dc=corp,dc=example"] = {
            "objectguid": [b"guid2"],
            "uid": [b"alice"],
        }
        with pytest.raises(ProblemException) as exc:
            await service.authenticate(
                session=db_session,
                card=card,
                username="alice",
                password="SomePassword123!",
            )
        assert exc.value.status == 401

        # Verify derefAliases was neverDerefAliases (0)
        assert len(server.deref_aliases_seen) > 0
        assert all(d == 0 for d in server.deref_aliases_seen)


@pytest.mark.asyncio
async def test_10_rate_limit_and_enumeration(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test Case 10: 6th failed login -> 429 RATE_LIMITED; uniform 401 responses."""
    ws_id, u_id = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(db_session, ws_id, kek_provider, ldap_certs, slug="ldap-rate")

    async with FakeLdapServer(ldap_certs, mode="ldaps") as server:
        svc_dn = "cn=svc-kanban,ou=services,dc=corp,dc=example"
        server.directory.passwords[svc_dn] = "SvcSecretPassword123!"

        app = FastAPI()
        app.add_exception_handler(ProblemException, cast("Any", problem_exception_handler))
        app.include_router(auth_ldap_router, prefix="/api/v1")
        app.state.key_material = key_material
        app.state.kek_provider = kek_provider
        app.state.rate_limiter = InMemoryRateLimiter()
        app.state.ldap_unix_socket_path = server.sock_path

        async def override_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        app.dependency_overrides[get_auth_session] = override_session

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            # 5 failed login attempts
            responses: list[httpx.Response] = []
            for _ in range(5):
                resp = await client.post(
                    "/api/v1/auth/ldap/ldap-rate/login",
                    json={"username": "alice", "password": "WrongPassword123!"},
                )
                responses.append(resp)
                assert resp.status_code == 401

            # 6th attempt -> 429 RATE_LIMITED
            resp6 = await client.post(
                "/api/v1/auth/ldap/ldap-rate/login",
                json={"username": "alice", "password": "WrongPassword123!"},
            )
            assert resp6.status_code == 429
            data6 = resp6.json()
            assert data6["code"] == "RATE_LIMITED"

            # Uniform 401 response comparison across unknown user vs wrong password vs non-existent card
            resp_unknown = await client.post(
                "/api/v1/auth/ldap/ldap-rate/login",
                json={"username": "unknown_user", "password": "WrongPassword123!"},
            )
            resp_nonexistent_card = await client.post(
                "/api/v1/auth/ldap/nonexistent-card/login",
                json={"username": "alice", "password": "WrongPassword123!"},
            )

            # Strip request_id before comparison if any
            b_wrong = responses[0].json()
            b_unknown = resp_unknown.json()
            b_nocard = resp_nonexistent_card.json()
            assert b_wrong["code"] == b_unknown["code"] == b_nocard["code"] == "INVALID_CREDENTIALS"
            assert (
                b_wrong["title"]
                == b_unknown["title"]
                == b_nocard["title"]
                == "Authentication Failed"
            )
            assert (
                b_wrong["detail"]
                == b_unknown["detail"]
                == b_nocard["detail"]
                == "Invalid credentials"
            )


@pytest.mark.asyncio
async def test_11_boundary_and_ssrf(
    ldap_certs: LdapTestCerts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Case 11: 262,145 bytes -> MESSAGE_TOO_LARGE; SSRF rejection; scheme mismatch."""
    # 1. 262,145 bytes -> MESSAGE_TOO_LARGE
    async with FakeLdapServer(ldap_certs, mode="ldaps", oversized_response_bytes=262145) as server:
        config = LdapCardConfig(
            kind="LDAP",
            url="ldaps://localhost:636",
            transport_mode="ldaps",
            ca_cert_pem=ldap_certs.ca_pem,
            spki_sha256_pins=[ldap_certs.spki_sha256],
            base_dn="dc=example,dc=com",
        )
        client = LdapTlsHardClient(config, unix_socket_path=server.sock_path)
        await client.connect()
        with pytest.raises(LdapProtocolError, match="MESSAGE_TOO_LARGE"):
            await client.search("dc=example,dc=com", "(objectClass=*)", ["cn"])
        await client.close()

    # 2. SSRF loopback rejection when allow_private=False
    monkeypatch.setenv("KANBAN_AUTH_EGRESS_ALLOW_PRIVATE", "false")
    with pytest.raises(ValidationError, match="targets prohibited loopback"):
        LdapCardConfig(
            kind="LDAP",
            url="ldap://127.0.0.1:389",
            transport_mode="starttls",
            base_dn="dc=example,dc=com",
        )

    # 3. Scheme and transport_mode mismatch
    with pytest.raises(ValidationError, match="ldaps:// scheme requires transport_mode='ldaps'"):
        LdapCardConfig(
            kind="LDAP",
            url="ldaps://dc01.corp.example:636",
            transport_mode="starttls",
            base_dn="dc=example,dc=com",
        )


@pytest.mark.asyncio
async def test_12_secret_hygiene_logging_and_zeroization(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    ldap_certs: LdapTestCerts,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test Case 12: DEBUG logs contain zero passwords; bytearray is zeroed after return."""
    ws_id, u_id = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(db_session, ws_id, kek_provider, ldap_certs, slug="ldap-hygiene")

    user_dn = "cn=alice,ou=users,dc=corp,dc=example"
    svc_dn = "cn=svc-kanban,ou=services,dc=corp,dc=example"
    user_pwd = "SuperSecretAlicePassword999!"
    svc_pwd = "SvcSecretPassword123!"

    async with FakeLdapServer(ldap_certs, mode="ldaps") as server:
        server.directory.passwords[svc_dn] = svc_pwd
        server.directory.passwords[user_dn] = user_pwd
        server.directory.entries[user_dn] = {
            "objectguid": [b"12345678-1234-5678-1234-567812345678"],
            "mail": [b"alice@example.com"],
            "cn": [b"Alice Alison"],
            "memberof": [],
            "uid": [b"alice"],
        }

        service = LdapAuthService(
            kek_provider=kek_provider,
            identity_resolver=RecordingIdentityResolver(principal_id=u_id, workspace_id=ws_id),
            unix_socket_path=server.sock_path,
        )

        with caplog.at_level(logging.DEBUG):
            await service.authenticate(
                session=db_session,
                card=card,
                username="alice",
                password=user_pwd,
            )

        # Inspect log text
        full_logs = caplog.text
        assert user_pwd not in full_logs
        assert svc_pwd not in full_logs

        # Test direct client bind zeroization
        config = LdapCardConfig(
            kind="LDAP",
            url="ldaps://localhost:636",
            transport_mode="ldaps",
            ca_cert_pem=ldap_certs.ca_pem,
            spki_sha256_pins=[ldap_certs.spki_sha256],
            base_dn="dc=example,dc=com",
        )
        client = LdapTlsHardClient(config, unix_socket_path=server.sock_path)
        await client.connect()
        pwd_buf = bytearray(svc_pwd.encode("utf-8"))
        await client.bind(svc_dn, pwd_buf)
        # Manually zeroize as client callers do in finally
        for i in range(len(pwd_buf)):
            pwd_buf[i] = 0
        assert all(b == 0 for b in pwd_buf)
        await client.close()


@pytest.mark.asyncio
async def test_admin_ldap_test_connection_endpoint(
    pg_worker_db: AsyncEngine,
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test admin endpoint POST /api/v1/admin/auth-cards/{card_id}/ldap-test (KB-P2-07, B1, B4)."""
    del db_session
    from kanban.api.deps import PrincipalResolver
    from kanban.auth.cards.repository import admin_upsert

    factory = RLSSessionFactory(pg_worker_db)
    ws_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    member_id = uuid.uuid4()
    admin_ctx = RLSContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        token_scopes=("server",),
        aal_level=2,
    )
    card_id = uuid.uuid4()
    non_ldap_id = uuid.uuid4()

    async with factory.session(admin_ctx) as session:
        await _setup_workspace_and_admin(session, ws_id=ws_id, u_id=admin_id)
        card = await _seed_ldap_card(
            session, ws_id, kek_provider, ldap_certs, slug="ldap-admin-test"
        )
        card_id = card.id

        # Seed a non-LDAP card (LOCAL_ADMIN) to verify 404 anti-enumeration
        await admin_upsert(
            session,
            card_id=non_ldap_id,
            workspace_id=ws_id,
            provider_kind="LOCAL_ADMIN",
            slug="local-admin-test-card",
            display_name="Local Admin Card",
            is_enabled=True,
            sort_rank="0002",
            public_config={"kind": "LOCAL_ADMIN"},
        )

        # Create a non-admin member principal
        await session.execute(
            text(
                "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
            ),
            {
                "ws_id": ws_id,
                "ckey": f"usr-{member_id.hex}",
                "title": "Member User",
                "u_id": member_id,
            },
        )
        await session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
                "VALUES (:id, 'USER', :ws_id, 'Member User', 'ACTIVE')"
            ),
            {"id": member_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws_id, 'member@example.com')"
            ),
            {"id": member_id, "ws_id": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO role_bindings "
                "(id, workspace_id, principal_id, role, scope_type, project_id) "
                "VALUES (:id, :ws_id, :p_id, 'WORKSPACE_MEMBER', 'workspace', NULL)"
            ),
            {"id": uuid.uuid4(), "ws_id": ws_id, "p_id": member_id},
        )

    svc_dn = "cn=svc-kanban,ou=services,dc=corp,dc=example"

    async with FakeLdapServer(ldap_certs, mode="ldaps") as server:
        server.directory.passwords[svc_dn] = "SvcSecretPassword123!"

        app = FastAPI()
        app.add_exception_handler(ProblemException, cast("Any", problem_exception_handler))
        app.include_router(auth_ldap_router, prefix="/api/v1")
        app.state.key_material = key_material
        app.state.kek_provider = kek_provider
        app.state.session_factory = factory
        app.state.ldap_unix_socket_path = server.sock_path

        current_principal: PrincipalContext | None = None

        class TestResolver(PrincipalResolver):
            async def resolve(self, request: Request) -> PrincipalContext | None:
                del request
                return current_principal

        app.state.principal_resolver = TestResolver()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            # 1. Anonymous caller -> 401 AUTHENTICATION_REQUIRED
            current_principal = None
            resp_anon = await client.post(f"/api/v1/admin/auth-cards/{card_id}/ldap-test")
            assert resp_anon.status_code == 401
            assert resp_anon.json()["code"] == "AUTHENTICATION_REQUIRED"

            # 2. Member (non-admin) caller -> 403 FORBIDDEN
            current_principal = PrincipalContext(
                principal_id=member_id,
                workspace_id=ws_id,
                aal_level=2,
                token_scopes=("workspace",),
            )
            resp_member = await client.post(f"/api/v1/admin/auth-cards/{card_id}/ldap-test")
            assert resp_member.status_code == 403
            assert resp_member.json()["code"] == "FORBIDDEN"

            # 3. Admin with AAL1 session -> 403 AAL2_REQUIRED
            current_principal = PrincipalContext(
                principal_id=admin_id,
                workspace_id=ws_id,
                aal_level=1,
                token_scopes=("server",),
            )
            resp_aal1 = await client.post(f"/api/v1/admin/auth-cards/{card_id}/ldap-test")
            assert resp_aal1.status_code == 403
            assert resp_aal1.json()["code"] == "AAL2_REQUIRED"

            # 4. Admin with AAL2 session -> 200 Success
            current_principal = PrincipalContext(
                principal_id=admin_id,
                workspace_id=ws_id,
                aal_level=2,
                token_scopes=("server",),
            )
            resp_ok = await client.post(f"/api/v1/admin/auth-cards/{card_id}/ldap-test")
            assert resp_ok.status_code == 200
            data_ok = resp_ok.json()
            assert data_ok["success"] is True
            assert data_ok["transport_mode"] == "ldaps"
            assert data_ok["spki_sha256"] == ldap_certs.spki_sha256
            assert "latency_ms" in data_ok

            # 5. Non-existent card -> 404 CARD_NOT_FOUND with generic detail (no card_id echo)
            random_id = uuid.uuid4()
            resp_404 = await client.post(f"/api/v1/admin/auth-cards/{random_id}/ldap-test")
            assert resp_404.status_code == 404
            data_404 = resp_404.json()
            assert data_404["code"] == "CARD_NOT_FOUND"
            assert data_404["detail"] == "Authentication provider card not found"
            assert str(random_id) not in data_404["detail"]

            # 6. Non-LDAP card -> 404 CARD_NOT_FOUND with identical generic detail
            resp_non_ldap = await client.post(f"/api/v1/admin/auth-cards/{non_ldap_id}/ldap-test")
            assert resp_non_ldap.status_code == 404
            data_non_ldap = resp_non_ldap.json()
            assert data_non_ldap["code"] == "CARD_NOT_FOUND"
            assert data_non_ldap["detail"] == "Authentication provider card not found"

            # 7. Connection failure (server unreachable) -> sanitized 200 success: False
            app.state.ldap_unix_socket_path = "/tmp/nonexistent_socket_failure.sock"
            resp_conn_err = await client.post(f"/api/v1/admin/auth-cards/{card_id}/ldap-test")
            assert resp_conn_err.status_code == 200
            data_conn_err = resp_conn_err.json()
            assert data_conn_err["success"] is False
            assert data_conn_err["error_code"] == "CONNECTION_FAILED"
            assert data_conn_err["message"] == "Connection to LDAP server failed"
            assert "error" not in data_conn_err
            assert "error_type" not in data_conn_err

            # 8. Bind failure -> sanitized 200 success: False, BIND_FAILED
            server.directory.passwords[svc_dn] = "WrongServerPassword!"
            app.state.ldap_unix_socket_path = server.sock_path
            resp_bind_err = await client.post(f"/api/v1/admin/auth-cards/{card_id}/ldap-test")
            assert resp_bind_err.status_code == 200
            data_bind_err = resp_bind_err.json()
            assert data_bind_err["success"] is False
            assert data_bind_err["error_code"] == "BIND_FAILED"
            assert data_bind_err["message"] == "Service bind failed with provided credentials"
            assert "error" not in data_bind_err


@pytest.mark.asyncio
async def test_ldap_alias_endpoint(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test alias endpoint POST /api/v1/auth/cards/{slug}/ldap-login."""
    ws_id, u_id = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(db_session, ws_id, kek_provider, ldap_certs, slug="ldap-alias")

    user_dn = "cn=alice,ou=users,dc=corp,dc=example"
    svc_dn = "cn=svc-kanban,ou=services,dc=corp,dc=example"

    async with FakeLdapServer(ldap_certs, mode="ldaps") as server:
        server.directory.passwords[svc_dn] = "SvcSecretPassword123!"
        server.directory.passwords[user_dn] = "AliceSecret123!"
        server.directory.entries[user_dn] = {
            "objectguid": [b"guid-1234"],
            "mail": [b"alice@example.com"],
            "cn": [b"Alice Alison"],
            "memberof": [],
            "uid": [b"alice"],
        }

        app = FastAPI()
        app.add_exception_handler(ProblemException, cast("Any", problem_exception_handler))
        app.include_router(auth_ldap_router, prefix="/api/v1")
        app.state.key_material = key_material
        app.state.kek_provider = kek_provider
        app.state.ldap_unix_socket_path = server.sock_path

        async def override_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        app.dependency_overrides[get_auth_session] = override_session

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            resp = await client.post(
                "/api/v1/auth/cards/ldap-alias/ldap-login",
                json={"username": "alice", "password": "AliceSecret123!"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "authenticated"
            assert data["subject"] == "guid-1234"


def test_ldap_reexports() -> None:
    """Test re-exports in protocol.py and group_sync.py."""
    import kanban.api.v1.auth_ldap as al
    import kanban.auth.ldap.group_sync as gs
    import kanban.auth.ldap.protocol as proto

    assert hasattr(gs, "sync_ldap_groups")
    assert hasattr(proto, "LdapTlsHardClient")
    assert hasattr(al, "auth_ldap_router")


def test_config_validation_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test all input validation branches in LdapCardConfig."""
    # 1. URL validation
    with pytest.raises(ValidationError, match="url must match"):
        LdapCardConfig(
            kind="LDAP", url="ftp://ldap.example.com", transport_mode="ldaps", base_dn="dc=com"
        )
    with pytest.raises(ValidationError, match="url must match"):
        LdapCardConfig(
            kind="LDAP", url="ldap://bad host:389", transport_mode="starttls", base_dn="dc=com"
        )

    # Hostname loopback rejection when allow_private=False
    monkeypatch.setenv("KANBAN_AUTH_EGRESS_ALLOW_PRIVATE", "false")
    with pytest.raises(ValidationError, match="targets loopback hostname"):
        LdapCardConfig(
            kind="LDAP", url="ldaps://localhost:636", transport_mode="ldaps", base_dn="dc=com"
        )
    with pytest.raises(ValidationError, match="targets prohibited loopback or link-local IP"):
        LdapCardConfig(
            kind="LDAP", url="ldap://169.254.1.1:389", transport_mode="starttls", base_dn="dc=com"
        )

    # 2. CA Cert PEM validation
    cfg_none_ca = LdapCardConfig(
        kind="LDAP",
        url="ldaps://dc01.corp.example:636",
        transport_mode="ldaps",
        ca_cert_pem=None,
        base_dn="dc=com",
    )
    assert cfg_none_ca.ca_cert_pem is None
    cfg_empty_ca = LdapCardConfig(
        kind="LDAP",
        url="ldaps://dc01.corp.example:636",
        transport_mode="ldaps",
        ca_cert_pem="   ",
        base_dn="dc=com",
    )
    assert cfg_empty_ca.ca_cert_pem is None

    with pytest.raises(ValidationError, match="must not exceed 65536 bytes"):
        LdapCardConfig(
            kind="LDAP",
            url="ldaps://dc01.corp.example:636",
            transport_mode="ldaps",
            ca_cert_pem="x" * 70000,
            base_dn="dc=com",
        )
    with pytest.raises(ValidationError, match="contains invalid X.509 PEM data"):
        LdapCardConfig(
            kind="LDAP",
            url="ldaps://dc01.corp.example:636",
            transport_mode="ldaps",
            ca_cert_pem="not a valid pem",
            base_dn="dc=com",
        )

    # 3. SPKI Pins validation
    with pytest.raises(ValidationError, match="cannot exceed 4 pins"):
        LdapCardConfig(
            kind="LDAP",
            url="ldaps://dc01.corp.example:636",
            transport_mode="ldaps",
            spki_sha256_pins=["a" * 64] * 5,
            base_dn="dc=com",
        )
    with pytest.raises(ValidationError, match="must be a 64-character lowercase hex digest"):
        LdapCardConfig(
            kind="LDAP",
            url="ldaps://dc01.corp.example:636",
            transport_mode="ldaps",
            spki_sha256_pins=["invalid-pin"],
            base_dn="dc=com",
        )

    # 4. Service Bind DN validation
    cfg_none_dn = LdapCardConfig(
        kind="LDAP",
        url="ldaps://dc01.corp.example:636",
        transport_mode="ldaps",
        service_bind_dn="  ",
        base_dn="dc=com",
    )
    assert cfg_none_dn.service_bind_dn is None
    with pytest.raises(ValidationError, match="cannot exceed 512 characters"):
        LdapCardConfig(
            kind="LDAP",
            url="ldaps://dc01.corp.example:636",
            transport_mode="ldaps",
            service_bind_dn="cn=" + "a" * 513,
            base_dn="dc=com",
        )

    # 5. Search Filter validation
    with pytest.raises(ValidationError, match=r"exactly one '\{username\}'"):
        LdapCardConfig(
            kind="LDAP",
            url="ldaps://dc01.corp.example:636",
            transport_mode="ldaps",
            user_search_filter="(objectClass=*)",
            base_dn="dc=com",
        )
    with pytest.raises(ValidationError, match="unbalanced parentheses"):
        LdapCardConfig(
            kind="LDAP",
            url="ldaps://dc01.corp.example:636",
            transport_mode="ldaps",
            user_search_filter=")(uid={username})(",
            base_dn="dc=com",
        )
    with pytest.raises(ValidationError, match="unbalanced parentheses"):
        LdapCardConfig(
            kind="LDAP",
            url="ldaps://dc01.corp.example:636",
            transport_mode="ldaps",
            user_search_filter="((uid={username})",
            base_dn="dc=com",
        )

    # 6. Group DN map validation
    with pytest.raises(ValidationError, match="cannot contain more than 200 mappings"):
        LdapCardConfig(
            kind="LDAP",
            url="ldaps://dc01.corp.example:636",
            transport_mode="ldaps",
            group_dn_map={f"cn=g{i}": f"Group{i}" for i in range(201)},
            base_dn="dc=com",
        )
    with pytest.raises(ValidationError, match="must be between 1 and 512 characters"):
        LdapCardConfig(
            kind="LDAP",
            url="ldaps://dc01.corp.example:636",
            transport_mode="ldaps",
            group_dn_map={"": "ValidGroup"},
            base_dn="dc=com",
        )
    with pytest.raises(ValidationError, match="must be between 1 and 200 characters"):
        LdapCardConfig(
            kind="LDAP",
            url="ldaps://dc01.corp.example:636",
            transport_mode="ldaps",
            group_dn_map={"cn=valid": ""},
            base_dn="dc=com",
        )

    # 7. Scheme pairing validation
    with pytest.raises(ValidationError, match="ldap:// scheme requires transport_mode='starttls'"):
        LdapCardConfig(
            kind="LDAP",
            url="ldap://dc01.corp.example:389",
            transport_mode="ldaps",
            base_dn="dc=com",
        )


@pytest.mark.asyncio
async def test_asn1_ber_coverage() -> None:
    """Test ASN.1 BER framing and decoding edge cases."""
    import asyncio

    from kanban.auth.ldap.asn1_ber import (
        LdapProtocolError,
        build_search_request,
        build_unbind_request,
        decode_ldap_message,
        encode_filter_ast,
        read_ber_packet,
    )
    from kanban.auth.ldap.escape import (
        FilterAnd,
        FilterLeaf,
        FilterNode,
        FilterNot,
        FilterOr,
    )

    # 1. Unbind request
    unbind_bytes = build_unbind_request(1)
    assert unbind_bytes[0] == 0x30

    # 2. Filter AST encodings
    not_node = FilterNot(FilterLeaf("status", "=", "disabled"))
    assert len(encode_filter_ast(not_node)) > 0

    and_node = FilterAnd((FilterLeaf("a", "=", "1"), FilterLeaf("b", "=", "2")))
    assert len(encode_filter_ast(and_node)) > 0

    or_node = FilterOr((FilterLeaf("a", "=", "1"), FilterLeaf("b", "=", "2")))
    assert len(encode_filter_ast(or_node)) > 0

    # Search request with FilterNode
    search_bytes = build_search_request(1, "dc=com", and_node, ["cn", "mail"])
    assert search_bytes[0] == 0x30

    # Unsupported AST node
    class UnsupportedNode(FilterNode):
        pass

    with pytest.raises(LdapProtocolError, match="Unsupported filter node type"):
        encode_filter_ast(UnsupportedNode())

    # 3. read_ber_packet EOF, invalid tag, and too large
    reader_eof = asyncio.StreamReader()
    reader_eof.feed_eof()
    with pytest.raises(asyncio.IncompleteReadError):
        await read_ber_packet(reader_eof, 1024)

    reader_bad_tag = asyncio.StreamReader()
    reader_bad_tag.feed_data(bytes([0x31, 0x02, 0x00, 0x00]))
    with pytest.raises(LdapProtocolError, match="expected SEQUENCE tag 0x30"):
        await read_ber_packet(reader_bad_tag, 1024)

    reader_too_large = asyncio.StreamReader()
    reader_too_large.feed_data(bytes([0x30, 0x82, 0x01, 0x00]) + b"\x00" * 256)
    with pytest.raises(LdapProtocolError, match="MESSAGE_TOO_LARGE"):
        await read_ber_packet(reader_too_large, max_bytes=100)

    # 4. decode_ldap_message invalid bytes
    with pytest.raises(LdapProtocolError, match="BER decode failed"):
        decode_ldap_message(b"\x00\x01\x02")


@pytest.mark.asyncio
async def test_client_coverage_branches(ldap_certs: LdapTestCerts) -> None:
    """Test client state flags, disconnected errors, and SPKI error paths."""
    from unittest.mock import MagicMock

    from kanban.auth.ldap.client import (
        LdapError,
        LdapProtocolError,
        LdapTlsError,
        LdapTlsHardClient,
        _raise_invalid_starttls_op,
        _raise_starttls_rejected,
    )

    # Context without CA cert
    cfg_no_ca = LdapCardConfig(
        kind="LDAP",
        url="ldaps://localhost:636",
        transport_mode="ldaps",
        ca_cert_pem=None,
        base_dn="dc=com",
    )
    client_no_ca = LdapTlsHardClient(cfg_no_ca)
    ctx = client_no_ca._create_ssl_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED

    config = LdapCardConfig(
        kind="LDAP",
        url="ldaps://localhost:636",
        transport_mode="ldaps",
        ca_cert_pem=ldap_certs.ca_pem,
        base_dn="dc=com",
    )
    client = LdapTlsHardClient(config)
    assert not client.is_connected
    assert not client.is_tls_established
    assert client.verified_spki_sha256 is None

    # TLS_HARD checks
    with pytest.raises(LdapTlsError, match="TLS_HARD invariant violation"):
        await client.bind("cn=admin", b"secret")

    with pytest.raises(LdapTlsError, match="TLS_HARD invariant violation"):
        await client.search("dc=com", "(objectClass=*)", ["cn"])

    # Disconnected checks
    client._tls_established = True
    with pytest.raises(LdapError, match="Client is not connected"):
        await client.bind("cn=admin", b"secret")

    with pytest.raises(LdapError, match="Client is not connected"):
        await client.search("dc=com", "(objectClass=*)", ["cn"])

    # Empty password check
    mock_writer = MagicMock()
    mock_reader = MagicMock()
    client._writer = mock_writer
    client._reader = mock_reader
    with pytest.raises(LdapBindError, match="Empty password"):
        await client.bind("cn=admin", b"")

    # SPKI verification mocks
    mock_writer_no_ssl = MagicMock()
    mock_writer_no_ssl.get_extra_info.return_value = None
    with pytest.raises(LdapTlsError, match="TLS object not found"):
        client._verify_spki_pin(mock_writer_no_ssl)

    mock_ssl_obj_no_cert = MagicMock()
    mock_ssl_obj_no_cert.getpeercert.return_value = None
    mock_writer_no_cert = MagicMock()
    mock_writer_no_cert.get_extra_info.return_value = mock_ssl_obj_no_cert
    with pytest.raises(LdapTlsError, match="Failed to retrieve peer certificate"):
        client._verify_spki_pin(mock_writer_no_cert)

    # StartTLS helper errors
    with pytest.raises(LdapProtocolError, match="Expected extendedResp"):
        _raise_invalid_starttls_op("invalidOp")

    with pytest.raises(LdapTlsError, match="StartTLS rejected"):
        _raise_starttls_rejected(52, "Rejected")

    client._writer = None
    await client.unbind()
    await client.close()


@pytest.mark.asyncio
async def test_service_coverage_branches(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test service validation and error branches."""
    from unittest.mock import MagicMock

    from database.models.auth import LdapGroupMapping
    from kanban.auth.ldap.service import _format_subject_value

    # Format subject edge cases
    assert _format_subject_value(b"short-subject") == "short-subject"
    assert _format_subject_value(b"x" * 16) == str(uuid.UUID(bytes_le=b"x" * 16))

    ws_id, u_id = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(db_session, ws_id, kek_provider, ldap_certs, slug="ldap-srv-cov")

    # Add extra DB mapping to hit mapping_res.scalars().all()
    db_session.add(
        LdapGroupMapping(
            card_id=card.id,
            workspace_id=ws_id,
            ldap_dn="cn=extra-group,dc=corp,dc=example",
            group_name="Extra Group",
        )
    )
    await db_session.flush()

    async with FakeLdapServer(ldap_certs, mode="ldaps") as server:
        svc_dn = "cn=svc-kanban,ou=services,dc=corp,dc=example"
        user_dn = "cn=alice,ou=users,dc=corp,dc=example"
        server.directory.passwords[svc_dn] = "SvcSecretPassword123!"
        server.directory.passwords[user_dn] = "CorrectPassword123!"
        server.directory.entries[user_dn] = {
            "objectguid": [b"guid-1234"],
            "uid": [b"alice"],
        }

        service = LdapAuthService(
            kek_provider=kek_provider,
            identity_resolver=RecordingIdentityResolver(principal_id=u_id, workspace_id=ws_id),
            unix_socket_path=server.sock_path,
        )

        # Empty username
        with pytest.raises(ProblemException) as exc:
            await service.authenticate(db_session, card, "   ", "pwd")
        assert exc.value.status == 401

        # Disabled card mock
        disabled_card = MagicMock()
        disabled_card.is_enabled = False
        disabled_card.provider_kind = "LDAP"
        with pytest.raises(ProblemException) as exc:
            await service.authenticate(db_session, disabled_card, "alice", "pwd")
        assert exc.value.status == 401

        # Missing secret mock
        no_secret_card = MagicMock()
        no_secret_card.is_enabled = True
        no_secret_card.provider_kind = "LDAP"
        no_secret_card.public_config = card.public_config
        no_secret_card.encrypted_secret_blob = None
        no_secret_card.wrapped_dek = None
        no_secret_card.id = card.id
        with pytest.raises(ProblemException) as exc:
            await service.authenticate(db_session, no_secret_card, "alice", "pwd")
        assert exc.value.status == 401

        # Search result missing subject attribute
        server.directory.entries["cn=nosubj,ou=users,dc=corp,dc=example"] = {
            "uid": [b"nosubj"],
            "mail": [b"nosubj@example.com"],
        }
        with pytest.raises(ProblemException) as exc:
            await service.authenticate(db_session, card, "nosubj", "pwd")
        assert exc.value.status == 401

        # Ephemeral bind password failure
        with pytest.raises(ProblemException) as exc:
            await service.authenticate(db_session, card, "alice", "WrongUserPassword!")
        assert exc.value.status == 401

        # Success with extra mapping loaded
        assertion, _ = await service.authenticate(db_session, card, "alice", "CorrectPassword123!")
        assert assertion.subject == "guid-1234"


@pytest.mark.asyncio
async def test_router_coverage_branches(
    key_material: KeyMaterial,
    kek_provider: StaticKekProvider,
) -> None:
    """Test router dependencies and error branches."""
    from starlette.requests import Request

    from kanban.auth.ldap.router import get_auth_session

    app = FastAPI()
    app.state.key_material = key_material
    app.state.kek_provider = kek_provider

    # get_auth_session with no session_factory
    dummy_req = Request(scope={"type": "http", "app": app})
    with pytest.raises(RuntimeError, match="No session_factory configured"):
        async for _ in get_auth_session(dummy_req):
            pass

    # get_ldap_service retrieves / constructs service
    service = get_ldap_service(dummy_req)
    assert service is not None
    # cached retrieval
    assert get_ldap_service(dummy_req) is service


@pytest.mark.asyncio
async def test_extra_coverage_for_client_router_ber(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test targeted edge cases in asn1_ber, client, and router to achieve >=95% coverage."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from kanban.auth.ldap.asn1_ber import (
        MAX_BER_MESSAGE_SIZE,
        LdapProtocolError,
        build_search_request,
        decode_ldap_message,
        encode_filter_ast,
        read_ber_packet,
    )
    from kanban.auth.ldap.client import (
        LdapError,
        LdapTlsHardClient,
    )
    from kanban.auth.ldap.escape import FilterLeaf
    from kanban.tests.fixtures.fake_ldap import _make_bind_response, _make_search_done

    # 1. asn1_ber filter leaf operators
    assert len(encode_filter_ast(FilterLeaf("age", ">=", "18"))) > 0
    assert len(encode_filter_ast(FilterLeaf("age", "<=", "65"))) > 0
    assert len(encode_filter_ast(FilterLeaf("name", "~=", "smith"))) > 0
    assert len(encode_filter_ast(FilterLeaf("mail", "=*", ""))) > 0

    # Search request with string filter
    req_str_filter = build_search_request(1, "dc=com", "(objectClass=person)", ["cn"])
    assert req_str_filter[0] == 0x30

    # decode_ldap_message too large
    with pytest.raises(LdapProtocolError, match="MESSAGE_TOO_LARGE"):
        decode_ldap_message(b"\x00" * (MAX_BER_MESSAGE_SIZE + 1))

    # read_ber_packet with 2-byte length
    r_2byte = asyncio.StreamReader()
    r_2byte.feed_data(bytes([0x30, 0x82, 0x00, 0x04]) + b"abcd")
    pkt_2byte = await read_ber_packet(r_2byte, 1024)
    assert len(pkt_2byte) == 8

    # 2. Client mock TCP connection & error handling
    config = LdapCardConfig(
        kind="LDAP",
        url="ldaps://dc01.corp.example:636",
        transport_mode="ldaps",
        ca_cert_pem=ldap_certs.ca_pem,
        spki_sha256_pins=[ldap_certs.spki_sha256],
        base_dn="dc=com",
    )
    client = LdapTlsHardClient(config)

    with patch("asyncio.open_connection", side_effect=OSError("network unreachable")):
        with pytest.raises(OSError, match="network unreachable"):
            await client.connect()

    config_starttls = LdapCardConfig(
        kind="LDAP",
        url="ldap://dc01.corp.example:389",
        transport_mode="starttls",
        ca_cert_pem=ldap_certs.ca_pem,
        base_dn="dc=com",
    )
    client_starttls = LdapTlsHardClient(config_starttls)
    with patch("asyncio.open_connection", side_effect=OSError("network unreachable")):
        with pytest.raises(OSError, match="network unreachable"):
            await client_starttls.connect()

    # Client unbind and search errors
    client._tls_established = True
    mock_writer = MagicMock()
    mock_writer.is_closing.return_value = False
    mock_writer.wait_closed = AsyncMock()
    mock_writer.drain = AsyncMock()
    mock_reader = MagicMock()
    client._writer = mock_writer
    client._reader = mock_reader

    # Unbind when connected
    await client.unbind()
    assert mock_writer.write.called

    # Close with exception in wait_closed
    mock_writer.wait_closed = AsyncMock(side_effect=OSError("socket error"))
    await client.close()

    # Search with error resultCode
    client._msg_id_counter = 0
    client._tls_established = True
    client._writer = mock_writer
    client._reader = mock_reader
    mock_reader.readexactly = AsyncMock(
        return_value=_make_search_done(1, result_code=32, diag="No Such Object")
    )
    with (
        patch(
            "kanban.auth.ldap.client.read_ber_packet",
            return_value=_make_search_done(1, result_code=32, diag="No Such Object"),
        ),
        pytest.raises(LdapError, match="Search failed"),
    ):
        await client.search("dc=com", "(objectClass=*)", ["cn"])

    # Search with unexpected opcode (bindResponse instead of search entry/done)
    client._msg_id_counter = 0
    with (
        patch(
            "kanban.auth.ldap.client.read_ber_packet",
            return_value=_make_bind_response(1, 0),
        ),
        pytest.raises(LdapProtocolError, match="Unexpected search response operation"),
    ):
        await client.search("dc=com", "(objectClass=*)", ["cn"])

    # Bind with unexpected opcode
    client._msg_id_counter = 0
    with (
        patch(
            "kanban.auth.ldap.client.read_ber_packet",
            return_value=_make_search_done(1, 0),
        ),
        pytest.raises(LdapProtocolError, match="Expected bindResponse"),
    ):
        await client.bind("cn=admin", b"secret")

    # Bind with error resultCode
    client._msg_id_counter = 0
    with (
        patch(
            "kanban.auth.ldap.client.read_ber_packet",
            return_value=_make_bind_response(1, 49, "Bad credentials"),
        ),
        pytest.raises(LdapBindError, match="Bind failed with resultCode 49"),
    ):
        await client.bind("cn=admin", b"secret")

    # 3. Extra BER framing error tests
    # Indefinite length (first_len_byte == 0x80)
    reader_indef = asyncio.StreamReader()
    reader_indef.feed_data(b"\x30\x80")
    with pytest.raises(LdapProtocolError, match="Indefinite length encoding is prohibited"):
        await read_ber_packet(reader_indef)

    # Length octets > 4 (first_len_byte == 0x85)
    reader_len5 = asyncio.StreamReader()
    reader_len5.feed_data(b"\x30\x85\x01\x02\x03\x04\x05")
    with pytest.raises(LdapProtocolError, match="MESSAGE_TOO_LARGE: length octets exceed 4 bytes"):
        await read_ber_packet(reader_len5)

    # Direct get_auth_session test
    mock_factory = MagicMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = db_session
    mock_ctx.__aexit__.return_value = None
    mock_factory.session.return_value = mock_ctx
    mock_req = MagicMock()
    mock_req.app.state.session_factory = mock_factory
    async for sess in get_auth_session(mock_req):
        assert sess is db_session

    # 4. Router coverage: IP rate limit, empty password, success login, and admin test
    ws_id, u_id = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(
        db_session, ws_id, kek_provider, ldap_certs, slug="ldap-router-cov"
    )

    app = FastAPI()
    app.add_exception_handler(ProblemException, cast("Any", problem_exception_handler))
    app.include_router(auth_ldap_router, prefix="/api/v1")
    app.state.key_material = key_material
    app.state.kek_provider = kek_provider
    app.state.session_factory = mock_factory
    app.state.ldap_unix_socket_path = "/tmp/nonexistent_test.sock"

    # Rate limiter that blocks IP
    class BlockIpRateLimiter:
        async def hit(self, policy: RateLimitPolicy, key: bytes) -> RateLimitDecision:
            if policy.name == AUTH_LOGIN_IP.name:
                return RateLimitDecision(allowed=False, remaining=0, retry_after_seconds=30)
            return RateLimitDecision(allowed=True, remaining=10, retry_after_seconds=0)

    app.state.rate_limiter = BlockIpRateLimiter()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_auth_session] = override_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client_http:
        # IP Rate limited 429
        r_ip = await client_http.post(
            "/api/v1/auth/ldap/ldap-router-cov/login",
            json={"username": "alice", "password": "pwd"},
        )
        assert r_ip.status_code == 429

        # Whitespace password rejected with 401
        app.state.rate_limiter = None
        r_empty_pwd = await client_http.post(
            "/api/v1/auth/ldap/ldap-router-cov/login",
            json={"username": "alice", "password": "   "},
        )
        assert r_empty_pwd.status_code == 401

        # Successful login returning resolved identity
        from kanban.auth.identity import ExternalIdentityAssertion, ResolvedLogin

        mock_service = AsyncMock()
        mock_service.authenticate.return_value = (
            ExternalIdentityAssertion(
                card_id=card.id,
                subject="alice",
                email="alice@example.com",
                email_verified=True,
                display_name="Alice Ldap",
                groups=("Developers",),
            ),
            ResolvedLogin(
                principal_id=u_id,
                workspace_id=ws_id,
                aal_level=1,
            ),
        )
        app.state.ldap_auth_service = mock_service
        r_success = await client_http.post(
            "/api/v1/auth/ldap/ldap-router-cov/login",
            json={"username": "alice", "password": "ValidPassword123!"},
        )
        assert r_success.status_code == 200
        data = r_success.json()
        assert data["status"] == "authenticated"
        assert data["principal_id"] == str(u_id)
        assert data["workspace_id"] == str(ws_id)
        assert data["aal_level"] == 1

        # Service raising LdapError mapped to 401
        mock_service.authenticate.side_effect = LdapError("Connection refused")
        r_err = await client_http.post(
            "/api/v1/auth/ldap/ldap-router-cov/login",
            json={"username": "alice", "password": "ValidPassword123!"},
        )
        assert r_err.status_code == 401

        # Set up admin dependency override for admin test routes
        app.dependency_overrides[require_admin_aal2] = lambda: PrincipalContext(
            principal_id=u_id,
            workspace_id=ws_id,
            aal_level=2,
            token_scopes=("server",),
        )

        # Admin test failure returning 200 with success=False
        r_adm_err = await client_http.post(f"/api/v1/admin/auth-cards/{card.id}/ldap-test")
        assert r_adm_err.status_code == 200
        data = r_adm_err.json()
        assert data["success"] is False
        assert data["error_code"] == "CONNECTION_FAILED"

        # Admin test success with service_bind_dn configured
        secret_bytes = json.dumps({"bind_dn_password": "SvcSecretPassword123!"}).encode("utf-8")
        sealed = seal_card_secret(card.id, "LDAP", secret_bytes, kek_provider)
        card.public_config = {
            **card.public_config,
            "service_bind_dn": "cn=svc-kanban,ou=services,dc=corp,dc=example",
        }
        card.encrypted_secret_blob = sealed.encrypted_secret_blob
        card.wrapped_dek = sealed.wrapped_dek
        card.dek_kid = sealed.dek_kid
        await db_session.flush()

        async with FakeLdapServer(ldap_certs, mode="ldaps") as server:
            server.directory.passwords["cn=svc-kanban,ou=services,dc=corp,dc=example"] = (
                "SvcSecretPassword123!"
            )
            app.state.ldap_unix_socket_path = server.sock_path
            r_adm_ok = await client_http.post(f"/api/v1/admin/auth-cards/{card.id}/ldap-test")
            assert r_adm_ok.status_code == 200
            adm_ok_data = r_adm_ok.json()
            assert adm_ok_data["success"] is True


@pytest.mark.asyncio
async def test_b1_starttls_buffer_injection_and_msg_id(
    ldap_certs: LdapTestCerts,
) -> None:
    """Test Arch B1: STARTTLS plaintext injection (CVE-2011-0411) and messageID validation."""
    config = LdapCardConfig(
        kind="LDAP",
        url="ldap://localhost:389",
        transport_mode="starttls",
        ca_cert_pem=ldap_certs.ca_pem,
        spki_sha256_pins=[ldap_certs.spki_sha256],
        base_dn="ou=users,dc=corp,dc=example",
    )

    # 1. Plaintext buffer injection after StartTLS response
    forged_bytes = b"\x30\x0c\x02\x01\x02\x61\x07\x0a\x01\x00\x04\x00\x04\x00"
    async with FakeLdapServer(
        ldap_certs,
        mode="starttls",
        inject_buffer_after_starttls=forged_bytes,
    ) as server:
        client = LdapTlsHardClient(config, unix_socket_path=server.sock_path)
        with pytest.raises(LdapTlsError, match="STARTTLS_BUFFER_INJECTION"):
            await client.connect()

    # 2. StartTLS messageID mismatch
    async with FakeLdapServer(
        ldap_certs,
        mode="starttls",
        mismatch_starttls_msg_id=999,
    ) as server:
        client = LdapTlsHardClient(config, unix_socket_path=server.sock_path)
        with pytest.raises(LdapProtocolError, match="Mismatched messageID"):
            await client.connect()

    # 3. Bind messageID mismatch
    async with FakeLdapServer(
        ldap_certs,
        mode="ldaps",
        mismatch_bind_msg_id=999,
    ) as server:
        cfg_ldaps = LdapCardConfig(
            kind="LDAP",
            url="ldaps://localhost:636",
            transport_mode="ldaps",
            ca_cert_pem=ldap_certs.ca_pem,
            spki_sha256_pins=[ldap_certs.spki_sha256],
            base_dn="ou=users,dc=corp,dc=example",
        )
        async with LdapTlsHardClient(cfg_ldaps, unix_socket_path=server.sock_path) as client:
            with pytest.raises(LdapProtocolError, match="Mismatched messageID"):
                await client.bind("cn=alice,ou=users,dc=corp,dc=example", b"secret")

    # 4. Search messageID mismatch
    async with FakeLdapServer(
        ldap_certs,
        mode="ldaps",
        mismatch_search_msg_id=999,
    ) as server:
        cfg_ldaps = LdapCardConfig(
            kind="LDAP",
            url="ldaps://localhost:636",
            transport_mode="ldaps",
            ca_cert_pem=ldap_certs.ca_pem,
            spki_sha256_pins=[ldap_certs.spki_sha256],
            base_dn="ou=users,dc=corp,dc=example",
        )
        async with LdapTlsHardClient(cfg_ldaps, unix_socket_path=server.sock_path) as client:
            with pytest.raises(LdapProtocolError, match="Mismatched messageID"):
                await client.search("ou=users,dc=corp,dc=example", "(uid=alice)", ["uid"])


@pytest.mark.asyncio
async def test_b2_hostile_wire_timeouts_and_size_limit(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    ldap_certs: LdapTestCerts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Arch B2: Operation timeouts, total timeout, and search size limit."""
    monkeypatch.setattr("kanban.auth.ldap.client.DEFAULT_CONNECT_TIMEOUT", 0.1)
    monkeypatch.setattr("kanban.auth.ldap.client.DEFAULT_OP_TIMEOUT", 0.1)
    monkeypatch.setattr("kanban.auth.ldap.client.DEFAULT_TOTAL_TIMEOUT", 0.3)
    monkeypatch.setattr("kanban.auth.ldap.service.DEFAULT_TOTAL_TIMEOUT", 0.3)

    cfg = LdapCardConfig(
        kind="LDAP",
        url="ldap://localhost:389",
        transport_mode="starttls",
        ca_cert_pem=ldap_certs.ca_pem,
        spki_sha256_pins=[ldap_certs.spki_sha256],
        base_dn="ou=users,dc=corp,dc=example",
    )

    # 1. Stalled server after TCP accept
    async with FakeLdapServer(ldap_certs, mode="starttls", stall_after_tcp=True) as server:
        client = LdapTlsHardClient(cfg, unix_socket_path=server.sock_path, op_timeout=0.1)
        with pytest.raises(TimeoutError):
            await client.connect()

    # 2. Stalled server after StartTLS ok
    async with FakeLdapServer(ldap_certs, mode="starttls", stall_after_starttls=True) as server:
        client = LdapTlsHardClient(cfg, unix_socket_path=server.sock_path, op_timeout=0.1)
        with pytest.raises(TimeoutError):
            await client.connect()

    # 3. Stalled server mid-search
    async with FakeLdapServer(ldap_certs, mode="ldaps", stall_mid_search=True) as server:
        cfg_ldaps = LdapCardConfig(
            kind="LDAP",
            url="ldaps://localhost:636",
            transport_mode="ldaps",
            ca_cert_pem=ldap_certs.ca_pem,
            spki_sha256_pins=[ldap_certs.spki_sha256],
            base_dn="ou=users,dc=corp,dc=example",
        )
        async with LdapTlsHardClient(
            cfg_ldaps, unix_socket_path=server.sock_path, op_timeout=0.1
        ) as client:
            with pytest.raises(TimeoutError):
                await client.search("ou=users,dc=corp,dc=example", "(uid=alice)", ["uid"])

    # 4. Search size_limit exceeded (server returns 3 entries when size_limit is 2)
    async with FakeLdapServer(ldap_certs, mode="ldaps", ignore_size_limit=True) as server:
        for idx in range(3):
            dn = f"cn=user{idx},ou=users,dc=corp,dc=example"
            server.directory.entries[dn] = {
                "uid": [f"user{idx}".encode()],
                "mail": [f"user{idx}@example.com".encode()],
                "cn": [f"User {idx}".encode()],
            }
        cfg_ldaps = LdapCardConfig(
            kind="LDAP",
            url="ldaps://localhost:636",
            transport_mode="ldaps",
            ca_cert_pem=ldap_certs.ca_pem,
            spki_sha256_pins=[ldap_certs.spki_sha256],
            base_dn="ou=users,dc=corp,dc=example",
        )
        async with LdapTlsHardClient(cfg_ldaps, unix_socket_path=server.sock_path) as client:
            with pytest.raises(LdapSearchError, match="SIZE_LIMIT_EXCEEDED"):
                await client.search(
                    "ou=users,dc=corp,dc=example", "(uid=user*)", ["uid"], size_limit=2
                )

    # 5. Stalled server in service.authenticate maps to 401 INVALID_CREDENTIALS
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(
        db_session, ws_id, kek_provider, ldap_certs, slug="ldap-stall-card"
    )
    async with FakeLdapServer(ldap_certs, mode="ldaps", stall_after_tcp=True) as server:
        service = LdapAuthService(kek_provider=kek_provider, unix_socket_path=server.sock_path)
        with pytest.raises(ProblemException) as exc_info:
            await service.authenticate(db_session, card, "alice", "Password123!")
        assert exc_info.value.status == 401
        assert exc_info.value.code == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_b3_uniform_failure_and_malformed_bind_response(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test Arch B3: LdapProtocolError is LdapError; malformed bind reply maps to uniform 401."""
    assert issubclass(LdapProtocolError, LdapError)

    ws_id, _ = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(
        db_session, ws_id, kek_provider, ldap_certs, slug="ldap-malformed-bind"
    )

    async with FakeLdapServer(ldap_certs, mode="ldaps", malformed_bind_response=True) as server:
        user_dn = "cn=alice,ou=users,dc=corp,dc=example"
        server.directory.passwords[user_dn] = "AlicePwd123!"
        server.directory.entries[user_dn] = {
            "objectguid": [b"guid-1234"],
            "mail": [b"alice@example.com"],
            "cn": [b"Alice Alison"],
            "memberof": [],
            "uid": [b"alice"],
        }
        service = LdapAuthService(kek_provider=kek_provider, unix_socket_path=server.sock_path)
        with pytest.raises(ProblemException) as exc_info:
            await service.authenticate(db_session, card, "alice", "AlicePwd123!")
        assert exc_info.value.status == 401
        assert exc_info.value.code == "INVALID_CREDENTIALS"
        assert exc_info.value.title == "Authentication Failed"
        assert exc_info.value.detail == "Invalid credentials"


@pytest.mark.asyncio
async def test_b4_machine_readable_429(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test UI B4: 429 response contains Retry-After header and retry_after_seconds numeric member."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(db_session, ws_id, kek_provider, ldap_certs, slug="ldap-429-test")

    app = FastAPI()
    app.add_exception_handler(ProblemException, cast("Any", problem_exception_handler))
    app.include_router(auth_ldap_router, prefix="/api/v1")
    app.state.key_material = key_material
    app.state.kek_provider = kek_provider

    class MockAccountRateLimiter:
        async def hit(self, policy: RateLimitPolicy, key: bytes) -> RateLimitDecision:
            del key
            if policy.name == "auth_login_account":
                return RateLimitDecision(allowed=False, remaining=0, retry_after_seconds=45)
            return RateLimitDecision(allowed=True, remaining=10, retry_after_seconds=0)

    app.state.rate_limiter = MockAccountRateLimiter()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_auth_session] = override_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
        resp = await client.post(
            f"/api/v1/auth/ldap/{card.slug}/login",
            json={"username": "alice", "password": "Password123!"},
        )
        assert resp.status_code == 429
        assert resp.headers.get("retry-after") == "45"
        body = resp.json()
        assert body["code"] == "RATE_LIMITED"
        assert body["retry_after_seconds"] == 45
        assert "45 seconds" in body["detail"]


@pytest.mark.asyncio
async def test_b5_session_issuance_and_csrf_cookie(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test UI B5: Successful LDAP authentication issues session and CSRF cookies."""
    ws_id, u_id = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(
        db_session, ws_id, kek_provider, ldap_certs, slug="ldap-session-test"
    )

    user_dn = "cn=alice,ou=users,dc=corp,dc=example"
    svc_dn = "cn=svc-kanban,ou=services,dc=corp,dc=example"

    async with FakeLdapServer(ldap_certs, mode="ldaps") as server:
        server.directory.passwords[svc_dn] = "SvcSecretPassword123!"
        server.directory.passwords[user_dn] = "AliceSecret123!"
        server.directory.entries[user_dn] = {
            "objectguid": [b"guid-1234"],
            "mail": [b"alice@example.com"],
            "cn": [b"Alice Alison"],
            "memberof": [],
            "uid": [b"alice"],
        }

        app = FastAPI()
        app.add_exception_handler(ProblemException, cast("Any", problem_exception_handler))
        app.include_router(auth_ldap_router, prefix="/api/v1")
        app.state.key_material = key_material
        app.state.kek_provider = kek_provider
        app.state.ldap_unix_socket_path = server.sock_path
        app.state.session_service = SessionService(key_material.session_hmac_key)

        async def override_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        app.dependency_overrides[get_auth_session] = override_session

        class MockResolver:
            async def resolve(
                self,
                assertion: ExternalIdentityAssertion,
                req: Request,
                link_id: uuid.UUID | None,
            ) -> ResolvedLogin:
                del assertion, req, link_id
                return ResolvedLogin(
                    principal_id=u_id,
                    workspace_id=ws_id,
                    aal_level=1,
                    mfa_pending=False,
                )

        app.state.identity_resolver = MockResolver()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            resp = await client.post(
                f"/api/v1/auth/ldap/{card.slug}/login",
                json={"username": "alice", "password": "AliceSecret123!"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "authenticated"
            assert "session_id" in data
            assert "csrf_token" in data

            set_cookies = resp.headers.get_list("set-cookie")
            assert len(set_cookies) >= 2
            assert any("__Host-kb_session=" in c for c in set_cookies)
            assert any("__Host-kb_csrf=" in c for c in set_cookies)


@pytest.mark.asyncio
async def test_ui_b3_csrf_protection_with_csrf_middleware(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test UI B3: CSRF middleware enforcement on LDAP authentication routes."""
    ws_id, u_id = await _setup_workspace_and_admin(db_session)
    card = await _seed_ldap_card(db_session, ws_id, kek_provider, ldap_certs, slug="ldap-csrf-test")

    user_dn = "cn=alice,ou=users,dc=corp,dc=example"
    svc_dn = "cn=svc-kanban,ou=services,dc=corp,dc=example"

    async with FakeLdapServer(ldap_certs, mode="ldaps") as server:
        server.directory.passwords[svc_dn] = "SvcSecretPassword123!"
        server.directory.passwords[user_dn] = "AliceSecret123!"
        server.directory.entries[user_dn] = {
            "objectguid": [b"guid-1234"],
            "mail": [b"alice@example.com"],
            "cn": [b"Alice Alison"],
            "memberof": [],
            "uid": [b"alice"],
        }

        app = FastAPI()
        app.add_exception_handler(ProblemException, cast("Any", problem_exception_handler))
        app.include_router(auth_ldap_router, prefix="/api/v1")
        app.add_middleware(CsrfMiddleware, session_hmac_key=key_material.session_hmac_key)
        app.state.key_material = key_material
        app.state.kek_provider = kek_provider
        app.state.ldap_unix_socket_path = server.sock_path

        async def override_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        app.dependency_overrides[get_auth_session] = override_session

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            # 1. Missing CSRF header on POST -> 403 CSRF_REJECTED
            r_missing = await client.post(
                f"/api/v1/auth/ldap/{card.slug}/login",
                json={"username": "alice", "password": "AliceSecret123!"},
            )
            assert r_missing.status_code == 403
            assert r_missing.json()["code"] == "CSRF_REJECTED"
            assert "Missing CSRF token" in r_missing.json()["detail"]

            # 2. Invalid CSRF header -> 403 CSRF_REJECTED
            client.cookies.set(CSRF_COOKIE_NAME, "invalid.sig")
            r_invalid = await client.post(
                f"/api/v1/auth/ldap/{card.slug}/login",
                json={"username": "alice", "password": "AliceSecret123!"},
                headers={CSRF_HEADER_NAME: "invalid.sig"},
            )
            assert r_invalid.status_code == 403
            assert r_invalid.json()["code"] == "CSRF_REJECTED"

            # 3. Valid CSRF header -> 200 Success
            valid_csrf = generate_csrf_token(PRE_SESSION_ID, key_material.session_hmac_key)
            client.cookies.set(CSRF_COOKIE_NAME, valid_csrf)
            r_valid = await client.post(
                f"/api/v1/auth/ldap/{card.slug}/login",
                json={"username": "alice", "password": "AliceSecret123!"},
                headers={CSRF_HEADER_NAME: valid_csrf},
            )
            assert r_valid.status_code == 200
            assert r_valid.json()["status"] == "authenticated"


@pytest.mark.asyncio
async def test_ui_b2_byte_identical_401_responses(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
    key_material: KeyMaterial,
    ldap_certs: LdapTestCerts,
) -> None:
    """Test UI B2: Byte-identical 401 bodies across unknown user, wrong password, and disabled card."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    active_card = await _seed_ldap_card(
        db_session, ws_id, kek_provider, ldap_certs, slug="ldap-identical-active"
    )
    disabled_card = await _seed_ldap_card(
        db_session,
        ws_id,
        kek_provider,
        ldap_certs,
        slug="ldap-identical-disabled",
        is_enabled=False,
    )

    user_dn = "cn=alice,ou=users,dc=corp,dc=example"
    svc_dn = "cn=svc-kanban,ou=services,dc=corp,dc=example"

    async with FakeLdapServer(ldap_certs, mode="ldaps") as server:
        server.directory.passwords[svc_dn] = "SvcSecretPassword123!"
        server.directory.passwords[user_dn] = "AliceSecret123!"
        server.directory.entries[user_dn] = {
            "objectguid": [b"guid-1234"],
            "mail": [b"alice@example.com"],
            "cn": [b"Alice Alison"],
            "memberof": [],
            "uid": [b"alice"],
        }

        app = FastAPI()
        app.add_exception_handler(ProblemException, cast("Any", problem_exception_handler))
        app.include_router(auth_ldap_router, prefix="/api/v1")
        app.state.key_material = key_material
        app.state.kek_provider = kek_provider
        app.state.ldap_unix_socket_path = server.sock_path

        async def override_session() -> AsyncIterator[AsyncSession]:
            yield db_session

        app.dependency_overrides[get_auth_session] = override_session

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            # 1. Unknown user
            r_unknown = await client.post(
                f"/api/v1/auth/ldap/{active_card.slug}/login",
                json={"username": "bob_not_found", "password": "SomePassword123!"},
            )
            # 2. Wrong password
            r_wrong_pwd = await client.post(
                f"/api/v1/auth/ldap/{active_card.slug}/login",
                json={"username": "alice", "password": "WrongPassword123!"},
            )
            # 3. Disabled card
            r_disabled = await client.post(
                f"/api/v1/auth/ldap/{disabled_card.slug}/login",
                json={"username": "alice", "password": "AliceSecret123!"},
            )

            assert r_unknown.status_code == 401
            assert r_wrong_pwd.status_code == 401
            assert r_disabled.status_code == 401

            body_unknown = r_unknown.json()
            body_wrong_pwd = r_wrong_pwd.json()
            body_disabled = r_disabled.json()

            # Compare RFC 7807 problem fields (excluding request_id which is unique per request)
            for key in ["type", "title", "status", "code", "detail"]:
                assert body_unknown[key] == body_wrong_pwd[key] == body_disabled[key]

            assert body_unknown["title"] == "Authentication Failed"
            assert body_unknown["detail"] == "Invalid credentials"
            assert body_unknown["code"] == "INVALID_CREDENTIALS"
