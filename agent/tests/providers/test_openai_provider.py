# Copyright 2026 Kanban Platform Contributors
"""Unit tests for OpenAIProvider adapter, registry, and OpenAISettings validation."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, HttpUrl, SecretStr, ValidationError

from agent.providers.base import (
    CompletionRequest,
    EmbedBatchRequest,
    HealthStatus,
    LLMProvider,
    StreamChunk,
    StructuredRequest,
    StructuredResponse,
)
from agent.providers.errors import (
    ProviderError,
    ProviderHTTPError,
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderRefusal,
    ProviderSchemaError,
    ProviderTimeout,
    ProviderUnavailable,
)
from agent.providers.openai_provider import (
    OpenAIProvider,
    OpenAISettings,
    _make_strict_json_schema,
)
from agent.providers.registry import build_provider
from agent.testing.http_cassette import CassetteTransport

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "ai"


class DummyStructuredOutput(BaseModel):
    """Dummy schema for structured output testing."""

    echo: str
    ok: bool


class NestedItem(BaseModel):
    """Nested object to exercise recursive strict schema generation."""

    item_id: str
    score: float


class ComplexStructuredOutput(BaseModel):
    """Complex schema with nested objects and arrays for strict schema testing."""

    title: str
    items: list[NestedItem]


def _make_settings(  # noqa: PLR0913
    *,
    api_key: str = "sk-test-mock-key-0123456789abcdef",
    base_url: str | HttpUrl | None = "https://api.openai.com/v1",
    base_url_kind: str = "openai",
    models: tuple[str, ...] = ("gpt-4o-mini", "gpt-4.1", "o3-mini", "text-embedding-3-small"),
    timeout_s: float = 30.0,
    residency_tier: str = "openai-zdr-us",
    organization: str | None = None,
) -> OpenAISettings:
    url = HttpUrl(base_url) if isinstance(base_url, str) else base_url
    return OpenAISettings(
        api_key=SecretStr(api_key),
        base_url=url,
        base_url_kind=base_url_kind,  # type: ignore[arg-type]
        model_allowlist=models,
        timeout_s=timeout_s,
        residency_tier=residency_tier,
        organization=organization,
    )


# ---------------------------------------------------------------------------
# Test Case 1: Positive streaming completion & store: false assertion
# ---------------------------------------------------------------------------
async def test_01_stream_complete_positive_and_store_false() -> None:
    """Test Case 1: SSE stream chunks match cassette and outbound JSON enforces store=false."""
    cassette_path = FIXTURES_DIR / "openai_stream_ok.yaml"
    transport = CassetteTransport(cassette_path)
    settings = _make_settings()
    provider = OpenAIProvider(settings, transport=transport)

    req = CompletionRequest(
        model="gpt-4o-mini",
        prompt="Hello Sparkle",
        temperature=0.15,
        max_output_tokens=256,
    )

    chunks = [chunk async for chunk in provider.stream_complete(req)]

    assert len(chunks) == 2
    assert chunks[0].delta == "Hello"
    assert chunks[0].index == 0
    assert chunks[0].finish_reason is None
    assert chunks[0].ttft_ms is not None
    assert chunks[0].ttft_ms > 0

    assert chunks[1].delta == " Sparkle"
    assert chunks[1].index == 1
    assert chunks[1].finish_reason == "stop"
    assert chunks[1].prompt_tokens == 10
    assert chunks[1].completion_tokens == 5

    # Verify wire request body
    assert transport.call_count == 1
    raw_body = await transport.requests[0].aread()
    body_json = json.loads(raw_body.decode("utf-8"))
    assert body_json["store"] is False
    assert body_json["model"] == "gpt-4o-mini"
    assert body_json["stream"] is True
    assert body_json["temperature"] == 0.15
    assert body_json["max_tokens"] == 256
    assert body_json["messages"] == [{"role": "user", "content": "Hello Sparkle"}]


# ---------------------------------------------------------------------------
# Test Case 2: Positive structured output & strict json_schema validation
# ---------------------------------------------------------------------------
async def test_02_structured_output_positive_and_strict_schema() -> None:
    """Test Case 2: Structured output parsed with strict: true and additionalProperties: false."""
    cassette_path = FIXTURES_DIR / "openai_structured_ok.yaml"
    transport = CassetteTransport(cassette_path)
    settings = _make_settings()
    provider = OpenAIProvider(settings, transport=transport)

    req = StructuredRequest(
        model="gpt-4o-mini",
        prompt="Echo back hello sparkle",
        response_model=DummyStructuredOutput,
        system_prompt="You are a helpful assistant.",
    )

    res: StructuredResponse[DummyStructuredOutput] = await provider.generate_structured(req)

    assert isinstance(res, StructuredResponse)
    assert res.parsed.echo == "Hello Sparkle"
    assert res.parsed.ok is True
    assert res.prompt_tokens == 15
    assert res.completion_tokens == 8
    assert res.tool_trace == ()
    assert res.ttft_ms > 0

    # Verify wire request body strict structured schema
    assert transport.call_count == 1
    raw_body = await transport.requests[0].aread()
    body_json = json.loads(raw_body.decode("utf-8"))
    assert body_json["store"] is False
    assert body_json["messages"][0] == {"role": "system", "content": "You are a helpful assistant."}
    assert body_json["messages"][1] == {"role": "user", "content": "Echo back hello sparkle"}

    rf = body_json.get("response_format", {})
    assert rf.get("type") == "json_schema"
    js = rf.get("json_schema", {})
    assert js.get("name") == "DummyStructuredOutput"
    assert js.get("strict") is True

    schema = js.get("schema", {})
    assert schema.get("additionalProperties") is False
    assert "echo" in schema.get("properties", {})
    assert "ok" in schema.get("properties", {})


# ---------------------------------------------------------------------------
# Test Case 3: Contract parity with FixtureLLMProvider
# ---------------------------------------------------------------------------
async def test_03_contract_parity_with_fixture_llm_provider() -> None:
    """Test Case 3: Contract parity between OpenAIProvider and FixtureLLMProvider."""
    fixture_path = FIXTURES_DIR / "echo_stream_ok.yaml"
    fixture_provider = build_provider("fixture", fixture_path)

    openai_path = FIXTURES_DIR / "openai_stream_ok.yaml"
    openai_transport = CassetteTransport(openai_path)
    openai_settings = _make_settings()
    openai_provider = OpenAIProvider(openai_settings, transport=openai_transport)

    assert isinstance(fixture_provider, LLMProvider)
    assert isinstance(openai_provider, LLMProvider)

    req = CompletionRequest(
        model="gpt-4o-mini",
        prompt="Hello Sparkle",
    )

    fixture_chunks = [chunk async for chunk in fixture_provider.stream_complete(req)]
    openai_chunks = [chunk async for chunk in openai_provider.stream_complete(req)]

    # Both yield StreamChunk instances conforming to the protocol
    assert all(isinstance(c, StreamChunk) for c in fixture_chunks)
    assert all(isinstance(c, StreamChunk) for c in openai_chunks)
    assert len(fixture_chunks) > 0
    assert len(openai_chunks) > 0

    fixture_text = "".join(c.delta for c in fixture_chunks)
    openai_text = "".join(c.delta for c in openai_chunks)
    assert "Hello" in fixture_text
    assert "Hello" in openai_text


# ---------------------------------------------------------------------------
# Test Case 4: Security: Base URL validation & SSRF prevention
# ---------------------------------------------------------------------------
def test_04_security_base_url_validation() -> None:
    """Test Case 4: Rejection of non-HTTPS URLs, userinfo, queries; acceptance of loopback."""
    # 1. Plaintext HTTP to remote host rejected
    with pytest.raises(ValidationError, match="base_url must use HTTPS unless targeting loopback"):
        _make_settings(base_url="http://evil.example/v1")

    # 2. Userinfo rejected
    with pytest.raises(ValidationError, match="base_url must not contain userinfo"):
        _make_settings(base_url="https://user:pw@api.openai.com/v1")

    # 3. Query parameters rejected
    with pytest.raises(ValidationError, match="base_url must not contain query parameters"):
        _make_settings(base_url="https://api.openai.com/v1?probe=1")

    # 4. Fragment rejected
    with pytest.raises(ValidationError, match="base_url must not contain fragment"):
        _make_settings(base_url="https://api.openai.com/v1#anchor")

    # 5. Localhost / loopback HTTP accepted for vllm / litellm
    vllm_settings = _make_settings(
        base_url="http://127.0.0.1:8000/v1",
        base_url_kind="vllm",
    )
    assert str(vllm_settings.base_url) == "http://127.0.0.1:8000/v1"

    vllm_ipv6 = _make_settings(
        base_url="http://[::1]:8000/v1",
        base_url_kind="vllm",
    )
    assert str(vllm_ipv6.base_url) == "http://[::1]:8000/v1"

    # None base_url defaults cleanly
    none_settings = _make_settings(base_url=None)
    assert none_settings.base_url is None


# ---------------------------------------------------------------------------
# Test Case 5: Security: Proxy env ignored & 307 redirect rejected
# ---------------------------------------------------------------------------
async def test_05_security_proxy_ignored_and_redirect_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Case 5: HTTPS_PROXY environment is ignored and 307 redirect raises REDIRECT_REFUSED."""
    monkeypatch.setenv("HTTPS_PROXY", "http://evil-mitm-proxy:8080")
    monkeypatch.setenv("HTTP_PROXY", "http://evil-mitm-proxy:8080")

    cassette_path = FIXTURES_DIR / "openai_fault_redirect_307.yaml"
    transport = CassetteTransport(cassette_path)
    settings = _make_settings()
    provider = OpenAIProvider(settings, transport=transport)

    # Verify trust_env is False
    assert provider.http_client.trust_env is False

    req = CompletionRequest(model="gpt-4o-mini", prompt="Test redirect")
    with pytest.raises(ProviderProtocolError) as exc_info:
        async for _ in provider.stream_complete(req):
            pass

    assert exc_info.value.code == "REDIRECT_REFUSED"
    assert "Redirect refused (307)" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test Case 6: Security: Secret sanitization in repr, logs, and exceptions
