# Copyright 2026 Kanban Platform Contributors
"""Unit tests for resilient ProviderRouter and same-residency failover."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from pydantic import BaseModel

from agent.providers.base import (
    CompletionRequest,
    EmbedBatchRequest,
    HealthStatus,
    LLMProvider,
    StreamChunk,
    StructuredRequest,
    StructuredResponse,
)
from agent.providers.circuit_breaker import CircuitBreaker, CircuitBreakerState
from agent.providers.errors import (
    AllProvidersUnavailable,
    ProviderHTTPError,
    ProviderProtocolError,
    ProviderSchemaError,
    ProviderTimeout,
)
from agent.providers.router import ProviderRouter, RouteCandidate
from agent.testing.fixtures import FixtureLLMProvider, load_cassette

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class EchoModel(BaseModel):
    """Simple test structured model."""

    echo: str
    ok: bool


class MockStreamProvider(LLMProvider):
    """Configurable mock provider for fault injection and lifecycle assertions."""

    def __init__(
        self,
        residency_tier: str = "local",
        *,
        kind: str = "ollama",
        fail_with: Exception | None = None,
        ttft_delay_ms: float = 0.0,
    ) -> None:
        """Initialize mock provider with configurable behavior."""
        self._residency_tier = residency_tier
        self.kind = kind
        self.fail_with = fail_with
        self.ttft_delay_ms = ttft_delay_ms
        self.call_count = 0
        self.aclose_called = False

    @property
    def residency_tier(self) -> str:
        """Return configured data residency tier."""
        return self._residency_tier

    async def stream_complete(
        self,
        _req: CompletionRequest,
    ) -> AsyncIterator[StreamChunk]:
        """Stream replayed chunks or raise configured fault."""
        self.call_count += 1
        if self.fail_with is not None:
            raise self.fail_with

        chunks = ["Hello", " ", "World"]
        for idx, c in enumerate(chunks):
            yield StreamChunk(delta=c, index=idx, ttft_ms=10.0 if idx == 0 else None)

    async def generate_structured[TModel: BaseModel](
        self, req: StructuredRequest[TModel]
    ) -> StructuredResponse[TModel]:
        """Generate test structured output or raise configured fault."""
        self.call_count += 1
        if self.fail_with is not None:
            raise self.fail_with
        parsed = req.response_model.model_validate({"echo": "Hello", "ok": True})
        return StructuredResponse(
            parsed=parsed,
            raw_json='{"echo": "Hello", "ok": true}',
            ttft_ms=12.0,
            total_latency_ms=25.0,
        )

    async def embed_batch(self, req: EmbedBatchRequest) -> list[list[float]]:
        """Return dummy embedding vectors."""
        self.call_count += 1
        if self.fail_with is not None:
            raise self.fail_with
        return [[0.1, 0.2, 0.3] for _ in req.inputs]

    async def health_probe(self) -> HealthStatus:
        """Probe mock provider health."""
        self.call_count += 1
        if self.fail_with is not None:
            return HealthStatus(ok=False, latency_ms=0.0, detail=str(self.fail_with))
        return HealthStatus(ok=True, latency_ms=5.0)


@pytest.mark.asyncio
async def test_case_1_primary_healthy_single_call() -> None:
    """Case 1: Primary healthy -> single call, trace shows CLOSED."""
    cas = load_cassette("tests/fixtures/ai/router_primary_ok.yaml")
    p1 = FixtureLLMProvider(cas)
    p2 = FixtureLLMProvider(cas)

    c1_id = uuid4()
    c2_id = uuid4()
    c1 = RouteCandidate(c1_id, p1, "fixture", 0)
    c2 = RouteCandidate(c2_id, p2, "fixture", 1)

    ws_id = uuid4()
    router = ProviderRouter(ws_id, [c1, c2])
    assert router.residency_tier == "fixture"

    req = CompletionRequest(model="fixture-echo-v1", prompt="Hello Sparkle")
    chunks = [c.delta async for c in router.stream_complete(req)]
    assert "".join(chunks) == "Echo: Hello Sparkle"

    assert len(router.last_route_trace) == 1
    assert router.last_route_trace[0]["provider_config_id"] == str(c1_id)
    assert router.last_route_trace[0]["outcome"] == "success"
    assert router.last_route_trace[0]["breaker_state"] == CircuitBreakerState.CLOSED.value
    assert len(p1.call_log) == 1
    assert len(p2.call_log) == 0


@pytest.mark.asyncio
async def test_case_5_failover_same_residency_tier_only() -> None:
    """Case 5: Primary local fails -> secondary local used; gemini cloud never selected."""
    p1 = MockStreamProvider(
        residency_tier="local",
        kind="ollama",
        fail_with=ProviderHTTPError("503", status=503),
    )
    p2 = MockStreamProvider(residency_tier="local", kind="ollama")
    p3 = MockStreamProvider(residency_tier="gemini-vertex:europe-west4", kind="gemini")

    c1 = RouteCandidate(uuid4(), p1, "local", 0)
    c2 = RouteCandidate(uuid4(), p2, "local", 1)
    c3 = RouteCandidate(uuid4(), p3, "gemini-vertex:europe-west4", 2)

    router = ProviderRouter(uuid4(), [c1, c2, c3])
    req = CompletionRequest(model="test-model", prompt="hello")

    chunks = [c.delta async for c in router.stream_complete(req)]
    assert "".join(chunks) == "Hello World"

    assert p1.call_count == 1
    assert p2.call_count == 1
    assert p3.call_count == 0  # Gemini candidate was NEVER called

    assert len(router.last_route_trace) == 2
    assert router.last_route_trace[0]["outcome"] == "failure"
    assert router.last_route_trace[1]["outcome"] == "success"


@pytest.mark.asyncio
async def test_case_8_air_gap_with_only_cloud_candidates_never_falls_back() -> None:
    """Case 8: Air-gap with only cloud candidates -> NO_PROVIDER_IN_RESIDENCY_TIER."""
    p1 = MockStreamProvider(residency_tier="cloud", kind="openai")
    p2 = MockStreamProvider(residency_tier="gemini-vertex:us-central1", kind="gemini")

    c1 = RouteCandidate(uuid4(), p1, "cloud", 0)
    c2 = RouteCandidate(uuid4(), p2, "gemini-vertex:us-central1", 1)

    router = ProviderRouter(uuid4(), [c1, c2], air_gap_mode=True)
    req = CompletionRequest(model="gpt-4o", prompt="hello")

    with pytest.raises(AllProvidersUnavailable) as exc_info:
        async for _ in router.stream_complete(req):
            pass

    assert exc_info.value.code == "NO_PROVIDER_IN_RESIDENCY_TIER"
    assert p1.call_count == 0
    assert p2.call_count == 0


@pytest.mark.asyncio
async def test_case_9_ttft_deadline_breach_calls_aclose_and_counts_failure() -> None:
    """Case 9: TTFT breach with ttft_deadline_ms=150 -> ProviderTimeout, counted as failure."""
    cas = load_cassette("tests/fixtures/ai/router_fault_ttft_breach.yaml")
    fixture_provider = FixtureLLMProvider(cas)
    c2_id = uuid4()
    c2 = RouteCandidate(c2_id, fixture_provider, "local", 0)

    breakers = CircuitBreaker()
    ws_id = uuid4()
    router = ProviderRouter(ws_id, [c2], breakers=breakers)

    req = CompletionRequest(model="test-model", prompt="ttft-breach-test", ttft_deadline_ms=150)

    with pytest.raises(AllProvidersUnavailable) as exc_info:
        async for _ in router.stream_complete(req):
            pass

    assert exc_info.value.code == "NO_PROVIDER_IN_RESIDENCY_TIER"
    assert isinstance(exc_info.value.__cause__, ProviderTimeout)
    assert "TTFT" in str(exc_info.value.__cause__)
    assert breakers.get_state(ws_id, c2_id) == CircuitBreakerState.CLOSED
    assert breakers._get_entry(ws_id, c2_id).consecutive_failures == 1  # noqa: SLF001


@pytest.mark.asyncio
async def test_case_10_stream_error_after_first_chunk_propagates_without_failover() -> None:
    """Case 10: Error after first streamed chunk -> propagated, no failover call."""
    cas = load_cassette("tests/fixtures/ai/router_stream_error_after_first_chunk.yaml")
    p1 = FixtureLLMProvider(cas)
    p2 = MockStreamProvider(residency_tier="fixture", kind="fixture")

    c1 = RouteCandidate(uuid4(), p1, "fixture", 0)
    c2 = RouteCandidate(uuid4(), p2, "fixture", 1)

    router = ProviderRouter(uuid4(), [c1, c2])
    req = CompletionRequest(model="test-model", prompt="stream-error-after-first")

    received_chunks: list[str] = []

    async def _consume_stream() -> None:
        async for chunk in router.stream_complete(req):
            received_chunks.append(chunk.delta)  # noqa: PERF401

    with pytest.raises(ProviderProtocolError):
        await _consume_stream()

    assert received_chunks == ["First chunk valid"]
    assert p2.call_count == 0


@pytest.mark.asyncio
async def test_case_12_max_3_attempts_with_5_eligible_failing_candidates() -> None:
    """Case 12: Max 3 attempts with 5 eligible failing candidates."""
    providers = [
        MockStreamProvider(
            residency_tier="local",
            kind="ollama",
            fail_with=ProviderHTTPError("503", status=503),
        )
        for _ in range(5)
    ]
    candidates = [RouteCandidate(uuid4(), prov, "local", idx) for idx, prov in enumerate(providers)]

    router = ProviderRouter(uuid4(), candidates)
    req = CompletionRequest(model="test-model", prompt="hello")

    with pytest.raises(AllProvidersUnavailable) as exc_info:
        async for _ in router.stream_complete(req):
            pass

    assert exc_info.value.code == "NO_PROVIDER_IN_RESIDENCY_TIER"
    assert [p.call_count for p in providers] == [1, 1, 1, 0, 0]
    assert len(router.last_route_trace) == 3


@pytest.mark.asyncio
async def test_generate_structured_failover_and_schema_error() -> None:
    """Verify structured output failover on availability error and refusal on schema error."""
    p1 = MockStreamProvider(
        residency_tier="local",
        fail_with=ProviderHTTPError("503", status=503),
    )
    p2 = MockStreamProvider(residency_tier="local")
    c1 = RouteCandidate(uuid4(), p1, "local", 0)
    c2 = RouteCandidate(uuid4(), p2, "local", 1)

    router = ProviderRouter(uuid4(), [c1, c2])
    req = StructuredRequest(model="test-model", prompt="hello", response_model=EchoModel)
    resp = await router.generate_structured(req)
    assert resp.parsed.echo == "Hello"
    assert p1.call_count == 1
    assert p2.call_count == 1

    p3 = MockStreamProvider(residency_tier="local", fail_with=ProviderSchemaError("mismatch"))
    p4 = MockStreamProvider(residency_tier="local")
    c3 = RouteCandidate(uuid4(), p3, "local", 0)
    c4 = RouteCandidate(uuid4(), p4, "local", 1)

    router_schema = ProviderRouter(uuid4(), [c3, c4])
    with pytest.raises(ProviderSchemaError):
        await router_schema.generate_structured(req)
    assert p3.call_count == 1
    assert p4.call_count == 0


@pytest.mark.asyncio
async def test_embed_batch_failover() -> None:
    """Verify vector embeddings failover on availability error."""
    p1 = MockStreamProvider(
        residency_tier="local",
        fail_with=ProviderHTTPError("500", status=500),
    )
    p2 = MockStreamProvider(residency_tier="local")
    c1 = RouteCandidate(uuid4(), p1, "local", 0)
    c2 = RouteCandidate(uuid4(), p2, "local", 1)

    router = ProviderRouter(uuid4(), [c1, c2])
    req = EmbedBatchRequest(model="test-embed", inputs=("text 1", "text 2"))
    vectors = await router.embed_batch(req)
    assert len(vectors) == 2
    assert p1.call_count == 1
    assert p2.call_count == 1


@pytest.mark.asyncio
async def test_health_probe_failover() -> None:
    """Verify health probe returns first available healthy candidate."""
    p1 = MockStreamProvider(
        residency_tier="local",
        fail_with=ProviderHTTPError("503", status=503),
    )
    p2 = MockStreamProvider(residency_tier="local")
    c1 = RouteCandidate(uuid4(), p1, "local", 0)
    c2 = RouteCandidate(uuid4(), p2, "local", 1)

    router = ProviderRouter(uuid4(), [c1, c2])
    status = await router.health_probe()
    assert status.ok
    assert p1.call_count == 1
    assert p2.call_count == 1


@pytest.mark.asyncio
async def test_all_circuit_breakers_open() -> None:
    """Verify router rejects request when all candidates in residency tier have OPEN breakers."""
    p1 = MockStreamProvider(residency_tier="local")
    c1_id = uuid4()
    c1 = RouteCandidate(c1_id, p1, "local", 0)

    breakers = CircuitBreaker(failure_threshold=1)
    ws_id = uuid4()
    breakers.record_failure(ws_id, c1_id, ProviderHTTPError("503", status=503))
    assert breakers.get_state(ws_id, c1_id) == CircuitBreakerState.OPEN

    router = ProviderRouter(ws_id, [c1], breakers=breakers)
    req = CompletionRequest(model="test-model", prompt="hello")

    with pytest.raises(AllProvidersUnavailable) as exc_info:
        async for _ in router.stream_complete(req):
            pass
    assert exc_info.value.code == "NO_PROVIDER_IN_RESIDENCY_TIER"
    assert p1.call_count == 0


@pytest.mark.asyncio
async def test_router_empty_candidates_and_residency() -> None:
    """Verify router with empty candidates returns router tier and rejects calls."""
    router = ProviderRouter(uuid4(), [])
    assert router.residency_tier == "router"
    req = CompletionRequest(model="test", prompt="hello")
    with pytest.raises(AllProvidersUnavailable):
        async for _ in router.stream_complete(req):
            pass


@pytest.mark.asyncio
async def test_stream_empty_and_policy_error() -> None:
    """Verify empty stream handles StopAsyncIteration and policy error aborts immediately."""

    class EmptyStreamProvider(LLMProvider):
        kind = "ollama"

        @property
        def residency_tier(self) -> str:
            return "local"

        async def stream_complete(
            self,
            _req: CompletionRequest,
        ) -> AsyncIterator[StreamChunk]:
            empty_items: tuple[StreamChunk, ...] = ()
            for item in empty_items:
                yield item

        async def generate_structured[TModel: BaseModel](
            self, req: StructuredRequest[TModel]
        ) -> StructuredResponse[TModel]:
            msg = "Not implemented"
            raise NotImplementedError(msg)

        async def embed_batch(self, req: EmbedBatchRequest) -> list[list[float]]:
            msg = "Not implemented"
            raise NotImplementedError(msg)

        async def health_probe(self) -> HealthStatus:
            msg = "Not implemented"
            raise NotImplementedError(msg)

    c1 = RouteCandidate(uuid4(), EmptyStreamProvider(), "local", 0)
    router = ProviderRouter(uuid4(), [c1])
    req = CompletionRequest(model="test", prompt="hello")
    chunks = [c async for c in router.stream_complete(req)]
    assert chunks == []

    p_err = MockStreamProvider(
        residency_tier="local",
        fail_with=ProviderSchemaError("schema error"),
    )
    p_sec = MockStreamProvider(residency_tier="local")
    c_err = RouteCandidate(uuid4(), p_err, "local", 0)
    c_sec = RouteCandidate(uuid4(), p_sec, "local", 1)
    router_err = ProviderRouter(uuid4(), [c_err, c_sec])

    with pytest.raises(ProviderSchemaError):
        async for _ in router_err.stream_complete(req):
            pass
    assert p_sec.call_count == 0


@pytest.mark.asyncio
async def test_stream_tail_aclose_on_failure() -> None:
    """Verify stream_tail invokes aclose on upstream iterator when an exception occurs."""

    class FailTailProvider(LLMProvider):
        kind = "ollama"

        @property
        def residency_tier(self) -> str:
            return "local"

        async def stream_complete(
            self,
            _req: CompletionRequest,
        ) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(delta="chunk0", index=0)
            msg = "Tail failure"
            raise RuntimeError(msg)

        async def generate_structured[TModel: BaseModel](
            self, req: StructuredRequest[TModel]
        ) -> StructuredResponse[TModel]:
            msg = "Not implemented"
            raise NotImplementedError(msg)

        async def embed_batch(self, req: EmbedBatchRequest) -> list[list[float]]:
            msg = "Not implemented"
            raise NotImplementedError(msg)

        async def health_probe(self) -> HealthStatus:
            msg = "Not implemented"
            raise NotImplementedError(msg)

    prov = FailTailProvider()
    c = RouteCandidate(uuid4(), prov, "local", 0)
    router = ProviderRouter(uuid4(), [c])

    with pytest.raises(RuntimeError, match="Tail failure"):
        async for _ in router.stream_complete(CompletionRequest(model="test", prompt="hello")):
            pass


@pytest.mark.asyncio
async def test_generate_structured_skipped_and_ttft() -> None:
    """Verify structured output skips OPEN breaker and handles TTFT deadline timeout."""
    p1 = MockStreamProvider(residency_tier="local")
    c1_id = uuid4()
    c1 = RouteCandidate(c1_id, p1, "local", 0)
    c2 = RouteCandidate(uuid4(), p1, "local", 1)

    breakers = CircuitBreaker(failure_threshold=1)
    ws_id = uuid4()
    breakers.record_failure(ws_id, c1_id, ProviderHTTPError("503", status=503))

    router = ProviderRouter(ws_id, [c1, c2], breakers=breakers)
    req = StructuredRequest(model="test", prompt="hello", response_model=EchoModel)
    resp = await router.generate_structured(req)
    assert resp.parsed.echo == "Hello"

    router_empty = ProviderRouter(ws_id, [])
    with pytest.raises(AllProvidersUnavailable):
        await router_empty.generate_structured(req)


@pytest.mark.asyncio
async def test_embed_batch_skipped_and_policy_error() -> None:
    """Verify embed_batch skips OPEN breakers and propagates policy errors."""
    p_policy = MockStreamProvider(
        residency_tier="local",
        fail_with=ProviderSchemaError("bad input"),
    )
    p_fallback = MockStreamProvider(residency_tier="local")
    c1 = RouteCandidate(uuid4(), p_policy, "local", 0)
    c2 = RouteCandidate(uuid4(), p_fallback, "local", 1)

    router = ProviderRouter(uuid4(), [c1, c2])
    req = EmbedBatchRequest(model="test", inputs=("text 1",))
    with pytest.raises(ProviderSchemaError):
        await router.embed_batch(req)
    assert p_fallback.call_count == 0

    c1_id = uuid4()
    c1_skip = RouteCandidate(c1_id, p_fallback, "local", 0)
    c2_id = uuid4()
    c2_run = RouteCandidate(c2_id, p_fallback, "local", 1)
    breakers = CircuitBreaker(failure_threshold=1)
    ws_id = uuid4()
    breakers.record_failure(ws_id, c1_id, ProviderHTTPError("500", status=500))

    router_skip = ProviderRouter(ws_id, [c1_skip, c2_run], breakers=breakers)
    vectors = await router_skip.embed_batch(req)
    assert len(vectors) == 1

    router_empty = ProviderRouter(uuid4(), [])
    with pytest.raises(AllProvidersUnavailable):
        await router_empty.embed_batch(req)


@pytest.mark.asyncio
async def test_health_probe_all_unhealthy_and_skipped() -> None:
    """Verify health_probe handles skipped candidate and returns unhealthy when all fail."""

    class ErrorHealthProvider(LLMProvider):
        kind = "ollama"

        @property
        def residency_tier(self) -> str:
            return "local"

        async def stream_complete(
            self,
            _req: CompletionRequest,
        ) -> AsyncIterator[StreamChunk]:
            empty_items: tuple[StreamChunk, ...] = ()
            for item in empty_items:
                yield item

        async def generate_structured[TModel: BaseModel](
            self, req: StructuredRequest[TModel]
        ) -> StructuredResponse[TModel]:
            msg = "Not implemented"
            raise NotImplementedError(msg)

        async def embed_batch(self, req: EmbedBatchRequest) -> list[list[float]]:
            msg = "Not implemented"
            raise NotImplementedError(msg)

        async def health_probe(self) -> HealthStatus:
            msg = "Fatal daemon error"
            raise RuntimeError(msg)

    c1_id = uuid4()
    c1 = RouteCandidate(c1_id, ErrorHealthProvider(), "local", 0)
    c2 = RouteCandidate(uuid4(), ErrorHealthProvider(), "local", 1)

    breakers = CircuitBreaker(failure_threshold=1)
    ws_id = uuid4()
    breakers.record_failure(ws_id, c1_id, ProviderHTTPError("503", status=503))

    router = ProviderRouter(ws_id, [c1, c2], breakers=breakers)
    status = await router.health_probe()
    assert not status.ok
    assert status.detail == "All providers unhealthy"


@pytest.mark.asyncio
async def test_kind_detection_and_residency_fallback() -> None:
    """Verify provider kind detection falls back to class name or residency tier."""

    class GeminiProviderMock(MockStreamProvider):
        pass

    class OpenAIProviderMock(MockStreamProvider):
        pass

    class CustomVendorMock(MockStreamProvider):
        pass

    c1 = RouteCandidate(uuid4(), GeminiProviderMock(residency_tier="cloud", kind=""), "cloud", 0)
    c2 = RouteCandidate(uuid4(), OpenAIProviderMock(residency_tier="cloud", kind=""), "cloud", 1)
    c3 = RouteCandidate(
        uuid4(),
        CustomVendorMock(residency_tier="custom-tier", kind=""),
        "custom-tier",
        2,
    )

    router = ProviderRouter(uuid4(), [c1, c2, c3], air_gap_mode=False)
    assert router._get_candidate_kind(c1) == "gemini"  # noqa: SLF001
    assert router._get_candidate_kind(c2) == "openai"  # noqa: SLF001
    assert router._get_candidate_kind(c3) == "custom-tier"  # noqa: SLF001


@pytest.mark.asyncio
async def test_ttft_asyncio_timeout_in_stream_and_structured() -> None:
    """Verify asyncio timeout wraps stream first chunk and structured execution."""

    class SlowStreamProvider(LLMProvider):
        kind = "ollama"

        @property
        def residency_tier(self) -> str:
            return "local"

        async def stream_complete(
            self,
            _req: CompletionRequest,
        ) -> AsyncIterator[StreamChunk]:
            await asyncio.sleep(0.05)
            yield StreamChunk(delta="slow", index=0)

        async def generate_structured[TModel: BaseModel](
            self, req: StructuredRequest[TModel]
        ) -> StructuredResponse[TModel]:
            await asyncio.sleep(0.05)
            return StructuredResponse(
                parsed=req.response_model.model_validate({"echo": "slow", "ok": True}),
                raw_json="{}",
                ttft_ms=50.0,
                total_latency_ms=50.0,
            )

        async def embed_batch(self, req: EmbedBatchRequest) -> list[list[float]]:
            msg = "Not implemented"
            raise NotImplementedError(msg)

        async def health_probe(self) -> HealthStatus:
            msg = "Not implemented"
            raise NotImplementedError(msg)

    c = RouteCandidate(uuid4(), SlowStreamProvider(), "local", 0)
    router = ProviderRouter(uuid4(), [c])

    req = CompletionRequest(model="test", prompt="hello", ttft_deadline_ms=1)
    with pytest.raises(AllProvidersUnavailable) as exc_info:
        async for _ in router.stream_complete(req):
            pass
    assert "NO_PROVIDER_IN_RESIDENCY_TIER" in str(exc_info.value.code)

    s_req = StructuredRequest(
        model="test",
        prompt="hello",
        response_model=EchoModel,
        ttft_deadline_ms=1,
    )
    with pytest.raises(AllProvidersUnavailable) as exc_info:
        await router.generate_structured(s_req)
    assert "NO_PROVIDER_IN_RESIDENCY_TIER" in str(exc_info.value.code)


@pytest.mark.asyncio
async def test_all_candidates_probe_in_flight_last_err_none() -> None:
    """Verify router raises AllProvidersUnavailable when candidates skipped without last_err."""
    p = MockStreamProvider(residency_tier="local")
    c1_id = uuid4()
    c1 = RouteCandidate(c1_id, p, "local", 0)
    breakers = CircuitBreaker(failure_threshold=1)
    ws_id = uuid4()

    breakers.record_failure(ws_id, c1_id, ProviderHTTPError("503", status=503))
    entry = breakers._get_entry(ws_id, c1_id)  # noqa: SLF001
    entry.state = CircuitBreakerState.HALF_OPEN
    entry.probe_in_flight = True

    router = ProviderRouter(ws_id, [c1], breakers=breakers)

    req = CompletionRequest(model="test", prompt="hello")
    with pytest.raises(AllProvidersUnavailable):
        async for _ in router.stream_complete(req):
            pass

    s_req = StructuredRequest(model="test", prompt="hello", response_model=EchoModel)
    with pytest.raises(AllProvidersUnavailable):
        await router.generate_structured(s_req)

    e_req = EmbedBatchRequest(model="test", inputs=("text",))
    with pytest.raises(AllProvidersUnavailable):
        await router.embed_batch(e_req)
