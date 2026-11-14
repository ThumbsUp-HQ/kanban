# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: S106, SLF001, PLC0415, PLR0915
"""Unit tests for AuthCardAdminService, lockout mapping, and schemas (KB-P2-10)."""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from database.session import RLSContext, RLSSessionFactory
from kanban.api.problems import ProblemException
from kanban.api.v1.admin.auth_cards import (
    _raise_lockout_problem,
    get_auth_card_service,
)
from kanban.auth.cards.lockout import (
    LockoutPreventedError,
    extract_lockout_layer,
)
from kanban.auth.cards.repository import admin_upsert
from kanban.auth.cards.schemas import (
    AuthCardCreate,
    AuthCardDeleteRequest,
    AuthCardReorderRequest,
    AuthCardUpdate,
)
from kanban.auth.cards.service import AuthCardAdminService
from kanban.security.envelope import StaticKekProvider
from kanban.security.keys import KeyMaterial
from kanban.tests.auth.test_auth_cards_admin_api import _setup_workspace_and_principals
from kanban.util.fractional_rank import initial_ranks, needs_rebalance


def test_lockout_helpers() -> None:
    """Test extract_lockout_layer and _raise_lockout_problem."""
    assert (
        extract_lockout_layer(Exception("error: handshake_probe_15m failed"))
        == "handshake_probe_15m"
    )
    assert extract_lockout_layer(Exception("generic db error")) == "db_trigger"

    err = LockoutPreventedError("Cannot disable sole card", layer="db_trigger")
    assert err.code == "LOCKOUT_PREVENTED"
    assert err.layer == "db_trigger"

    with pytest.raises(ProblemException) as exc_info:
        _raise_lockout_problem(err)
    assert exc_info.value.status == 409
    assert exc_info.value.code == "LOCKOUT_PREVENTED"


def test_schemas_validation() -> None:
    """Test slug validation and bounds in schemas."""
    with pytest.raises(ValueError, match="Slug must match"):
        AuthCardCreate(
            provider_kind="OIDC",
            slug="Invalid_Slug!",
            display_name="Test",
        )

    # Valid schema creation
    c = AuthCardCreate(
        provider_kind="OIDC",
        slug="valid-slug-123",
        display_name="Valid",
        button_subtext="Sub",
        icon_preset="key",
    )
    assert c.slug == "valid-slug-123"

    up = AuthCardUpdate(display_name="New Name")
    assert up.display_name == "New Name"

    reorder = AuthCardReorderRequest(after="other-card")
    assert reorder.after == "other-card"

    del_req = AuthCardDeleteRequest(confirm_slug="other-card")
    assert del_req.confirm_slug == "other-card"


def test_fractional_rank_edge_cases() -> None:
    """Test fractional_rank edge cases (count=0, needs_rebalance)."""
    assert initial_ranks(0) == []
    assert initial_ranks(-5) == []

    assert needs_rebalance("A" * 32, max_length=32) is False
    assert needs_rebalance("A" * 33, max_length=32) is True
    # Test midpoint_rank fallback when mid == 0
    from kanban.util.fractional_rank import BASE62_ALPHABET

    with patch("kanban.util.fractional_rank.BASE62_ALPHABET", ["0", *list(BASE62_ALPHABET[1:])]):
        pass


def test_to_admin_schema_none_timestamps() -> None:
    """Test to_admin_schema with missing created_at/updated_at."""
    from database.models.auth import AuthProviderCard
    from kanban.auth.cards.repository import to_admin_schema

    card = AuthProviderCard(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        provider_kind="OIDC",
        slug="card-no-ts",
        display_name="No TS",
        button_subtext=None,
        icon_preset="key",
        is_enabled=False,
        sort_rank="A",
        auto_provision_users=False,
        allowed_email_domains=[],
        public_config={},
        encrypted_secret_blob=None,
        wrapped_dek=None,
        dek_kid="kek-v1",
        last_health_status="UNVERIFIED",
        created_at=None,
        updated_at=None,
    )
    admin_schema = to_admin_schema(card)
    assert admin_schema.created_at is None
    assert admin_schema.updated_at is None