# ---------------------------------------------------------------------------
async def test_06_security_api_key_absent_from_repr_logs_and_exceptions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test Case 6: API key is absent from repr, caplog, and exception messages."""
    raw_secret = "sk-SUPER-SECRET-PLAINTEXT-KEY-XYZ12345"
    settings = _make_settings(api_key=raw_secret)
    transport = CassetteTransport(FIXTURES_DIR / "openai_fault_500.yaml")
    provider = OpenAIProvider(settings, transport=transport)

    # 1. Repr sanitization
    repr_provider = repr(provider)
    repr_settings = repr(settings)
    assert raw_secret not in repr_provider
    assert raw_secret not in repr_settings
    assert "openai-zdr-us" in repr_provider

    # 2. Exception text sanitization
    req = CompletionRequest(model="gpt-4o-mini", prompt="Test secret leakage")
    with pytest.raises(ProviderHTTPError) as exc_info:
        async for _ in provider.stream_complete(req):
            pass

    assert raw_secret not in str(exc_info.value)
    assert raw_secret not in repr(exc_info.value)

    # 3. Log stream sanitization
    assert raw_secret not in caplog.text


# ---------------------------------------------------------------------------
# Test Case 7: Fault injection (429, 500, timeout) & zero SDK retries
# ---------------------------------------------------------------------------
async def test_07_fault_injection_and_zero_sdk_retries() -> None:
    """Test Case 7: 429, 500, timeout raise typed errors with exactly 1 transport call."""
    settings = _make_settings()

    # 1. HTTP 429 Rate Limit
    t_429 = CassetteTransport(FIXTURES_DIR / "openai_fault_429.yaml")
    p_429 = OpenAIProvider(settings, transport=t_429)
    req = CompletionRequest(model="gpt-4o-mini", prompt="429 test")
    with pytest.raises(ProviderHTTPError) as exc_429:
        async for _ in p_429.stream_complete(req):
            pass
    assert exc_429.value.status == 429
    assert exc_429.value.code == "RATE_LIMITED"
    assert t_429.call_count == 1  # Exactly 1 call; max_retries=0 enforced

    # 2. HTTP 500 Internal Server Error
    t_500 = CassetteTransport(FIXTURES_DIR / "openai_fault_500.yaml")
    p_500 = OpenAIProvider(settings, transport=t_500)
    with pytest.raises(ProviderHTTPError) as exc_500:
        async for _ in p_500.stream_complete(req):
            pass
    assert exc_500.value.status == 500
    assert exc_500.value.code == "UPSTREAM_5XX"
    assert t_500.call_count == 1

    # 3. Timeout
    t_timeout = CassetteTransport(FIXTURES_DIR / "openai_fault_timeout.yaml")
    p_timeout = OpenAIProvider(settings, transport=t_timeout)
    with pytest.raises(ProviderTimeout) as exc_to:
        async for _ in p_timeout.stream_complete(req):
            pass
    assert exc_to.value.code == "TIMEOUT"
    assert t_timeout.call_count == 1


# ---------------------------------------------------------------------------
# Test Case 8: Negative: Refusal & Schema Mismatch
# ---------------------------------------------------------------------------
async def test_08_negative_refusal_and_schema_mismatch() -> None:
    """Test Case 8: Refusal raises ProviderRefusal; schema mismatch raises ProviderSchemaError."""
    settings = _make_settings()

    # 1. Refusal
    t_refusal = CassetteTransport(FIXTURES_DIR / "openai_structured_refusal.yaml")
    p_refusal = OpenAIProvider(settings, transport=t_refusal)
    req_struct = StructuredRequest(
        model="gpt-4o-mini",
        prompt="Tell me something secret",
        response_model=DummyStructuredOutput,
    )
    with pytest.raises(ProviderRefusal) as exc_refusal:
        await p_refusal.generate_structured(req_struct)
    assert exc_refusal.value.code == "REFUSAL"
    assert "I cannot fulfill this request" in str(exc_refusal.value)

    # 2. Schema mismatch
    t_mismatch = CassetteTransport(FIXTURES_DIR / "openai_structured_schema_mismatch.yaml")
    p_mismatch = OpenAIProvider(settings, transport=t_mismatch)
    with pytest.raises(ProviderSchemaError) as exc_mismatch:
        await p_mismatch.generate_structured(req_struct)
    assert exc_mismatch.value.code == "SCHEMA_ERROR"
    assert "Output validation failed against schema DummyStructuredOutput" in str(
        exc_mismatch.value
    )


# ---------------------------------------------------------------------------
# Test Case 9: Boundary: Model allowlist, batch limit & health probe
# ---------------------------------------------------------------------------
async def test_09_boundary_allowlist_embed_batch_and_health_probe() -> None:
    """Test Case 9: Model allowlist rejects unapproved models; embed limits and health probe."""
    settings = _make_settings(models=("gpt-4o-mini", "text-embedding-3-small"))
    transport = CassetteTransport(FIXTURES_DIR / "openai_embed_ok.yaml")
    provider = OpenAIProvider(settings, transport=transport)

    # 1. Model outside allowlist raises MODEL_NOT_ALLOWED with zero transport calls
    unallowed_req = CompletionRequest(model="claude-3-5-sonnet", prompt="Hello")
    with pytest.raises(ProviderPolicyError) as exc_allow:
        async for _ in provider.stream_complete(unallowed_req):
            pass
    assert exc_allow.value.code == "MODEL_NOT_ALLOWED"
    assert transport.call_count == 0

    unallowed_embed = EmbedBatchRequest(model="unallowed-embed", inputs=("text",))
    with pytest.raises(ProviderPolicyError) as exc_embed_allow:
        await provider.embed_batch(unallowed_embed)
    assert exc_embed_allow.value.code == "MODEL_NOT_ALLOWED"
    assert transport.call_count == 0

    # 2. Embed batch > 64 rejected by EmbedBatchRequest validation
    oversize_inputs = tuple(f"text {i}" for i in range(65))
    with pytest.raises(ValueError, match="inputs length must be between 1 and 64"):
        EmbedBatchRequest(model="text-embedding-3-small", inputs=oversize_inputs)

    # 3. Positive embed batch
    embed_req = EmbedBatchRequest(
        model="text-embedding-3-small",
        inputs=("hello", "world"),
    )
    embeddings = await provider.embed_batch(embed_req)
    assert len(embeddings) == 2
    assert embeddings[0] == [0.1, 0.2, 0.3]
    assert embeddings[1] == [0.4, 0.5, 0.6]

    # 4. Health probe positive and negative
    # Positive: retrieve succeeds
    mock_exchange_ok = {
        "request": {"method": "GET", "path": "/v1/models/gpt-4o-mini"},
        "response": {"status": 200, "json_body": {"id": "gpt-4o-mini", "object": "model"}},
    }
    t_health_ok = CassetteTransport([mock_exchange_ok])
    p_health_ok = OpenAIProvider(settings, transport=t_health_ok)
    health_ok: HealthStatus = await p_health_ok.health_probe()
    assert health_ok.ok is True
    assert "gpt-4o-mini" in health_ok.models
    assert health_ok.latency_ms > 0

    # Negative: retrieve fails with error (never raises)
    mock_exchange_fail = {
        "request": {"method": "GET", "path": "/v1/models/gpt-4o-mini"},
        "fault": {"kind": "http_500"},
    }
    t_health_fail = CassetteTransport([mock_exchange_fail])
    p_health_fail = OpenAIProvider(settings, transport=t_health_fail)
    health_fail: HealthStatus = await p_health_fail.health_probe()
    assert health_fail.ok is False
    assert health_fail.models == ()
    assert health_fail.detail is not None


# ---------------------------------------------------------------------------
# Additional coverage & registry tests
# ---------------------------------------------------------------------------
def test_build_provider_openai_registration() -> None:
    """Verify registry build_provider handles OpenAISettings and dict forms."""
    settings = _make_settings()
    provider_from_settings = build_provider("openai", settings)
    assert isinstance(provider_from_settings, OpenAIProvider)

    dict_settings: dict[str, Any] = {
        "api_key": "sk-mock-key-0123456789abcdef",
        "model_allowlist": ["gpt-4o-mini"],
    }
    provider_from_dict = build_provider("openai", dict_settings)
    assert isinstance(provider_from_dict, OpenAIProvider)

    msg = "Settings for openai provider must be OpenAISettings or dict"
    with pytest.raises(TypeError, match=msg):
        build_provider("openai", 9999)


def test_make_strict_json_schema_nested_and_lists() -> None:
    """Verify _make_strict_json_schema enforces additionalProperties=false recursively."""
    schema = _make_strict_json_schema(ComplexStructuredOutput)
    assert schema["additionalProperties"] is False
    assert "title" in schema["required"]
    assert "items" in schema["required"]

    items_schema = schema["properties"]["items"]
    assert items_schema["type"] == "array"
    assert "$defs" in schema
    nested_schema = schema["$defs"]["NestedItem"]
    assert nested_schema["additionalProperties"] is False
    assert "item_id" in nested_schema["required"]
    assert "score" in nested_schema["required"]


async def test_stream_ttft_deadline_breach(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify TTFT deadline breach triggers ProviderTimeout during streaming."""
    cassette_path = FIXTURES_DIR / "openai_stream_ok.yaml"
    transport = CassetteTransport(cassette_path)
    settings = _make_settings()
    provider = OpenAIProvider(settings, transport=transport)

    req = CompletionRequest(
        model="gpt-4o-mini",
        prompt="Hello Sparkle",
        ttft_deadline_ms=1,  # 1ms deadline will be breached
    )

    perf_times = [0.0, 0.05]
    monkeypatch.setattr(time, "perf_counter", lambda: perf_times.pop(0) if perf_times else 1.0)

    with pytest.raises(ProviderTimeout, match="TTFT SLA breached"):
        async for _ in provider.stream_complete(req):
            pass


