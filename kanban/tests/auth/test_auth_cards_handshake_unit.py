# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: PLR0913, PLR0917, D103
"""Unit tests for Auth Provider Cards live handshake probe (KB-P2-10)."""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from database.models.auth import AuthProviderCard
from kanban.auth.cards.handshake import (
    probe_auth_card_handshake,
)
from kanban.auth.ldap.client import LdapTlsError
from kanban.security.envelope import StaticKekProvider, seal_card_secret


def _make_card(
    provider_kind: str,
    slug: str = "test-card",
    public_config: dict[str, Any] | None = None,
    encrypted_secret_blob: bytes | None = None,
    wrapped_dek: bytes | None = None,
    dek_kid: str = "kek-v1",
) -> AuthProviderCard:
    return AuthProviderCard(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        provider_kind=provider_kind,
        slug=slug,
        display_name="Test Card",
        button_subtext="Sign In",
        icon_preset="key",
        is_enabled=True,
        sort_rank="A",
        auto_provision_users=False,
        allowed_email_domains=[],
        public_config=public_config or {},
        encrypted_secret_blob=encrypted_secret_blob,
        wrapped_dek=wrapped_dek,
        dek_kid=dek_kid,
        last_health_status="UNVERIFIED",
    )


@pytest.fixture(autouse=True)
def _set_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KANBAN_MASTER_KEK", "a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s=")
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", "cHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHA=")
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", "c3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3M=")
    monkeypatch.setenv("KANBAN_AUTH_EGRESS_ALLOW_PRIVATE", "true")


@pytest.mark.asyncio
async def test_probe_oidc_missing_issuer() -> None:
    card = _make_card("OIDC", public_config={})
    res = await probe_auth_card_handshake(card)
    assert res.ok is False
    assert res.error_code == "MISSING_ISSUER"
    assert res.status == "FAILED:MISSING_ISSUER"


@pytest.mark.asyncio
async def test_probe_oauth2_missing_endpoints() -> None:
    card = _make_card("OAUTH2", public_config={})
    res = await probe_auth_card_handshake(card)
    assert res.ok is False
    assert res.error_code == "MISSING_ENDPOINTS"