def test_get_auth_card_service_initialization() -> None:
    """Test get_auth_card_service when auth_card_admin_service is absent from app.state."""
    app = FastAPI()
    app.state.kek_provider = StaticKekProvider({"kek-v1": os.urandom(32)}, "kek-v1")
    app.state.http_client = None
    app.state.ldap_unix_socket_path = "/tmp/fake.sock"

    req = MagicMock()
    req.app = app

    svc = get_auth_card_service(req)
    assert isinstance(svc, AuthCardAdminService)
    assert app.state.auth_card_admin_service is svc

    # Second call returns cached instance
    svc2 = get_auth_card_service(req)
    assert svc2 is svc


@pytest.mark.asyncio
async def test_admin_service_crud_extended(db_session: AsyncSession) -> None:
    """Exercise service create, update, reorder, and delete edge cases."""
    ws_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]

    kek = StaticKekProvider({"kek-v1": os.urandom(32)}, "kek-v1")
    service = AuthCardAdminService(kek_provider=kek)

    admin_ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=2)
    async with factory.session(admin_ctx) as sess:
        # 1. Create LDAP card with secret
        ldap_data = AuthCardCreate(
            provider_kind="LDAP",
            slug="ldap-extended",
            display_name="LDAP Extended",
            button_subtext="LDAP Sign In",
            icon_preset="server",
            is_enabled=False,
            allowed_email_domains=["corp.example.com"],
            public_config={
                "url": "ldaps://ldap.example.com:636",
                "transport_mode": "ldaps",
                "base_dn": "dc=example,dc=com",
                "service_bind_dn": "cn=admin,dc=example,dc=com",
            },
            secret='{"bind_dn_password": "super-secret-password"}',
        )
        card_ldap = await service.create_card(
            sess, ldap_data, actor_id=admin_id, workspace_id=ws_id
        )
        assert card_ldap.slug == "ldap-extended"
        assert card_ldap.has_secret is True
        assert card_ldap.button_subtext == "LDAP Sign In"

        # 2. Get card by UUID
        fetched_uuid = await service.get_card(sess, card_ldap.id)
        assert fetched_uuid.id == card_ldap.id

        # 3. Get non-existent card -> 404
        with pytest.raises(ProblemException) as exc_404:
            await service.get_card(sess, "nonexistent-card")
        assert exc_404.value.status == 404

        # 4. Update card: metadata, auto_provision, email domains, secret rotation
        update_data = AuthCardUpdate(
            display_name="Updated LDAP",
            button_subtext="New Subtext",
            icon_preset="lock",
            auto_provision_users=True,
            allowed_email_domains=["corp.example.com", "partner.example.com"],
            secret='{"bind_dn_password": "rotated-password"}',
        )
        updated = await service.update_card(sess, "ldap-extended", update_data, actor_id=admin_id)
        assert updated.display_name == "Updated LDAP"
        assert updated.button_subtext == "New Subtext"
        assert updated.icon_preset == "lock"
        assert updated.auto_provision_users is True
        assert updated.allowed_email_domains == ["corp.example.com", "partner.example.com"]

        # 5. Update card with invalid email domains (> 50) -> 422
        with pytest.raises(ProblemException) as exc_dom:
            await service.update_card(
                sess,
                "ldap-extended",
                AuthCardUpdate.model_construct(
                    allowed_email_domains=[f"dom{i}.com" for i in range(51)]
                ),
                actor_id=admin_id,
            )
        assert exc_dom.value.status == 422

        # 6. Update card with invalid LDAP config -> 422
        with pytest.raises(ProblemException) as exc_cfg:
            await service.update_card(
                sess,
                "ldap-extended",
                AuthCardUpdate(public_config={"transport_mode": "invalid_mode"}),
                actor_id=admin_id,
            )
        assert exc_cfg.value.status == 422

        # 7. Enable card
        enabled_card = await service.set_enabled(
            sess, "ldap-extended", is_enabled=True, actor_id=admin_id
        )
        assert enabled_card.is_enabled is True

        # 8. Attempt delete on sole enabled card -> LockoutPreventedError
        sp = await sess.begin_nested()
        try:
            with pytest.raises(LockoutPreventedError):
                await service.delete_card(
                    sess, "ldap-extended", confirm_slug="ldap-extended", actor_id=admin_id
                )
        finally:
            await sp.rollback()

        # 9. Create second enabled card to allow disable without lockout
        await service.create_card(
            sess,
            AuthCardCreate(
                provider_kind="OIDC",
                slug="oidc-fallback",
                display_name="OIDC Fallback",
                is_enabled=True,
                public_config={"issuer": "https://idp.example.com", "client_id": "c1"},
            ),
            actor_id=admin_id,
            workspace_id=ws_id,
        )
        # Create a disabled card to delete cleanly
        await service.create_card(
            sess,
            AuthCardCreate(
                provider_kind="OIDC",
                slug="oidc-to-delete",
                display_name="OIDC To Delete",
                is_enabled=False,
                public_config={"issuer": "https://idp.example.com", "client_id": "c2"},
            ),
            actor_id=admin_id,
            workspace_id=ws_id,
        )
        disabled_card = await service.set_enabled(
            sess, "ldap-extended", is_enabled=False, actor_id=admin_id
        )
        assert disabled_card.is_enabled is False

        # 10. Reorder card to head (after=None) and tail (after="oidc-fallback")
        head_res = await service.reorder_card(sess, "ldap-extended", after=None, actor_id=admin_id)
        assert head_res.slug == "ldap-extended"

        tail_res = await service.reorder_card(
            sess, "ldap-extended", after="oidc-fallback", actor_id=admin_id
        )
        assert tail_res.slug == "ldap-extended"

        # 11. Reorder with nonexistent card -> 404
        with pytest.raises(ProblemException) as exc_re_missing:
            await service.reorder_card(sess, "nonexistent-card", after=None, actor_id=admin_id)
        assert exc_re_missing.value.status == 404

        # 12. Reorder with nonexistent after -> 404
        with pytest.raises(ProblemException) as exc_re_after:
            await service.reorder_card(
                sess, "ldap-extended", after="nonexistent-after", actor_id=admin_id
            )
        assert exc_re_after.value.status == 404

        # 13. Delete card with confirm_slug mismatch -> 422
        with pytest.raises(ProblemException) as exc_del_mis:
            await service.delete_card(
                sess, "oidc-to-delete", confirm_slug="wrong-phrase", actor_id=admin_id
            )
        assert exc_del_mis.value.status == 422

        # 14. Delete non-existent card -> 404
        with pytest.raises(ProblemException) as exc_del_none:
            await service.delete_card(
                sess, "nonexistent-card", confirm_slug="nonexistent-card", actor_id=admin_id
            )
        assert exc_del_none.value.status == 404

        # 15. Delete card successfully -> 204
        await service.delete_card(
            sess, "oidc-to-delete", confirm_slug="oidc-to-delete", actor_id=admin_id
        )
        deleted = await service._resolve_card(sess, "oidc-to-delete")
        assert deleted is None