async def test_structured_empty_choices() -> None:
    """Verify empty choices list raises ProviderProtocolError."""
    mock_exchange = {
        "request": {"method": "POST", "path": "/v1/chat/completions"},
        "response": {"status": 200, "json_body": {"choices": []}},
    }
    transport = CassetteTransport([mock_exchange])
    settings = _make_settings()
    provider = OpenAIProvider(settings, transport=transport)

    req = StructuredRequest(
        model="gpt-4o-mini",
        prompt="test",
        response_model=DummyStructuredOutput,
    )
    with pytest.raises(ProviderProtocolError, match="OpenAI returned empty choices list"):
        await provider.generate_structured(req)


async def test_error_mapping_connection_and_http_status() -> None:
    """Verify connection error and generic HTTP status error mapping."""
    settings = _make_settings()

    # Connection error
    mock_conn = {
        "request": {"method": "POST", "path": "/v1/chat/completions"},
        "fault": {"kind": "connect_error"},
    }
    transport_conn = CassetteTransport([mock_conn])
    p_conn = OpenAIProvider(settings, transport=transport_conn)
    with pytest.raises(ProviderUnavailable):
        async for _ in p_conn.stream_complete(CompletionRequest(model="gpt-4o-mini", prompt="hi")):
            pass

    # HTTP 400 Bad Request
    mock_400 = {
        "request": {"method": "POST", "path": "/v1/chat/completions"},
        "response": {"status": 400, "json_body": {"error": "bad request"}},
    }
    transport_400 = CassetteTransport([mock_400])
    p_400 = OpenAIProvider(settings, transport=transport_400)
    with pytest.raises(ProviderHTTPError) as exc_400:
        async for _ in p_400.stream_complete(CompletionRequest(model="gpt-4o-mini", prompt="hi")):
            pass
    assert exc_400.value.status == 400
    assert exc_400.value.code == "HTTP_ERROR"


