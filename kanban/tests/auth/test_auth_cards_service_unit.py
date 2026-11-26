# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: S106, SLF001, PLC0415, PLR0915, E501, TRY003, EM101, ANN401
"""Unit tests for AuthCardAdminService, lockout mapping, and schemas (KB-P2-10)."""

from __future__ import annotations

import json
import os
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from sqlalchemy import text

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
    assert_local_admin_disable_allowed,
    extract_lockout_layer,
    map_sqlstate_to_lockout_error,
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

    prob = err.to_problem_exception()
    assert prob.status == 409
    assert prob.code == "LOCKOUT_PREVENTED"
    assert prob.extra is not None
    assert prob.extra.get("layer") == "db_trigger"

    err2 = LockoutPreventedError("db_trigger", detail="custom detail")
    assert err2.layer == "db_trigger"
    assert err2.detail == "custom detail"

    err3 = LockoutPreventedError(layer="handshake_probe_15m", detail="probe detail")
    assert err3.layer == "handshake_probe_15m"

    with pytest.raises(ProblemException) as exc_info:
        _raise_lockout_problem(err)
    assert exc_info.value.status == 409
    assert exc_info.value.code == "LOCKOUT_PREVENTED"

    # map_sqlstate_to_lockout_error
    e1 = Exception("LOCKOUT_PREVENTED: some error (layer=handshake_probe_15m)")
    mapped1 = map_sqlstate_to_lockout_error(e1)
    assert mapped1 is not None
    assert mapped1.layer == "handshake_probe_15m"

    e2 = Exception("LOCKOUT_PREVENTED: some db error")
    mapped2 = map_sqlstate_to_lockout_error(e2)
    assert mapped2 is not None
    assert mapped2.layer == "db_trigger"

    class _FakeDbapiError(Exception):
        sqlstate = "P0001"
        detail = "handshake_probe_15m"

    mapped3 = map_sqlstate_to_lockout_error(_FakeDbapiError("generic db error"))
    assert mapped3 is not None
    assert mapped3.layer == "handshake_probe_15m"

    assert map_sqlstate_to_lockout_error(Exception("unrelated error")) is None


