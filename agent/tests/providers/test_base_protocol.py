# Copyright 2026 Kanban Platform Contributors
"""Unit tests for agent LLMProvider protocol, DTOs, and error hierarchy."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel, ValidationError

from agent.providers.base import (
    CLIRunner,
    CLIRunRequest,
    CLIRunResult,
    CompletionRequest,
    EmbedBatchRequest,
    HealthStatus,
    LLMProvider,
    StreamChunk,
    StructuredRequest,
    StructuredResponse,
    ToolCallStep,
)
from agent.providers.errors import (
    AllProvidersUnavailable,
    EgressDenied,
    ProviderError,
    ProviderHTTPError,
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderRefusal,
    ProviderSafetyBlock,
    ProviderSchemaError,
    ProviderTimeout,
    ProviderUnavailable,
    redact_secrets,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class DummyOutput(BaseModel):
    """Sample output schema for structured testing."""

    decision: str
    confidence: float


class DummyLLM:
    """Mock class implementing LLMProvider protocol."""

    @property
    def residency_tier(self) -> str:
        """Return mock residency tier."""
        return "mock"

    async def stream_complete(self, _req: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Yield mock stream chunk."""
        yield StreamChunk(delta="ok", index=0, finish_reason="stop")

    async def generate_structured(
        self, _req: StructuredRequest[DummyOutput]
    ) -> StructuredResponse[DummyOutput]:
        """Return mock structured generation."""
        return StructuredResponse(
            parsed=DummyOutput(decision="approve", confidence=1.0),
            raw_json='{"decision": "approve", "confidence": 1.0}',
            ttft_ms=1.0,
            total_latency_ms=2.0,
        )

    async def embed_batch(self, _req: EmbedBatchRequest) -> list[list[float]]:
        """Return dummy embedding vectors."""
        return [[1.0, 0.0]]

    async def health_probe(self) -> HealthStatus:
        """Return healthy status."""
        return HealthStatus(ok=True, latency_ms=1.0)


class DummyCLI:
    """Mock class implementing CLIRunner protocol."""

    async def run(self, _req: CLIRunRequest) -> CLIRunResult:
        """Return dummy CLI result."""
        return CLIRunResult(stdout=b"ok", stderr=b"", exit_code=0, duration_ms=1.0)


def test_error_hierarchy_and_properties() -> None:
    """Test all 11 error classes, inheritance, codes, and attributes."""
    err = ProviderError("Something failed", code="CUSTOM_ERR")
    assert err.code == "CUSTOM_ERR"
    assert "Something failed" in str(err)
    assert repr(err).startswith("ProviderError(")

    http_err = ProviderHTTPError("Rate limited", status=429, retry_after_s=30.0)
    assert isinstance(http_err, ProviderError)
    assert http_err.status == 429
    assert http_err.retry_after_s == 30.0
    assert http_err.code == "HTTP_ERROR"

    timeout_err = ProviderTimeout("Deadline exceeded")
    assert isinstance(timeout_err, ProviderError)
    assert timeout_err.code == "TIMEOUT"

    unavail = ProviderUnavailable("Host down")
    assert isinstance(unavail, ProviderError)
    assert unavail.code == "UNAVAILABLE"

    all_unavail = AllProvidersUnavailable("All down")
    assert isinstance(all_unavail, ProviderUnavailable)
    assert isinstance(all_unavail, ProviderError)
    assert all_unavail.code == "ALL_PROVIDERS_UNAVAILABLE"

    proto_err = ProviderProtocolError("Bad SSE framing")
    assert isinstance(proto_err, ProviderError)
    assert proto_err.code == "PROTOCOL_ERROR"

    schema_err = ProviderSchemaError("JSON mismatch")
    assert isinstance(schema_err, ProviderError)
    assert schema_err.code == "SCHEMA_ERROR"

    safety_err = ProviderSafetyBlock("Harmful prompt")
    assert isinstance(safety_err, ProviderError)
    assert safety_err.code == "SAFETY_BLOCK"

    refusal_err = ProviderRefusal("I cannot comply")
    assert isinstance(refusal_err, ProviderError)
    assert refusal_err.code == "REFUSAL"

    policy_err = ProviderPolicyError("Budget exceeded")
    assert isinstance(policy_err, ProviderError)
    assert policy_err.code == "POLICY_ERROR"

    egress_err = EgressDenied("Air gap blocked outbound connection")
    assert isinstance(egress_err, ProviderPolicyError)
    assert isinstance(egress_err, ProviderError)
    assert egress_err.code == "EGRESS_DENIED"


