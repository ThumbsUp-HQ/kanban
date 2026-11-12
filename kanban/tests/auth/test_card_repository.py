"""Unit and integration tests for Auth Provider Cards repository and schemas (KB-P2-03)."""

from __future__ import annotations

import json
import os
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from database.models.auth import AuthProviderCard
from kanban.auth.cards.repository import (
    admin_get,
    admin_list,
    admin_upsert,
    card_rewrap,
    get_for_login,
    list_enabled_public,
    rewrap_all,
    to_admin_schema,
)
from kanban.auth.cards.schemas import AuthCardAdmin, AuthCardPublic
from kanban.security.envelope import StaticKekProvider, seal_card_secret


@pytest.fixture
def kek_provider() -> StaticKekProvider:
    """Fixture providing StaticKekProvider with kek-v1 and kek-v2."""
    k1 = os.urandom(32)
    k2 = os.urandom(32)
    return StaticKekProvider(
        keys={"kek-v1": k1, "kek-v2": k2},
        current="kek-v1",
    )


async def _setup_admin_session(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision workspace and SERVER_ADMIN principal with AAL2 session context."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Repo WS"},
    )

    u_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{u_id.hex}",
            "title": "Repo Admin User",
            "u_id": u_id,
        },
    )

    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Repo Admin User', 'ACTIVE')"
        ),
        {"id": u_id, "ws_id": ws_id},
    )

    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'repo-admin@example.com')"
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

    # Bind session context
    await session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"p_id": str(u_id), "w_id": str(ws_id)},
    )

    return ws_id, u_id


def test_09_serializer_and_repr_invariants() -> None:
    """Test Case 9: Schema properties and model representations never leak secret ciphertext."""
    forbidden = ("encrypted_secret_blob", "wrapped_dek", "client_secret", "bind_password", "secret")

    # 1. AuthCardPublic schema verification
    pub_props = AuthCardPublic.model_json_schema().get("properties", {})
    for f in forbidden:
        assert f not in pub_props

    # 2. AuthCardAdmin schema verification
    admin_props = AuthCardAdmin.model_json_schema().get("properties", {})
    for f in forbidden:
        assert f not in admin_props
    assert "has_secret" in admin_props

    # 3. Model repr and str sanitize ciphertext
    card = AuthProviderCard(
        id=uuid.uuid4(),
        provider_kind="OIDC",
        slug="github-login",
        display_name="GitHub",
        sort_rank="0|hzzzzz:",
        encrypted_secret_blob=b"\x01verysecretciphertextblob1234567890",
        wrapped_dek=b"\x01verywrappeddekblob1234567890",
    )
    repr_str = repr(card)
    str_val = str(card)

    assert "verysecret" not in repr_str
    assert "verywrapped" not in repr_str
    assert "encrypted_secret_blob" not in repr_str
    assert "wrapped_dek" not in repr_str
    assert repr_str == str_val

    # 4. json.dumps of AuthCardAdmin contains no secret bytes or ciphertext
    admin_schema = to_admin_schema(card)
    dumped = json.dumps(admin_schema.model_dump(mode="json"))
    assert "verysecret" not in dumped
    assert "verywrapped" not in dumped
    assert "encrypted_secret_blob" not in dumped
    assert "wrapped_dek" not in dumped
    assert "client_secret" not in dumped
    assert "bind_password" not in dumped
    assert '"has_secret": true' in dumped