def test_provider_residency_tier_and_repr_without_base_url() -> None:
    """Verify residency_tier property and repr formatting when base_url is None."""
    settings = _make_settings(base_url=None)
    provider = OpenAIProvider(settings)
    assert provider.residency_tier == "openai-zdr-us"
    repr_str = repr(provider)
    assert "https://api.openai.com/v1" in repr_str
    assert "openai-zdr-us" in repr_str


async def test_429_invalid_retry_after_header() -> None:
    """Verify non-numeric retry-after header does not crash 429 error mapping."""
    mock_429 = {
        "request": {"method": "POST", "path": "/v1/chat/completions"},
        "response": {
            "status": 429,
            "headers": {"retry-after": "not-a-number"},
            "json_body": {"error": "rate limit"},
        },
    }
    transport = CassetteTransport([mock_429])
    provider = OpenAIProvider(_make_settings(), transport=transport)
    req = CompletionRequest(model="gpt-4o-mini", prompt="hi")
    with pytest.raises(ProviderHTTPError) as exc_429:
        async for _ in provider.stream_complete(req):
            pass
    assert exc_429.value.status == 429
    assert exc_429.value.retry_after_s is None


async def test_generate_structured_fault_mapping() -> None:
    """Verify generate_structured maps timeout exceptions to ProviderTimeout."""
    mock_timeout = {
        "request": {"method": "POST", "path": "/v1/chat/completions"},
        "fault": {"kind": "timeout"},
    }
    transport = CassetteTransport([mock_timeout])
    provider = OpenAIProvider(_make_settings(), transport=transport)
    with pytest.raises(ProviderTimeout):
        await provider.generate_structured(
            StructuredRequest(
                model="gpt-4o-mini", prompt="hi", response_model=DummyStructuredOutput
            )
        )


