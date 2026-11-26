# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for LdapAuthService edge cases and branch coverage (KB-P2-07)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database.models.auth import AuthProviderCard
from kanban.api.problems import ProblemException
from kanban.auth.identity import IdentityResolver, ResolvedLogin
from kanban.auth.ldap.client import LdapSearchError, SearchEntry
from kanban.auth.ldap.service import LdapAuthService, _format_subject_value
from kanban.security.envelope import KekProvider


def test_format_subject_value_guid_and_fallback() -> None:
    """Test _format_subject_value with valid GUID, ValueError fallback, and string."""
    # 1. 16-byte valid GUID
    u = uuid.uuid4()
    assert _format_subject_value(u.bytes_le) == str(u)

    # 2. 16-byte ValueError fallback
    with patch("uuid.UUID", side_effect=ValueError("bad uuid")):
        raw = b"1234567890123456"
        assert _format_subject_value(raw) == "1234567890123456"

    # 3. Non-16-byte raw string
    assert _format_subject_value(b"Hermes Conrad") == "Hermes Conrad"


def _make_mock_session() -> AsyncMock:
    """Create a mock AsyncSession with synchronous mapping_res.scalars().all()."""
    session = AsyncMock()
    session.add = MagicMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_res
    return session


def _make_mock_card(  # noqa: PLR0913
    *,
    workspace_id: uuid.UUID | None = None,
    service_bind_dn: str | None = "cn=admin,dc=example,dc=com",
    group_dn_map: dict[str, str] | None = None,
    admin_groups: list[str] | None = None,
    user_groups: list[str] | None = None,
    encrypted_secret_blob: bytes | None = b"encrypted",
    wrapped_dek: bytes | None = b"wrapped",
) -> MagicMock:
    """Create a mock AuthProviderCard with valid public_config."""
    card = MagicMock(spec=AuthProviderCard)
    card.id = uuid.uuid4()
    card.slug = "planet-express"
    card.provider_kind = "LDAP"
    card.is_enabled = True
    card.workspace_id = workspace_id or uuid.uuid4()
    card.encrypted_secret_blob = encrypted_secret_blob
    card.wrapped_dek = wrapped_dek
    card.dek_kid = "kek-1"
    card.public_config = {
        "url": "ldap://ldap.example.com:10389",
        "transport_mode": "starttls",
        "service_bind_dn": service_bind_dn,
        "base_dn": "dc=example,dc=com",
        "user_search_filter": "(&(objectClass=person)(uid={username}))",
        "group_dn_map": group_dn_map or {},
        "admin_groups": admin_groups or [],
        "user_groups": user_groups or [],
    }
    return card


@pytest.mark.asyncio
async def test_ldap_auth_service_plaintext_bind_secret() -> None:
    """Test LDAP authentication when bind secret is a plaintext string (lines 151-152)."""
    kek_provider = MagicMock(spec=KekProvider)
    service = LdapAuthService(kek_provider=kek_provider)
    card = _make_mock_card()

    mock_client = AsyncMock()
    user_entry = SearchEntry(
        dn="uid=hermes,ou=users,dc=example,dc=com",
        attributes={
            "entryuuid": [b"test-uuid-1234"],
            "mail": [b"hermes@example.com"],
            "cn": [b"Hermes Conrad"],
        },
    )
    mock_client.search.return_value = [user_entry]

    with (
        patch("kanban.auth.ldap.service.LdapTlsHardClient", return_value=mock_client),
        patch(
            "kanban.auth.ldap.service.open_card_secret",
            return_value=bytearray(b"plain-not-json-secret"),
        ),
    ):
        mock_session = _make_mock_session()
        assertion, resolved = await service.authenticate(
            mock_session,
            card,
            "hermes",
            "secretpass",
        )
        assert assertion.subject == "test-uuid-1234"
        assert assertion.email == "hermes@example.com"
        assert assertion.display_name == "Hermes Conrad"
        assert resolved is None