def test_error_code_validation() -> None:
    """Verify error codes must conform to ^[A-Z][A-Z0-9_]{2,63}$."""
    with pytest.raises(ValueError, match="Invalid provider error code"):
        ProviderError("msg", code="invalid-lowercase")

    with pytest.raises(ValueError, match="Invalid provider error code"):
        ProviderError("msg", code="123_NUMERIC")

    with pytest.raises(ValueError, match="Invalid provider error code"):
        ProviderError("msg", code="AB")  # Too short (needs min 3 chars)

    long_code = "A" + "B" * 65
    with pytest.raises(ValueError, match="Invalid provider error code"):
        ProviderError("msg", code=long_code)

    valid_code = "VALID_CODE_123"
    err = ProviderError("test", code=valid_code)
    assert err.code == valid_code


def test_secret_redaction() -> None:
    """Test redaction of bearer tokens, API keys, and sensitive auth strings."""
    raw = (
        "Failed request with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c and sk-1234567890abcdef1234567890 "
        "and ghp_abcdefghijklmnopqrstuvwxyz1234 and AKIAIOSFODNN7EXAMPLE and "
        "kb_authsecret12345 and AIzaSyD-1234567890abcdefghijklmnopqr and "
        "api_key=supersecretpassword1234"
    )
    redacted = redact_secrets(raw)
    assert "Bearer [REDACTED]" in redacted
    assert "sk-[REDACTED]" in redacted
    assert "ghp-[REDACTED]" in redacted
    assert "AKIA[REDACTED]" in redacted
    assert "kb_[REDACTED]" in redacted
    assert "AIza[REDACTED]" in redacted
    assert "api_key=[REDACTED]" in redacted

    err = ProviderError(raw)
    assert "supersecretpassword" not in err.message
    assert "sk-1234567890" not in err.message


def test_completion_request_dto() -> None:
    """Test CompletionRequest validation, defaults, and immutability."""
    req = CompletionRequest(model="test-model", prompt="Hello world")
    assert req.model == "test-model"
    assert req.prompt == "Hello world"
    assert req.temperature == 0.15
    assert req.max_output_tokens == 256
    assert req.ttft_deadline_ms is None
    assert req.metadata == {}

    # Immutability
    with pytest.raises(ValidationError):
        setattr(req, "model", "other")  # noqa: B010  # Verifying immutability raises ValidationError

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        CompletionRequest(model="m", prompt="p", unknown="val")  # type: ignore[call-arg]

    # Bounds validation
    with pytest.raises(ValidationError):
        CompletionRequest(model="m", prompt="p", temperature=2.5)

    with pytest.raises(ValidationError):
        CompletionRequest(model="m", prompt="p", max_output_tokens=0)

    with pytest.raises(ValidationError):
        CompletionRequest(model="m", prompt="p", ttft_deadline_ms=600001)

    with pytest.raises(ValidationError):
        CompletionRequest(model="m", prompt="p", ttft_deadline_ms=0)

    # Valid deadline bounds up to 600000 ms
    valid_c_120k = CompletionRequest(model="m", prompt="p", ttft_deadline_ms=120000)
    assert valid_c_120k.ttft_deadline_ms == 120000
    valid_c_600k = CompletionRequest(model="m", prompt="p", ttft_deadline_ms=600000)
    assert valid_c_600k.ttft_deadline_ms == 600000


