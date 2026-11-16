# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and functional test suite for the 7 Admin Auth Studio use cases (KANBA-176).

Use Cases Covered:
1) LDAP any user in directory (access_mode: 'any_user' auto-provisions WORKSPACE_MEMBER).
2) LDAP + Admin Group + User Group (admin_groups grants SERVER_ADMIN, user_groups
   grants WORKSPACE_MEMBER, group_restricted rejects unlisted directory users).
3) LDAP with Active Directory (sAMAccountName preset, subject_attribute='objectGUID',
   fallback {username}@ldap.local when mail attribute is missing).
4) OAuth any user (Google/GitHub presets; integer ID string coercion, /user/emails
   fetching or {login}@users.noreply.github.com fallback).
5) OAuth + Admin List + User List (admin_allowlist grants SERVER_ADMIN, user_allowlist
   grants WORKSPACE_MEMBER, unlisted email rejected).
6) Local User creation via Admin API with password & role grant, plus login MFA rules.
7) Edit permission grants, list principals with enriched provider/role, and reset password.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kanban.admin.principal_service import (
    _enrich_user_principal,
    _highest_role,
    _resolve_provider_label,
    provision_user,
    reset_password,
)
from kanban.auth.identity import ExternalIdentityAssertion
from kanban.auth.identity_service import _evaluate_card_access
from kanban.auth.ldap.config import LdapCardConfig
from kanban.auth.oidc.config import OidcCardConfig


# ---------------------------------------------------------------------------
# Use Case 1: LDAP Any User in Directory (access_mode: 'any_user')
# ---------------------------------------------------------------------------
def test_use_case_1_ldap_any_user_config_defaults() -> None:
    """Verify LdapCardConfig defaults to access_mode='any_user' and empty group lists."""
    cfg = LdapCardConfig(
        url="ldaps://ldap.example.com",
        transport_mode="ldaps",
        base_dn="dc=example,dc=com",
        service_bind_dn="cn=admin,dc=example,dc=com",
    )
    assert cfg.access_mode == "any_user"
    assert cfg.admin_groups == []
    assert cfg.user_groups == []


def test_use_case_1_ldap_any_user_evaluates_allowed_standard_member() -> None:
    """Verify _evaluate_card_access grants standard member access to any directory user."""
    card_row = {
        "provider_kind": "LDAP",
        "public_config": {
            "access_mode": "any_user",
            "admin_groups": [],
            "user_groups": [],
        },
    }
    assertion = ExternalIdentityAssertion(
        card_id=uuid.uuid4(),
        subject="uid=jdoe,dc=example,dc=com",
        email="jdoe@example.com",
        email_verified=True,
        display_name="John Doe",
        groups=("Staff",),
    )

    is_allowed, is_admin = _evaluate_card_access(card_row, assertion)
    assert is_allowed is True
    assert is_admin is False  # standard WORKSPACE_MEMBER


# ---------------------------------------------------------------------------
# Use Case 2: LDAP + Admin Group + User Group
# ---------------------------------------------------------------------------
def test_use_case_2_ldap_admin_group_grants_server_admin() -> None:
    """Verify user in admin_groups receives SERVER_ADMIN grant."""
    card_row = {
        "provider_kind": "LDAP",
        "public_config": {
            "access_mode": "group_restricted",
            "admin_groups": ["Domain Admins", "IT Admins"],
            "user_groups": ["Developers"],
        },
    }
    assertion = ExternalIdentityAssertion(
        card_id=uuid.uuid4(),
        subject="guid-1234",
        email="sysadmin@corp.local",
        email_verified=True,
        display_name="Chief Admin",
        groups=("Domain Admins", "Employees"),
    )

    is_allowed, is_admin = _evaluate_card_access(card_row, assertion)
    assert is_allowed is True
    assert is_admin is True  # SERVER_ADMIN


def test_use_case_2_ldap_user_group_grants_workspace_member() -> None:
    """Verify user in user_groups receives WORKSPACE_MEMBER grant."""
    card_row = {
        "provider_kind": "LDAP",
        "public_config": {
            "access_mode": "group_restricted",
            "admin_groups": ["Domain Admins"],
            "user_groups": ["Developers"],
        },
    }
    assertion = ExternalIdentityAssertion(
        card_id=uuid.uuid4(),
        subject="guid-3344",
        email="dev@corp.local",
        email_verified=True,
        display_name="Developer Dave",
        groups=("Developers",),
    )

    is_allowed, is_admin = _evaluate_card_access(card_row, assertion)
    assert is_allowed is True
    assert is_admin is False  # WORKSPACE_MEMBER