@pytest.mark.asyncio
async def test_ldap_auth_service_anonymous_search_and_no_email() -> None:
    """Test LDAP authentication with no service_bind_dn and missing email."""
    service = LdapAuthService()
    card = _make_mock_card(service_bind_dn=None, encrypted_secret_blob=None, wrapped_dek=None)
    card.workspace_id = None  # skips group sync (line 320->330)

    mock_client = AsyncMock()
    user_entry = SearchEntry(
        dn="uid=fry,ou=users,dc=example,dc=com",
        attributes={
            "entryuuid": [b"fry-uuid"],
            # No mail attribute
            "cn": [b"Philip J. Fry"],
        },
    )
    mock_client.search.return_value = [user_entry]

    resolver = MagicMock(spec=IdentityResolver)
    resolved_login = ResolvedLogin(principal_id=uuid.uuid4(), workspace_id=uuid.uuid4())
    resolver.resolve = AsyncMock(return_value=resolved_login)
    service._identity_resolver = resolver  # noqa: SLF001

    with patch("kanban.auth.ldap.service.LdapTlsHardClient", return_value=mock_client):
        mock_session = _make_mock_session()
        assertion, resolved = await service.authenticate(
            mock_session,
            card,
            "fry",
            "secretpass",
        )
        assert assertion.email == "fry@ldap.local"
        assert resolved is not None


@pytest.mark.asyncio
async def test_ldap_auth_service_group_hierarchy_discovery_and_exception() -> None:
    """Test nested group search discovery and search exception handling (lines 203-212)."""
    kek_provider = MagicMock(spec=KekProvider)
    service = LdapAuthService(kek_provider=kek_provider)
    child_dn = "cn=subteam,ou=groups,dc=example,dc=com"
    parent_dn = "cn=parent,ou=groups,dc=example,dc=com"
    card = _make_mock_card(
        group_dn_map={
            child_dn: "Subteam",
            parent_dn: "Parent",
        }
    )

    mock_client = AsyncMock()
    user_entry = SearchEntry(
        dn="uid=hermes,ou=users,dc=example,dc=com",
        attributes={
            "entryuuid": [b"hermes-uuid"],
            "mail": [b"hermes@example.com"],
            "cn": [b"Hermes Conrad"],
            "memberof": [child_dn.encode("utf-8")],
        },
    )
    group_entry = SearchEntry(
        dn=child_dn,
        attributes={
            "memberof": [parent_dn.encode("utf-8")],
        },
    )

    # First call: user search; Second call: group search
    mock_client.search.side_effect = [[user_entry], [group_entry]]

    secret_json = json.dumps({"bind_dn_password": "validpassword"}).encode("utf-8")
    with (
        patch("kanban.auth.ldap.service.LdapTlsHardClient", return_value=mock_client),
        patch("kanban.auth.ldap.service.open_card_secret", return_value=bytearray(secret_json)),
        patch("kanban.auth.ldap.service.sync_ldap_groups", new_callable=AsyncMock) as mock_sync,
    ):
        resolver = MagicMock(spec=IdentityResolver)
        resolved_login = ResolvedLogin(principal_id=uuid.uuid4(), workspace_id=uuid.uuid4())
        resolver.resolve = AsyncMock(return_value=resolved_login)
        service._identity_resolver = resolver  # noqa: SLF001

        mock_session = _make_mock_session()
        await service.authenticate(
            mock_session,
            card,
            "hermes",
            "secretpass",
        )
        assert mock_sync.call_count == 1
        _, kwargs = mock_sync.call_args
        assert child_dn in kwargs["group_parent_map"]
        assert kwargs["group_parent_map"][child_dn] == [parent_dn]

    # Test group search throwing exception (lines 211-212)
    mock_client.search.side_effect = [
        [user_entry],
        LdapSearchError("LDAP timeout on group search"),
    ]
    with (
        patch("kanban.auth.ldap.service.LdapTlsHardClient", return_value=mock_client),
        patch("kanban.auth.ldap.service.open_card_secret", return_value=bytearray(secret_json)),
    ):
        mock_session = _make_mock_session()
        await service.authenticate(
            mock_session,
            card,
            "hermes",
            "secretpass",
        )