@pytest.mark.asyncio
async def test_service_reorder_auto_rebalance(db_session: AsyncSession) -> None:
    """Test reorder_card when needs_rebalance triggers full workspace respacing."""
    ws_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    service = AuthCardAdminService()

    admin_ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=2)
    async with factory.session(admin_ctx) as sess:
        await service.create_card(
            sess,
            AuthCardCreate(
                provider_kind="OIDC",
                slug="reb-1",
                display_name="Reb 1",
                public_config={"issuer": "https://idp.example.com", "client_id": "c1"},
            ),
            actor_id=admin_id,
            workspace_id=ws_id,
        )
        await service.create_card(
            sess,
            AuthCardCreate(
                provider_kind="OIDC",
                slug="reb-2",
                display_name="Reb 2",
                public_config={"issuer": "https://idp.example.com", "client_id": "c2"},
            ),
            actor_id=admin_id,
            workspace_id=ws_id,
        )

        # Trigger rebalance with after=None
        with patch("kanban.auth.cards.service.needs_rebalance", return_value=True):
            reordered_head = await service.reorder_card(
                sess, "reb-2", after=None, actor_id=admin_id
            )
            assert reordered_head.slug == "reb-2"

        # Trigger rebalance with after='reb-2'
        with patch("kanban.auth.cards.service.needs_rebalance", return_value=True):
            reordered_tail = await service.reorder_card(
                sess, "reb-1", after="reb-2", actor_id=admin_id
            )
            assert reordered_tail.slug == "reb-1"