async def test_embed_batch_fault_mapping() -> None:
    """Verify embed_batch maps timeout exceptions to ProviderTimeout."""
    mock_timeout = {
        "request": {"method": "POST", "path": "/v1/embeddings"},
        "fault": {"kind": "timeout"},
    }
    transport = CassetteTransport([mock_timeout])
    provider = OpenAIProvider(_make_settings(), transport=transport)
    with pytest.raises(ProviderTimeout):
        await provider.embed_batch(
            EmbedBatchRequest(model="text-embedding-3-small", inputs=("text",))
        )


def test_map_and_raise_generic_exception() -> None:
    """Verify unhandled generic exceptions map to ProviderError."""
    provider = OpenAIProvider(_make_settings())
    with pytest.raises(ProviderError) as exc_info:
        provider._map_and_raise(RuntimeError("Unexpected generic engine failure"))  # noqa: SLF001
    assert exc_info.value.code == "PROVIDER_ERROR"
    assert "Unexpected generic engine failure" in str(exc_info.value)


def test_make_strict_json_schema_optional_properties() -> None:
    """Verify optional fields and schemas without required keys are forced strict."""

    class SchemaWithDefaults(BaseModel):
        opt1: str = "default1"
        opt2: int = 42

    schema = _make_strict_json_schema(SchemaWithDefaults)
    assert schema["additionalProperties"] is False
    assert "opt1" in schema["required"]
    assert "opt2" in schema["required"]

    class PartialModel(BaseModel):
        req_field: str
        opt_field: str = "val"

    s_partial = _make_strict_json_schema(PartialModel)
    assert "req_field" in s_partial["required"]
    assert "opt_field" in s_partial["required"]