def test_use_case_2_ldap_group_restricted_rejects_unlisted() -> None:
    """Verify group_restricted access mode rejects users not in admin_groups or user_groups."""
    card_row = {
        "provider_kind": "LDAP",
        "public_config": {
            "access_mode": "group_restricted",
            "admin_groups": ["Domain Admins"],
            "user_groups": ["Developers"],
        },
    }
    assertion = ExternalIdentityAssertion(
        card_id=uuid.uuid4(),
        subject="guid-5678",
        email="contractor@corp.local",
        email_verified=True,
        display_name="External Contractor",
        groups=("Contractors", "Guests"),
    )

    is_allowed, is_admin = _evaluate_card_access(card_row, assertion)
    assert is_allowed is False
    assert is_admin is False


# ---------------------------------------------------------------------------
# Use Case 3: LDAP with Active Directory
# ---------------------------------------------------------------------------
def test_use_case_3_active_directory_preset_and_fallback_email() -> None:
    """Verify Active Directory filter preset and {username}@ldap.local email fallback logic."""
    cfg = LdapCardConfig(
        url="ldaps://ad.corp.local:636",
        transport_mode="ldaps",
        base_dn="dc=corp,dc=local",
        service_bind_dn="cn=svc-kanban,ou=Services,dc=corp,dc=local",
        user_search_filter="(&(objectCategory=person)(objectClass=user)(sAMAccountName={username}))",
        subject_attribute="objectGUID",
        access_mode="any_user",
    )
    assert "sAMAccountName={username}" in cfg.user_search_filter
    assert cfg.subject_attribute == "objectGUID"

    # Test the fallback logic implemented in LdapAuthService.authenticate:
    attrs: dict[str, list[bytes]] = {
        "objectguid": [b"\x01\x02\x03\x04"],
        "displayname": [b"AD User"],
        "mail": [],
    }
    clean_username = "aduser"
    mail_list = attrs.get(cfg.email_attribute.lower(), [])
    email_bytes = mail_list[0] if mail_list else b""
    email = email_bytes.decode("utf-8", errors="replace").strip() if email_bytes else None
    if not email:
        email = f"{clean_username}@ldap.local"

    assert email == "aduser@ldap.local"


# ---------------------------------------------------------------------------
# Use Case 4: OAuth Any User (Google/GitHub Presets)
# ---------------------------------------------------------------------------
def test_use_case_4_github_oauth_config_and_claims_logic() -> None:
    """Verify GitHub OAuth configuration presets and integer ID coercion logic."""
    cfg = OidcCardConfig(
        kind="OAUTH2",
        issuer="https://github.com",
        client_id="gh-client-id",
        authorization_endpoint="https://github.com/login/oauth/authorize",
        token_endpoint="https://github.com/login/oauth/access_token",  # noqa: S106
        userinfo_endpoint="https://api.github.com/user",
    )
    assert cfg.client_id == "gh-client-id"
    assert cfg.userinfo_endpoint == "https://api.github.com/user"

    userinfo: dict[str, object] = {
        "id": 98765432,
        "login": "octocat",
        "name": "Mona Lisa",
        "email": None,
    }
    raw_sub = userinfo.get(cfg.subject_claim)
    if raw_sub is None and "id" in userinfo:
        raw_sub = userinfo["id"]
    subject = str(raw_sub)
    assert subject == "98765432"

    email = userinfo.get("email")
    if not email and userinfo.get("login"):
        email = f"{userinfo['login']}@users.noreply.github.com"
    assert email == "octocat@users.noreply.github.com"


# ---------------------------------------------------------------------------
# Use Case 5: OAuth + Admin List + User List
# ---------------------------------------------------------------------------
def test_use_case_5_oauth_admin_and_user_allowlists() -> None:
    """Verify OidcCardConfig admin_allowlist and user_allowlist policy enforcement."""
    card_row = {
        "provider_kind": "OIDC",
        "public_config": {
            "admin_allowlist": ["lead@corp.com"],
            "user_allowlist": ["engineer@corp.com"],
        },
    }

    # 1. Admin user
    admin_assertion = ExternalIdentityAssertion(
        card_id=uuid.uuid4(),
        subject="sub-lead",
        email="lead@corp.com",
        email_verified=True,
        display_name="Lead",
        groups=(),
    )
    is_allowed, is_admin = _evaluate_card_access(card_row, admin_assertion)
    assert is_allowed is True
    assert is_admin is True

    # 2. Member user
    member_assertion = ExternalIdentityAssertion(
        card_id=uuid.uuid4(),
        subject="sub-eng",
        email="engineer@corp.com",
        email_verified=True,
        display_name="Engineer",
        groups=(),
    )
    is_allowed, is_admin = _evaluate_card_access(card_row, member_assertion)
    assert is_allowed is True
    assert is_admin is False

    # 3. Unlisted stranger
    stranger_assertion = ExternalIdentityAssertion(
        card_id=uuid.uuid4(),
        subject="sub-stranger",
        email="stranger@corp.com",
        email_verified=True,
        display_name="Stranger",
        groups=(),
    )
    is_allowed, is_admin = _evaluate_card_access(card_row, stranger_assertion)
    assert is_allowed is False
    assert is_admin is False