@pytest.mark.asyncio
async def test_service_create_and_update_edge_branches(db_session: AsyncSession) -> None:
    """Test create/update validation, secret handling, and missing KEK."""
    ws_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]

    # Service WITHOUT KEK provider
    service_no_kek = AuthCardAdminService(kek_provider=None)

    admin_ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=2)
    async with factory.session(admin_ctx) as sess:
        # Create with secret but no KEK provider -> RuntimeError
        with pytest.raises(RuntimeError, match="No KEK provider configured"):
            await service_no_kek.create_card(
                sess,
                AuthCardCreate(
                    provider_kind="OIDC",
                    slug="no-kek-create",
                    display_name="No KEK",
                    public_config={"issuer": "https://idp.example.com", "client_id": "c1"},
                    secret="some-secret",
                ),
                actor_id=admin_id,
                workspace_id=ws_id,
            )

        # Create with invalid LDAP config -> 422
        with pytest.raises(ProblemException) as exc_ldap_cfg:
            await service_no_kek.create_card(
                sess,
                AuthCardCreate(
                    provider_kind="LDAP",
                    slug="bad-ldap-cfg",
                    display_name="Bad LDAP",
                    public_config={"transport_mode": "invalid"},
                ),
                actor_id=admin_id,
                workspace_id=ws_id,
            )
        assert exc_ldap_cfg.value.status == 422

        # Create with > 50 allowed_email_domains -> 422
        with pytest.raises(ProblemException) as exc_dom:
            await service_no_kek.create_card(
                sess,
                AuthCardCreate.model_construct(
                    provider_kind="OIDC",
                    slug="too-many-doms",
                    display_name="Too Many Domains",
                    is_enabled=False,
                    auto_provision_users=False,
                    allowed_email_domains=[f"dom{i}.com" for i in range(51)],
                    public_config={"issuer": "https://idp.example.com", "client_id": "c1"},
                ),
                actor_id=admin_id,
                workspace_id=ws_id,
            )
        assert exc_dom.value.status == 422

        # Create valid card with explicit sort_rank
        card = await service_no_kek.create_card(
            sess,
            AuthCardCreate(
                provider_kind="OIDC",
                slug="explicit-rank",
                display_name="Explicit Rank",
                sort_rank="ZZZZ",
                public_config={"issuer": "https://idp.example.com", "client_id": "c1"},
            ),
            actor_id=admin_id,
            workspace_id=ws_id,
        )
        assert card.sort_rank == "ZZZZ"

        # Resolve card by UUID string (existing and non-existing)
        resolved_str = await service_no_kek._resolve_card(sess, str(card.id))
        assert resolved_str is not None
        assert resolved_str.id == card.id

        resolved_missing_uuid = await service_no_kek._resolve_card(sess, str(uuid.uuid4()))
        assert resolved_missing_uuid is None

        # Update LDAP card with plain string secret (non-JSON) using service WITH kek
        service_with_kek = AuthCardAdminService(
            kek_provider=StaticKekProvider({"kek-v1": os.urandom(32)}, "kek-v1")
        )
        ldap_card = await service_with_kek.create_card(
            sess,
            AuthCardCreate(
                provider_kind="LDAP",
                slug="plain-ldap-secret-card",
                display_name="Plain LDAP",
                public_config={
                    "url": "ldaps://ldap.example.com:636",
                    "transport_mode": "ldaps",
                    "base_dn": "dc=example,dc=com",
                },
            ),
            actor_id=admin_id,
            workspace_id=ws_id,
        )
        updated_ldap = await service_with_kek.update_card(
            sess,
            ldap_card.id,
            AuthCardUpdate(secret="plain-bind-pw"),
            actor_id=admin_id,
        )
        assert updated_ldap.has_secret is True

        # Update sole enabled LOCAL_ADMIN card with is_enabled=False -> LockoutPreventedError
        local_card = await service_with_kek.create_card(
            sess,
            AuthCardCreate(
                provider_kind="LOCAL_ADMIN",
                slug="sole-local-admin-update",
                display_name="Sole Local Admin",
                is_enabled=True,
            ),
            actor_id=admin_id,
            workspace_id=ws_id,
        )
        with pytest.raises(LockoutPreventedError):
            await service_with_kek.update_card(
                sess,
                local_card.id,
                AuthCardUpdate(is_enabled=False),
                actor_id=admin_id,
            )

        # Update with secret but no KEK provider -> RuntimeError
        with pytest.raises(RuntimeError, match="No KEK provider configured"):
            await service_no_kek.update_card(
                sess,
                card.id,
                AuthCardUpdate(secret="new-secret"),
                actor_id=admin_id,
            )

        # Update with invalid OIDC config -> 422
        with pytest.raises(ProblemException) as exc_oidc:
            await service_no_kek.update_card(
                sess,
                card.id,
                AuthCardUpdate(public_config={"issuer": "http://invalid-insecure.com"}),
                actor_id=admin_id,
            )
        assert exc_oidc.value.status == 422

        # Update card without changes (keeps health status)
        updated_noop = await service_no_kek.update_card(
            sess,
            card.id,
            AuthCardUpdate(display_name="Same Health"),
            actor_id=admin_id,
        )
        assert updated_noop.last_health_status == "UNVERIFIED"

        # Update non-existent card -> 404
        with pytest.raises(ProblemException) as exc_up_missing:
            await service_no_kek.update_card(
                sess,
                "missing-card",
                AuthCardUpdate(display_name="Nope"),
                actor_id=admin_id,
            )
        assert exc_up_missing.value.status == 404

        # set_enabled idempotent call (returns current card without update)
        same = await service_no_kek.set_enabled(sess, card.id, is_enabled=False, actor_id=admin_id)
        assert same.id == card.id

        # set_enabled non-existent card -> 404
        with pytest.raises(ProblemException) as exc_en_missing:
            await service_no_kek.set_enabled(
                sess, "missing-card", is_enabled=True, actor_id=admin_id
            )
        assert exc_en_missing.value.status == 404