@pytest.mark.asyncio
async def test_ldap_auth_service_unauthorized_group_and_admin_role() -> None:
    """Test group authorization policies: rejection (lines 288-294) and SERVER_ADMIN (line 298)."""
    kek_provider = MagicMock(spec=KekProvider)
    service = LdapAuthService(kek_provider=kek_provider)
    card = _make_mock_card(
        admin_groups=["cn=directory_admins,ou=groups,dc=example,dc=com"],
        user_groups=["cn=directory_users,ou=groups,dc=example,dc=com"],
    )

    mock_client = AsyncMock()
    secret_json = json.dumps({"bind_dn_password": "validpassword"}).encode("utf-8")

    # 1. User has neither admin nor user group -> IDENTITY_NOT_PROVISIONED (lines 288-294)
    unauthorized_entry = SearchEntry(
        dn="uid=scruffy,ou=users,dc=example,dc=com",
        attributes={
            "entryuuid": [b"scruffy-uuid"],
            "mail": [b"scruffy@example.com"],
            "cn": [b"Scruffy"],
            "memberof": [b"cn=janitors,ou=groups,dc=example,dc=com"],
        },
    )
    mock_client.search.return_value = [unauthorized_entry]

    with (
        patch("kanban.auth.ldap.service.LdapTlsHardClient", return_value=mock_client),
        patch("kanban.auth.ldap.service.open_card_secret", return_value=bytearray(secret_json)),
    ):
        mock_session = _make_mock_session()
        with pytest.raises(ProblemException) as exc_info:
            await service.authenticate(
                mock_session,
                card,
                "scruffy",
                "secretpass",
            )
        assert exc_info.value.code == "IDENTITY_NOT_PROVISIONED"
        assert exc_info.value.status == 403

    # 2. User is in admin group -> SERVER_ADMIN role appended (line 298)
    admin_entry = SearchEntry(
        dn="uid=farnsworth,ou=users,dc=example,dc=com",
        attributes={
            "entryuuid": [b"farnsworth-uuid"],
            "mail": [b"hubert@example.com"],
            "cn": [b"Hubert Farnsworth"],
            "memberof": [b"cn=directory_admins,ou=groups,dc=example,dc=com"],
        },
    )
    mock_client.search.return_value = [admin_entry]

    with (
        patch("kanban.auth.ldap.service.LdapTlsHardClient", return_value=mock_client),
        patch("kanban.auth.ldap.service.open_card_secret", return_value=bytearray(secret_json)),
    ):
        mock_session = _make_mock_session()
        assertion, _ = await service.authenticate(
            mock_session,
            card,
            "farnsworth",
            "secretpass",
        )
        assert "SERVER_ADMIN" in assertion.groups


@pytest.mark.asyncio
async def test_ldap_auth_service_missing_subject_attribute() -> None:
    """Test LDAP authentication when entry lacks subject attribute (lines 219-220)."""
    kek_provider = MagicMock(spec=KekProvider)
    service = LdapAuthService(kek_provider=kek_provider)
    card = _make_mock_card()

    mock_client = AsyncMock()
    # Missing entryuuid attribute
    bad_entry = SearchEntry(
        dn="uid=nobody,ou=users,dc=example,dc=com",
        attributes={
            "mail": [b"nobody@example.com"],
            "cn": [b"Nobody"],
        },
    )
    mock_client.search.return_value = [bad_entry]

    secret_json = json.dumps({"bind_dn_password": "validpassword"}).encode("utf-8")
    with (
        patch("kanban.auth.ldap.service.LdapTlsHardClient", return_value=mock_client),
        patch("kanban.auth.ldap.service.open_card_secret", return_value=bytearray(secret_json)),
    ):
        mock_session = _make_mock_session()
        with pytest.raises(ProblemException) as exc_info:
            await service.authenticate(
                mock_session,
                card,
                "nobody",
                "secretpass",
            )
        assert exc_info.value.code == "INVALID_CREDENTIALS"