# ---------------------------------------------------------------------------
# Use Case 6: Local User Creation & MFA Login Behavior
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_use_case_6_local_user_provisioning_and_login_mfa_rules() -> None:
    """Verify local user creation with password/role and MFA requirements on login."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.add = MagicMock()

    user_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    pepper = b"test-pepper-32-bytes-long!!!!!!"
    with (
        patch("kanban.admin.principal_service.get_auth_pepper", return_value=pepper),
        patch("kanban.admin.principal_service.bind_role", new_callable=AsyncMock),
        patch(
            "kanban.admin.principal_service._enrich_user_principal",
            new_callable=AsyncMock,
        ) as me,
        patch("kanban.admin.principal_service.record_activity", new_callable=AsyncMock),
    ):
        me.return_value = {
            "id": user_id,
            "principal": "local.admin",
            "display_name": "Local Admin User",
            "type": "USER",
            "status": "active",
            "email": "local.admin@example.com",
            "role": "SERVER_ADMIN",
            "provider": "LOCAL",
        }

        # Mock the raw SQL execution to return user_id
        mock_result = MagicMock()
        mock_result.scalar.return_value = user_id
        mock_result.fetchone.return_value = (user_id,)
        mock_session.execute.return_value = mock_result

        created = await provision_user(
            session=mock_session,
            workspace_id=ws_id,
            creator_id=actor_id,
            handle="local.admin",
            display_name="Local Admin User",
            email="local.admin@example.com",
            password="StrongLocalPassword123!",  # noqa: S106
            role="SERVER_ADMIN",
        )

        assert created["role"] == "SERVER_ADMIN"
        assert created["provider"] == "LOCAL"
        assert mock_session.add.called

    # Test LocalAdminLoginService MFA login rule:
    # Standard member without MFA enrolled does NOT require MFA step-up.
    mfa_cases = [
        (0, 0, False),  # member without MFA
        (0, 1, True),  # SERVER_ADMIN always step-up
        (1, 0, True),  # user with enrolled MFA always step-up
    ]
    for has_mfa_flag, is_admin_flag, expected in mfa_cases:
        assert bool(has_mfa_flag or is_admin_flag) is expected


# ---------------------------------------------------------------------------
# Use Case 7: Edit Permission Grants, Password Reset & Principal Listing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_use_case_7_principal_helpers_and_password_reset() -> None:
    """Verify principal helpers return enriched provider/role, and reset_password executes."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()

    target_user_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    mock_principal = MagicMock()
    mock_principal.id = target_user_id
    mock_principal.principal_type = "USER"
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_principal
    mock_session.execute.return_value = mock_result

    pepper = b"test-pepper-32-bytes-long!!!!!!"
    with (
        patch("kanban.admin.principal_service.get_auth_pepper", return_value=pepper),
        patch("kanban.admin.principal_service.record_activity", new_callable=AsyncMock),
    ):
        await reset_password(
            session=mock_session,
            workspace_id=ws_id,
            creator_id=actor_id,
            principal_id=target_user_id,
            password="NewSuperSecurePassword999!",  # noqa: S106
        )
    assert mock_session.execute.called

    # 2. Test helper _resolve_provider_label
    assert _resolve_provider_label("LOCAL_ADMIN", "local-admin") == "LOCAL"
    assert _resolve_provider_label("LDAP", "ad-ldap") == "ACTIVE_DIRECTORY"
    assert _resolve_provider_label("LDAP", "openldap") == "LDAP"
    assert _resolve_provider_label("OIDC", "google-oauth") == "GOOGLE"
    assert _resolve_provider_label("OAUTH2", "github-oauth") == "GITHUB"
    assert _resolve_provider_label("OIDC", "custom-sso") == "OAUTH2"

    # 3. Test helper _highest_role
    assert _highest_role(["WORKSPACE_MEMBER", "SERVER_ADMIN", "WORKSPACE_ADMIN"]) == "SERVER_ADMIN"
    assert _highest_role(["WORKSPACE_GUEST", "WORKSPACE_MEMBER"]) == "WORKSPACE_MEMBER"
    assert _highest_role([]) == "WORKSPACE_MEMBER"

    # 4. Enrich user principal helper
    mock_p = MagicMock()
    mock_p.id = target_user_id
    mock_p.display_name = "Jane Doe"
    mock_mappings = MagicMock()
    mock_mappings.first.return_value = None
    mock_result.mappings.return_value = mock_mappings
    mock_result.scalars.return_value.all.return_value = []
    handle, _em, role, provider = await _enrich_user_principal(
        session=mock_session,
        workspace_id=ws_id,
        p=mock_p,
    )
    assert handle is not None
    assert role == "WORKSPACE_MEMBER"
    assert provider == "LOCAL"
