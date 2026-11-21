# Copyright 2026 Kanban Platform Contributors
"""Comprehensive unit tests for GeminiProvider adapter and GeminiSettings."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from google.auth.credentials import Credentials
from pydantic import BaseModel, HttpUrl, SecretStr, ValidationError

from agent.providers.base import (
    CompletionRequest,
    EmbedBatchRequest,
    StreamChunk,
    StructuredRequest,
    StructuredResponse,
)
from agent.providers.errors import (
    ProviderHTTPError,
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderSafetyBlock,
    ProviderSchemaError,
    ProviderTimeout,
)
from agent.providers.gemini import (
    DEFAULT_SAFETY_SETTINGS,
    GeminiProvider,
    GeminiSettings,
    SafetySetting,
)
from agent.providers.registry import build_provider
from agent.testing.fixtures import FixtureLLMProvider, load_cassette
from agent.testing.http_cassette import CassetteTransport


class ApprovalResult(BaseModel):
    """Test schema for structured validation."""

    status: str
    confidence: float


class MockCredentials(Credentials):
    """Hermetic mock credentials for Vertex AI client instantiation."""

    def __init__(self) -> None:
        """Initialize mock credentials with synthetic token."""
        super().__init__()  # type: ignore[no-untyped-call]
        self.token = "mock-bearer-token"

    def refresh(self, request: object) -> None:
        """Mock refresh by assigning static token."""
        _ = request
        self.token = "mock-bearer-token"

    @property
    def valid(self) -> bool:
        """Return True indicating valid credential token."""
        return True


def _make_ai_studio_settings(
    *,
    api_key: str = "test-gemini-key-123",
    model_allowlist: tuple[str, ...] = (
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "text-embedding-004",
    ),
    safety_settings: tuple[SafetySetting, ...] = DEFAULT_SAFETY_SETTINGS,
    timeout_s: float = 30.0,
) -> GeminiSettings:
    return GeminiSettings(
        mode="ai_studio_paid",
        api_key=SecretStr(api_key),
        model_allowlist=model_allowlist,
        safety_settings=safety_settings,
        timeout_s=timeout_s,
    )


# ---------------------------------------------------------------------------
# Test Case 1: Positive Streamed Text & Safety Settings in Body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_1_positive_stream_text_and_safety_settings() -> None:
    """Streamed chunks match cassette and request body carries configured safetySettings."""
    cassette_path = Path("tests/fixtures/ai/gemini_stream_ok.yaml")
    transport = CassetteTransport(cassette_path)
    settings = _make_ai_studio_settings()
    provider = GeminiProvider(settings, transport=transport)

    req = CompletionRequest(
        model="gemini-2.5-flash",
        prompt="Hello Gemini",
        temperature=0.2,
        max_output_tokens=128,
    )

    chunks = [chunk async for chunk in provider.stream_complete(req)]

    assert len(chunks) == 3
    assert chunks[0].delta == "Hello "
    assert chunks[0].index == 0
    assert chunks[0].ttft_ms is not None
    assert chunks[1].delta == "from "
    assert chunks[1].index == 1
    assert chunks[2].delta == "Gemini!"
    assert chunks[2].index == 2
    assert chunks[2].finish_reason == "stop"
    assert chunks[2].prompt_tokens == 5
    assert chunks[2].completion_tokens == 3

    # Inspect captured wire request
    assert len(transport.requests) == 1
    req_body = json.loads(transport.requests[0].content.decode("utf-8"))
    assert "safetySettings" in req_body
    safety_list = req_body["safetySettings"]
    assert len(safety_list) == 4
    categories = {entry["category"] for entry in safety_list}
    assert categories == {
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
    }
    for entry in safety_list:
        assert entry["threshold"] == "BLOCK_MEDIUM_AND_ABOVE"


# ---------------------------------------------------------------------------
# Test Case 2: Positive Structured Output & Generation Config in Body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_2_positive_structured_output() -> None:
    """Structured output validated into Pydantic model and request has responseSchema."""
    cassette_path = Path("tests/fixtures/ai/gemini_structured_ok.yaml")
    transport = CassetteTransport(cassette_path)
    settings = _make_ai_studio_settings()
    provider = GeminiProvider(settings, transport=transport)

    req = StructuredRequest(
        model="gemini-2.5-flash",
        prompt="Classify this ticket",
        response_model=ApprovalResult,
        temperature=0.0,
    )

    resp = await provider.generate_structured(req)
    assert isinstance(resp, StructuredResponse)
    assert resp.parsed.status == "APPROVED"
    assert resp.parsed.confidence == 0.95
    assert resp.raw_json == '{"status": "APPROVED", "confidence": 0.95}'
    assert resp.prompt_tokens == 12
    assert resp.completion_tokens == 6
    assert resp.total_latency_ms >= 0.0

    # Inspect captured wire request
    assert len(transport.requests) == 1
    req_body = json.loads(transport.requests[0].content.decode("utf-8"))
    gen_cfg = req_body.get("generationConfig", {})
    assert gen_cfg.get("responseMimeType") == "application/json"
    assert "responseSchema" in gen_cfg
    schema = gen_cfg["responseSchema"]
    assert "status" in schema.get("properties", {})
    assert "confidence" in schema.get("properties", {})


# ---------------------------------------------------------------------------
# Test Case 3: Contract Parity with FixtureLLMProvider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_3_contract_parity_with_fixture_provider() -> None:
    """GeminiProvider and FixtureLLMProvider emit parity-compatible typed outputs."""
    # Compare streaming contract
    gemini_transport = CassetteTransport(Path("tests/fixtures/ai/gemini_stream_ok.yaml"))
    gemini_provider = GeminiProvider(_make_ai_studio_settings(), transport=gemini_transport)
    gemini_req = CompletionRequest(model="gemini-2.5-flash", prompt="Test")
    gemini_chunks = [c async for c in gemini_provider.stream_complete(gemini_req)]

    fixture_cas = load_cassette(Path("tests/fixtures/ai/echo_stream_ok.yaml"))
    fixture_provider = FixtureLLMProvider(fixture_cas)
    fixture_req = CompletionRequest(model="fixture-echo-v1", prompt="Hello")
    fixture_chunks = [c async for c in fixture_provider.stream_complete(fixture_req)]

    assert len(gemini_chunks) == len(fixture_chunks) == 3
    for g_chunk, f_chunk in zip(gemini_chunks, fixture_chunks, strict=True):
        assert isinstance(g_chunk, StreamChunk)
        assert isinstance(f_chunk, StreamChunk)
        assert g_chunk.index == f_chunk.index
        assert bool(g_chunk.delta) == bool(f_chunk.delta)
    assert gemini_chunks[0].ttft_ms is not None
    assert fixture_chunks[0].ttft_ms is not None
    assert gemini_chunks[-1].finish_reason == fixture_chunks[-1].finish_reason == "stop"


# ---------------------------------------------------------------------------
# Test Case 4: Security: Vertex Region Pinning & Global Rejection
# ---------------------------------------------------------------------------


def test_case_4_vertex_region_validation() -> None:
    """Vertex location must be in allowed_vertex_regions; 'global' is rejected."""
    # Region not in allowed regions
    with pytest.raises(ValidationError, match="not permitted"):
        GeminiSettings(
            mode="vertex",
            vertex_project="my-gcp-project",
            vertex_location="us-east4",
            allowed_vertex_regions=("europe-west4",),
            model_allowlist=("gemini-2.5-flash",),
        )

    # 'global' location rejected
    with pytest.raises(ValidationError, match="'global' region is rejected"):
        GeminiSettings(
            mode="vertex",
            vertex_project="my-gcp-project",
            vertex_location="global",
            allowed_vertex_regions=("global",),
            model_allowlist=("gemini-2.5-flash",),
        )

    # 'global' in allowed_vertex_regions rejected
    with pytest.raises(ValidationError, match="'global' region is rejected"):
        GeminiSettings(
            mode="vertex",
            vertex_project="my-gcp-project",
            vertex_location="europe-west4",
            allowed_vertex_regions=("europe-west4", "global"),
            model_allowlist=("gemini-2.5-flash",),
        )

    # Empty allowed regions rejected
    with pytest.raises(ValidationError, match="at least one region"):
        GeminiSettings(
            mode="vertex",
            vertex_project="my-gcp-project",
            vertex_location="europe-west4",
            allowed_vertex_regions=(),
            model_allowlist=("gemini-2.5-flash",),
        )

    # Valid Vertex settings
    valid = GeminiSettings(
        mode="vertex",
        vertex_project="my-gcp-project",
        vertex_location="europe-west4",
        allowed_vertex_regions=("europe-west4", "us-central1"),
        model_allowlist=("gemini-2.5-flash",),
    )
    provider = GeminiProvider(valid, credentials=MockCredentials())
    assert provider.residency_tier == "gemini-vertex:europe-west4"


# ---------------------------------------------------------------------------
# Test Case 5: Security: Free-tier Impossible & API Key Isolation
# ---------------------------------------------------------------------------


def test_case_5_free_tier_impossible_and_api_key_isolation() -> None:
    """Free tier 'ai_studio' is rejected; api_key forbidden for vertex."""
    # 'ai_studio' free tier mode rejected
    with pytest.raises(ValidationError):
        GeminiSettings.model_validate(
            {
                "mode": "ai_studio",
                "api_key": "some-key",
                "model_allowlist": ["gemini-2.5-flash"],
            }
        )

    # api_key present when mode is vertex
    with pytest.raises(ValidationError, match="api_key is forbidden when mode is 'vertex'"):
        GeminiSettings(
            mode="vertex",
            api_key=SecretStr("leak-key"),
            vertex_project="my-project",
            vertex_location="europe-west4",
            allowed_vertex_regions=("europe-west4",),
            model_allowlist=("gemini-2.5-flash",),
        )

    # missing api_key when mode is ai_studio_paid
    with pytest.raises(ValidationError, match="api_key is required"):
        GeminiSettings(
            mode="ai_studio_paid",
            api_key=None,
            model_allowlist=("gemini-2.5-flash",),
        )

    # empty api_key rejected
    with pytest.raises(ValidationError, match="api_key is required"):
        GeminiSettings(
            mode="ai_studio_paid",
            api_key=SecretStr("   "),
            model_allowlist=("gemini-2.5-flash",),
        )

    # vertex fields provided when mode is ai_studio_paid
    with pytest.raises(ValidationError, match="forbidden when mode is 'ai_studio_paid'"):
        GeminiSettings(
            mode="ai_studio_paid",
            api_key=SecretStr("valid-key"),
            vertex_project="unwanted-project",
            model_allowlist=("gemini-2.5-flash",),
        )


# ---------------------------------------------------------------------------
# Test Case 6: Security: Secret Redaction in Repr, Str, and Exceptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_6_secret_redaction() -> None:
    """API key secret is never exposed in repr(settings), str(provider), or exceptions."""
    secret_key = "AIzaSyD-SecretGeminiKey12345"
    settings = _make_ai_studio_settings(api_key=secret_key)
    provider = GeminiProvider(settings)

    # Repr / str assertions
    assert secret_key not in repr(settings)
    assert secret_key not in str(provider)
    assert secret_key not in repr(provider)

    # Exception message redaction on HTTP fault
    fault_transport = CassetteTransport(Path("tests/fixtures/ai/gemini_fault_429.yaml"))
    fault_provider = GeminiProvider(settings, transport=fault_transport)
    req = CompletionRequest(model="gemini-2.5-flash", prompt="ping")

    with pytest.raises(ProviderHTTPError) as exc_info:
        async for _ in fault_provider.stream_complete(req):
            pass
    assert secret_key not in str(exc_info.value)
    assert secret_key not in repr(exc_info.value)

    # Health probe failure redaction
    health = await fault_provider.health_probe()
    assert health.ok is False
    assert health.detail is not None
    assert secret_key not in health.detail


# ---------------------------------------------------------------------------
# Test Case 7: Fault Injection (429, 503, Timeout, Safety Block)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_7_fault_injection() -> None:
    """429, 503, timeout, and safety blocks raise typed ProviderError subclasses."""
    settings = _make_ai_studio_settings()

    # Fault 429
    t_429 = CassetteTransport(Path("tests/fixtures/ai/gemini_fault_429.yaml"))
    p_429 = GeminiProvider(settings, transport=t_429)
    req = CompletionRequest(model="gemini-2.5-flash", prompt="test")
    with pytest.raises(ProviderHTTPError) as exc_429:
        async for _ in p_429.stream_complete(req):
            pass
    assert exc_429.value.status == 429

    # Fault 503
    t_503 = CassetteTransport(Path("tests/fixtures/ai/gemini_fault_503.yaml"))
    p_503 = GeminiProvider(settings, transport=t_503)
    with pytest.raises(ProviderHTTPError) as exc_503:
        async for _ in p_503.stream_complete(req):
            pass
    assert exc_503.value.status == 503

    # Timeout
    t_timeout = CassetteTransport(Path("tests/fixtures/ai/gemini_fault_timeout.yaml"))
    p_timeout = GeminiProvider(settings, transport=t_timeout)
    with pytest.raises(ProviderTimeout):
        async for _ in p_timeout.stream_complete(req):
            pass

    # Safety Block
    t_safety = CassetteTransport(Path("tests/fixtures/ai/gemini_safety_block.yaml"))
    p_safety = GeminiProvider(settings, transport=t_safety)
    with pytest.raises(ProviderSafetyBlock):
        async for _ in p_safety.stream_complete(req):
            pass


# ---------------------------------------------------------------------------
# Test Case 8: Negative Structured Schema Mismatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_8_structured_schema_mismatch() -> None:
    """Missing required schema field raises ProviderSchemaError."""
    cassette_path = Path("tests/fixtures/ai/gemini_structured_schema_mismatch.yaml")
    transport = CassetteTransport(cassette_path)
    settings = _make_ai_studio_settings()
    provider = GeminiProvider(settings, transport=transport)

    req = StructuredRequest(
        model="gemini-2.5-flash",
        prompt="Missing field prompt",
        response_model=ApprovalResult,
    )

    with pytest.raises(ProviderSchemaError, match="local schema validation"):
        await provider.generate_structured(req)


# ---------------------------------------------------------------------------
# Test Case 9: Boundary Checks (Allowlist, Batch Bounds, Embeddings)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_9_boundary_allowlist_and_batch_bounds() -> None:
    """Model outside allowlist triggers MODEL_NOT_ALLOWED; batch > 64 rejected."""
    settings = _make_ai_studio_settings(model_allowlist=("gemini-2.5-flash", "text-embedding-004"))
    transport = CassetteTransport([])
    provider = GeminiProvider(settings, transport=transport)

    # Model not allowed in stream
    req_stream = CompletionRequest(model="unapproved-model", prompt="hi")
    with pytest.raises(ProviderPolicyError) as exc_policy:
        async for _ in provider.stream_complete(req_stream):
            pass
    assert exc_policy.value.code == "MODEL_NOT_ALLOWED"
    assert transport.call_count == 0

    # Model not allowed in structured
    req_struct = StructuredRequest(
        model="unapproved-model",
        prompt="hi",
        response_model=ApprovalResult,
    )
    with pytest.raises(ProviderPolicyError) as exc_policy_s:
        await provider.generate_structured(req_struct)
    assert exc_policy_s.value.code == "MODEL_NOT_ALLOWED"

    # Model not allowed in embed
    req_embed_bad_model = EmbedBatchRequest(model="unapproved-model", inputs=("hello",))
    with pytest.raises(ProviderPolicyError) as exc_policy_e:
        await provider.embed_batch(req_embed_bad_model)
    assert exc_policy_e.value.code == "MODEL_NOT_ALLOWED"

    # Embed batch > 64 rejected (using model_construct to bypass Pydantic DTO validator)
    req_embed_oversize = EmbedBatchRequest.model_construct(
        model="text-embedding-004",
        inputs=tuple(f"text {i}" for i in range(65)),
    )
    with pytest.raises(ProviderProtocolError) as exc_proto:
        await provider.embed_batch(req_embed_oversize)
    assert exc_proto.value.code == "BATCH_TOO_LARGE"

    # Embed input > 8192 chars rejected
    req_embed_large_char = EmbedBatchRequest.model_construct(
        model="text-embedding-004",
        inputs=("x" * 8193,),
    )
    with pytest.raises(ProviderProtocolError) as exc_input:
        await provider.embed_batch(req_embed_large_char)
    assert exc_input.value.code == "INPUT_TOO_LARGE"

    # Positive embed batch replay
    embed_transport = CassetteTransport(Path("tests/fixtures/ai/gemini_embed_ok.yaml"))
    embed_provider = GeminiProvider(settings, transport=embed_transport)
    req_embed = EmbedBatchRequest(
        model="text-embedding-004",
        inputs=("alpha", "beta"),
    )
    embeddings = await embed_provider.embed_batch(req_embed)
    assert len(embeddings) == 2
    assert embeddings[0] == [0.01, 0.02, 0.03, 0.04]
    assert embeddings[1] == [0.05, 0.06, 0.07, 0.08]


# ---------------------------------------------------------------------------
# Additional Coverage Tests: Health Probe, Registry, Prompt Blocking, Errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_probe_success() -> None:
    """Positive health probe returns HealthStatus(ok=True)."""
    exchange = {
        "request": {
            "method": "GET",
            "path": "/v1/models/gemini-2.5-flash",
        },
        "response": {
            "status": 200,
            "json_body": {"name": "models/gemini-2.5-flash"},
        },
    }
    transport = CassetteTransport([exchange])
    settings = _make_ai_studio_settings()
    provider = GeminiProvider(settings, transport=transport)

    health = await provider.health_probe()
    assert health.ok is True
    assert health.latency_ms >= 0.0
    assert "gemini-2.5-flash" in health.models


def test_registry_integration() -> None:
    """build_provider correctly builds GeminiProvider from settings and dict."""
    settings = _make_ai_studio_settings()
    p1 = build_provider("gemini", settings)
    assert isinstance(p1, GeminiProvider)
    assert p1.residency_tier == "gemini-ai-studio-paid"

    p2 = build_provider(
        "gemini",
        {
            "mode": "ai_studio_paid",
            "api_key": "test-dict-key",
            "model_allowlist": ["gemini-2.5-flash"],
        },
    )
    assert isinstance(p2, GeminiProvider)

    with pytest.raises(TypeError, match="GeminiSettings or dict"):
        build_provider("gemini", 12345)


@pytest.mark.asyncio
async def test_prompt_blocked_by_safety() -> None:
    """Prompt blocked by safety filters raises ProviderSafetyBlock."""
    exchange = {
        "request": {
            "method": "POST",
            "path": "/v1/models/gemini-2.5-flash:streamGenerateContent",
        },
        "response": {
            "status": 200,
            "sse_chunks": [
                json.dumps({"promptFeedback": {"blockReason": "SAFETY"}}),
            ],
        },
    }
    transport = CassetteTransport([exchange])
    provider = GeminiProvider(_make_ai_studio_settings(), transport=transport)
    req = CompletionRequest(model="gemini-2.5-flash", prompt="Harmful prompt")

    with pytest.raises(ProviderSafetyBlock, match="Prompt blocked by safety filters"):
        async for _ in provider.stream_complete(req):
            pass


@pytest.mark.asyncio
async def test_structured_prompt_blocked_by_safety() -> None:
    """Prompt blocked in structured generation raises ProviderSafetyBlock."""
    exchange = {
        "request": {
            "method": "POST",
            "path": "/v1/models/gemini-2.5-flash:generateContent",
        },
        "response": {
            "status": 200,
            "json_body": {"promptFeedback": {"blockReason": "SAFETY"}},
        },
    }
    transport = CassetteTransport([exchange])
    provider = GeminiProvider(_make_ai_studio_settings(), transport=transport)
    req = StructuredRequest(
        model="gemini-2.5-flash",
        prompt="Harmful prompt",
        response_model=ApprovalResult,
    )

    with pytest.raises(ProviderSafetyBlock, match="Prompt blocked by safety filters"):
        await provider.generate_structured(req)


@pytest.mark.asyncio
async def test_structured_candidate_safety_block() -> None:
    """Candidate safety block in structured generation raises ProviderSafetyBlock."""
    exchange = {
        "request": {
            "method": "POST",
            "path": "/v1/models/gemini-2.5-flash:generateContent",
        },
        "response": {
            "status": 200,
            "json_body": {
                "candidates": [
                    {
                        "finishReason": "SAFETY",
                        "safetyRatings": [
                            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "blocked": True}
                        ],
                    }
                ]
            },
        },
    }
    transport = CassetteTransport([exchange])
    provider = GeminiProvider(_make_ai_studio_settings(), transport=transport)
    req = StructuredRequest(
        model="gemini-2.5-flash",
        prompt="Harmful prompt",
        response_model=ApprovalResult,
    )

    with pytest.raises(ProviderSafetyBlock, match="Generation blocked by safety filters"):
        await provider.generate_structured(req)


@pytest.mark.asyncio
async def test_error_translation_http_status_error() -> None:
    """HTTPStatusError from httpx is mapped to ProviderHTTPError."""
    settings = _make_ai_studio_settings()
    provider = GeminiProvider(settings)

    req_mock = httpx.Request("GET", "https://example.com")
    resp_mock = httpx.Response(403, request=req_mock)
    raw_err = httpx.HTTPStatusError("Forbidden", request=req_mock, response=resp_mock)

    mapped = provider._translate_error(raw_err)  # noqa: SLF001
    assert isinstance(mapped, ProviderHTTPError)
    assert mapped.status == 403


@pytest.mark.asyncio
async def test_error_translation_unexpected() -> None:
    """Generic unexpected exception maps to ProviderProtocolError."""
    settings = _make_ai_studio_settings()
    provider = GeminiProvider(settings)

    mapped = provider._translate_error(RuntimeError("Unexpected glitch"))  # noqa: SLF001
    assert isinstance(mapped, ProviderProtocolError)
    assert "Unexpected glitch" in mapped.message


def test_vertex_initialization_without_explicit_credentials() -> None:
    """Vertex mode can initialize without explicit credentials parameter."""
    settings = GeminiSettings(
        mode="vertex",
        vertex_project="my-gcp-project",
        vertex_location="europe-west4",
        allowed_vertex_regions=("europe-west4",),
        model_allowlist=("gemini-2.5-flash",),
    )
    provider = GeminiProvider(settings)
    assert provider.residency_tier == "gemini-vertex:europe-west4"


def test_settings_empty_model_allowlist_and_whitespace_vertex() -> None:
    """Empty model allowlist or empty vertex project/location raises ValidationError."""
    with pytest.raises(ValidationError, match="model_allowlist must contain at least one model"):
        GeminiSettings(
            mode="ai_studio_paid",
            api_key=SecretStr("valid-key"),
            model_allowlist=(),
        )

    with pytest.raises(ValidationError, match="vertex_project is required"):
        GeminiSettings(
            mode="vertex",
            vertex_project="   ",
            vertex_location="europe-west4",
            allowed_vertex_regions=("europe-west4",),
            model_allowlist=("gemini-2.5-flash",),
        )

    with pytest.raises(ValidationError, match="vertex_location is required"):
        GeminiSettings(
            mode="vertex",
            vertex_project="my-project",
            vertex_location="   ",
            allowed_vertex_regions=("europe-west4",),
            model_allowlist=("gemini-2.5-flash",),
        )


def test_translate_error_provider_error_passthrough() -> None:
    """ProviderError instances are passed through directly without re-wrapping."""
    settings = _make_ai_studio_settings()
    provider = GeminiProvider(settings)
    original_err = ProviderPolicyError("Direct policy error", code="CUSTOM_CODE")
    result = provider._translate_error(original_err)  # noqa: SLF001
    assert result is original_err


@pytest.mark.asyncio
async def test_stream_complete_max_tokens_and_text_attribute_fallback() -> None:
    """Stream chunks with MAX_TOKENS finish_reason map to 'length'."""
    exchange = {
        "request": {
            "method": "POST",
            "path": "/v1/models/gemini-2.5-flash:streamGenerateContent",
        },
        "response": {
            "status": 200,
            "sse_chunks": [
                json.dumps(
                    {
                        "candidates": [
                            {
                                "finishReason": "MAX_TOKENS",
                                "content": {"parts": [{"text": "Truncated content"}]},
                            }
                        ]
                    }
                ),
            ],
        },
    }
    transport = CassetteTransport([exchange])
    provider = GeminiProvider(_make_ai_studio_settings(), transport=transport)
    req = CompletionRequest(model="gemini-2.5-flash", prompt="Test length")
    chunks = [c async for c in provider.stream_complete(req)]
    assert len(chunks) == 1
    assert chunks[0].finish_reason == "length"
    assert chunks[0].delta == "Truncated content"


@pytest.mark.asyncio
async def test_generate_structured_text_fallback_and_no_usage() -> None:
    """Structured response without usageMetadata defaults token counts to 0."""
    exchange = {
        "request": {
            "method": "POST",
            "path": "/v1/models/gemini-2.5-flash:generateContent",
        },
        "response": {
            "status": 200,
            "json_body": {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": '{"status": "OK", "confidence": 1.0}'}]},
                    }
                ]
            },
        },
    }
    transport = CassetteTransport([exchange])
    provider = GeminiProvider(_make_ai_studio_settings(), transport=transport)
    req = StructuredRequest(
        model="gemini-2.5-flash",
        prompt="Test",
        response_model=ApprovalResult,
    )
    resp = await provider.generate_structured(req)
    assert resp.parsed.status == "OK"
    assert resp.prompt_tokens == 0
    assert resp.completion_tokens == 0


@pytest.mark.asyncio
async def test_embed_batch_empty_embeddings_and_error_handling() -> None:
    """Embed batch handles empty embeddings and maps transport errors."""
    # Empty embeddings in response
    exchange_empty = {
        "request": {
            "method": "POST",
            "path": "/v1/models/text-embedding-004:batchEmbedContents",
        },
        "response": {
            "status": 200,
            "json_body": {"embeddings": []},
        },
    }
    transport = CassetteTransport([exchange_empty])
    provider = GeminiProvider(_make_ai_studio_settings(), transport=transport)
    req = EmbedBatchRequest(model="text-embedding-004", inputs=("query",))
    res = await provider.embed_batch(req)
    assert res == []

    # Error handling during embed_batch
    exchange_err = {
        "request": {
            "method": "POST",
            "path": "/v1/models/text-embedding-004:batchEmbedContents",
        },
        "fault": {"kind": "timeout"},
    }
    transport_err = CassetteTransport([exchange_err])
    provider_err = GeminiProvider(_make_ai_studio_settings(), transport=transport_err)
    with pytest.raises(ProviderTimeout):
        await provider_err.embed_batch(req)


@pytest.mark.asyncio
async def test_health_probe_empty_allowlist_fallback() -> None:
    """Health probe with empty allowlist uses default model and probe works."""
    exchange = {
        "request": {
            "method": "GET",
            "path": "/v1/models/gemini-2.5-flash",
        },
        "response": {
            "status": 200,
            "json_body": {"name": "models/gemini-2.5-flash"},
        },
    }
    transport = CassetteTransport([exchange])
    settings = GeminiSettings.model_construct(
        mode="ai_studio_paid",
        api_key=SecretStr("key"),
        model_allowlist=(),
        safety_settings=DEFAULT_SAFETY_SETTINGS,
        timeout_s=30.0,
    )
    provider = GeminiProvider(settings, transport=transport)
    health = await provider.health_probe()
    assert health.ok is True


@pytest.mark.asyncio
async def test_generate_structured_fault_exception() -> None:
    """Exception during generate_structured is translated to ProviderError."""
    exchange = {
        "request": {
            "method": "POST",
            "path": "/v1/models/gemini-2.5-flash:generateContent",
        },
        "fault": {"kind": "http_429"},
    }
    transport = CassetteTransport([exchange])
    provider = GeminiProvider(_make_ai_studio_settings(), transport=transport)
    req = StructuredRequest(
        model="gemini-2.5-flash",
        prompt="Test",
        response_model=ApprovalResult,
    )
    with pytest.raises(ProviderHTTPError) as exc_info:
        await provider.generate_structured(req)
    assert exc_info.value.status == 429


def test_vertex_redact_without_api_key() -> None:
    """_redact on vertex provider with api_key=None returns message unchanged."""
    settings = GeminiSettings(
        mode="vertex",
        vertex_project="my-project",
        vertex_location="europe-west4",
        allowed_vertex_regions=("europe-west4",),
        model_allowlist=("gemini-2.5-flash",),
    )
    provider = GeminiProvider(settings)
    assert provider._redact("Plain message") == "Plain message"  # noqa: SLF001


@pytest.mark.asyncio
async def test_stream_and_structured_text_fallback_without_content_parts() -> None:
    """When candidates has no content or parts, fallback to text attribute."""
    # In stream
    exchange_stream = {
        "request": {
            "method": "POST",
            "path": "/v1/models/gemini-2.5-flash:streamGenerateContent",
        },
        "response": {
            "status": 200,
            "sse_chunks": [
                json.dumps(
                    {
                        "candidates": [{"finishReason": "STOP"}],
                    }
                ),
            ],
        },
    }
    transport_stream = CassetteTransport([exchange_stream])
    provider = GeminiProvider(_make_ai_studio_settings(), transport=transport_stream)
    req_stream = CompletionRequest(model="gemini-2.5-flash", prompt="Test")
    chunks = [c async for c in provider.stream_complete(req_stream)]
    assert len(chunks) == 1
    assert chunks[0].delta == ""
    assert chunks[0].finish_reason == "stop"

    # In structured
    exchange_struct = {
        "request": {
            "method": "POST",
            "path": "/v1/models/gemini-2.5-flash:generateContent",
        },
        "response": {
            "status": 200,
            "json_body": {
                "candidates": [{"finishReason": "STOP"}],
            },
        },
    }
    transport_struct = CassetteTransport([exchange_struct])
    provider_struct = GeminiProvider(_make_ai_studio_settings(), transport=transport_struct)
    req_struct = StructuredRequest(
        model="gemini-2.5-flash",
        prompt="Test",
        response_model=ApprovalResult,
    )
    with pytest.raises(ProviderSchemaError):
        await provider_struct.generate_structured(req_struct)


def test_gemini_custom_base_url_validation() -> None:
    """Verify GeminiSettings custom base_url validation rules."""
    # 1. Valid custom base_url
    settings = GeminiSettings(
        mode="ai_studio_paid",
        api_key=SecretStr("test-key"),
        base_url=HttpUrl("https://generativelanguage.googleapis.com"),
        model_allowlist=("gemini-2.5-flash",),
    )
    assert settings.base_url is not None
    assert str(settings.base_url).rstrip("/") == "https://generativelanguage.googleapis.com"

    # 2. Userinfo rejected
    with pytest.raises(ValidationError, match="base_url must not contain userinfo"):
        GeminiSettings.model_validate(
            {
                "mode": "ai_studio_paid",
                "api_key": "test-key",
                "base_url": "https://user:pass@generativelanguage.googleapis.com",
                "model_allowlist": ("gemini-2.5-flash",),
            }
        )

    # 3. Query rejected
    with pytest.raises(ValidationError, match="base_url must not contain query parameters"):
        GeminiSettings.model_validate(
            {
                "mode": "ai_studio_paid",
                "api_key": "test-key",
                "base_url": "https://generativelanguage.googleapis.com?key=123",
                "model_allowlist": ("gemini-2.5-flash",),
            }
        )

    # 4. Fragment rejected
    with pytest.raises(ValidationError, match="base_url must not contain fragment"):
        GeminiSettings.model_validate(
            {
                "mode": "ai_studio_paid",
                "api_key": "test-key",
                "base_url": "https://generativelanguage.googleapis.com#frag",
                "model_allowlist": ("gemini-2.5-flash",),
            }
        )


@pytest.mark.asyncio
async def test_gemini_vertex_express_aq_key() -> None:
    """Verify AQ.* keys configure Vertex AI Express and target aiplatform.googleapis.com."""
    captured_url: str = ""
    captured_headers: dict[str, str] = {}

    class MockExpressTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal captured_url, captured_headers
            captured_url = str(request.url)
            captured_headers = dict(request.headers)
            body = {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": '{"status": "APPROVED", "confidence": 0.99}'}]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
            }
            return httpx.Response(200, json=body)

    settings = GeminiSettings(
        mode="vertex_express",
        api_key=SecretStr("AQ.mockvertexkey1234567890123456"),
        model_allowlist=("gemini-2.5-flash-lite",),
    )
    assert settings.mode == "vertex_express"
    provider = GeminiProvider(settings, transport=MockExpressTransport())
    assert provider.residency_tier == "gemini-vertex-express:us-central1"

    req = StructuredRequest(
        model="gemini-2.5-flash-lite",
        prompt="Audit transition",
        response_model=ApprovalResult,
    )
    res = await provider.generate_structured(req)
    assert res.parsed.status == "APPROVED"
    assert "aiplatform.googleapis.com" in captured_url
    assert captured_headers.get("x-goog-api-key") == "AQ.mockvertexkey1234567890123456"


@pytest.mark.asyncio
async def test_gemini_generate_structured_strips_think_tags() -> None:
    """Verify thinking traces <think>...</think> are stripped before parsing Gemini output."""
    class MockThinkingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, _request: httpx.Request) -> httpx.Response:
            raw_text = (
                "<think>\n"
                "Reviewing issue details and verifying requirements.\n"
                "</think>\n"
                '{"status": "APPROVED", "confidence": 0.98}'
            )
            body = {
                "candidates": [
                    {
                        "content": {"parts": [{"text": raw_text}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 15, "candidatesTokenCount": 8},
            }
            return httpx.Response(200, json=body)

    settings = _make_ai_studio_settings()
    provider = GeminiProvider(settings, transport=MockThinkingTransport())

    req = StructuredRequest(
        model="gemini-2.5-flash",
        prompt="Validate issue",
        response_model=ApprovalResult,
    )
    res = await provider.generate_structured(req)
    assert res.parsed.status == "APPROVED"
    assert res.parsed.confidence == 0.98
    assert "<think>" not in res.raw_json
    assert res.raw_json == '{"status": "APPROVED", "confidence": 0.98}'


def test_gemini_aq_secret_redaction() -> None:
    """Verify AQ.* keys are redacted in errors.redact_secrets and scrubber."""
    from agent.providers.errors import redact_secrets  # noqa: PLC0415
    from kanban.security.scrubber import outbound_secret_scrubber  # noqa: PLC0415

    raw_err = (
        "Auth failed with key AQ.AbCdEf1234567890_xyz1234567890 "
        "and sk-proj-12345678901234567890"
    )
    redacted = redact_secrets(raw_err)
    assert "AQ.AbCdEf" not in redacted
    assert "AQ.[REDACTED]" in redacted
    assert "sk-[REDACTED]" in redacted

    scrub_res = outbound_secret_scrubber(
        "Sensitive token: AQ.AbCdEf1234567890_xyz1234567890 in log"
    )
    assert scrub_res.redacted is True
    assert "AQ.AbCdEf" not in scrub_res.text
    assert "[REDACTED:API_KEY]" in scrub_res.text

