# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for identity resolution and auto-provisioning (KB-P2-08)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from starlette.requests import Request

from database.session import RLSContext, RLSSessionFactory
from kanban.api.problems import ProblemException
from kanban.auth.identity import ExternalIdentityAssertion
from kanban.auth.identity_service import DatabaseIdentityResolver
from kanban.services.activity import ActivityEventType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


def _make_dummy_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/callback",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    )


async def _create_test_workspace_and_card(
    factory: RLSSessionFactory,
    *,
    auto_provision_users: bool = True,
    allowed_email_domains: list[str] | None = None,
    slug_suffix: str = "",
) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision test workspace and auth provider card."""
    ws_id = uuid.uuid4()
    p_id = uuid.uuid4()
    card_id = uuid.uuid4()
    suffix = slug_suffix or uuid.uuid4().hex[:6]

    ctx = RLSContext(principal_id=p_id, workspace_id=ws_id, aal_level=2)
    async with factory.session(ctx) as session:
        await session.execute(text("RESET SESSION AUTHORIZATION"))
        await session.execute(
            text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": ws_id, "slug": f"ws-resolv-{suffix}", "name": "Resolution Test WS"},
        )
        await session.execute(
            text(
                "INSERT INTO auth_provider_cards ("
                "  id, workspace_id, provider_kind, slug, display_name, is_enabled, sort_rank, "
                "  auto_provision_users, allowed_email_domains"
                ") VALUES ("
                "  :id, :ws_id, 'OIDC', :slug, 'Corp OIDC', true, '0|h00000:', :auto_prov, :domains"
                ")"
            ),
            {
                "id": card_id,
                "ws_id": ws_id,
                "slug": f"oidc-card-{suffix}",
                "auto_prov": auto_provision_users,
                "domains": allowed_email_domains or [],
            },
        )
    return ws_id, card_id


@pytest.mark.asyncio
async def test_case_1_auto_provision_and_subject_stability(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test Case 1: Positive auto-provision on 1st login and subject stability on 2nd login."""
    session_factory = RLSSessionFactory(pg_worker_db)
    ws_id, card_id = await _create_test_workspace_and_card(
        session_factory,
        auto_provision_users=True,
        allowed_email_domains=["corp.example"],
    )

    resolver = DatabaseIdentityResolver(session_factory=session_factory)
    req = _make_dummy_request()

    # 1. First login: auto-provisions new user U1
    assertion1 = ExternalIdentityAssertion(
        card_id=card_id,
        subject="sub-maya-001",
        email="maya@corp.example",
        email_verified=True,
        display_name="Maya Lin",
        groups=(),
    )
    resolved1 = await resolver.resolve(assertion1, req, None)
    assert resolved1.workspace_id == ws_id
    assert resolved1.aal_level == 1
    assert resolved1.mfa_pending is False
    user_id = resolved1.principal_id

    # Verify user exists in users and user_identities
    ctx = RLSContext(principal_id=user_id, workspace_id=ws_id, aal_level=1)
    async with session_factory.session(ctx) as session:
        await session.execute(text("RESET SESSION AUTHORIZATION"))
        u_row = await session.execute(
            text("SELECT email FROM users WHERE id = :id"),
            {"id": user_id},
        )
        assert u_row.scalar_one() == "maya@corp.example"

        ident_row = await session.execute(
            text("SELECT immutable_subject_id FROM user_identities WHERE principal_id = :id"),
            {"id": user_id},
        )
        assert ident_row.scalar_one() == "sub-maya-001"

    # 2. Second login: IdP email changed to maya.lin@corp.example, but subject is unchanged
    assertion2 = ExternalIdentityAssertion(
        card_id=card_id,
        subject="sub-maya-001",
        email="maya.lin@corp.example",
        email_verified=True,
        display_name="Maya Lin Renamed",
        groups=(),
    )
    resolved2 = await resolver.resolve(assertion2, req, None)
    # Subject stability: resolves to the exact same user_id U1!
    assert resolved2.principal_id == user_id
    assert resolved2.workspace_id == ws_id