@pytest.mark.asyncio
async def test_card_repository_lifecycle(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Verify repository admin upsert, get, list, login retrieval, and rewrap operations."""
    ws_id, _admin_id = await _setup_admin_session(db_session)

    # 1. Upsert a disabled card without secrets
    c1_id = uuid.uuid4()
    upserted_id1 = await admin_upsert(
        db_session,
        card_id=c1_id,
        workspace_id=ws_id,
        provider_kind="LOCAL_ADMIN",
        slug="local-admin",
        display_name="Local Administrator",
        button_subtext="Username & password",
        icon_preset="shield",
        is_enabled=False,
        sort_rank="0|h00000:",
    )
    assert upserted_id1 == c1_id

    # 2. Upsert an enabled OIDC card with sealed secret
    c2_id = uuid.uuid4()
    sealed = seal_card_secret(c2_id, "OIDC", b"google-client-secret-999", kek_provider)
    upserted_id2 = await admin_upsert(
        db_session,
        card_id=c2_id,
        workspace_id=ws_id,
        provider_kind="OIDC",
        slug="google-sso",
        display_name="Google Workspace",
        button_subtext="Sign in with Google",
        icon_preset="google",
        is_enabled=True,
        sort_rank="0|h11111:",
        auto_provision_users=True,
        allowed_email_domains=["example.com"],
        public_config={"client_id": "google-client-123.apps.googleusercontent.com"},
        encrypted_secret_blob=sealed.encrypted_secret_blob,
        wrapped_dek=sealed.wrapped_dek,
        dek_kid=sealed.dek_kid,
    )
    assert upserted_id2 == c2_id

    # 3. Public list returns only enabled cards
    public_cards = await list_enabled_public(db_session)
    assert len(public_cards) == 1
    assert public_cards[0].slug == "google-sso"
    assert public_cards[0].display_name == "Google Workspace"
    assert public_cards[0].provider_kind == "OIDC"

    # 4. get_for_login retrieves card row with ciphertext
    login_card = await get_for_login(db_session, "google-sso")
    assert login_card is not None
    assert login_card.id == c2_id
    assert login_card.encrypted_secret_blob == sealed.encrypted_secret_blob
    assert login_card.wrapped_dek == sealed.wrapped_dek

    # get_for_login on disabled card returns None
    disabled_card = await get_for_login(db_session, "local-admin")
    assert disabled_card is None

    # get_for_login on nonexistent slug returns None
    missing_card = await get_for_login(db_session, "nonexistent-slug")
    assert missing_card is None

    # 5. admin_get retrieves card by ID
    admin_c1 = await admin_get(db_session, c1_id)
    assert admin_c1 is not None
    assert admin_c1.slug == "local-admin"

    missing_admin_card = await admin_get(db_session, uuid.uuid4())
    assert missing_admin_card is None

    # 6. admin_list retrieves all cards ordered by sort rank
    all_cards = await admin_list(db_session)
    assert len(all_cards) == 2
    assert all_cards[0].slug == "local-admin"
    assert all_cards[1].slug == "google-sso"

    # 7. card_rewrap single card
    new_wrapped_mock = b"\x01" + os.urandom(12) + os.urandom(48)
    rewrapped = await card_rewrap(db_session, c2_id, new_wrapped_mock, "kek-v1", "kek-v2")
    assert rewrapped is True

    # Check updated kid
    updated_card = await admin_get(db_session, c2_id)
    assert updated_card is not None
    assert updated_card.dek_kid == "kek-v2"
    assert updated_card.wrapped_dek == new_wrapped_mock

    # card_rewrap with mismatched old_kid returns False
    rewrap_fail = await card_rewrap(db_session, c2_id, new_wrapped_mock, "kek-v1", "kek-v3")
    assert rewrap_fail is False

    # 8. rewrap_all test
    # Re-seal card 2 under kek-v1 so rewrap_all has work to do
    sealed_v1 = seal_card_secret(c2_id, "OIDC", b"google-secret-v1", kek_provider)
    await admin_upsert(
        db_session,
        card_id=c2_id,
        workspace_id=ws_id,
        provider_kind="OIDC",
        slug="google-sso",
        display_name="Google Workspace",
        sort_rank="0|h11111:",
        encrypted_secret_blob=sealed_v1.encrypted_secret_blob,
        wrapped_dek=sealed_v1.wrapped_dek,
        dek_kid="kek-v1",
    )

    count = await rewrap_all(db_session, kek_provider, "kek-v2")
    assert count == 1

    final_card = await admin_get(db_session, c2_id)
    assert final_card is not None
    assert final_card.dek_kid == "kek-v2"

    # Second run when all cards already on kek-v2 should skip and return 0
    count2 = await rewrap_all(db_session, kek_provider, "kek-v2")
    assert count2 == 0