@pytest.mark.asyncio
async def test_assert_local_admin_disable_allowed_branches(db_session: AsyncSession) -> None:
    """Test assert_local_admin_disable_allowed edge cases and empty conditions."""
    # 1. Non-existent card with explicit workspace -> returns silently
    await assert_local_admin_disable_allowed(db_session, uuid.uuid4(), uuid.uuid4())

    # 2. Workspace ID only without recent handshake -> raises LockoutPreventedError
    with pytest.raises(LockoutPreventedError):
        await assert_local_admin_disable_allowed(db_session, uuid.uuid4())

    # 3. Workspace without active admin -> returns silently
    ws_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "No Admin WS"},
    )
    c_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO auth_provider_cards "
            "(id, workspace_id, provider_kind, slug, display_name, sort_rank, is_enabled) "
            "VALUES (:id, :ws_id, 'LOCAL_ADMIN', 'c-no-admin', 'No Admin Card', 'V', TRUE)"
        ),
        {"id": c_id, "ws_id": ws_id},
    )
    await assert_local_admin_disable_allowed(db_session, c_id, ws_id)


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
        fallback_card = await service.create_card(
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
        await sess.execute(
            text(
                "INSERT INTO user_identities ("
                "  workspace_id, auth_card_id, principal_id, "
                "  immutable_subject_id, subject_email_at_link"
                ") VALUES (:ws_id, :cid, :pid, 'oidc-fallback-sub', 'admin@example.com')"
            ),
            {"ws_id": ws_id, "cid": fallback_card.id, "pid": admin_id},
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


@pytest.mark.asyncio
async def test_draft_handshake_ldap_and_google_json() -> None:
    """Test test_draft_handshake handling of LDAP plaintext vs JSON secrets and Google OAuth JSON."""
    from kanban.auth.cards.schemas import HandshakeProbeResult
    from kanban.security.envelope import SealedSecret, open_card_secret

    kek = StaticKekProvider({"kek-v1": os.urandom(32)}, "kek-v1")
    service = AuthCardAdminService(kek_provider=kek)
    actor_id = uuid.uuid4()

    mock_probe = HandshakeProbeResult(ok=True, status="OK", latency_ms=10)

    # 1. LDAP draft with plaintext password (not starting with '{')
    draft_ldap_plain = AuthCardCreate(
        provider_kind="LDAP",
        slug="draft-ldap-plain",
        display_name="Draft LDAP Plain",
        public_config={
            "kind": "LDAP",
            "url": "ldaps://127.0.0.1:10636",
            "base_dn": "dc=example,dc=com",
        },
        secret="plaintext-secret-123",
    )
    with patch(
        "kanban.auth.cards.service.probe_auth_card_handshake",
        new_callable=AsyncMock,
        return_value=mock_probe,
    ) as mock_p:
        res = await service.test_draft_handshake(draft_ldap_plain, actor_id=actor_id)
        assert res.ok is True
        assert mock_p.call_count == 1
        probed_card = mock_p.call_args[0][0]
        assert probed_card.encrypted_secret_blob is not None
        sealed = SealedSecret(
            encrypted_secret_blob=probed_card.encrypted_secret_blob,
            wrapped_dek=probed_card.wrapped_dek,
            dek_kid=probed_card.dek_kid,
        )
        unsealed = open_card_secret(probed_card.id, probed_card.provider_kind, sealed, kek)
        payload = json.loads(bytes(unsealed).decode("utf-8"))
        assert payload == {"bind_dn_password": "plaintext-secret-123"}

    # 2. LDAP draft with JSON secret already formatted
    draft_ldap_json = AuthCardCreate(
        provider_kind="LDAP",
        slug="draft-ldap-json",
        display_name="Draft LDAP JSON",
        public_config={
            "kind": "LDAP",
            "url": "ldaps://127.0.0.1:10636",
            "base_dn": "dc=example,dc=com",
        },
        secret='{"bind_dn_password": "existing-json-secret"}',
    )
    with patch(
        "kanban.auth.cards.service.probe_auth_card_handshake",
        new_callable=AsyncMock,
        return_value=mock_probe,
    ) as mock_p:
        res = await service.test_draft_handshake(draft_ldap_json, actor_id=actor_id)
        assert res.ok is True
        probed_card = mock_p.call_args[0][0]
        sealed = SealedSecret(
            encrypted_secret_blob=probed_card.encrypted_secret_blob,
            wrapped_dek=probed_card.wrapped_dek,
            dek_kid=probed_card.dek_kid,
        )
        unsealed = open_card_secret(probed_card.id, probed_card.provider_kind, sealed, kek)
        payload = json.loads(bytes(unsealed).decode("utf-8"))
        assert payload == {"bind_dn_password": "existing-json-secret"}

    # 3. OIDC draft with google_oauth_json (web format)
    draft_google_web = AuthCardCreate(
        provider_kind="OIDC",
        slug="draft-google-web",
        display_name="Draft Google Web",
        public_config={
            "kind": "OIDC",
            "issuer": "https://accounts.google.com",
            "client_id": "google-client-id",
        },
        google_oauth_json=json.dumps({
            "web": {
                "client_id": "google-client-id",
                "client_secret": "web-extracted-secret",
            }
        }),
    )
    with patch(
        "kanban.auth.cards.service.probe_auth_card_handshake",
        new_callable=AsyncMock,
        return_value=mock_probe,
    ) as mock_p:
        res = await service.test_draft_handshake(draft_google_web, actor_id=actor_id)
        assert res.ok is True
        probed_card = mock_p.call_args[0][0]
        sealed = SealedSecret(
            encrypted_secret_blob=probed_card.encrypted_secret_blob,
            wrapped_dek=probed_card.wrapped_dek,
            dek_kid=probed_card.dek_kid,
        )
        unsealed = open_card_secret(probed_card.id, probed_card.provider_kind, sealed, kek)
        assert bytes(unsealed).decode("utf-8") == "web-extracted-secret"

    # 4. OAUTH2 draft with google_oauth_json (installed format)
    draft_google_installed = AuthCardCreate(
        provider_kind="OAUTH2",
        slug="draft-google-inst",
        display_name="Draft Google Installed",
        public_config={
            "kind": "OAUTH2",
            "authorization_endpoint": "https://accounts.google.com/o/oauth2/auth",
            "token_endpoint": "https://oauth2.googleapis.com/token",
            "client_id": "google-client-id-inst",
        },
        google_oauth_json=json.dumps({
            "installed": {
                "client_id": "google-client-id-inst",
                "client_secret": "installed-extracted-secret",
            }
        }),
    )
    with patch(
        "kanban.auth.cards.service.probe_auth_card_handshake",
        new_callable=AsyncMock,
        return_value=mock_probe,
    ) as mock_p:
        res = await service.test_draft_handshake(draft_google_installed, actor_id=actor_id)
        assert res.ok is True
        probed_card = mock_p.call_args[0][0]
        sealed = SealedSecret(
            encrypted_secret_blob=probed_card.encrypted_secret_blob,
            wrapped_dek=probed_card.wrapped_dek,
            dek_kid=probed_card.dek_kid,
        )
        unsealed = open_card_secret(probed_card.id, probed_card.provider_kind, sealed, kek)
        assert bytes(unsealed).decode("utf-8") == "installed-extracted-secret"

    # 5. Malformed google_oauth_json with fallback secret
    draft_google_malformed = AuthCardCreate(
        provider_kind="OIDC",
        slug="draft-google-bad",
        display_name="Draft Google Bad",
        public_config={
            "kind": "OIDC",
            "issuer": "https://accounts.google.com",
            "client_id": "google-client-id",
        },
        google_oauth_json="{malformed-json-here",
        secret="fallback-secret-value",
    )
    with patch(
        "kanban.auth.cards.service.probe_auth_card_handshake",
        new_callable=AsyncMock,
        return_value=mock_probe,
    ) as mock_p:
        res = await service.test_draft_handshake(draft_google_malformed, actor_id=actor_id)
        assert res.ok is True
        probed_card = mock_p.call_args[0][0]
        sealed = SealedSecret(
            encrypted_secret_blob=probed_card.encrypted_secret_blob,
            wrapped_dek=probed_card.wrapped_dek,
            dek_kid=probed_card.dek_kid,
        )
        unsealed = open_card_secret(probed_card.id, probed_card.provider_kind, sealed, kek)
        assert bytes(unsealed).decode("utf-8") == "fallback-secret-value"

    # 5b. google_oauth_json with web block missing client_secret
    draft_google_no_secret = AuthCardCreate(
        provider_kind="OIDC",
        slug="draft-google-nosec",
        display_name="Draft Google No Secret",
        public_config={
            "kind": "OIDC",
            "issuer": "https://accounts.google.com",
            "client_id": "google-client-id",
        },
        google_oauth_json=json.dumps({"web": {"client_id": "cid"}}),
    )
    with patch(
        "kanban.auth.cards.service.probe_auth_card_handshake",
        new_callable=AsyncMock,
        return_value=mock_probe,
    ) as mock_p:
        res = await service.test_draft_handshake(draft_google_no_secret, actor_id=actor_id)
        assert res.ok is True
        probed_card = mock_p.call_args[0][0]
        assert probed_card.encrypted_secret_blob is None

    # 6. Service without KEK provider and no secret
    service_no_kek = AuthCardAdminService(kek_provider=None)
    draft_no_secret = AuthCardCreate(
        provider_kind="OIDC",
        slug="draft-no-sec",
        display_name="Draft No Secret",
        public_config={
            "kind": "OIDC",
            "issuer": "https://accounts.example.com",
            "client_id": "cid",
        },
    )
    with patch(
        "kanban.auth.cards.service.probe_auth_card_handshake",
        new_callable=AsyncMock,
        return_value=mock_probe,
    ) as mock_p:
        res = await service_no_kek.test_draft_handshake(draft_no_secret, actor_id=actor_id)
        assert res.ok is True
        probed_card = mock_p.call_args[0][0]
        assert probed_card.encrypted_secret_blob is None


@pytest.mark.asyncio
async def test_admin_service_validation_and_lockout_branches(db_session: AsyncSession) -> None:
    """Test service error branches: email limits, invalid configs, missing cards, and db errors."""
    import json
    from unittest.mock import AsyncMock, patch

    ws_id, admin_id, _ = await _setup_workspace_and_principals(db_session)
    factory = RLSSessionFactory(db_session.bind)  # type: ignore[arg-type]

    kek = StaticKekProvider({"kek-v1": os.urandom(32)}, "kek-v1")
    service = AuthCardAdminService(kek_provider=kek)
    admin_ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=2)

    google_json = json.dumps({
        "web": {
            "client_id": "1234567890-test.apps.googleusercontent.com",
            "client_secret": "GOCSPX-testsecret12345",
            "redirect_uris": ["https://kanban.example.com/api/v1/auth/oidc/google/callback"],
        }
    })

    async with factory.session(admin_ctx) as sess:
        # 1. create_card with plaintext LDAP secret
        ldap_data = AuthCardCreate(
            provider_kind="LDAP",
            slug="ldap-plain-create",
            display_name="LDAP Plain Create",
            is_enabled=False,
            sort_rank="A0",
            public_config={
                "kind": "LDAP",
                "url": "ldaps://ldap.example.com:636",
                "transport_mode": "ldaps",
                "base_dn": "dc=example,dc=com",
            },
            secret="plaintext-password",
        )
        created_ldap = await service.create_card(sess, ldap_data, actor_id=admin_id, workspace_id=ws_id)
        assert created_ldap.has_secret is True

        # 2. create_card with google_oauth_json and sort_rank=None (tests rank ending with 0 branch)
        create_google = AuthCardCreate(
            provider_kind="OIDC",
            slug="google-created-card",
            display_name="Google Created Card",
            public_config={},
            google_oauth_json=google_json,
        )
        created_g = await service.create_card(sess, create_google, actor_id=admin_id, workspace_id=ws_id)
        assert created_g.provider_kind == "OIDC"
        assert created_g.has_secret is True

        # create_card with existing slug and sort_rank=None (line 195)
        create_same_slug = AuthCardCreate(
            provider_kind="OIDC",
            slug="google-created-card",
            display_name="Google Same Slug",
            public_config={},
            google_oauth_json=google_json,
        )
        created_same = await service.create_card(sess, create_same_slug, actor_id=admin_id, workspace_id=ws_id)
        assert created_same.slug == "google-created-card"

        # 3. update_card with valid LDAP config (line 357-360)
        up_valid_ldap = AuthCardUpdate(
            public_config={
                "kind": "LDAP",
                "url": "ldaps://ldap2.example.com:636",
                "transport_mode": "ldaps",
                "base_dn": "dc=example,dc=com",
            }
        )
        updated_ldap = await service.update_card(sess, created_ldap.id, up_valid_ldap, actor_id=admin_id)
        assert updated_ldap.public_config.get("url") == "ldaps://ldap2.example.com:636"

        # update_card with google_oauth_json and clean public_config
        up_google = AuthCardUpdate(public_config={}, google_oauth_json=google_json)
        updated_google = await service.update_card(sess, created_ldap.id, up_google, actor_id=admin_id)
        assert updated_google.provider_kind == "OIDC"
        assert updated_google.public_config.get("client_id") == "1234567890-test.apps.googleusercontent.com"

        # 4. update_card disabling sole LOCAL_ADMIN -> LockoutPreventedError (lines 417-424)
        local_admin_card = await service.create_card(
            sess,
            AuthCardCreate(
                provider_kind="LOCAL_ADMIN",
                slug="sole-local-admin-unit",
                display_name="Sole Local Admin",
                is_enabled=True,
                public_config={},
            ),
            actor_id=admin_id,
            workspace_id=ws_id,
        )
        with pytest.raises(LockoutPreventedError):
            await service.update_card(
                sess, local_admin_card.id, AuthCardUpdate(is_enabled=False), actor_id=admin_id
            )

        # 4. update_card with invalid email domains (> 50) using model_construct to test service-level check
        up_bad_domains = AuthCardUpdate.model_construct(allowed_email_domains=[f"d{i}.com" for i in range(55)])
        with pytest.raises(ProblemException) as exc_domains:
            await service.update_card(sess, created_ldap.id, up_bad_domains, actor_id=admin_id)
        assert exc_domains.value.status == 422
        assert exc_domains.value.code == "INVALID_EMAIL_DOMAINS"

        # 5. update_card with invalid OIDC config
        up_bad_oidc = AuthCardUpdate(public_config={"kind": "OIDC", "issuer": "ftp://not-https"})
        with pytest.raises(ProblemException) as exc_oidc:
            await service.update_card(sess, created_ldap.id, up_bad_oidc, actor_id=admin_id)
        assert exc_oidc.value.status == 422
        assert exc_oidc.value.code == "INVALID_CARD_CONFIG"

        # 6. update_card with invalid LDAP config
        up_bad_ldap = AuthCardUpdate(public_config={"kind": "LDAP", "url": "ftp://not-ldap"})
        with pytest.raises(ProblemException) as exc_ldap:
            await service.update_card(sess, created_ldap.id, up_bad_ldap, actor_id=admin_id)
        assert exc_ldap.value.status == 422
        assert exc_ldap.value.code == "INVALID_CARD_CONFIG"

        # 7. set_enabled when state is already matching -> returns immediately
        res_already = await service.set_enabled(sess, created_ldap.id, is_enabled=False, actor_id=admin_id)
        assert res_already.is_enabled is False

        # 8. test_handshake on nonexistent card -> 404 ProblemException
        with pytest.raises(ProblemException) as exc_handshake_404:
            await service.test_handshake(sess, "nonexistent-card-slug", actor_id=admin_id)
        assert exc_handshake_404.value.status == 404

        # 9. reorder_card on nonexistent card -> 404 ProblemException
        with pytest.raises(ProblemException) as exc_reorder_404:
            await service.reorder_card(sess, "nonexistent-card-slug", after=None, actor_id=admin_id)
        assert exc_reorder_404.value.status == 404

        # 10. Test DB trigger LOCKOUT_PREVENTED mapping in update_card, set_enabled, delete_card
        class _LockoutDbError(Exception):
            sqlstate = "P0001"

        # Enable card first so update_card with is_enabled=False triggers disable execution
        await service.set_enabled(sess, created_ldap.id, is_enabled=True, actor_id=admin_id)

        orig_execute = sess.execute

        async def _mock_lockout_execute(stmt: Any, *args: Any, **kwargs: Any) -> Any:
            stmt_text = str(getattr(stmt, "text", stmt))
            if "card_admin_set_enabled" in stmt_text or "card_admin_delete" in stmt_text:
                raise _LockoutDbError("LOCKOUT_PREVENTED: (layer=db_trigger)")
            return await orig_execute(stmt, *args, **kwargs)

        with patch.object(sess, "execute", side_effect=_mock_lockout_execute):
            with pytest.raises(LockoutPreventedError) as exc_up_lockout:
                await service.update_card(
                    sess, created_ldap.id, AuthCardUpdate(is_enabled=False), actor_id=admin_id
                )
            assert exc_up_lockout.value.layer == "db_trigger"

            with pytest.raises(LockoutPreventedError) as exc_set_lockout:
                await service.set_enabled(sess, created_ldap.id, is_enabled=False, actor_id=admin_id)
            assert exc_set_lockout.value.layer == "db_trigger"

            with pytest.raises(LockoutPreventedError) as exc_del_lockout:
                await service.delete_card(sess, created_ldap.id, confirm_slug="ldap-plain-create", actor_id=admin_id)
            assert exc_del_lockout.value.layer == "db_trigger"

        # 11. Test admin_get returning None in create, update, set_enabled, reorder (lines 274, 461, 521, 613)
        with patch("kanban.auth.cards.service.admin_get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(ProblemException) as exc_cg:
                await service.create_card(sess, ldap_data, actor_id=admin_id, workspace_id=ws_id)
            assert exc_cg.value.status == 404

            with pytest.raises(ProblemException) as exc_ug:
                await service.update_card(sess, created_ldap.id, AuthCardUpdate(display_name="New"), actor_id=admin_id)
            assert exc_ug.value.status == 404

            with pytest.raises(ProblemException) as exc_sg:
                await service.set_enabled(sess, created_ldap.id, is_enabled=True, actor_id=admin_id)
            assert exc_sg.value.status == 404

            with pytest.raises(ProblemException) as exc_rg:
                await service.reorder_card(sess, created_ldap.id, after=None, actor_id=admin_id)
            assert exc_rg.value.status == 404

        # 12. update_card / set_enabled / delete_card DB error propagation when not LOCKOUT_PREVENTED
        class _UnexpectedDbError(Exception):
            pass

        # Re-enable card so disabling it triggers card_admin_set_enabled execution
        await service.set_enabled(sess, created_ldap.id, is_enabled=True, actor_id=admin_id)

        async def _mock_unexpected_execute(stmt: Any, *args: Any, **kwargs: Any) -> Any:
            stmt_text = str(getattr(stmt, "text", stmt))
            if "card_admin_set_enabled" in stmt_text or "card_admin_delete" in stmt_text:
                raise _UnexpectedDbError("connection terminated")
            return await orig_execute(stmt, *args, **kwargs)

        with patch.object(sess, "execute", side_effect=_mock_unexpected_execute):
            with pytest.raises(_UnexpectedDbError):
                await service.update_card(
                    sess, created_ldap.id, AuthCardUpdate(is_enabled=False), actor_id=admin_id
                )
            with pytest.raises(_UnexpectedDbError):
                await service.set_enabled(sess, created_ldap.id, is_enabled=False, actor_id=admin_id)
            with pytest.raises(_UnexpectedDbError):
                await service.delete_card(sess, created_ldap.id, confirm_slug="ldap-plain-create", actor_id=admin_id)