def test_stream_chunk_and_tool_call_step() -> None:
    """Test StreamChunk and ToolCallStep DTO properties."""
    chunk = StreamChunk(
        delta="foo",
        index=0,
        finish_reason="stop",
        ttft_ms=12.5,
        prompt_tokens=5,
        completion_tokens=1,
    )
    assert chunk.delta == "foo"
    assert chunk.index == 0
    assert chunk.finish_reason == "stop"

    with pytest.raises(ValidationError):
        StreamChunk(delta="x", index=-1)

    with pytest.raises(ValidationError):
        StreamChunk(delta="x", index=0, finish_reason="invalid_reason")  # type: ignore[arg-type]

    step = ToolCallStep(tool="repo_grep", args={"pattern": "test"}, result={"count": 3})
    assert step.tool == "repo_grep"
    assert step.args == {"pattern": "test"}
    assert step.result == {"count": 3}


def test_structured_request_and_response() -> None:
    """Test generic StructuredRequest and StructuredResponse DTOs."""
    req = StructuredRequest(
        model="reasoning-model",
        prompt="Classify code",
        response_model=DummyOutput,
        temperature=0.0,
        max_output_tokens=512,
    )
    assert req.response_model is DummyOutput
    assert req.temperature == 0.0

    # StructuredRequest boundary validations (120000, 600000 valid; 600001, 0 rejected)
    req_120k = StructuredRequest(
        model="nemotron-3-super:latest",
        prompt="Evaluate gate",
        response_model=DummyOutput,
        ttft_deadline_ms=120000,
    )
    assert req_120k.ttft_deadline_ms == 120000

    req_600k = StructuredRequest(
        model="nemotron-3-super:latest",
        prompt="Evaluate gate",
        response_model=DummyOutput,
        ttft_deadline_ms=600000,
    )
    assert req_600k.ttft_deadline_ms == 600000

    with pytest.raises(ValidationError):
        StructuredRequest(
            model="nemotron-3-super:latest",
            prompt="Evaluate gate",
            response_model=DummyOutput,
            ttft_deadline_ms=600001,
        )

    with pytest.raises(ValidationError):
        StructuredRequest(
            model="nemotron-3-super:latest",
            prompt="Evaluate gate",
            response_model=DummyOutput,
            ttft_deadline_ms=0,
        )

    parsed = DummyOutput(decision="approve", confidence=0.99)
    resp = StructuredResponse(
        parsed=parsed,
        raw_json='{"decision": "approve", "confidence": 0.99}',
        tool_trace=(ToolCallStep(tool="t", args={}),),
        ttft_ms=14.0,
        total_latency_ms=25.0,
        prompt_tokens=10,
        completion_tokens=5,
    )
    assert resp.parsed.decision == "approve"
    assert len(resp.tool_trace) == 1
    assert resp.ttft_ms == 14.0


def test_embed_batch_request_bounds() -> None:
    """Test validation bounds for EmbedBatchRequest."""
    # Zero inputs rejected
    with pytest.raises(ValueError, match="inputs length must be between 1 and 64"):
        EmbedBatchRequest(model="embed-model", inputs=())

    # 65 inputs rejected
    too_many = tuple(f"text-{i}" for i in range(65))
    with pytest.raises(ValueError, match="inputs length must be between 1 and 64"):
        EmbedBatchRequest(model="embed-model", inputs=too_many)

    # Empty string rejected
    with pytest.raises(ValueError, match="length must be between 1 and 8192"):
        EmbedBatchRequest(model="embed-model", inputs=("",))

    # Non-string input rejected
    with pytest.raises(ValueError, match="must be a string"):
        EmbedBatchRequest(model="embed-model", inputs=(123,))  # type: ignore[arg-type]

    # >8192 chars rejected
    too_long = "x" * 8193
    with pytest.raises(ValueError, match="length must be between 1 and 8192"):
        EmbedBatchRequest(model="embed-model", inputs=(too_long,))

    # Valid bounds
    exact_max = "y" * 8192
    req = EmbedBatchRequest(model="embed-model", inputs=(exact_max,))
    assert len(req.inputs[0]) == 8192


