# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for AIProviderConfigService, key custody, and air-gap enforcement (KB-P5-05a)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest import mock

import httpx
import pytest

from database.tests.conftest import bootstrap_workspace_admin
from kanban.ai_config.net_guard import EgressDeniedError
from kanban.ai_config.service import (
    AIConfigNotFoundError,
    AIConfigValidationError,
    AIProviderConfigService,
    AirGapViolation,
    EnvelopeIntegrityError,
    validate_base_url,
)
from kanban.security.envelope import StaticKekProvider
from kanban.tests.security.helpers import create_project

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def kek_provider() -> StaticKekProvider:
    """Fixture providing static KEK provider."""
    return StaticKekProvider(
        keys={"kek-v1": b"k" * 32, "kek-v2": b"m" * 32},
        current="kek-v1",
    )


@pytest.mark.asyncio
async def test_01_positive_create_and_unwrap_secret(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Test Case 1: Positive create config with key, verify public dict and unwrap roundtrip."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    service = AIProviderConfigService(db_session, kek_provider)

    original_key = bytearray(b"test-openai-super-secret-key-12345")
    config = await service.create_config(
        workspace_id=ws_id,
        provider_kind="openai",
        display_name="Production OpenAI",
        model_allowlist=["gpt-4o", "gpt-4o-mini"],
        residency_tier="us-east-1",
        base_url="https://api.openai.com/v1",
        api_key=original_key,
    )

    # 1. Row has ciphertext, nonce, wrapped_dek, dek_kid
    assert config.wrapped_api_key is not None
    assert len(config.wrapped_api_key) > 0
    assert config.api_key_nonce is not None
    assert len(config.api_key_nonce) == 12
    assert config.wrapped_dek is not None
    assert len(config.wrapped_dek) > 0
    assert config.dek_kid == "kek-v1"

    # 2. to_public_dict() has api_key_set: true and no secret key material
    public_dict = service.to_public_dict(config)
    assert public_dict["api_key_set"] is True
    assert "wrapped_api_key" not in public_dict
    assert "api_key_nonce" not in public_dict
    assert "wrapped_dek" not in public_dict
    assert "dek_kid" not in public_dict
    assert public_dict["display_name"] == "Production OpenAI"
    assert public_dict["provider_kind"] == "openai"

    # 3. Unwrap through ai_provider_secret yields original plaintext key
    unwrapped = await service.unwrap_api_key(config.id)
    assert unwrapped == bytearray(b"test-openai-super-secret-key-12345")


@pytest.mark.asyncio
async def test_03_gcm_tag_tamper_fails_closed(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Test Case 3: GCM tag tamper (flip 1 byte) raises EnvelopeIntegrityError."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    service = AIProviderConfigService(db_session, kek_provider)

    config = await service.create_config(
        workspace_id=ws_id,
        provider_kind="fixture",
        display_name="Fixture LLM",
        model_allowlist=["fixture-fast"],
        residency_tier="test-tier",
        api_key=bytearray(b"fixture-secret-token"),
    )

    assert config.wrapped_api_key is not None
    assert config.api_key_nonce is not None
    assert config.wrapped_dek is not None
    assert config.dek_kid is not None

    # Flip 1 byte in the wrapped API key ciphertext/tag
    tampered_bytes = bytearray(config.wrapped_api_key)
    tampered_bytes[-1] ^= 0x01

    tampered_secret = (
        bytes(tampered_bytes),
        config.api_key_nonce,
        config.wrapped_dek,
        config.dek_kid,
    )

    with pytest.raises(EnvelopeIntegrityError) as exc_info:
        await service.unwrap_api_key(config.id, secret_override=tampered_secret)

    assert exc_info.value.code == "TAG_MISMATCH"


@pytest.mark.asyncio
async def test_04_save_gemini_air_gap_violation(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Test Case 4: Security: save gemini/openai with air_gap_mode=TRUE raises AirGapViolation."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    service = AIProviderConfigService(db_session, kek_provider)

    # 1. Saving gemini under air_gap_mode=True raises AirGapViolation
    with pytest.raises(AirGapViolation) as exc_gemini:
        await service.create_config(
            workspace_id=ws_id,
            provider_kind="gemini",
            display_name="Cloud Gemini",
            model_allowlist=["gemini-1.5-pro"],
            air_gap_mode=True,
        )
    assert exc_gemini.value.code == "AIR_GAP_EGRESS_DENIED"

    # 2. Saving openai under air_gap_mode=True raises AirGapViolation
    with pytest.raises(AirGapViolation) as exc_openai:
        await service.create_config(
            workspace_id=ws_id,
            provider_kind="openai",
            display_name="Cloud OpenAI",
            model_allowlist=["gpt-4o"],
            air_gap_mode=True,
        )
    assert exc_openai.value.code == "AIR_GAP_EGRESS_DENIED"

    # 3. Saving ollama and fixture under air_gap_mode=True is permitted
    ollama_cfg = await service.create_config(
        workspace_id=ws_id,
        provider_kind="ollama",
        display_name="Local Ollama",
        model_allowlist=["llama3.1:8b"],
        air_gap_mode=True,
    )
    assert ollama_cfg.provider_kind == "ollama"

    fixture_cfg = await service.create_config(
        workspace_id=ws_id,
        provider_kind="fixture",
        display_name="Fixture LLM",
        model_allowlist=["fixture-model"],
        air_gap_mode=True,
    )
    assert fixture_cfg.provider_kind == "fixture"

    # 4. Saving gemini under air_gap_mode=False succeeds
    cloud_ok = await service.create_config(
        workspace_id=ws_id,
        provider_kind="gemini",
        display_name="Permitted Cloud Gemini",
        model_allowlist=["gemini-1.5-pro"],
        air_gap_mode=False,
    )
    assert cloud_ok.provider_kind == "gemini"


@pytest.mark.asyncio
async def test_05_plaintext_bytearray_zeroized_after_create(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Test Case 5: Security: plaintext bytearray is all zero bytes after create() returns."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    service = AIProviderConfigService(db_session, kek_provider)

    secret_payload = b"test-sensitive-api-token-must-be-scrubbed"
    key_buf = bytearray(secret_payload)
    assert any(b != 0 for b in key_buf)

    config = await service.create_config(
        workspace_id=ws_id,
        provider_kind="openai",
        display_name="Zeroize Test Provider",
        model_allowlist=["gpt-4o"],
        api_key=key_buf,
    )

    # In-place zeroization verified: every single byte in the caller's bytearray is 0x00
    assert len(key_buf) == len(secret_payload)
    assert all(b == 0 for b in key_buf)

    # Key was sealed properly and can still be unwrapped
    unwrapped = await service.unwrap_api_key(config.id)
    assert unwrapped == bytearray(secret_payload)


def test_base_url_validation_matrix() -> None:
    """Verify base_url constraints: schemes, userinfo, queries, fragments, and loopback rules."""
    # Valid configurations
    assert validate_base_url(None) is None
    assert validate_base_url("   ") is None
    assert validate_base_url("https://api.openai.com/v1") == "https://api.openai.com/v1"
    assert validate_base_url("http://127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert validate_base_url("http://localhost:8000") == "http://localhost:8000"
    assert validate_base_url("http://[::1]:8080") == "http://[::1]:8080"

    # Invalid schemes
    with pytest.raises(AIConfigValidationError, match="scheme must be 'http' or 'https'"):
        validate_base_url("ftp://127.0.0.1:11434")

    # Userinfo rejected
    with pytest.raises(AIConfigValidationError, match="userinfo"):
        validate_base_url("https://user:pass@api.openai.com/v1")

    # Query parameters rejected
    with pytest.raises(AIConfigValidationError, match="query parameters"):
        validate_base_url("https://api.openai.com/v1?token=123")

    # Fragment rejected
    with pytest.raises(AIConfigValidationError, match="fragment"):
        validate_base_url("https://api.openai.com/v1#heading")

    # Insecure HTTP on non-loopback rejected
    with pytest.raises(AIConfigValidationError, match="must use HTTPS unless targeting loopback"):
        validate_base_url("http://api.openai.com/v1")


@pytest.mark.asyncio
async def test_field_validation_errors(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Verify validation errors for provider_kind, display_name, models, and residency_tier."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    service = AIProviderConfigService(db_session, kek_provider)

    # 1. Invalid provider kind
    with pytest.raises(AIConfigValidationError, match="provider_kind must be one of"):
        await service.create_config(
            workspace_id=ws_id,
            provider_kind="unknown-kind",
            display_name="Invalid Provider",
            model_allowlist=["model-1"],
        )

    # 2. Display name too short or too long
    with pytest.raises(AIConfigValidationError, match="display_name length"):
        await service.create_config(
            workspace_id=ws_id,
            provider_kind="fixture",
            display_name="",
            model_allowlist=["model-1"],
        )
    with pytest.raises(AIConfigValidationError, match="display_name length"):
        await service.create_config(
            workspace_id=ws_id,
            provider_kind="fixture",
            display_name="A" * 81,
            model_allowlist=["model-1"],
        )

    # 3. Model allowlist empty or too large or containing empty items
    with pytest.raises(AIConfigValidationError, match="model_allowlist cardinality"):
        await service.create_config(
            workspace_id=ws_id,
            provider_kind="fixture",
            display_name="Empty Models",
            model_allowlist=[],
        )
    with pytest.raises(AIConfigValidationError, match="model_allowlist cardinality"):
        await service.create_config(
            workspace_id=ws_id,
            provider_kind="fixture",
            display_name="Too Many Models",
            model_allowlist=[f"m-{i}" for i in range(33)],
        )
    with pytest.raises(AIConfigValidationError, match="non-empty string"):
        await service.create_config(
            workspace_id=ws_id,
            provider_kind="fixture",
            display_name="Blank Model Entry",
            model_allowlist=["valid", "  "],
        )

    # 4. Residency tier regex violation
    with pytest.raises(AIConfigValidationError, match="residency_tier must match"):
        await service.create_config(
            workspace_id=ws_id,
            provider_kind="fixture",
            display_name="Bad Residency",
            model_allowlist=["model-1"],
            residency_tier="INVALID TIER WITH SPACES",
        )


@pytest.mark.asyncio
async def test_crud_and_lifecycle_operations(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Verify create, get, list, update, disable, delete, and string/bytes API key support."""
    ws_id, admin_id = await bootstrap_workspace_admin(db_session)
    proj_id = await create_project(db_session, ws_id, identifier="PRJ", created_by_id=admin_id)

    service = AIProviderConfigService(db_session, kek_provider)

    # 1. Create with str key and project_id
    cfg1 = await service.create_config(
        workspace_id=ws_id,
        project_id=proj_id,
        provider_kind="fixture",
        display_name="Provider 1",
        model_allowlist=["model-a"],
        priority=10,
        api_key="str-api-key-test",
    )
    assert cfg1.project_id == proj_id

    # 2. Create with bytes key (no project_id -> workspace default)
    cfg2 = await service.create_config(
        workspace_id=ws_id,
        project_id=None,
        provider_kind="ollama",
        display_name="Provider 2",
        model_allowlist=["model-b"],
        priority=20,
        api_key=b"bytes-api-key-test",
    )

    # 3. Create without key
    cfg3 = await service.create_config(
        workspace_id=ws_id,
        provider_kind="fixture",
        display_name="Provider 3",
        model_allowlist=["model-c"],
        priority=5,
    )
    assert cfg3.wrapped_api_key is None
    pub3 = service.to_public_dict(cfg3)
    assert pub3["api_key_set"] is False

    # 4. List configs
    all_ws = await service.list_configs(ws_id)
    assert len(all_ws) == 3
    # Ordered by priority: cfg3 (5), cfg1 (10), cfg2 (20)
    assert [c.id for c in all_ws] == [cfg3.id, cfg1.id, cfg2.id]

    proj_only = await service.list_configs(ws_id, project_id=proj_id)
    assert len(proj_only) == 1
    assert proj_only[0].id == cfg1.id

    # 5. Get config
    fetched = await service.get_config(cfg1.id)
    assert fetched is not None
    assert fetched.display_name == "Provider 1"
    assert await service.get_config(uuid.uuid4()) is None

    # 6. Update config fields
    new_key = bytearray(b"rotated-secret-key")
    updated = await service.update_config(
        cfg1.id,
        display_name="Updated Provider 1",
        model_allowlist=["model-a-new", "model-a-v2"],
        residency_tier="eu-west-1",
        base_url="http://127.0.0.1:9000",
        priority=50,
        settings_json={"timeout": 30},
        api_key=new_key,
        is_enabled=True,
    )
    assert updated.display_name == "Updated Provider 1"
    assert updated.model_allowlist == ["model-a-new", "model-a-v2"]
    assert updated.residency_tier == "eu-west-1"
    assert updated.base_url == "http://127.0.0.1:9000"
    assert updated.priority == 50
    assert updated.settings_json == {"timeout": 30}
    assert all(b == 0 for b in new_key)  # zeroized

    # Verify unwrapped key is updated key
    unwrapped_new = await service.unwrap_api_key(cfg1.id)
    assert unwrapped_new == bytearray(b"rotated-secret-key")

    # 7. Update air-gap check
    cloud_cfg = await service.create_config(
        workspace_id=ws_id,
        provider_kind="openai",
        display_name="Cloud For Update",
        model_allowlist=["gpt-4o"],
        air_gap_mode=False,
    )
    with pytest.raises(AirGapViolation):
        await service.update_config(cloud_cfg.id, air_gap_mode=True)

    # 8. Update validation error checks
    with pytest.raises(AIConfigNotFoundError):
        await service.update_config(uuid.uuid4(), display_name="Ghost")
    with pytest.raises(AIConfigValidationError):
        await service.update_config(cfg1.id, display_name="")
    with pytest.raises(AIConfigValidationError):
        await service.update_config(cfg1.id, model_allowlist=[])
    with pytest.raises(AIConfigValidationError):
        await service.update_config(cfg1.id, residency_tier="BAD TIER")

    # 9. Disable config
    disabled = await service.disable_config(cfg2.id)
    assert disabled.is_enabled is False

    # 10. Delete config
    await service.delete_config(cfg2.id)
    assert await service.get_config(cfg2.id) is None


@pytest.mark.asyncio
async def test_unwrap_edge_cases(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Verify unwrap_api_key edge cases: missing config and missing secret."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    service = AIProviderConfigService(db_session, kek_provider)

    cfg = await service.create_config(
        workspace_id=ws_id,
        provider_kind="fixture",
        display_name="No Key Provider",
        model_allowlist=["m1"],
    )

    # 1. Row has no secret -> AIConfigNotFoundError
    with pytest.raises(AIConfigNotFoundError, match="No secret or configuration found"):
        await service.unwrap_api_key(cfg.id)

    # 2. Non-existent ID -> AIConfigNotFoundError
    with pytest.raises(AIConfigNotFoundError, match="No secret or configuration found"):
        await service.unwrap_api_key(uuid.uuid4())

    # 3. Secret override with non-existent ID -> AIConfigNotFoundError
    with pytest.raises(AIConfigNotFoundError, match="not found"):
        await service.unwrap_api_key(
            uuid.uuid4(),
            secret_override=(b"k", b"n" * 12, b"d", "kek-v1"),
        )


def test_private_lan_and_ssrf_base_urls() -> None:
    """Verify validate_base_url allows private LAN and rejects SSRF/metadata/insecure public."""
    # 1. RFC1918 private IPv4 addresses allowed over http
    assert validate_base_url("http://10.0.0.1:11434") == "http://10.0.0.1:11434"
    assert validate_base_url("http://172.16.0.5:8000/v1") == "http://172.16.0.5:8000/v1"
    assert validate_base_url("http://192.168.1.100:8080") == "http://192.168.1.100:8080"

    # 2. IPv6 ULA (fc00::/7) allowed over http
    assert validate_base_url("http://[fc00::1]:8000") == "http://[fc00::1]:8000"
    assert (
        validate_base_url("http://[fd12:3456:789a::1]:11434") == "http://[fd12:3456:789a::1]:11434"
    )

    # 3. Pinned private LAN hostnames allowed over http
    assert validate_base_url("http://ollama.local:11434") == "http://ollama.local:11434"
    assert validate_base_url("http://vllm.internal:8000") == "http://vllm.internal:8000"
    assert validate_base_url("http://inference.lan:8000") == "http://inference.lan:8000"
    assert validate_base_url("http://model.home:8000") == "http://model.home:8000"
    assert validate_base_url("http://cluster.corp:8000") == "http://cluster.corp:8000"

    # 4. Public HTTPS allowed
    assert validate_base_url("https://api.openai.com/v1") == "https://api.openai.com/v1"
    assert (
        validate_base_url("https://generativelanguage.googleapis.com")
        == "https://generativelanguage.googleapis.com"
    )

    # 5. Public HTTP rejected
    with pytest.raises(AIConfigValidationError, match="must use HTTPS"):
        validate_base_url("http://api.openai.com/v1")
    with pytest.raises(AIConfigValidationError, match="must use HTTPS"):
        validate_base_url("http://8.8.8.8:8000")

    # 6. Hard-denied cloud metadata and link-local rejected on HTTP and HTTPS
    with pytest.raises(AIConfigValidationError, match="link-local, multicast, or metadata"):
        validate_base_url("http://169.254.169.254/latest/meta-data")
    with pytest.raises(AIConfigValidationError, match="link-local, multicast, or metadata"):
        validate_base_url("https://169.254.169.254")
    with pytest.raises(AIConfigValidationError, match="link-local, multicast, or metadata"):
        validate_base_url("http://[fe80::1]:8000")
    with pytest.raises(AIConfigValidationError, match="link-local, multicast, or metadata"):
        validate_base_url("http://100.64.0.1:8000")
    with pytest.raises(AIConfigValidationError, match="link-local, multicast, or metadata"):
        validate_base_url("http://0.0.0.0:8000")
    with pytest.raises(AIConfigValidationError, match="link-local, multicast, or metadata"):
        validate_base_url("http://224.0.0.1:8000")
    with pytest.raises(AIConfigValidationError, match="link-local, multicast, or metadata"):
        validate_base_url("http://[ff02::1]:8000")


@pytest.mark.asyncio
async def test_air_gap_with_local_openai(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Verify local openai endpoints are allowed under air gap mode, while cloud is rejected."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    service = AIProviderConfigService(db_session, kek_provider)

    # 1. Local OpenAI endpoint with private LAN base_url works under air-gap
    local_cfg = await service.create_config(
        workspace_id=ws_id,
        provider_kind="openai",
        display_name="Local vLLM Server",
        model_allowlist=["llama-3-70b"],
        base_url="http://192.168.1.50:8000/v1",
        air_gap_mode=True,
    )
    assert local_cfg.base_url == "http://192.168.1.50:8000/v1"

    # 2. Cloud OpenAI endpoint without local base_url fails under air-gap
    with pytest.raises(AirGapViolation, match="outbound cloud egress"):
        await service.create_config(
            workspace_id=ws_id,
            provider_kind="openai",
            display_name="Cloud OpenAI",
            model_allowlist=["gpt-4o"],
            base_url="https://api.openai.com/v1",
            air_gap_mode=True,
        )


@pytest.mark.asyncio
async def test_probe_provider_ollama(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Verify probe_provider for ollama returns models on 200 and handles non-200."""
    await bootstrap_workspace_admin(db_session)
    service = AIProviderConfigService(db_session, kek_provider)

    # 1. Successful probe
    mock_resp = mock.MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"models": [{"name": "llama3:8b"}, {"name": "mistral:latest"}]}

    with mock.patch.object(httpx.AsyncClient, "get", new_callable=mock.AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await service.probe_provider(
            provider_kind="ollama",
            base_url="http://127.0.0.1:11434",
        )
        assert res["ok"] is True
        assert res["models"] == ["llama3:8b", "mistral:latest"]
        assert res["model_count"] == 2
        assert res["error_code"] is None
        assert mock_get.call_args[0][0] == "http://127.0.0.1:11434/api/tags"

    # 2. HTTP error response
    mock_err_resp = mock.MagicMock(spec=httpx.Response)
    mock_err_resp.status_code = 503
    mock_err_resp.text = "Service Unavailable"

    with mock.patch.object(httpx.AsyncClient, "get", new_callable=mock.AsyncMock) as mock_get:
        mock_get.return_value = mock_err_resp
        res = await service.probe_provider(
            provider_kind="ollama",
            base_url="http://127.0.0.1:11434",
        )
        assert res["ok"] is False
        assert res["error_code"] == "HTTP_503"
        assert "Service Unavailable" in res["message"]


@pytest.mark.asyncio
async def test_probe_provider_gemini_and_headers(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Verify probe_provider sends x-goog-api-key header and strips prefix."""
    await bootstrap_workspace_admin(db_session)
    service = AIProviderConfigService(db_session, kek_provider)

    # 1. Successful probe with x-goog-api-key header
    mock_resp = mock.MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "models/gemini-1.5-pro"}, {"name": "models/gemini-1.5-flash"}]
    }

    with (
        mock.patch("kanban.ai_config.service.resolve_and_pin", new_callable=mock.AsyncMock),
        mock.patch.object(httpx.AsyncClient, "get", new_callable=mock.AsyncMock) as mock_get,
    ):
        mock_get.return_value = mock_resp
        res = await service.probe_provider(
            provider_kind="gemini",
            api_key="secret-gemini-key",
        )
        assert res["ok"] is True
        assert res["models"] == ["gemini-1.5-pro", "gemini-1.5-flash"]
        assert res["model_count"] == 2

        # Verify x-goog-api-key header was used, not ?key= URL query
        called_url = mock_get.call_args[0][0]
        assert "?key=" not in called_url
        headers = mock_get.call_args[1].get("headers", {})
        assert headers.get("x-goog-api-key") == "secret-gemini-key"

    # 2. Upstream auth failure
    mock_auth_fail = mock.MagicMock(spec=httpx.Response)
    mock_auth_fail.status_code = 401
    mock_auth_fail.text = "API key not valid"

    with (
        mock.patch("kanban.ai_config.service.resolve_and_pin", new_callable=mock.AsyncMock),
        mock.patch.object(httpx.AsyncClient, "get", new_callable=mock.AsyncMock) as mock_get,
    ):
        mock_get.return_value = mock_auth_fail
        res = await service.probe_provider(
            provider_kind="gemini",
            api_key="invalid-key",
        )
        assert res["ok"] is False
        assert res["error_code"] == "UPSTREAM_AUTH_FAILED"


@pytest.mark.asyncio
async def test_probe_provider_openai_and_network_errors(  # noqa: PLR0915
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Verify probe_provider for openai handles fallback, connection errors, and timeouts."""
    await bootstrap_workspace_admin(db_session)
    service = AIProviderConfigService(db_session, kek_provider)

    # 1. OpenAI 404 fallback from /v1/models to /models
    resp_404 = mock.MagicMock(spec=httpx.Response)
    resp_404.status_code = 404
    resp_200 = mock.MagicMock(spec=httpx.Response)
    resp_200.status_code = 200
    resp_200.json.return_value = {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]}

    with mock.patch.object(httpx.AsyncClient, "get", new_callable=mock.AsyncMock) as mock_get:
        mock_get.side_effect = [resp_404, resp_200]
        res = await service.probe_provider(
            provider_kind="openai",
            base_url="http://127.0.0.1:8000",
            api_key="test-key",
        )
        assert res["ok"] is True
        assert res["models"] == ["gpt-4o", "gpt-4o-mini"]
        assert mock_get.call_count == 2

    # 2. Connection refused error
    with mock.patch.object(httpx.AsyncClient, "get", new_callable=mock.AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        res = await service.probe_provider(
            provider_kind="openai",
            base_url="http://127.0.0.1:8000/v1",
        )
        assert res["ok"] is False
        assert res["error_code"] == "CONNECTION_REFUSED"

    # 3. Upstream timeout error
    with mock.patch.object(httpx.AsyncClient, "get", new_callable=mock.AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Timed out")
        res = await service.probe_provider(
            provider_kind="openai",
            base_url="http://127.0.0.1:8000/v1",
        )
        assert res["ok"] is False
        assert res["error_code"] == "UPSTREAM_TIMEOUT"

    # 4. Air gap rejection during probe
    res_air_gap = await service.probe_provider(
        provider_kind="openai",
        base_url="https://api.openai.com/v1",
        air_gap_mode=True,
    )
    assert res_air_gap["ok"] is False
    assert res_air_gap["error_code"] == "AIR_GAP_EGRESS_DENIED"

    # 5. Invalid base URL during probe
    res_bad_url = await service.probe_provider(
        provider_kind="openai",
        base_url="ftp://127.0.0.1",
    )
    assert res_bad_url["ok"] is False
    assert res_bad_url["error_code"] == "INVALID_BASE_URL"

    # 6. EgressDeniedError during probe
    with mock.patch(
        "kanban.ai_config.service.resolve_and_pin", new_callable=mock.AsyncMock
    ) as mock_pin:
        mock_pin.side_effect = EgressDeniedError("SSRF denied", code="METADATA_DENIED")
        res_egress = await service.probe_provider(
            provider_kind="ollama",
            base_url="http://127.0.0.1:11434",
        )
        assert res_egress["ok"] is False
        assert res_egress["error_code"] == "METADATA_DENIED"

    # 7. Generic unexpected Exception during probe
    with mock.patch.object(httpx.AsyncClient, "get", new_callable=mock.AsyncMock) as mock_get:
        mock_get.side_effect = RuntimeError("Fatal hardware failure")
        res_err = await service.probe_provider(
            provider_kind="openai",
            base_url="http://127.0.0.1:8000/v1",
        )
        assert res_err["ok"] is False
        assert res_err["error_code"] == "PROBE_ERROR"

    # 8. Gemini HTTP 500 error
    resp_500 = mock.MagicMock(spec=httpx.Response)
    resp_500.status_code = 500
    resp_500.text = "Internal error"
    with (
        mock.patch("kanban.ai_config.service.resolve_and_pin", new_callable=mock.AsyncMock),
        mock.patch.object(httpx.AsyncClient, "get", new_callable=mock.AsyncMock) as mock_get,
    ):
        mock_get.return_value = resp_500
        res_g500 = await service.probe_provider(
            provider_kind="gemini",
            api_key="valid-key",
        )
        assert res_g500["ok"] is False
        assert res_g500["error_code"] == "HTTP_500"

    # 9. OpenAI HTTP 500 error
    with (
        mock.patch("kanban.ai_config.service.resolve_and_pin", new_callable=mock.AsyncMock),
        mock.patch.object(httpx.AsyncClient, "get", new_callable=mock.AsyncMock) as mock_get,
    ):
        mock_get.return_value = resp_500
        res_o500 = await service.probe_provider(
            provider_kind="openai",
            base_url="http://127.0.0.1:8000/v1",
        )
        assert res_o500["ok"] is False
        assert res_o500["error_code"] == "HTTP_500"

    # 7. Empty host rejected
    with pytest.raises(AIConfigValidationError, match="valid host"):
        validate_base_url("http://:8080")


@pytest.mark.asyncio
async def test_budget_additional_branches(
    db_session: AsyncSession,
    kek_provider: StaticKekProvider,
) -> None:
    """Verify set_budget and get_budgets validation branches and monthly period."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    service = AIProviderConfigService(db_session, kek_provider)
    proj_id = await create_project(db_session, ws_id, identifier="BPRJ")

    cfg = await service.create_config(
        workspace_id=ws_id,
        provider_kind="ollama",
        display_name="Budget Ollama",
        model_allowlist=["llama3"],
    )

    # 1. Invalid period_kind
    with pytest.raises(AIConfigValidationError, match="period_kind must be 'daily' or 'monthly'"):
        await service.set_budget(ws_id, cfg.id, period_kind="yearly", token_cap=1000)

    # 2. Negative token_cap
    with pytest.raises(AIConfigValidationError, match="token_cap must be between 0"):
        await service.set_budget(ws_id, cfg.id, period_kind="daily", token_cap=-1)

    # 3. Monthly budget creation and update
    monthly_b = await service.set_budget(
        ws_id, cfg.id, period_kind="monthly", token_cap=50000, project_id=proj_id
    )
    assert monthly_b.period_kind == "monthly"
    assert monthly_b.token_cap == 50000
    assert monthly_b.project_id == proj_id

    # Update existing monthly budget
    monthly_updated = await service.set_budget(
        ws_id, cfg.id, period_kind="monthly", token_cap=60000, project_id=proj_id
    )
    assert monthly_updated.token_cap == 60000

    # 4. get_budgets with project_id
    budgets = await service.get_budgets(cfg.id, project_id=proj_id)
    assert len(budgets) == 1
    assert budgets[0].project_id == proj_id
