# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0915, PLR0913, PLR0917, SLF001, ANN401, D401, S106, PLC0415, FBT001, FBT002, PYI034, PYI036, TRY003, EM101, ARG002
"""Targeted unit tests achieving >=95% branch & statement coverage across auth modules (KAN-27)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import FastAPI
from starlette.requests import Request

from database.models.auth import (
    AuthProviderCard,
    IdentityLinkIntent,
    LdapGroupMapping,
    LocalAdminCredential,
    OidcAuthRequest,
    RecoveryCode,
    SetupClaimToken,
    TotpFactor,
    UserIdentity,
    UserSession,
    WebauthnChallenge,
    WebauthnCredential,
)
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.api.v1.auth_identities import (
    IdentityLinkStartRequest,
    _check_mfa_and_admin,
    start_identity_link,
)
from kanban.auth.identity import ExternalIdentityAssertion
from kanban.auth.identity_service import (
    DatabaseIdentityResolver,
    IdentityLinkService,
    _ensure_server_admin_role,
    _evaluate_card_access,
)
from kanban.auth.oidc.flow import OidcFlow, sanitize_return_to
from kanban.security.keys import KeyMaterial, derive_subkey


def make_assertion(
    card_id: uuid.UUID | None = None,
    subject: str = "alice-sub",
    email: str | None = "alice@corp.example.test",
    email_verified: bool = True,
    display_name: str | None = "Alice",
    groups: tuple[str, ...] = ("engineering",),
) -> ExternalIdentityAssertion:
    """Helper to instantiate complete ExternalIdentityAssertion with valid invariants."""
    return ExternalIdentityAssertion(
        card_id=card_id or uuid.uuid4(),
        subject=subject,
        email=email,
        email_verified=email_verified,
        display_name=display_name,
        groups=groups,
    )


# ==============================================================================
# 1. Database Auth Models __repr__ and __str__ Tests (100% database/models/auth.py)
# ==============================================================================


def test_auth_models_repr_and_str() -> None:
    """Verify __repr__ and __str__ on all 12 models in database/models/auth.py."""
    u1 = uuid.uuid4()
    c1 = uuid.uuid4()
    now = datetime.now(UTC)

    models = [
        AuthProviderCard(
            id=c1,
            slug="test-oidc",
            provider_kind="OIDC",
            is_enabled=True,
            sort_rank="0|h00000:",
            dek_kid="kek-v1",
        ),
        UserSession(
            id=uuid.uuid4(),
            principal_id=u1,
            workspace_id=uuid.uuid4(),
            aal_level=1,
            idle_expires_at=now,
            absolute_expires_at=now,
            mfa_pending=False,
            revoked_at=None,
        ),
        LocalAdminCredential(
            principal_id=u1,
            username="admin",
            pepper_kid="pepper-v1",
            password_hash="hashval",
        ),
        OidcAuthRequest(
            id=uuid.uuid4(),
            card_id=c1,
            state_hash=b"123",
            nonce=b"123",
            code_verifier_sealed=b"123",
            browser_binding_hash=b"123",
            expires_at=now,
            consumed_at=None,
        ),
        TotpFactor(
            id=uuid.uuid4(),
            principal_id=u1,
            status="ACTIVE",
            encrypted_secret_blob=b"sec",
            wrapped_dek=b"dek",
            last_accepted_step=1,
        ),
        RecoveryCode(
            id=uuid.uuid4(),
            principal_id=u1,
            code_hmac=b"code",
            used_at=None,
        ),
        LdapGroupMapping(
            id=uuid.uuid4(),
            card_id=c1,
            workspace_id=uuid.uuid4(),
            ldap_dn="cn=admins",
            group_name="admins",
        ),
        WebauthnCredential(
            id=uuid.uuid4(),
            principal_id=u1,
            credential_id=b"c",
            public_key=b"k",
            sign_count=0,
            nickname="My Key",
            suspect_clone_at=None,
        ),
        WebauthnChallenge(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            purpose="reg",
            challenge=b"ch",
            expires_at=now,
            consumed_at=None,
        ),
        UserIdentity(
            id=uuid.uuid4(),
            auth_card_id=c1,
            principal_id=u1,
            immutable_subject_id="sub-1",
            last_login_at=None,
        ),
        IdentityLinkIntent(
            id=uuid.uuid4(),
            principal_id=u1,
            session_id=uuid.uuid4(),
            target_card_id=c1,
            expires_at=now,
            consumed_at=None,
        ),
        SetupClaimToken(
            id=uuid.uuid4(),
            token_hmac=b"th",
            expires_at=now,
            consumed_at=None,
            revoked_at=None,
        ),
    ]

    for model in models:
        r = repr(model)
        s = str(model)
        assert len(r) > 0
        assert r == s


# ==============================================================================
# 2. auth_identities.py Targeted Tests (Lines 73, 75, 77, 209)
# ==============================================================================


@pytest.mark.asyncio
async def test_compute_link_aal2_requirement_all_methods() -> None:
    """Exercise _check_mfa_and_admin lines 73, 75, 77 (totp, webauthn, recovery)."""
    mock_factory = MagicMock()
    mock_session = AsyncMock()
    mock_factory.session.return_value.__aenter__.return_value = mock_session

    mock_admin_res = MagicMock()
    mock_admin_res.scalar_one_or_none.return_value = None

    mock_status_res = MagicMock()
    mock_status_res.mappings.return_value.first.return_value = {
        "has_active_totp": True,
        "webauthn_credential_count": 2,
        "unused_recovery_codes": 3,
    }

    mock_session.execute.side_effect = [mock_admin_res, mock_status_res]

    principal = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("session",),
        aal_level=1,
    )
    is_required, methods = await _check_mfa_and_admin(mock_factory, principal)
    assert is_required is True
    assert "totp" in methods
    assert "webauthn" in methods
    assert "recovery" in methods


@pytest.mark.asyncio
async def test_start_identity_link_singular_cookie_header() -> None:
    """Exercise start_identity_link line 209 (cookie_header singular fallback)."""
    mock_factory = MagicMock()
    mock_ctx_session = AsyncMock()
    mock_factory.session.return_value.__aenter__.return_value = mock_ctx_session

    principal = PrincipalContext(
        principal_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        token_scopes=("session",),
        aal_level=2,
    )
    app = FastAPI()
    app.state.session_factory = mock_factory
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/identities/link/start",
            "headers": [],
            "app": app,
        }
    )
    body = IdentityLinkStartRequest(card_slug="corp-sso")

    with patch(
        "kanban.api.v1.auth_identities.IdentityLinkService.start_link",
        new_callable=AsyncMock,
    ) as mock_start:
        mock_start.return_value = {
            "mode": "redirect",
            "authorize_url": "https://auth.example.test/authorize?state=abc",
            "cookie_header": "kb_oidc=cookieval123; Path=/; Secure; HttpOnly",
        }
        resp = await start_identity_link(
            request=request,
            body=body,
            principal=principal,
        )
        assert resp.status_code == 200
        headers_dict = dict(resp.raw_headers)
        assert b"set-cookie" in headers_dict
        assert b"kb_oidc=cookieval123" in headers_dict[b"set-cookie"]


# ==============================================================================
# 3. kanban/auth/identity_service.py Coverage
# ==============================================================================


def test_evaluate_card_access_edge_cases() -> None:
    """Exercise _evaluate_card_access lines 47, 51, 63, 65, 67, 77-94."""
    assertion = make_assertion(
        subject="alice-sub",
        email="alice@corp.example.test",
        display_name="Alice Smith",
        groups=("engineering", "devops"),
    )

    # Line 47: card_row is None
    allowed, admin = _evaluate_card_access(None, assertion)
    assert allowed is True
    assert admin is False

    # Line 51: public_config is not a dict
    allowed, admin = _evaluate_card_access({"public_config": "not_a_dict"}, assertion)
    assert allowed is True
    assert admin is False

    # Line 63: LDAP admin_groups match
    card_ldap_admin = {
        "public_config": {
            "access_mode": "group_restricted",
            "admin_groups": ["engineering"],
            "user_groups": ["contractors"],
        }
    }
    allowed, admin = _evaluate_card_access(card_ldap_admin, assertion)
    assert allowed is True
    assert admin is True

    # Line 65: LDAP user_groups match
    card_ldap_user = {
        "public_config": {
            "access_mode": "group_restricted",
            "admin_groups": ["superadmins"],
            "user_groups": ["devops"],
        }
    }
    allowed, admin = _evaluate_card_access(card_ldap_user, assertion)
    assert allowed is True
    assert admin is False

    # Line 67: group_restricted and neither matches
    card_ldap_reject = {
        "public_config": {
            "access_mode": "group_restricted",
            "admin_groups": ["superadmins"],
            "user_groups": ["interns"],
        }
    }
    allowed, admin = _evaluate_card_access(card_ldap_reject, assertion)
    assert allowed is False
    assert admin is False

    # Lines 86-94: admin_allowlist and user_allowlist candidate matching
    # Matches email prefix
    card_oidc_admin = {
        "public_config": {
            "admin_allowlist": ["alice"],
            "user_allowlist": ["bob"],
        }
    }
    allowed, admin = _evaluate_card_access(card_oidc_admin, assertion)
    assert allowed is True
    assert admin is True

    # Matches subject in user_allowlist
    card_oidc_user = {
        "public_config": {
            "admin_allowlist": ["bob"],
            "user_allowlist": ["alice-sub"],
        }
    }
    allowed, admin = _evaluate_card_access(card_oidc_user, assertion)
    assert allowed is True
    assert admin is False

    # Matches display_name in admin_allowlist
    card_oidc_disp = {
        "public_config": {
            "admin_allowlist": ["Alice Smith"],
            "user_allowlist": [],
        }
    }
    allowed, admin = _evaluate_card_access(card_oidc_disp, assertion)
    assert allowed is True
    assert admin is True

    # Allowlist configured but no candidate matches -> False, False (Line 94)
    card_oidc_none = {
        "public_config": {
            "admin_allowlist": ["bob@example.test"],
            "user_allowlist": ["charlie@example.test"],
        }
    }
    allowed, admin = _evaluate_card_access(card_oidc_none, assertion)
    assert allowed is False
    assert admin is False


@pytest.mark.asyncio
async def test_ensure_server_admin_role_fallback() -> None:
    """Exercise _ensure_server_admin_role lines 103-120 (fallback on routine failure)."""
    mock_session = MagicMock()
    mock_session.info = {}

    class MockNested:
        async def __aenter__(self) -> MockNested:
            return self

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    mock_session.begin_nested = MagicMock(return_value=MockNested())
    mock_session.execute = AsyncMock(
        side_effect=[
            Exception("DB routine failed"),
            MagicMock(),  # Direct INSERT success
        ]
    )

    await _ensure_server_admin_role(mock_session, uuid.uuid4(), uuid.uuid4())
    assert mock_session.execute.call_count == 2
    assert "INSERT INTO role_bindings" in str(mock_session.execute.call_args_list[1][0][0])


def test_validate_assertion_email_branches() -> None:
    """Exercise DatabaseIdentityResolver._validate_assertion_email lines 428, 437-440."""
    card_row = {"allowed_email_domains": ["corp.example.test", "subsidiary.example.test"]}

    # Missing email
    with pytest.raises(ProblemException) as exc1:
        DatabaseIdentityResolver._validate_assertion_email(
            card_row,
            make_assertion(email=None, email_verified=True),
        )
    assert exc1.value.code == "EMAIL_NOT_VERIFIED"

    # Unverified email
    with pytest.raises(ProblemException) as exc2:
        DatabaseIdentityResolver._validate_assertion_email(
            card_row,
            make_assertion(email="a@corp.example.test", email_verified=False),
        )
    assert exc2.value.code == "EMAIL_NOT_VERIFIED"

    # Forbidden domain
    with pytest.raises(ProblemException) as exc3:
        DatabaseIdentityResolver._validate_assertion_email(
            card_row,
            make_assertion(email="a@gmail.com", email_verified=True),
        )
    assert exc3.value.code == "EMAIL_DOMAIN_FORBIDDEN"

    # Valid domain
    DatabaseIdentityResolver._validate_assertion_email(
        card_row,
        make_assertion(email="a@corp.example.test", email_verified=True),
    )


@pytest.mark.asyncio
async def test_resolve_bound_login_branches() -> None:
    """Exercise _resolve_bound_login lines 325-330, 359-364, 371, 404-405."""
    resolver = DatabaseIdentityResolver()
    mock_session = AsyncMock()
    mock_session.info = {}

    card_id = uuid.uuid4()
    principal_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    ident_id = uuid.uuid4()

    # 1. Status != ACTIVE -> ACCOUNT_DISABLED (Lines 325-330)
    with pytest.raises(ProblemException) as exc_disabled:
        await resolver._resolve_bound_login(
            mock_session,
            make_assertion(card_id=card_id),
            {
                "id": ident_id,
                "principal_id": principal_id,
                "workspace_id": workspace_id,
                "status": "DISABLED",
            },
        )
    assert exc_disabled.value.code == "ACCOUNT_DISABLED"

    # 2. Allowlist rejects -> IDENTITY_NOT_PROVISIONED (Lines 359-364)
    mock_card_res = MagicMock()
    mock_card_res.mappings.return_value.first.return_value = {
        "id": card_id,
        "workspace_id": workspace_id,
        "provider_kind": "OIDC",
        "public_config": {"user_allowlist": ["only_bob@test.com"]},
    }
    mock_session.execute.side_effect = [
        MagicMock(),  # set_config
        mock_card_res,  # card_get_by_id
    ]
    with pytest.raises(ProblemException) as exc_prov:
        await resolver._resolve_bound_login(
            mock_session,
            make_assertion(card_id=card_id, email="alice@test.com"),
            {
                "id": ident_id,
                "principal_id": principal_id,
                "workspace_id": workspace_id,
                "status": "ACTIVE",
            },
        )
    assert exc_prov.value.code == "IDENTITY_NOT_PROVISIONED"


@pytest.mark.asyncio
async def test_resolve_unbound_login_branches() -> None:
    """Exercise _resolve_unbound_login lines 463-469, 478-484, 493-519, 527-537, 540-541, 548-553."""
    resolver = DatabaseIdentityResolver()
    mock_session = AsyncMock()
    mock_session.info = {}

    class MockNested:
        async def __aenter__(self) -> MockNested:
            return self

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    mock_session.begin_nested = MagicMock(return_value=MockNested())

    card_id = uuid.uuid4()
    assertion = make_assertion(card_id=card_id)

    # 1. Card not found or not enabled -> IDENTITY_NOT_PROVISIONED (Lines 463-469)
    mock_card_disabled = MagicMock()
    mock_card_disabled.mappings.return_value.first.return_value = {
        "id": card_id,
        "is_enabled": False,
        "workspace_id": uuid.uuid4(),
    }
    mock_session.execute.side_effect = [mock_card_disabled]
    with pytest.raises(ProblemException) as exc1:
        await resolver._resolve_unbound_login(mock_session, assertion)
    assert exc1.value.code == "IDENTITY_NOT_PROVISIONED"

    # 2. auto_provision_users is False -> IDENTITY_NOT_PROVISIONED (Lines 493-519)
    ws_id = uuid.uuid4()
    mock_card_no_auto = MagicMock()
    mock_card_no_auto.mappings.return_value.first.return_value = {
        "id": card_id,
        "is_enabled": True,
        "workspace_id": ws_id,
        "auto_provision_users": False,
        "allowed_email_domains": [],
        "provider_kind": "OIDC",
        "public_config": {},
    }
    mock_session.execute.side_effect = [
        mock_card_no_auto,
        MagicMock(),  # set_config
        MagicMock(),  # record_activity
    ]
    with pytest.raises(ProblemException) as exc2:
        await resolver._resolve_unbound_login(mock_session, assertion)
    assert exc2.value.code == "IDENTITY_NOT_PROVISIONED"

    # 3. user not in allowlist -> Access Denied (Lines 527-537)
    mock_card_restricted = MagicMock()
    mock_card_restricted.mappings.return_value.first.return_value = {
        "id": card_id,
        "is_enabled": True,
        "workspace_id": ws_id,
        "auto_provision_users": True,
        "allowed_email_domains": [],
        "provider_kind": "OIDC",
        "public_config": {"user_allowlist": ["bob@corp.example.test"]},
    }
    mock_session.execute.side_effect = [
        mock_card_restricted,
        MagicMock(),  # set_config
    ]
    with pytest.raises(ProblemException) as exc3:
        await resolver._resolve_unbound_login(mock_session, assertion)
    assert exc3.value.code == "IDENTITY_NOT_PROVISIONED"


@pytest.mark.asyncio
async def test_provision_user_error_branches() -> None:
    """Exercise _provision_user lines 599-601, 627-628, 644-651, 655, 671-672."""
    resolver = DatabaseIdentityResolver()
    mock_session = AsyncMock()
    mock_session.info = {}

    class MockNested:
        async def __aenter__(self) -> MockNested:
            return self

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    mock_session.begin_nested = MagicMock(return_value=MockNested())

    ws_id = uuid.uuid4()
    card_id = uuid.uuid4()
    assertion = make_assertion(card_id=card_id, display_name="Alice")

    # 1. IDENTITY_ALREADY_LINKED in exc -> raises IDENTITY_ALREADY_LINKED (Lines 644-650)
    mock_session.execute.side_effect = Exception("error: IDENTITY_ALREADY_LINKED detected")
    with pytest.raises(ProblemException) as exc1:
        await resolver._provision_user(mock_session, ws_id, assertion)
    assert exc1.value.code == "IDENTITY_ALREADY_LINKED"

    # 2. Arbitrary exception is re-raised (Line 651)
    mock_session.execute.side_effect = ValueError("Some other database constraint failure")
    with pytest.raises(ValueError, match="Some other database constraint failure"):
        await resolver._provision_user(mock_session, ws_id, assertion)

    # 3. prov_row is None -> RuntimeError (Line 655)
    mock_res_none = MagicMock()
    mock_res_none.mappings.return_value.first.return_value = None
    mock_session.execute.side_effect = [mock_res_none]
    with pytest.raises(RuntimeError, match="Failed to provision new user identity"):
        await resolver._provision_user(mock_session, ws_id, assertion)


@pytest.mark.asyncio
async def test_identity_link_service_link_ldap_auth_user_fn() -> None:
    """Exercise IdentityLinkService.link_ldap lines 856-857 (auth_user_fn fallback)."""
    service = IdentityLinkService()
    mock_session = AsyncMock()

    card_id = uuid.uuid4()
    intent_id = uuid.uuid4()
    principal_id = uuid.uuid4()
    session_id = uuid.uuid4()

    mock_intent_res = MagicMock()
    mock_intent_res.mappings.return_value.first.return_value = {
        "id": intent_id,
        "principal_id": principal_id,
        "session_id": session_id,
        "target_card_id": card_id,
        "status": "PENDING",
        "consumed_at": None,
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
    }

    mock_card = AuthProviderCard(
        id=card_id,
        workspace_id=uuid.uuid4(),
        slug="test-ldap",
        provider_kind="LDAP",
        display_name="Corp LDAP",
        is_enabled=True,
    )

    class CustomLdapAuthService:
        def __init__(self) -> None:
            self.auth_called = False

        async def authenticate_user(self, *args: Any, **kwargs: Any) -> None:
            self.auth_called = True

    custom_ldap = CustomLdapAuthService()

    app = FastAPI()
    app.state.ldap_auth_service = custom_ldap

    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/identities/link/ldap",
            "headers": [],
            "app": app,
        }
    )
    assert mock_card.workspace_id is not None
    principal = PrincipalContext(
        principal_id=principal_id,
        workspace_id=mock_card.workspace_id,
        token_scopes=("session",),
        aal_level=2,
        session_id=session_id,
    )
    req.state.principal = principal

    mock_session.execute.return_value = mock_intent_res
    mock_session.scalar.return_value = "test-ldap"

    with patch(
        "kanban.auth.identity_service.get_for_login",
        new_callable=AsyncMock,
        return_value=mock_card,
    ):
        result = await service.link_ldap(
            mock_session,
            principal,
            intent_id,
            username="ldapuser",
            password="ldappassword",
            request=req,
        )
        assert result["linked"] is True
        assert custom_ldap.auth_called is True


# ==============================================================================
# 4. kanban/auth/oidc/flow.py Coverage
# ==============================================================================


def test_sanitize_return_to_backslash_unquoted() -> None:
    """Exercise sanitize_return_to line 85 (unquoted URL with backslash returns '/')."""
    assert sanitize_return_to("/path%5Cextra") == "/"
    assert sanitize_return_to("/safe/path") == "/safe/path"
    assert sanitize_return_to("https://external.attack.test") == "/"


def test_resolve_public_origin_branches() -> None:
    """Exercise OidcFlow._resolve_public_origin lines 194, 200, 206-207."""
    km = KeyMaterial(master_kek=b"m" * 32, auth_pepper=b"p" * 32, session_hmac_key=b"s" * 32)
    flow = OidcFlow(key_material=km, public_origin="https://default.example.com")

    # Line 194: KANBAN_PUBLIC_ORIGIN environment variable set
    orig_env = os.environ.get("KANBAN_PUBLIC_ORIGIN")
    try:
        os.environ["KANBAN_PUBLIC_ORIGIN"] = "https://env.example.com/"
        assert flow._resolve_public_origin(None) == "https://env.example.com"
    finally:
        if orig_env is not None:
            os.environ["KANBAN_PUBLIC_ORIGIN"] = orig_env
        else:
            os.environ.pop("KANBAN_PUBLIC_ORIGIN", None)

    # Line 200: x-forwarded-proto and x-forwarded-host
    req_forwarded = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (b"x-forwarded-proto", b"https"),
                (b"x-forwarded-host", b"proxy.example.com"),
            ],
        }
    )
    assert flow._resolve_public_origin(req_forwarded) == "https://proxy.example.com"

    # Line 206-207: host only and request.base_url
    req_host = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"host", b"direct.example.com")],
        }
    )
    assert flow._resolve_public_origin(req_host) == "http://direct.example.com"


@pytest.mark.asyncio
async def test_oidc_flow_callback_error_branches() -> None:
    """Exercise OidcFlow.callback lines 444, 457-458, 468, 558-559, 571-572, 611, 657, 729-773."""
    km = KeyMaterial(master_kek=b"m" * 32, auth_pepper=b"p" * 32, session_hmac_key=b"s" * 32)
    flow = OidcFlow(key_material=km)
    mock_session = AsyncMock()
    mock_session.info = {}

    card_id = uuid.uuid4()

    # 1. Line 444: code_verifier_sealed < 28 bytes
    mock_res_short = MagicMock()
    mock_res_short.mappings.return_value.first.return_value = {
        "status": "OK",
        "card_id": card_id,
        "nonce": b"1234567890123456",
        "code_verifier_sealed": b"too_short",
        "return_to": "/",
        "link_intent_id": None,
    }
    mock_session.execute.side_effect = [mock_res_short]
    with pytest.raises(ProblemException) as exc1:
        await flow.callback(
            mock_session,
            "test-slug",
            code="test-code",
            state="test-state",
            browser_binding_cookie="test-cookie",
        )
    assert exc1.value.code == "OIDC_STATE_INVALID"
    assert exc1.value.detail is not None
    assert "Corrupt sealed code verifier" in exc1.value.detail

    # 2. Lines 457-458: Corrupt ciphertext AESGCM decryption fails
    mock_res_corrupt_ct = MagicMock()
    mock_res_corrupt_ct.mappings.return_value.first.return_value = {
        "status": "OK",
        "card_id": card_id,
        "nonce": b"1234567890123456",
        "code_verifier_sealed": b"123456789012" + b"bad_ciphertext_data_here_1234",
        "return_to": "/",
        "link_intent_id": None,
    }
    mock_session.execute.side_effect = [mock_res_corrupt_ct]
    with pytest.raises(ProblemException) as exc2:
        await flow.callback(
            mock_session,
            "test-slug",
            code="test-code",
            state="test-state",
            browser_binding_cookie="test-cookie",
        )
    assert exc2.value.code == "OIDC_STATE_INVALID"
    assert exc2.value.detail is not None
    assert "Failed to decrypt code verifier" in exc2.value.detail

    # 3. Line 468: Card not found or card.id != req_card_id
    sub_key = derive_subkey(km.master_kek, "oidc/code-verifier")
    nonce = b"n" * 12
    valid_ct = AESGCM(sub_key).encrypt(nonce, b"valid-code-verifier", card_id.bytes)
    sealed = nonce + valid_ct

    mock_res_valid_sealed = MagicMock()
    mock_res_valid_sealed.mappings.return_value.first.return_value = {
        "status": "OK",
        "card_id": card_id,
        "nonce": b"1234567890123456",
        "code_verifier_sealed": sealed,
        "return_to": "/",
        "link_intent_id": None,
    }
    mock_session.execute.side_effect = [
        mock_res_valid_sealed,
        MagicMock(mappings=lambda: MagicMock(first=lambda: None)),
    ]
    with pytest.raises(ProblemException) as exc3:
        await flow.callback(
            mock_session,
            "test-slug",
            code="test-code",
            state="test-state",
            browser_binding_cookie="test-cookie",
        )
    assert exc3.value.code == "AUTH_PROVIDER_NOT_FOUND"


def test_evaluate_card_access_missing_fields() -> None:
    """Exercise _evaluate_card_access branches 78->81, 81->83, 83->86."""
    from kanban.auth.identity_service import _evaluate_card_access

    card_row = {"public_config": {"user_allowlist": ["alice"]}}

    assertion_empty = ExternalIdentityAssertion(
        card_id=uuid.uuid4(),
        subject="sub_nomatch",
        email=None,
        email_verified=False,
        display_name=None,
        groups=(),
    )
    is_allowed, is_admin = _evaluate_card_access(card_row, assertion_empty)
    assert is_allowed is False
    assert is_admin is False

    assertion_sub = ExternalIdentityAssertion(
        card_id=uuid.uuid4(),
        subject="alice",
        email=None,
        email_verified=False,
        display_name=None,
        groups=(),
    )
    is_allowed2, is_admin2 = _evaluate_card_access(card_row, assertion_sub)
    assert is_allowed2 is True
    assert is_admin2 is False

    assertion_dn = ExternalIdentityAssertion(
        card_id=uuid.uuid4(),
        subject="sub_dn",
        email=None,
        email_verified=False,
        display_name="Alice",
        groups=(),
    )
    is_allowed3, is_admin3 = _evaluate_card_access(card_row, assertion_dn)
    assert is_allowed3 is True
    assert is_admin3 is False


@pytest.mark.asyncio
async def test_ensure_server_admin_role_success() -> None:
    """Exercise _ensure_server_admin_role line 110 (success return)."""
    mock_session = MagicMock()
    mock_session.info = {}

    class MockNested:
        async def __aenter__(self) -> MockNested:
            return self

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    mock_session.begin_nested = MagicMock(return_value=MockNested())
    mock_session.execute = AsyncMock(return_value=MagicMock())

    await _ensure_server_admin_role(mock_session, uuid.uuid4(), uuid.uuid4())
    assert mock_session.execute.call_count == 1


@pytest.mark.asyncio
async def test_database_identity_resolver_open_session_branches() -> None:
    """Exercise DatabaseIdentityResolver._open_session lines 172-201."""
    # Sessionmaker branch: success path
    mock_session = AsyncMock(
        spec=["in_transaction", "commit", "rollback", "begin", "execute", "info"]
    )
    mock_session.info = {}
    mock_session.begin = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.in_transaction.return_value = True

    class MockMakerContext:
        async def __aenter__(self) -> Any:
            return mock_session

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    mock_factory_maker = MagicMock(spec=["sessionmaker"])
    mock_factory_maker.sessionmaker = MagicMock(return_value=MockMakerContext())

    resolver = DatabaseIdentityResolver(session_factory=mock_factory_maker)
    dummy_req = Request({"type": "http", "method": "GET", "path": "/", "headers": []})

    async with resolver._open_session(dummy_req) as sess:
        assert sess == mock_session
    assert mock_session.commit.called

    # Sessionmaker branch: exception path
    mock_session_fail = AsyncMock(
        spec=["in_transaction", "commit", "rollback", "begin", "execute", "info"]
    )
    mock_session_fail.info = {}
    mock_session_fail.begin = AsyncMock()
    mock_session_fail.rollback = AsyncMock()
    mock_session_fail.execute = AsyncMock()
    mock_session_fail.in_transaction.return_value = True

    class MockMakerContextFail:
        async def __aenter__(self) -> Any:
            return mock_session_fail

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    mock_factory_fail = MagicMock(spec=["sessionmaker"])
    mock_factory_fail.sessionmaker = MagicMock(return_value=MockMakerContextFail())
    resolver_fail = DatabaseIdentityResolver(session_factory=mock_factory_fail)

    with pytest.raises(RuntimeError):
        async with resolver_fail._open_session(dummy_req):
            raise RuntimeError("test session fail")
    assert mock_session_fail.rollback.called

    # Callable branch (lines 192-201)
    mock_sess_callable = AsyncMock()

    class MockCallableContext:
        async def __aenter__(self) -> Any:
            return mock_sess_callable

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    mock_callable_factory = MagicMock(return_value=MockCallableContext())
    del mock_callable_factory.session
    del mock_callable_factory.sessionmaker
    resolver_callable = DatabaseIdentityResolver(session_factory=mock_callable_factory)

    async with resolver_callable._open_session(dummy_req) as sess:
        assert sess == mock_sess_callable


@pytest.mark.asyncio
async def test_resolve_bound_login_admin_card_and_activity_error() -> None:
    """Exercise DatabaseIdentityResolver._resolve_bound_login lines 371, 404-405."""
    resolver = DatabaseIdentityResolver()
    mock_session = AsyncMock()
    mock_session.info = {}

    card_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    pid = uuid.uuid4()
    ident_id = uuid.uuid4()

    mock_card_row = {
        "id": card_id,
        "workspace_id": ws_id,
        "provider_kind": "OIDC",
        "public_config": {"admin_allowlist": ["alice@corp.example.test"]},
    }
    mock_identity_row = {
        "id": ident_id,
        "principal_id": pid,
        "workspace_id": ws_id,
        "status": "ACTIVE",
    }
    assertion = make_assertion(card_id=card_id, email="alice@corp.example.test")

    mock_card_res = MagicMock()
    mock_card_res.mappings.return_value.first.return_value = mock_card_row

    mock_admin_res = MagicMock()
    mock_admin_res.scalar.return_value = 1

    mock_session.execute.side_effect = [
        MagicMock(),  # set_config
        mock_card_res,  # card_get_by_id
        MagicMock(),  # identity_record_login
        mock_admin_res,  # role_bindings check
    ]

    with (
        patch(
            "kanban.auth.identity_service.record_activity",
            new_callable=AsyncMock,
            side_effect=Exception("Activity logging network error"),
        ),
        patch(
            "kanban.auth.identity_service._ensure_server_admin_role",
            new_callable=AsyncMock,
        ) as mock_ensure,
    ):
        resolved = await resolver._resolve_bound_login(
            mock_session,
            assertion,
            mock_identity_row,
        )
        assert resolved.principal_id == pid
        assert mock_ensure.called


@pytest.mark.asyncio
async def test_resolve_unbound_login_workspace_fallback_and_admin() -> None:
    """Exercise _resolve_unbound_login lines 478-484, 505-506, 540-541, 548-553."""
    resolver = DatabaseIdentityResolver()

    card_id = uuid.uuid4()
    assertion = make_assertion(card_id=card_id, email="bob@corp.example.test")

    # 1. effective_ws_id is None when auto_provision_users=True -> line 540-541 RuntimeError
    mock_session_none = AsyncMock()
    mock_session_none.info = {}

    class MockNested:
        async def __aenter__(self) -> MockNested:
            return self

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    mock_session_none.begin_nested = MagicMock(return_value=MockNested())
    mock_card_res_none = MagicMock()
    mock_card_res_none.mappings.return_value.first.return_value = {
        "id": card_id,
        "is_enabled": True,
        "workspace_id": None,
        "auto_provision_users": True,
        "allowed_email_domains": [],
        "provider_kind": "OIDC",
        "public_config": {},
    }
    mock_session_none.execute.side_effect = [mock_card_res_none]
    mock_session_none.scalar.side_effect = [Exception("No default ws routine"), None]

    with patch(
        "kanban.auth.identity_service._evaluate_card_access",
        return_value=(True, False),
    ):
        with pytest.raises(RuntimeError) as exc_none:
            await resolver._resolve_unbound_login(mock_session_none, assertion)
        assert "No target workspace found" in str(exc_none.value)

    # 2. record_activity fails in auto_provision_users=False -> line 505-506
    ws_id = uuid.uuid4()
    mock_session_act_fail = AsyncMock()
    mock_session_act_fail.info = {}
    mock_card_res_no_auto = MagicMock()
    mock_card_res_no_auto.mappings.return_value.first.return_value = {
        "id": card_id,
        "is_enabled": True,
        "workspace_id": ws_id,
        "auto_provision_users": False,
        "allowed_email_domains": [],
        "provider_kind": "OIDC",
        "public_config": {},
    }
    mock_session_act_fail.execute.side_effect = [
        mock_card_res_no_auto,
        MagicMock(),  # set_config
    ]
    with patch(
        "kanban.auth.identity_service.record_activity",
        new_callable=AsyncMock,
        side_effect=Exception("Unprovisioned activity error"),
    ):
        with pytest.raises(ProblemException) as exc_unprov:
            await resolver._resolve_unbound_login(mock_session_act_fail, assertion)
        assert exc_unprov.value.code == "IDENTITY_NOT_PROVISIONED"

    # 3. is_admin_user=True in unbound login -> lines 548-553 (_ensure_server_admin_role called)
    mock_session_admin = AsyncMock()
    mock_session_admin.info = {}
    mock_card_res_admin = MagicMock()
    mock_card_res_admin.mappings.return_value.first.return_value = {
        "id": card_id,
        "is_enabled": True,
        "workspace_id": ws_id,
        "auto_provision_users": True,
        "allowed_email_domains": [],
        "provider_kind": "OIDC",
        "public_config": {},
    }
    mock_session_admin.execute.side_effect = [
        mock_card_res_admin,
        MagicMock(),  # set_config
    ]
    new_pid = uuid.uuid4()
    with (
        patch(
            "kanban.auth.identity_service._evaluate_card_access",
            return_value=(True, True),
        ),
        patch.object(
            resolver,
            "_provision_user",
            new_callable=AsyncMock,
            return_value=new_pid,
        ),
        patch(
            "kanban.auth.identity_service._ensure_server_admin_role",
            new_callable=AsyncMock,
        ) as mock_admin_ensure,
    ):
        res = await resolver._resolve_unbound_login(mock_session_admin, assertion)
        assert res.principal_id == new_pid
        assert mock_admin_ensure.called


@pytest.mark.asyncio
async def test_provision_user_activity_errors_and_no_nested() -> None:
    """Exercise _provision_user lines 599-601, 627-628, 671-672."""
    resolver = DatabaseIdentityResolver()

    # 1. nested_ctx has no __aenter__ -> lines 599-601
    mock_nested_close = MagicMock(spec=["close"])
    mock_session_no_nested = AsyncMock()
    mock_session_no_nested.info = {}
    mock_session_no_nested.begin_nested = MagicMock(return_value=mock_nested_close)

    pid = uuid.uuid4()
    mock_prov_res = MagicMock()
    mock_prov_res.mappings.return_value.first.return_value = {"principal_id": pid}
    mock_session_no_nested.execute.return_value = mock_prov_res

    ws_id = uuid.uuid4()
    assertion = make_assertion()

    # record_activity fails on success -> line 671-672
    with patch(
        "kanban.auth.identity_service.record_activity",
        new_callable=AsyncMock,
        side_effect=Exception("Activity logging error"),
    ):
        result_pid = await resolver._provision_user(mock_session_no_nested, ws_id, assertion)
        assert result_pid == pid
        assert mock_nested_close.close.called

    # 2. record_activity fails on IDENTITY_LINK_REQUIRED -> line 627-628
    mock_session_link_req = AsyncMock()
    mock_session_link_req.info = {}
    mock_session_link_req.execute.side_effect = Exception("error: IDENTITY_LINK_REQUIRED triggered")

    with patch(
        "kanban.auth.identity_service.record_activity",
        new_callable=AsyncMock,
        side_effect=Exception("Auto-merge activity error"),
    ):
        with pytest.raises(ProblemException) as exc_link:
            await resolver._provision_user(mock_session_link_req, ws_id, assertion)
        assert exc_link.value.code == "IDENTITY_LINK_REQUIRED"


def test_sanitize_return_to_backslash_in_query_target() -> None:
    """Exercise sanitize_return_to line 85 (backslash in query string)."""
    assert sanitize_return_to("/safe/path?param=%5Cevil") == "/"
    assert sanitize_return_to("/safe/path?param=safe") == "/safe/path?param=safe"


def test_resolve_public_origin_base_url_fallback() -> None:
    """Exercise OidcFlow._resolve_public_origin lines 206-207."""
    km = KeyMaterial(master_kek=b"m" * 32, auth_pepper=b"p" * 32, session_hmac_key=b"s" * 32)
    flow = OidcFlow(key_material=km, public_origin="https://default.example.com")

    orig_env = os.environ.pop("KANBAN_PUBLIC_ORIGIN", None)
    try:
        req = MagicMock()
        req.headers = {}
        req.url = MagicMock(scheme="")
        req.base_url = "http://kanban.internal:9000/"
        assert flow._resolve_public_origin(req) == "http://kanban.internal:9000"
    finally:
        if orig_env:
            os.environ["KANBAN_PUBLIC_ORIGIN"] = orig_env


@pytest.mark.asyncio
async def test_oidc_callback_link_flow_fallback_cookie() -> None:
    """Exercise OidcFlow.callback lines 812-814, 824-826 (fallback Set-Cookie under HTTP non-test host)."""
    km = KeyMaterial(master_kek=b"m" * 32, auth_pepper=b"p" * 32, session_hmac_key=b"s" * 32)

    card_id = uuid.uuid4()
    link_intent_id = uuid.uuid4()

    sub_key = derive_subkey(km.master_kek, "oidc/code-verifier")
    nonce = b"n" * 12
    valid_ct = AESGCM(sub_key).encrypt(nonce, b"valid-code-verifier", card_id.bytes)
    sealed = nonce + valid_ct

    mock_state_row = {
        "status": "OK",
        "card_id": card_id,
        "nonce": b"1234567890123456",
        "code_verifier_sealed": sealed,
        "return_to": "/",
        "link_intent_id": link_intent_id,
    }

    mock_card_dict = {
        "id": card_id,
        "workspace_id": uuid.uuid4(),
        "slug": "corp-oauth",
        "provider_kind": "OAUTH2",
        "display_name": "Corp OAuth",
        "is_enabled": True,
        "encrypted_secret_blob": b"encrypted_secret",
        "wrapped_dek": b"wrapped_dek_bytes",
        "dek_kid": "kek-v1",
        "public_config": {
            "kind": "OAUTH2",
            "client_id": "test-client",
            "client_auth": "client_secret_basic",
            "authorization_endpoint": "https://auth.example.test/authorize",
            "token_endpoint": "https://auth.example.test/token",
            "userinfo_endpoint": "https://auth.example.test/userinfo",
        },
        "auto_provision_users": False,
        "allowed_email_domains": [],
        "sort_rank": "a0",
    }

    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/auth/oidc/corp-oauth/callback",
            "headers": [(b"host", b"production.corp.example.test:8080")],
            "scheme": "http",
        }
    )

    mock_client = AsyncMock()
    mock_client.post.return_value = httpx.Response(200, json={"access_token": "at_123"})
    mock_client.get.return_value = httpx.Response(
        200, json={"sub": "user_123", "email": "alice@corp.test", "email_verified": True}
    )

    flow = OidcFlow(key_material=km, http_client=mock_client)

    # Test link success branch (lines 824-826)
    mock_session = AsyncMock()
    mock_session.execute.side_effect = [
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_state_row)),
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_card_dict)),
    ]

    with (
        patch("kanban.auth.oidc.flow.open_card_secret", return_value=bytearray(b"secret123")),
        patch.object(flow._identity_resolver, "resolve", new_callable=AsyncMock),
    ):
        resp = await flow.callback(
            mock_session,
            "corp-oauth",
            code="test-code",
            state="test-state",
            browser_binding_cookie="test-cookie",
            request=req,
        )
        assert resp.status_code == 302
        assert "/settings/profile?linked=corp-oauth" in resp.headers["location"]
        set_cookies = resp.headers.getlist("set-cookie")
        assert any("kb_oidc=" in c for c in set_cookies)

    # Test link error branch (lines 812-814)
    mock_session_err = AsyncMock()
    mock_session_err.execute.side_effect = [
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_state_row)),
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_card_dict)),
    ]
    with (
        patch("kanban.auth.oidc.flow.open_card_secret", return_value=bytearray(b"secret123")),
        patch.object(
            flow._identity_resolver,
            "resolve",
            new_callable=AsyncMock,
            side_effect=ProblemException(
                code="IDENTITY_ALREADY_LINKED",
                status=409,
                title="Identity Already Linked",
                detail="Already linked",
            ),
        ),
    ):
        resp_err = await flow.callback(
            mock_session_err,
            "corp-oauth",
            code="test-code",
            state="test-state",
            browser_binding_cookie="test-cookie",
            request=req,
        )
        assert resp_err.status_code == 302
        assert (
            "/settings/profile?link_error=IDENTITY_ALREADY_LINKED" in resp_err.headers["location"]
        )
        set_cookies_err = resp_err.headers.getlist("set-cookie")
        assert any("kb_oidc=" in c for c in set_cookies_err)


@pytest.mark.asyncio
async def test_oidc_callback_github_and_token_error_branches() -> None:
    """Exercise OidcFlow.callback lines 523, 534, 571-572, 657, 729-773."""
    km = KeyMaterial(master_kek=b"m" * 32, auth_pepper=b"p" * 32, session_hmac_key=b"s" * 32)

    card_id = uuid.uuid4()
    sub_key = derive_subkey(km.master_kek, "oidc/code-verifier")
    nonce = b"n" * 12
    valid_ct = AESGCM(sub_key).encrypt(nonce, b"valid-code-verifier", card_id.bytes)
    sealed = nonce + valid_ct

    mock_state_row = {
        "status": "OK",
        "card_id": card_id,
        "nonce": b"1234567890123456",
        "code_verifier_sealed": sealed,
        "return_to": "/dashboard",
        "link_intent_id": None,
    }

    mock_gh_card: dict[str, Any] = {
        "id": card_id,
        "workspace_id": uuid.uuid4(),
        "slug": "github-card",
        "provider_kind": "OAUTH2",
        "display_name": "GitHub OAuth",
        "is_enabled": True,
        "encrypted_secret_blob": b"secret_bytes",
        "wrapped_dek": b"dek_bytes",
        "dek_kid": "kek-v1",
        "public_config": {
            "kind": "OAUTH2",
            "client_id": "gh-client-id",
            "client_auth": "client_secret_basic",
            "authorization_endpoint": "https://github.com/login/oauth/authorize",
            "token_endpoint": "https://github.com/login/oauth/access_token",
            "userinfo_endpoint": "https://api.github.com/user",
            "subject_claim": "id",
            "email_claim": "email",
        },
        "auto_provision_users": True,
        "allowed_email_domains": [],
        "sort_rank": "a0",
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = httpx.Response(200, json={"access_token": "gh_at_123"})
    mock_client.get.side_effect = [
        httpx.Response(200, json={"id": 9999, "login": "octocat"}),
        httpx.Response(
            200, json=[{"email": "octo@example.test", "primary": True, "verified": True}]
        ),
    ]

    flow_gh = OidcFlow(key_material=km, http_client=mock_client)
    mock_session = AsyncMock()
    mock_session.execute.side_effect = [
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_state_row)),
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_gh_card)),
    ]

    with (
        patch(
            "kanban.auth.oidc.flow.open_card_secret", return_value=bytearray(b"client_secret_val")
        ),
        patch.object(flow_gh._identity_resolver, "resolve", new_callable=AsyncMock) as mock_resolve,
    ):
        resp = await flow_gh.callback(
            mock_session,
            "github-card",
            code="test-code",
            state="test-state",
            browser_binding_cookie="test-cookie",
        )
        assert resp.status_code == 302
        assert mock_resolve.called
        assertion_passed = mock_resolve.call_args[0][0]
        assert assertion_passed.email == "octo@example.test"

    # 2. GitHub fallback to {login}@users.noreply.github.com (lines 770-773)
    mock_client.get.side_effect = [
        httpx.Response(200, json={"id": 8888, "login": "botuser"}),
        httpx.Response(200, json=[]),
    ]
    mock_session2 = AsyncMock()
    mock_session2.execute.side_effect = [
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_state_row)),
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_gh_card)),
    ]
    with (
        patch(
            "kanban.auth.oidc.flow.open_card_secret", return_value=bytearray(b"client_secret_val")
        ),
        patch.object(
            flow_gh._identity_resolver, "resolve", new_callable=AsyncMock
        ) as mock_resolve2,
    ):
        resp2 = await flow_gh.callback(
            mock_session2,
            "github-card",
            code="test-code",
            state="test-state",
            browser_binding_cookie="test-cookie",
        )
        assert resp2.status_code == 302
        assertion_passed2 = mock_resolve2.call_args[0][0]
        assert assertion_passed2.email == "botuser@users.noreply.github.com"

    # 3. Line 523: client_secret_basic missing secret
    mock_card_no_secret = dict(mock_gh_card)
    mock_card_no_secret["encrypted_secret_blob"] = None
    mock_card_no_secret["wrapped_dek"] = None
    mock_session3 = AsyncMock()
    mock_session3.execute.side_effect = [
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_state_row)),
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_card_no_secret)),
    ]
    with pytest.raises(ProblemException) as exc3:
        await flow_gh.callback(
            mock_session3,
            "github-card",
            code="test-code",
            state="test-state",
            browser_binding_cookie="test-cookie",
        )
    assert exc3.value.code == "OIDC_TOKEN_INVALID"
    assert exc3.value.detail is not None
    assert "Missing client secret" in exc3.value.detail

    # 4. Line 534: private_key_jwt missing secret
    mock_card_jwt_no_sec = dict(mock_gh_card)
    mock_card_jwt_no_sec["encrypted_secret_blob"] = None
    mock_card_jwt_no_sec["wrapped_dek"] = None
    mock_card_jwt_no_sec["public_config"] = dict(mock_gh_card["public_config"])
    mock_card_jwt_no_sec["public_config"]["client_auth"] = "private_key_jwt"
    mock_session4 = AsyncMock()
    mock_session4.execute.side_effect = [
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_state_row)),
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_card_jwt_no_sec)),
    ]
    with pytest.raises(ProblemException) as exc4:
        await flow_gh.callback(
            mock_session4,
            "github-card",
            code="test-code",
            state="test-state",
            browser_binding_cookie="test-cookie",
        )
    assert exc4.value.code == "OIDC_TOKEN_INVALID"
    assert exc4.value.detail is not None
    assert "Missing private key" in exc4.value.detail

    # 5. Line 571-572: token response error json
    mock_client.post.return_value = httpx.Response(400, json={"error": "invalid_grant"})
    mock_session5 = AsyncMock()
    mock_session5.execute.side_effect = [
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_state_row)),
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_gh_card)),
    ]
    with patch(
        "kanban.auth.oidc.flow.open_card_secret", return_value=bytearray(b"client_secret_val")
    ):
        with pytest.raises(ProblemException) as exc5:
            await flow_gh.callback(
                mock_session5,
                "github-card",
                code="test-code",
                state="test-state",
                browser_binding_cookie="test-cookie",
            )
        assert exc5.value.code == "OIDC_TOKEN_INVALID"
        assert exc5.value.detail is not None
        assert "(invalid_grant)" in exc5.value.detail


@pytest.mark.asyncio
async def test_oidc_callback_default_client_branches() -> None:
    """Exercise OidcFlow.callback lines 558-559, 677-678, 714, 745-746, 764-766."""
    km = KeyMaterial(master_kek=b"m" * 32, auth_pepper=b"p" * 32, session_hmac_key=b"s" * 32)
    flow_default = OidcFlow(key_material=km, http_client=None)

    card_id = uuid.uuid4()
    sub_key = derive_subkey(km.master_kek, "oidc/code-verifier")
    nonce = b"n" * 12
    valid_ct = AESGCM(sub_key).encrypt(nonce, b"valid-code-verifier", card_id.bytes)
    sealed = nonce + valid_ct

    mock_state_row = {
        "status": "OK",
        "card_id": card_id,
        "nonce": b"1234567890123456",
        "code_verifier_sealed": sealed,
        "return_to": "/dashboard",
        "link_intent_id": None,
    }

    mock_gh_card = {
        "id": card_id,
        "workspace_id": uuid.uuid4(),
        "slug": "github-default",
        "provider_kind": "OAUTH2",
        "display_name": "GitHub Default",
        "is_enabled": True,
        "encrypted_secret_blob": b"secret_bytes",
        "wrapped_dek": b"dek_bytes",
        "dek_kid": "kek-v1",
        "public_config": {
            "kind": "OAUTH2",
            "client_id": "gh-client-id",
            "client_auth": "client_secret_basic",
            "authorization_endpoint": "https://github.com/login/oauth/authorize",
            "token_endpoint": "https://github.com/login/oauth/access_token",
            "userinfo_endpoint": "https://api.github.com/user",
            "subject_claim": "nonexistent_claim",
            "email_claim": "email",
        },
        "auto_provision_users": True,
        "allowed_email_domains": [],
        "sort_rank": "a0",
    }

    mock_session = AsyncMock()
    mock_session.execute.side_effect = [
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_state_row)),
        MagicMock(mappings=lambda: MagicMock(first=lambda: mock_gh_card)),
    ]

    mock_token = httpx.Response(200, json={"access_token": "gh_at_123"})
    mock_userinfo = httpx.Response(200, json={"id": 5555, "login": "octo5555"})
    mock_emails = httpx.Response(
        200, json=[{"email": "secondary@example.test", "primary": False, "verified": True}]
    )

    with (
        patch(
            "kanban.auth.oidc.flow.open_card_secret", return_value=bytearray(b"client_secret_val")
        ),
        patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_token),
        patch(
            "httpx.AsyncClient.get",
            new_callable=AsyncMock,
            side_effect=[mock_userinfo, mock_emails],
        ),
        patch.object(
            flow_default._identity_resolver, "resolve", new_callable=AsyncMock
        ) as mock_resolve,
    ):
        resp = await flow_default.callback(
            mock_session,
            "github-default",
            code="test-code",
            state="test-state",
            browser_binding_cookie="test-cookie",
        )
        assert resp.status_code == 302
        assertion_passed = mock_resolve.call_args[0][0]
        assert assertion_passed.subject == "5555"
        assert assertion_passed.email == "secondary@example.test"