def test_cli_run_request_and_result() -> None:
    """Test CLIRunRequest validation, shell wrapper rejection, and result DTO."""
    # Empty argv rejected
    with pytest.raises(ValueError, match="argv must not be empty"):
        CLIRunRequest(argv=(), stdin_bytes=b"")

    # Shell wrapper /bin/sh rejected
    with pytest.raises(ValueError, match="Shell wrapper '/bin/sh' is forbidden"):
        CLIRunRequest(argv=("/bin/sh", "-c", "id"), stdin_bytes=b"")

    # Shell wrapper bash rejected
    with pytest.raises(ValueError, match="Shell wrapper 'bash' is forbidden"):
        CLIRunRequest(argv=("bash", "script.sh"), stdin_bytes=b"")

    # -c invocation rejected
    with pytest.raises(ValueError, match="Shell invocation with '-c' wrapper is forbidden"):
        CLIRunRequest(argv=("/usr/bin/python3", "-c", "import sys"), stdin_bytes=b"")

    # Valid CLI request
    req = CLIRunRequest(
        argv=("/usr/local/bin/agy", "-p"),
        stdin_bytes=b'{"action": "test"}',
        timeout_s=15.0,
    )
    assert req.argv == ("/usr/local/bin/agy", "-p")
    assert req.stdin_bytes == b'{"action": "test"}'
    assert req.timeout_s == 15.0

    res = CLIRunResult(
        stdout=b"success",
        stderr=b"",
        exit_code=0,
        duration_ms=42.1,
    )
    assert res.exit_code == 0
    assert res.stdout == b"success"


def test_runtime_protocols() -> None:
    """Verify @runtime_checkable LLMProvider and CLIRunner protocols."""
    llm = DummyLLM()
    assert isinstance(llm, LLMProvider)
    assert llm.residency_tier == "mock"

    async def _exercise() -> None:
        async for chunk in llm.stream_complete(CompletionRequest(model="m", prompt="p")):
            assert chunk.delta == "ok"
        res_struct = await llm.generate_structured(
            StructuredRequest(model="m", prompt="p", response_model=DummyOutput)
        )
        assert res_struct.parsed.decision == "approve"
        vecs = await llm.embed_batch(EmbedBatchRequest(model="m", inputs=("test",)))
        assert vecs == [[1.0, 0.0]]
        assert (await llm.health_probe()).ok is True

        cli = DummyCLI()
        assert isinstance(cli, CLIRunner)
        res = await cli.run(CLIRunRequest(argv=("/bin/echo", "hi"), stdin_bytes=b""))
        assert res.exit_code == 0

    asyncio.run(_exercise())


def test_structured_request_token_bounds_and_defaults() -> None:
    """Verify StructuredRequest defaults max_output_tokens to 4096 and enforces bounds."""
    req_default = StructuredRequest(
        model="reasoning-model",
        prompt="Classify code",
        response_model=DummyOutput,
    )
    assert req_default.max_output_tokens == 4096

    req_min = StructuredRequest(
        model="m",
        prompt="p",
        response_model=DummyOutput,
        max_output_tokens=1,
    )
    assert req_min.max_output_tokens == 1

    req_max = StructuredRequest(
        model="m",
        prompt="p",
        response_model=DummyOutput,
        max_output_tokens=32768,
    )
    assert req_max.max_output_tokens == 32768

    with pytest.raises(ValidationError):
        StructuredRequest(
            model="m",
            prompt="p",
            response_model=DummyOutput,
            max_output_tokens=0,
        )

    with pytest.raises(ValidationError):
        StructuredRequest(
            model="m",
            prompt="p",
            response_model=DummyOutput,
            max_output_tokens=32769,
        )

    comp_default = CompletionRequest(model="m", prompt="p")
    assert comp_default.max_output_tokens == 256
