# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: SLF001, E501
"""Security unit and integration tests for AIProviderConfigService KEK enforcement (KAN-338).

Verifies:
  1. Static fallback key _DEFAULT_KEK_FALLBACK is eliminated from codebase.
  2. Attempting to seal or unwrap secrets with kek_provider=None fails closed with RuntimeError.
  3. AIProviderConfigService requires explicit or app-injected KEK provider for secret custody.
  4. _get_kek_provider in admin ai_providers routes raises 500 KEK_PROVIDER_UNAVAILABLE
     when cryptographic key custody is missing, refusing static fallback.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING
from unittest import mock

import pytest
from starlette.requests import Request

from database.tests.conftest import bootstrap_workspace_admin
from kanban.ai_config import service as ai_svc
from kanban.ai_config.service import (
    AIProviderConfigService,
    EnvelopeIntegrityError,
)
from kanban.api.problems import ProblemException
from kanban.api.v1.admin.ai_providers import _get_kek_provider
from kanban.security.envelope import StaticKekProvider
from kanban.security.keys import KeyMaterial

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def test_case_1_static_fallback_kek_eliminated() -> None:
    """Case 1: Verify _DEFAULT_KEK_FALLBACK is eliminated from module namespace."""
    assert not hasattr(ai_svc, "_DEFAULT_KEK_FALLBACK"), (
        "Insecure _DEFAULT_KEK_FALLBACK still exists in kanban.ai_config.service"
    )


@pytest.mark.asyncio
async def test_case_2_seal_and_unwrap_fail_closed_without_kek(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 2: Sealing and unwrapping secrets without KEK provider fails closed with RuntimeError."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.delenv("KANBAN_MASTER_KEK", raising=False)
    monkeypatch.delenv("KB_MASTER_KEK_B64", raising=False)

    ws_id, _ = await bootstrap_workspace_admin(db_session)
    service = AIProviderConfigService(db_session, kek_provider=None)
    assert service._kek is None

    # Attempting to seal an API key must raise RuntimeError
    with pytest.raises(RuntimeError, match="No KEK provider configured"):
        await service.create_config(
            workspace_id=ws_id,
            provider_kind="openai",
            display_name="OpenAI Test",
            model_allowlist=["gpt-4o"],
            residency_tier="us-east-1",
            base_url="https://api.openai.com/v1",
            api_key=bytearray(b"sk-test-secret-key-12345"),
        )

    # Creating a provider without API key succeeds even without KEK provider
    config_no_key = await service.create_config(
        workspace_id=ws_id,
        provider_kind="ollama",
        display_name="Local Ollama",
        model_allowlist=["llama3"],
        residency_tier="on-premises",
        base_url="http://127.0.0.1:11434",
        api_key=None,
    )
    assert config_no_key.id is not None

    # Attempting to update with an API key without KEK provider must raise RuntimeError
    with pytest.raises(RuntimeError, match="No KEK provider configured"):
        await service.update_config(
            config_id=config_no_key.id,
            api_key="sk-new-key-12345",
        )

    # Attempting to unwrap without KEK provider must raise RuntimeError
    with pytest.raises(RuntimeError, match="No KEK provider configured"):
        await service.unwrap_api_key(
            config_no_key.id,
            secret_override=(b"fake_key", b"fake_nonce", b"fake_dek", "kid"),
        )


@pytest.mark.asyncio
async def test_case_3_injected_kek_provider_seals_and_unwraps_cleanly(
    db_session: AsyncSession,
) -> None:
    """Case 3: Injected KEK provider seals and unwraps secrets with envelope integrity."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    kek_prod = StaticKekProvider(
        keys={"kek-prod-v1": b"p" * 32, "kek-prod-v2": b"q" * 32},
        current="kek-prod-v1",
    )
    service = AIProviderConfigService(db_session, kek_provider=kek_prod)

    raw_secret = b"sk-production-cloud-key-54321"
    config = await service.create_config(
        workspace_id=ws_id,
        provider_kind="openai",
        display_name="Production OpenAI",
        model_allowlist=["gpt-4o"],
        residency_tier="us-east-1",
        base_url="https://api.openai.com/v1",
        api_key=bytearray(raw_secret),
    )
    assert config.dek_kid == "kek-prod-v1"

    # Unwrap secret using valid KEK
    unwrapped = await service.unwrap_api_key(config.id)
    assert bytes(unwrapped) == raw_secret

    # Attempt to unwrap using wrong KEK fails envelope integrity check
    wrong_kek = StaticKekProvider(keys={"kek-prod-v1": b"w" * 32}, current="kek-prod-v1")
    service_wrong = AIProviderConfigService(db_session, kek_provider=wrong_kek)
    with pytest.raises(EnvelopeIntegrityError):
        await service_wrong.unwrap_api_key(config.id)


def test_case_4_get_kek_provider_resolution_and_fail_closed() -> None:
    """Case 4: _get_kek_provider resolves app state or key material and fails closed on absence."""
    scope = {"type": "http", "app": type("App", (), {"state": type("State", (), {})()})()}
    req = Request(scope)

    # 1. When app.state.kek_provider is already set
    custom_kek = StaticKekProvider(keys={"k1": b"a" * 32}, current="k1")
    req.app.state.kek_provider = custom_kek
    assert _get_kek_provider(req) is custom_kek

    # 2. When app.state.kek_provider is None but key_material is set
    del req.app.state.kek_provider
    km = KeyMaterial(master_kek=b"m" * 32, auth_pepper=b"p" * 32, session_hmac_key=b"s" * 32)
    req.app.state.key_material = km
    resolved = _get_kek_provider(req)
    assert isinstance(resolved, StaticKekProvider)
    assert resolved.get(km.master_kek_kid) == b"m" * 32

    # 3. When both are None and load_key_material raises exception -> raises 500 ProblemException
    del req.app.state.kek_provider
    del req.app.state.key_material
    with (
        mock.patch(
            "kanban.security.keys.load_key_material",
            side_effect=RuntimeError("Keyring unavailable"),
        ),
        pytest.raises(ProblemException) as exc_info,
    ):
        _get_kek_provider(req)
    assert exc_info.value.status == 500
    assert exc_info.value.code == "KEK_PROVIDER_UNAVAILABLE"