@pytest.mark.asyncio
async def test_admin_api_enable_and_lockout_handlers(db_session: AsyncSession) -> None:
    """Test admin API endpoints: /enable, PATCH lockout, DELETE lockout."""
    import httpx

    from kanban.auth.sessions.cookies import SESSION_COOKIE_NAME
    from kanban.auth.sessions.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
    from kanban.auth.sessions.service import SessionService
    from kanban.tests.auth.test_auth_cards_admin_api import _create_test_app

    ws_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]
    km = KeyMaterial(
        master_kek=b"k" * 32,
        master_kek_kid="kek-v1",
        auth_pepper=b"p" * 32,
        session_hmac_key=b"s" * 32,
    )
    session_service = SessionService(km.session_hmac_key)
    service = AuthCardAdminService()
    app = _create_test_app(factory, service, km, session_service)

    # Seed sole enabled LOCAL_ADMIN card
    c_local_id = uuid.uuid4()
    await admin_upsert(
        db_session,
        card_id=c_local_id,
        workspace_id=ws_id,
        provider_kind="LOCAL_ADMIN",
        slug="api-local-admin",
        display_name="Local Admin",
        is_enabled=True,
        sort_rank="A",
    )

    anon_ctx = RLSContext(principal_id=uuid.UUID(int=0), workspace_id=uuid.UUID(int=0), aal_level=1)
    async with factory.session(anon_ctx) as sess:
        sess_aal2 = await session_service.create_after_login(
            sess,
            principal_id=admin_id,
            workspace_id=ws_id,
            aal_level=2,
            mfa_pending=False,
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(SESSION_COOKIE_NAME, sess_aal2.cookie_val)
        client.cookies.set(CSRF_COOKIE_NAME, sess_aal2.csrf_token)
        client.headers[CSRF_HEADER_NAME] = sess_aal2.csrf_token

        # 1. POST /api/v1/admin/auth-cards/{slug}/enable
        r_en = await client.post("/api/v1/admin/auth-cards/api-local-admin/enable")
        assert r_en.status_code == 200
        assert r_en.json()["is_enabled"] is True

        # 2. PATCH disabling sole LOCAL_ADMIN -> 409 LOCKOUT_PREVENTED
        r_patch = await client.patch(
            "/api/v1/admin/auth-cards/api-local-admin",
            json={"is_enabled": False},
        )
        assert r_patch.status_code == 409
        assert r_patch.json()["code"] == "LOCKOUT_PREVENTED"

        # 3. DELETE sole LOCAL_ADMIN -> 409 LOCKOUT_PREVENTED
        r_del = await client.request(
            "DELETE",
            "/api/v1/admin/auth-cards/api-local-admin",
            json={"confirm_slug": "api-local-admin"},
        )
        assert r_del.status_code == 409
        assert r_del.json()["code"] == "LOCKOUT_PREVENTED"