@pytest.mark.asyncio
async def test_case_2_pre_hijack_defense_blocks_auto_merge(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test Case 2: Security pre-hijack scenario.

    Existing user with victim@corp.example causes 409 IDENTITY_LINK_REQUIRED
    and records IDENTITY_AUTO_MERGE_BLOCKED activity without touching victim account.
    """
    session_factory = RLSSessionFactory(pg_worker_db)
    ws_id, card_id = await _create_test_workspace_and_card(
        session_factory,
        auto_provision_users=True,
        allowed_email_domains=["corp.example"],
    )

    # Pre-create victim user in workspace
    victim_id = uuid.uuid4()
    ctx = RLSContext(principal_id=victim_id, workspace_id=ws_id, aal_level=2)
    async with session_factory.session(ctx) as session:
        await session.execute(text("RESET SESSION AUTHORIZATION"))
        await session.execute(
            text(
                "INSERT INTO principals (id, principal_type, workspace_id, status, display_name) "
                "VALUES (:id, 'USER', :ws, 'ACTIVE', 'Victim User')"
            ),
            {"id": victim_id, "ws": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO objects ("
                "  id, object_type, workspace_id, canonical_key, display_title, created_by_id"
                ") VALUES (:id, 'user', :ws, 'victim@corp.example', 'Victim User', :id)"
            ),
            {"id": victim_id, "ws": ws_id},
        )
        await session.execute(
            text(
                "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
                "VALUES (:id, 'user', 'USER', :ws, 'victim@corp.example')"
            ),
            {"id": victim_id, "ws": ws_id},
        )

    resolver = DatabaseIdentityResolver(session_factory=session_factory)
    req = _make_dummy_request()

    # Attacker asserts new subject with victim's email
    attacker_assertion = ExternalIdentityAssertion(
        card_id=card_id,
        subject="attacker-sub-999",
        email="victim@corp.example",
        email_verified=True,
        display_name="Victim Impersonator",
        groups=(),
    )

    with pytest.raises(ProblemException) as exc_info:
        await resolver.resolve(attacker_assertion, req, None)

    assert exc_info.value.code == "IDENTITY_LINK_REQUIRED"
    assert exc_info.value.status == 409

    # Verify victim account was NOT bound to attacker's subject
    async with session_factory.session(ctx) as session:
        await session.execute(text("RESET SESSION AUTHORIZATION"))
        ident_check = await session.execute(
            text(
                "SELECT COUNT(*) FROM user_identities "
                "WHERE immutable_subject_id = 'attacker-sub-999'"
            )
        )
        assert ident_check.scalar_one() == 0

        # Verify IDENTITY_AUTO_MERGE_BLOCKED was recorded
        act_check = await session.execute(
            text(
                "SELECT COUNT(*) FROM activity_records "
                "WHERE event_type = :etype AND workspace_id = :ws"
            ),
            {"etype": ActivityEventType.IDENTITY_AUTO_MERGE_BLOCKED, "ws": ws_id},
        )
        assert act_check.scalar_one() >= 1


@pytest.mark.asyncio
async def test_case_3_same_subject_across_different_cards(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test Case 3: Same subject on Card A and Card B resolve independently."""
    session_factory = RLSSessionFactory(pg_worker_db)
    _ws_id_a, card_a = await _create_test_workspace_and_card(
        session_factory, auto_provision_users=True, slug_suffix="card-a"
    )
    _ws_id_b, card_b = await _create_test_workspace_and_card(
        session_factory, auto_provision_users=True, slug_suffix="card-b"
    )

    resolver = DatabaseIdentityResolver(session_factory=session_factory)
    req = _make_dummy_request()

    assertion_a = ExternalIdentityAssertion(
        card_id=card_a,
        subject="common-sub-1001",
        email="alice@company-a.example",
        email_verified=True,
        display_name="Alice A",
        groups=(),
    )
    resolved_a = await resolver.resolve(assertion_a, req, None)

    assertion_b = ExternalIdentityAssertion(
        card_id=card_b,
        subject="common-sub-1001",
        email="bob@company-b.example",
        email_verified=True,
        display_name="Bob B",
        groups=(),
    )
    resolved_b = await resolver.resolve(assertion_b, req, None)

    # Distinct cards -> distinct users even with identical subject "common-sub-1001"
    assert resolved_a.principal_id != resolved_b.principal_id


@pytest.mark.asyncio
async def test_case_4_unverified_email_domain_forbidden_and_unprovisioned(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test Case 4: Email verification, domain allowlist, and auto-provision gates."""
    session_factory = RLSSessionFactory(pg_worker_db)
    ws_id, card_id = await _create_test_workspace_and_card(
        session_factory,
        auto_provision_users=True,
        allowed_email_domains=["allowed.example"],
        slug_suffix="sec-card",
    )

    resolver = DatabaseIdentityResolver(session_factory=session_factory)
    req = _make_dummy_request()

    # 1. email_verified = False -> 403 EMAIL_NOT_VERIFIED
    assertion_unverified = ExternalIdentityAssertion(
        card_id=card_id,
        subject="sub-unverified",
        email="user@allowed.example",
        email_verified=False,
        display_name="Unverified User",
        groups=(),
    )
    with pytest.raises(ProblemException) as exc_unverified:
        await resolver.resolve(assertion_unverified, req, None)
    assert exc_unverified.value.code == "EMAIL_NOT_VERIFIED"
    assert exc_unverified.value.status == 403

    # 2. Forbidden domain -> 403 EMAIL_DOMAIN_FORBIDDEN
    assertion_bad_domain = ExternalIdentityAssertion(
        card_id=card_id,
        subject="sub-bad-domain",
        email="user@other.example",
        email_verified=True,
        display_name="Other Domain User",
        groups=(),
    )
    with pytest.raises(ProblemException) as exc_bad_domain:
        await resolver.resolve(assertion_bad_domain, req, None)
    assert exc_bad_domain.value.code == "EMAIL_DOMAIN_FORBIDDEN"
    assert exc_bad_domain.value.status == 403

    # 3. auto_provision_users = False -> 403 IDENTITY_NOT_PROVISIONED
    ctx = RLSContext(principal_id=uuid.uuid4(), workspace_id=ws_id, aal_level=2)
    async with session_factory.session(ctx) as session:
        await session.execute(text("RESET SESSION AUTHORIZATION"))
        await session.execute(
            text("UPDATE auth_provider_cards SET auto_provision_users = false WHERE id = :id"),
            {"id": card_id},
        )

    assertion_unprov = ExternalIdentityAssertion(
        card_id=card_id,
        subject="sub-unprov",
        email="user@allowed.example",
        email_verified=True,
        display_name="Allowed User",
        groups=(),
    )
    with pytest.raises(ProblemException) as exc_unprov:
        await resolver.resolve(assertion_unprov, req, None)
    assert exc_unprov.value.code == "IDENTITY_NOT_PROVISIONED"
    assert exc_unprov.value.status == 403


@pytest.mark.asyncio
async def test_case_9_admin_mfa_gate_on_external_login(
    pg_worker_db: AsyncEngine,
) -> None:
    """Test Case 9: External login for SERVER_ADMIN principal receives mfa_pending=True."""
    session_factory = RLSSessionFactory(pg_worker_db)
    ws_id, card_id = await _create_test_workspace_and_card(
        session_factory,
        auto_provision_users=True,
        allowed_email_domains=["admin.example"],
        slug_suffix="admin-card",
    )

    resolver = DatabaseIdentityResolver(session_factory=session_factory)
    req = _make_dummy_request()

    # Auto-provision user
    assertion = ExternalIdentityAssertion(
        card_id=card_id,
        subject="sub-admin-001",
        email="superadmin@admin.example",
        email_verified=True,
        display_name="Super Admin",
        groups=(),
    )
    resolved = await resolver.resolve(assertion, req, None)
    admin_id = resolved.principal_id
    assert resolved.mfa_pending is False  # Non-admin on initial auto-provision

    # Elevate principal to SERVER_ADMIN in role_bindings
    ctx = RLSContext(principal_id=admin_id, workspace_id=ws_id, aal_level=2)
    async with session_factory.session(ctx) as session:
        await session.execute(text("RESET SESSION AUTHORIZATION"))
        await session.execute(
            text(
                "INSERT INTO role_bindings (id, workspace_id, principal_id, role, scope_type) "
                "VALUES (:id, :ws, :p_id, 'SERVER_ADMIN', 'server')"
            ),
            {"id": uuid.uuid4(), "ws": ws_id, "p_id": admin_id},
        )

    # Second login: now holds SERVER_ADMIN role -> mfa_pending must be True!
    resolved_admin = await resolver.resolve(assertion, req, None)
    assert resolved_admin.principal_id == admin_id
    assert resolved_admin.aal_level == 1
    assert resolved_admin.mfa_pending is True


@pytest.mark.asyncio
async def test_disabled_principal_blocks_login(
    pg_worker_db: AsyncEngine,
) -> None:
    """Verify bound identity with status != ACTIVE raises 403 ACCOUNT_DISABLED."""
    session_factory = RLSSessionFactory(pg_worker_db)
    ws_id, card_id = await _create_test_workspace_and_card(
        session_factory, auto_provision_users=True, slug_suffix="disabled-test"
    )

    resolver = DatabaseIdentityResolver(session_factory=session_factory)
    req = _make_dummy_request()

    assertion = ExternalIdentityAssertion(
        card_id=card_id,
        subject="sub-disable-01",
        email="disable@example.com",
        email_verified=True,
        display_name="Disabled User",
        groups=(),
    )
    resolved = await resolver.resolve(assertion, req, None)

    # Disable principal
    ctx = RLSContext(principal_id=resolved.principal_id, workspace_id=ws_id, aal_level=2)
    async with session_factory.session(ctx) as session:
        await session.execute(text("RESET SESSION AUTHORIZATION"))
        await session.execute(
            text("UPDATE principals SET status = 'DISABLED' WHERE id = :id"),
            {"id": resolved.principal_id},
        )

    with pytest.raises(ProblemException) as exc_info:
        await resolver.resolve(assertion, req, None)

    assert exc_info.value.code == "ACCOUNT_DISABLED"
    assert exc_info.value.status == 403