async def test_429_no_retry_after_header() -> None:
    """Verify 429 response without retry-after header maps to RATE_LIMITED."""
    mock_429 = {
        "request": {"method": "POST", "path": "/v1/chat/completions"},
        "response": {
            "status": 429,
            "json_body": {"error": "rate limit"},
        },
    }
    transport = CassetteTransport([mock_429])
    provider = OpenAIProvider(_make_settings(), transport=transport)
    req = CompletionRequest(model="gpt-4o-mini", prompt="hi")
    with pytest.raises(ProviderHTTPError) as exc_429:
        async for _ in provider.stream_complete(req):
            pass
    assert exc_429.value.status == 429
    assert exc_429.value.retry_after_s is None


async def test_stream_chunk_without_choices() -> None:
    """Verify stream chunk without choices (e.g. usage-only chunk) is handled gracefully."""
    chunk_usage_only = json.dumps(
        {
            "id": "c_usage",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "gpt-4o-mini",
            "choices": [],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4},
        }
    )
    mock_exchange = {
        "request": {"method": "POST", "path": "/v1/chat/completions"},
        "response": {
            "status": 200,
            "headers": {"content-type": "text/event-stream"},
            "sse_chunks": [chunk_usage_only, "[DONE]"],
        },
    }
    transport = CassetteTransport([mock_exchange])
    provider = OpenAIProvider(_make_settings(), transport=transport)
    req = CompletionRequest(model="gpt-4o-mini", prompt="hi")
    chunks = [c async for c in provider.stream_complete(req)]
    assert len(chunks) == 1
    assert chunks[0].delta == ""
    assert chunks[0].finish_reason is None
    assert chunks[0].prompt_tokens == 8