@pytest.mark.asyncio
async def test_probe_oauth2_success() -> None:
    card = _make_card(
        "OAUTH2",
        public_config={
            "authorization_endpoint": "https://auth.example.com/oauth/authorize",
            "token_endpoint": "https://auth.example.com/oauth/token",
        },
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = httpx.Response(200)

    res = await probe_auth_card_handshake(card, http_client=mock_client)
    assert res.ok is True
    assert res.status == "OK"
    assert res.error_code is None


@pytest.mark.asyncio
async def test_probe_oauth2_500_failure() -> None:
    card = _make_card(
        "OAUTH2",
        public_config={
            "authorization_endpoint": "https://auth.example.com/oauth/authorize",
            "token_endpoint": "https://auth.example.com/oauth/token",
        },
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = httpx.Response(500)

    res = await probe_auth_card_handshake(card, http_client=mock_client)
    assert res.ok is False
    assert "500" in res.status


@pytest.mark.asyncio
async def test_probe_oauth2_default_client_failure() -> None:
    card = _make_card(
        "OAUTH2",
        public_config={
            "authorization_endpoint": "https://auth.example.com/oauth/authorize",
            "token_endpoint": "https://auth.example.com/oauth/token",
        },
    )
    with patch("httpx.AsyncClient.get", return_value=httpx.Response(503)):
        res = await probe_auth_card_handshake(card, http_client=None)
        assert res.ok is False
        assert "503" in res.status


@pytest.mark.asyncio
async def test_probe_ldap_with_service_bind() -> None:
    kek = StaticKekProvider({"kek-v1": os.urandom(32)}, "kek-v1")
    card_id = uuid.uuid4()
    sealed = seal_card_secret(card_id, "LDAP", b'{"bind_dn_password": "test"}', kek)

    card = _make_card(
        "LDAP",
        public_config={
            "kind": "LDAP",
            "url": "ldap://localhost:389",
            "transport_mode": "starttls",
            "base_dn": "dc=example,dc=com",
            "service_bind_dn": "cn=admin,dc=example,dc=com",
        },
        encrypted_secret_blob=sealed.encrypted_secret_blob,
        wrapped_dek=sealed.wrapped_dek,
        dek_kid=sealed.dek_kid,
    )
    card.id = card_id

    mock_ldap = AsyncMock()
    mock_ldap.connect = AsyncMock()
    mock_ldap.bind = AsyncMock()
    mock_ldap.unbind = AsyncMock()

    with patch("kanban.auth.cards.handshake.LdapTlsHardClient", return_value=mock_ldap):
        res = await probe_auth_card_handshake(card, kek_provider=kek)
        assert res.ok is True
        assert res.status == "OK"
        mock_ldap.connect.assert_awaited_once()
        mock_ldap.bind.assert_awaited_once()
        mock_ldap.unbind.assert_awaited_once()


@pytest.mark.asyncio
async def test_probe_local_admin_success() -> None:
    card = _make_card("LOCAL_ADMIN")
    res = await probe_auth_card_handshake(card)
    assert res.ok is True
    assert res.status == "OK"


@pytest.mark.asyncio
async def test_probe_local_admin_verification_failure() -> None:
    card = _make_card("LOCAL_ADMIN")
    with patch("kanban.auth.cards.handshake.verify_password", return_value=False):
        res = await probe_auth_card_handshake(card)
        assert res.ok is False
        assert res.error_code == "CRYPTO_ROUNDTRIP_FAILED"


@pytest.mark.asyncio
async def test_probe_unsupported_kind() -> None:
    card = _make_card("SAML2")
    res = await probe_auth_card_handshake(card)
    assert res.ok is False
    assert res.error_code == "UNSUPPORTED_KIND"


@pytest.mark.asyncio
async def test_probe_timeout() -> None:
    card = _make_card("OIDC", public_config={"issuer": "https://idp.example.com"})

    async def _slow_discovery(*_args: object, **_kwargs: object) -> object:
        await asyncio.sleep(10.0)
        return None

    with (
        patch("kanban.auth.cards.handshake.fetch_discovery", side_effect=_slow_discovery),
        patch("kanban.auth.cards.handshake.PROBE_TIMEOUT_SECONDS", 0.05),
    ):
        res = await probe_auth_card_handshake(card)
        assert res.ok is False
        assert res.error_code == "TIMEOUT"
        assert res.status == "FAILED:TIMEOUT"


@pytest.mark.asyncio
async def test_probe_ldap_tls_error() -> None:
    card = _make_card(
        "LDAP",
        public_config={
            "kind": "LDAP",
            "url": "ldap://example.com:389",
            "transport_mode": "starttls",
            "base_dn": "dc=example,dc=com",
        },
    )
    with patch(
        "kanban.auth.cards.handshake.LdapTlsHardClient.connect",
        side_effect=LdapTlsError("LDAP_CONNECT_FAILED", "Could not connect"),
    ):
        res = await probe_auth_card_handshake(card)
        assert res.ok is False
        assert res.error_code == "LDAP_TLS_ERROR"
        assert res.status == "FAILED:LDAP_TLS_ERROR"


@pytest.mark.asyncio
async def test_probe_generic_exception() -> None:
    card = _make_card(
        "OAUTH2",
        public_config={
            "authorization_endpoint": "https://auth.example.com/oauth/authorize",
            "token_endpoint": "https://auth.example.com/oauth/token",
        },
    )
    with patch("httpx.AsyncClient.get", side_effect=ConnectionResetError("Reset by peer")):
        res = await probe_auth_card_handshake(card)
        assert res.ok is False
        assert res.error_code == "CONNECTIONRESETERROR"
        assert res.status == "FAILED:CONNECTIONRESETERROR"
