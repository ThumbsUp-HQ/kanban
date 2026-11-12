# Copyright 2026 Kanban Platform Contributors
"""Unit tests for OllamaProvider adapter, registry, and OllamaSettings validation."""

from __future__ import annotations

import asyncio
import ipaddress
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from pydantic import BaseModel, HttpUrl, ValidationError

from agent.providers.base import (
    CompletionRequest,
    EmbedBatchRequest,
    LLMProvider,
    StructuredRequest,
)
from agent.providers.errors import (
    ProviderHTTPError,
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderSchemaError,
    ProviderTimeout,
    ProviderUnavailable,
)
from agent.providers.ollama import (
    OllamaProvider,
    OllamaSettings,
    _parse_embeddings_data,
)
from agent.providers.registry import build_provider
from agent.testing.fixtures import FixtureLLMProvider
from agent.testing.http_cassette import CassetteTransport

if TYPE_CHECKING:
    from ipaddress import IPv4Network, IPv6Network

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "ai"

DEFAULT_ALLOWED_CIDRS: tuple[IPv4Network | IPv6Network, ...] = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("10.0.0.0/8"),
)


class DummyStructuredOutput(BaseModel):
    """Dummy schema for structured output testing."""

    echo: str
    ok: bool


def _make_settings(  # noqa: PLR0913
    *,
    base_url: str | HttpUrl = "http://127.0.0.1:11434",
    allowed_cidrs: tuple[IPv4Network | IPv6Network, ...] = DEFAULT_ALLOWED_CIDRS,
    models: tuple[str, ...] = ("qwen2.5-coder:7b", "llama3.2:3b"),
    connect_timeout_s: float = 2.0,
    read_timeout_s: float = 30.0,
    mtls_cert: Path | None = None,
    mtls_key: Path | None = None,
    ca_bundle: Path | None = None,
) -> OllamaSettings:
    url = HttpUrl(base_url) if isinstance(base_url, str) else base_url
    return OllamaSettings(
        base_url=url,
        allowed_ollama_cidrs=allowed_cidrs,
        model_allowlist=models,
        connect_timeout_s=connect_timeout_s,
        read_timeout_s=read_timeout_s,
        mtls_client_cert_path=mtls_cert,
        mtls_client_key_path=mtls_key,
        ca_bundle_path=ca_bundle,
    )


class TestOllamaSettings:
    """Tests for OllamaSettings configuration validation."""

    def test_valid_settings(self) -> None:
        """Verify valid settings initialize with expected defaults."""
        settings = _make_settings()
        assert settings.connect_timeout_s == 2.0
        assert settings.read_timeout_s == 30.0
        assert settings.keep_alive == "30m"

    def test_reject_query_and_fragment(self) -> None:
        """Reject base_url containing query parameters or URL fragments."""
        with pytest.raises(ValidationError, match="base_url must not contain query parameters"):
            _make_settings(base_url="http://127.0.0.1:11434/?param=1")

        with pytest.raises(ValidationError, match="base_url must not contain fragment"):
            _make_settings(base_url="http://127.0.0.1:11434/#frag")

    def test_reject_userinfo(self) -> None:
        """Reject base_url containing userinfo."""
        with pytest.raises(ValidationError, match="must not contain userinfo"):
            _make_settings(base_url="http://user:pass@127.0.0.1:11434")

    def test_reject_unsupported_scheme(self) -> None:
        """Reject base_url with non-http/https scheme."""
        with pytest.raises(ValidationError):
            _make_settings(base_url="ftp://127.0.0.1:11434")

    def test_empty_cidrs_raises(self) -> None:
        """Reject empty allowed_ollama_cidrs tuple."""
        with pytest.raises(
            ValidationError, match="Tuple should have at least 1 item after validation"
        ):
            _make_settings(allowed_cidrs=())

    def test_empty_models_raises(self) -> None:
        """Reject empty model_allowlist tuple."""
        with pytest.raises(
            ValidationError, match="Tuple should have at least 1 item after validation"
        ):
            _make_settings(models=())

    def test_timeout_bounds(self) -> None:
        """Enforce connect and read timeout bounds."""
        with pytest.raises(ValidationError):
            _make_settings(connect_timeout_s=0.01)
        with pytest.raises(ValidationError):
            _make_settings(connect_timeout_s=15.0)
        with pytest.raises(ValidationError):
            _make_settings(read_timeout_s=0.5)
        with pytest.raises(ValidationError):
            _make_settings(read_timeout_s=500.0)

    def test_mtls_cert_and_key_mutual_requirement(self, tmp_path: Path) -> None:
        """Enforce that mTLS cert and key paths are both present or both absent."""
        cert = tmp_path / "client.crt"
        key = tmp_path / "client.key"
        cert.write_text("cert")
        key.write_text("key")

        # Both present is valid
        s = _make_settings(mtls_cert=cert, mtls_key=key)
        assert s.mtls_client_cert_path == cert
        assert s.mtls_client_key_path == key

        # Cert only raises
        with pytest.raises(
            ValidationError,
            match="Both mtls_client_cert_path and mtls_client_key_path",
        ):
            _make_settings(mtls_cert=cert, mtls_key=None)

        # Key only raises
        with pytest.raises(
            ValidationError,
            match="Both mtls_client_cert_path and mtls_client_key_path",
        ):
            _make_settings(mtls_cert=None, mtls_key=key)


class TestOllamaProviderOperations:
    """Tests for OllamaProvider LLMProvider protocol implementation."""

    @pytest.mark.asyncio
    async def test_case_1_fim_stream_success(self) -> None:
        """Case 1: FIM stream against recorded cassette yields exact chunk tokens."""
        cassette_path = FIXTURES_DIR / "ollama_fim_stream_ok.yaml"
        transport = CassetteTransport(cassette_path)
        settings = _make_settings()
        provider = OllamaProvider(settings, transport=transport)

        assert isinstance(provider, LLMProvider)
        assert provider.residency_tier == "ollama"

        req = CompletionRequest(
            model="qwen2.5-coder:7b",
            prompt="def ",
            suffix="",
            temperature=0.0,
            max_output_tokens=32,
        )

        chunks = [chunk async for chunk in provider.stream_complete(req)]

        assert len(chunks) == 3
        assert chunks[0].delta == "def "
        assert chunks[0].ttft_ms is not None
        assert chunks[0].ttft_ms >= 0.0

        assert chunks[1].delta == "hello():\n"

        assert chunks[2].delta == "    return True\n"
        assert chunks[2].finish_reason == "stop"

        # Verify sent payload in transport
        assert transport.call_count == 1
        req_sent = transport.requests[0]
        assert req_sent.url.path == "/api/generate"
        assert req_sent.headers.get("host") == "127.0.0.1:11434"

    @pytest.mark.asyncio
    async def test_case_2_structured_chat_success(self) -> None:
        """Case 2: Structured chat against recorded cassette parses against Pydantic schema."""
        cassette_path = FIXTURES_DIR / "ollama_chat_structured_ok.yaml"
        transport = CassetteTransport(cassette_path)
        settings = _make_settings()
        provider = OllamaProvider(settings, transport=transport)

        req = StructuredRequest(
            model="qwen2.5-coder:7b",
            prompt="Review this code",
            response_model=DummyStructuredOutput,
        )

        resp = await provider.generate_structured(req)
        assert isinstance(resp.parsed, DummyStructuredOutput)
        assert resp.parsed.echo == "Hello Sparkle"
        assert resp.parsed.ok is True
        assert resp.raw_json == '{"echo": "Hello Sparkle", "ok": true}'

    @pytest.mark.asyncio
    async def test_structured_chat_invalid_json_raises_schema_error(self) -> None:
        """Invalid JSON content from Ollama chat raises ProviderSchemaError."""
        cassette_path = FIXTURES_DIR / "ollama_chat_structured_invalid_json.yaml"
        transport = CassetteTransport(cassette_path)
        settings = _make_settings()
        provider = OllamaProvider(settings, transport=transport)

        req = StructuredRequest(
            model="qwen2.5-coder:7b",
            prompt="Review this code",
            response_model=DummyStructuredOutput,
        )

        with pytest.raises(ProviderSchemaError):
            await provider.generate_structured(req)

    @pytest.mark.asyncio
    async def test_embed_batch_success(self) -> None:
        """Batch embedding against cassette returns vector lists of identical dimensions."""
        cassette_path = FIXTURES_DIR / "ollama_embed_ok.yaml"
        transport = CassetteTransport(cassette_path)
        settings = _make_settings()
        provider = OllamaProvider(settings, transport=transport)

        req = EmbedBatchRequest(
            model="qwen2.5-coder:7b",
            inputs=("First document", "Second document"),
        )

        vectors = await provider.embed_batch(req)
        assert len(vectors) == 2
        assert len(vectors[0]) == 4
        assert len(vectors[1]) == 4

    @pytest.mark.asyncio
    async def test_case_7_model_not_allowed_raises_before_dispatch(self) -> None:
        """Case 7: Model not in allowlist raises MODEL_NOT_ALLOWED before network dispatch."""
        transport = CassetteTransport([])
        settings = _make_settings(models=("qwen2.5-coder:7b",))
        provider = OllamaProvider(settings, transport=transport)

        req = CompletionRequest(model="unapproved-model:latest", prompt="Hi")
        with pytest.raises(ProviderPolicyError) as exc_info:
            async for _ in provider.stream_complete(req):
                pass

        assert exc_info.value.code == "MODEL_NOT_ALLOWED"
        assert transport.call_count == 0

    @pytest.mark.asyncio
    async def test_case_8_redirect_refused(self) -> None:
        """Case 8: HTTP 302 redirect from server raises REDIRECT_REFUSED."""
        cassette_path = FIXTURES_DIR / "ollama_fault_redirect_302.yaml"
        transport = CassetteTransport(cassette_path)
        settings = _make_settings()
        provider = OllamaProvider(settings, transport=transport)

        req = CompletionRequest(model="qwen2.5-coder:7b", prompt="Hi")
        with pytest.raises(ProviderProtocolError) as exc_info:
            async for _ in provider.stream_complete(req):
                pass

        assert exc_info.value.code == "REDIRECT_REFUSED"

    @pytest.mark.asyncio
    async def test_case_9_fault_429_rate_limited(self) -> None:
        """Case 9: HTTP 429 maps to ProviderHTTPError with retry_after_s."""
        cassette_path = FIXTURES_DIR / "ollama_fault_429.yaml"
        transport = CassetteTransport(cassette_path)
        settings = _make_settings()
        provider = OllamaProvider(settings, transport=transport)

        req = CompletionRequest(model="qwen2.5-coder:7b", prompt="Hi")
        with pytest.raises(ProviderHTTPError) as exc_info:
            async for _ in provider.stream_complete(req):
                pass

        assert exc_info.value.status == 429
        assert exc_info.value.retry_after_s == 30.0

    @pytest.mark.asyncio
    async def test_case_10_fault_500_server_error(self) -> None:
        """Case 10: HTTP 500 maps to ProviderHTTPError with status 500."""
        cassette_path = FIXTURES_DIR / "ollama_fault_500.yaml"
        transport = CassetteTransport(cassette_path)
        settings = _make_settings()
        provider = OllamaProvider(settings, transport=transport)

        req = CompletionRequest(model="qwen2.5-coder:7b", prompt="Hi")
        with pytest.raises(ProviderHTTPError) as exc_info:
            async for _ in provider.stream_complete(req):
                pass

        assert exc_info.value.status == 500

    @pytest.mark.asyncio
    async def test_fault_timeout(self) -> None:
        """Timeout during request maps to ProviderTimeout."""
        cassette_path = FIXTURES_DIR / "ollama_fault_timeout.yaml"
        transport = CassetteTransport(cassette_path)
        settings = _make_settings()
        provider = OllamaProvider(settings, transport=transport)

        req = CompletionRequest(model="qwen2.5-coder:7b", prompt="Hi")
        with pytest.raises(ProviderTimeout):
            async for _ in provider.stream_complete(req):
                pass

    @pytest.mark.asyncio
    async def test_case_11_fault_oversize_line(self) -> None:
        """Case 11: Line larger than 64 KiB raises LINE_TOO_LARGE."""
        cassette_path = FIXTURES_DIR / "ollama_fault_oversize_line.yaml"
        transport = CassetteTransport(cassette_path)
        settings = _make_settings()
        provider = OllamaProvider(settings, transport=transport)

        req = CompletionRequest(model="qwen2.5-coder:7b", prompt="Hi")
        with pytest.raises(ProviderProtocolError) as exc_info:
            async for _ in provider.stream_complete(req):
                pass

        assert exc_info.value.code == "LINE_TOO_LARGE"

    @pytest.mark.asyncio
    async def test_case_12_embed_batch_too_large(self) -> None:
        """Case 12: Embed batch > 512 texts raises BATCH_TOO_LARGE before network dispatch."""
        transport = CassetteTransport([])
        settings = _make_settings()
        provider = OllamaProvider(settings, transport=transport)

        texts = tuple(["hello"] * 513)
        req = EmbedBatchRequest.model_construct(model="qwen2.5-coder:7b", inputs=texts)

        with pytest.raises(ProviderProtocolError) as exc_info:
            await provider.embed_batch(req)

        assert exc_info.value.code == "BATCH_TOO_LARGE"
        assert transport.call_count == 0

    @pytest.mark.asyncio
    async def test_embed_batch_empty_texts_raises(self) -> None:
        """Empty texts inputs in embed batch raises ProviderProtocolError."""
        transport = CassetteTransport([])
        settings = _make_settings()
        provider = OllamaProvider(settings, transport=transport)

        req = EmbedBatchRequest.model_construct(model="qwen2.5-coder:7b", inputs=())
        with pytest.raises(ProviderProtocolError, match="must not be empty"):
            await provider.embed_batch(req)

    @pytest.mark.asyncio
    async def test_embed_batch_text_too_large_raises(self) -> None:
        """Individual text exceeding 8192 characters raises ProviderProtocolError."""
        transport = CassetteTransport([])
        settings = _make_settings()
        provider = OllamaProvider(settings, transport=transport)

        oversize_text = "a" * 8193
        req = EmbedBatchRequest.model_construct(model="qwen2.5-coder:7b", inputs=(oversize_text,))
        with pytest.raises(ProviderProtocolError, match="exceeds 8192"):
            await provider.embed_batch(req)

    def test_parse_embeddings_response_edge_cases(self) -> None:
        """Verify validation edge cases in _parse_embeddings_data."""
        # Non-list raw
        with pytest.raises(ProviderProtocolError, match="missing 'embeddings'"):
            _parse_embeddings_data("not a list")

        # Row is not a list
        with pytest.raises(ProviderProtocolError, match="not a vector list"):
            _parse_embeddings_data(["not a vector"])

        # Dimension mismatch
        with pytest.raises(ProviderProtocolError, match="dimension mismatch"):
            _parse_embeddings_data([[1.0, 2.0], [1.0, 2.0, 3.0]])

    @pytest.mark.asyncio
    async def test_stream_complete_empty_options(self) -> None:
        """Stream complete with default parameters (no suffix, no temp, no max_tokens)."""
        cassette_data = {
            "http_exchanges": [
                {
                    "request": {"method": "POST", "path": "/api/generate"},
                    "response": {
                        "status": 200,
                        "headers": {"content-type": "application/x-ndjson"},
                        "ndjson_chunks": [{"response": "chunk1", "done": True}],
                    },
                }
            ]
        }
        transport = CassetteTransport(cassette_data)
        provider = OllamaProvider(_make_settings(), transport=transport)
        req = CompletionRequest.model_construct(
            model="qwen2.5-coder:7b",
            prompt="Hello",
            temperature=None,
            max_output_tokens=None,
            suffix=None,
        )
        chunks = [c async for c in provider.stream_complete(req)]
        assert len(chunks) == 1
        assert chunks[0].delta == "chunk1"

    @pytest.mark.asyncio
    async def test_stream_empty_line_and_corrupt_json(self) -> None:
        """Stream with blank lines ignores them; corrupt NDJSON line raises error."""
        # Blank line followed by valid chunk
        cassette_blank = {
            "http_exchanges": [
                {
                    "request": {"method": "POST", "path": "/api/generate"},
                    "response": {
                        "status": 200,
                        "text": '\n   \n{"response": "ok", "done": true}\n',
                    },
                }
            ]
        }
        t_blank = CassetteTransport(cassette_blank)
        p_blank = OllamaProvider(_make_settings(), transport=t_blank)
        req = CompletionRequest(model="qwen2.5-coder:7b", prompt="hi")
        chunks = [c async for c in p_blank.stream_complete(req)]
        assert len(chunks) == 1
        assert chunks[0].delta == "ok"

        # Corrupt JSON line
        cassette_bad = {
            "http_exchanges": [
                {
                    "request": {"method": "POST", "path": "/api/generate"},
                    "response": {
                        "status": 200,
                        "text": "not valid json\n",
                    },
                }
            ]
        }
        t_bad = CassetteTransport(cassette_bad)
        p_bad = OllamaProvider(_make_settings(), transport=t_bad)
        with pytest.raises(ProviderProtocolError, match="Failed to parse Ollama NDJSON line"):
            async for _ in p_bad.stream_complete(req):
                pass

    @pytest.mark.asyncio
    async def test_stream_sla_breach(self) -> None:
        """TTFT SLA breach raises ProviderTimeout."""

        class SlowTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                await asyncio.sleep(0.005)
                return httpx.Response(
                    200,
                    headers={"content-type": "application/x-ndjson"},
                    content=b'{"response": "token", "done": true}\n',
                    request=request,
                )

        provider = OllamaProvider(_make_settings(), transport=SlowTransport())
        req = CompletionRequest(
            model="qwen2.5-coder:7b",
            prompt="hi",
            ttft_deadline_ms=1,  # 1ms deadline will trigger breach after 5ms sleep
        )
        with pytest.raises(ProviderTimeout, match="TTFT SLA breached"):
            async for _ in provider.stream_complete(req):
                pass

    @pytest.mark.asyncio
    async def test_stream_connect_error(self) -> None:
        """Connect error during stream raises ProviderUnavailable."""
        transport = CassetteTransport(
            [
                {
                    "request": {"method": "POST", "path": "/api/generate"},
                    "fault": {"kind": "connect_error"},
                }
            ]
        )
        provider = OllamaProvider(_make_settings(), transport=transport)
        req = CompletionRequest(model="qwen2.5-coder:7b", prompt="hi")
        with pytest.raises(ProviderUnavailable, match="Failed to connect to Ollama"):
            async for _ in provider.stream_complete(req):
                pass

    @pytest.mark.asyncio
    async def test_structured_chat_malformed_json_body(self) -> None:
        """Malformed top-level JSON response from /api/chat raises ProviderProtocolError."""
        transport = CassetteTransport(
            [
                {
                    "request": {"method": "POST", "path": "/api/chat"},
                    "response": {"status": 200, "text": "invalid non json"},
                }
            ]
        )
        provider = OllamaProvider(_make_settings(), transport=transport)
        req = StructuredRequest(
            model="qwen2.5-coder:7b",
            prompt="hi",
            response_model=DummyStructuredOutput,
        )
        with pytest.raises(ProviderProtocolError, match="malformed JSON payload"):
            await provider.generate_structured(req)

    @pytest.mark.asyncio
    async def test_structured_chat_schema_mismatch_error(self) -> None:
        """Valid JSON not conforming to response_model raises ProviderSchemaError."""
        transport = CassetteTransport(
            [
                {
                    "request": {"method": "POST", "path": "/api/chat"},
                    "response": {
                        "status": 200,
                        "json_body": {"message": {"content": '{"unrelated": 123}'}},
                    },
                }
            ]
        )
        provider = OllamaProvider(_make_settings(), transport=transport)
        req = StructuredRequest(
            model="qwen2.5-coder:7b",
            prompt="hi",
            response_model=DummyStructuredOutput,
        )
        with pytest.raises(ProviderSchemaError, match="failed schema validation"):
            await provider.generate_structured(req)

    @pytest.mark.asyncio
    async def test_structured_chat_network_errors(self) -> None:
        """Timeout and ConnectError in generate_structured map to typed errors."""
        t_time = CassetteTransport(
            [{"request": {"method": "POST", "path": "/api/chat"}, "fault": {"kind": "timeout"}}]
        )
        p_time = OllamaProvider(_make_settings(), transport=t_time)
        req = StructuredRequest(
            model="qwen2.5-coder:7b",
            prompt="hi",
            response_model=DummyStructuredOutput,
        )
        with pytest.raises(ProviderTimeout):
            await p_time.generate_structured(req)

        t_conn = CassetteTransport(
            [
                {
                    "request": {"method": "POST", "path": "/api/chat"},
                    "fault": {"kind": "connect_error"},
                }
            ]
        )
        p_conn = OllamaProvider(_make_settings(), transport=t_conn)
        with pytest.raises(ProviderUnavailable):
            await p_conn.generate_structured(req)

    @pytest.mark.asyncio
    async def test_embed_batch_malformed_and_network_errors(self) -> None:
        """Malformed JSON and network errors in embed_batch map to typed errors."""
        t_bad = CassetteTransport(
            [
                {
                    "request": {"method": "POST", "path": "/api/embed"},
                    "response": {"status": 200, "text": "bad json"},
                }
            ]
        )
        p_bad = OllamaProvider(_make_settings(), transport=t_bad)
        req = EmbedBatchRequest(model="qwen2.5-coder:7b", inputs=("test",))
        with pytest.raises(ProviderProtocolError, match="malformed JSON payload"):
            await p_bad.embed_batch(req)

        t_time = CassetteTransport(
            [{"request": {"method": "POST", "path": "/api/embed"}, "fault": {"kind": "timeout"}}]
        )
        p_time = OllamaProvider(_make_settings(), transport=t_time)
        with pytest.raises(ProviderTimeout):
            await p_time.embed_batch(req)

        t_conn = CassetteTransport(
            [
                {
                    "request": {"method": "POST", "path": "/api/embed"},
                    "fault": {"kind": "connect_error"},
                }
            ]
        )
        p_conn = OllamaProvider(_make_settings(), transport=t_conn)
        with pytest.raises(ProviderUnavailable):
            await p_conn.embed_batch(req)

    def test_settings_custom_cert_and_ca_bundle(self, tmp_path: Path) -> None:
        """Instantiate OllamaProvider with custom cert and CA bundle paths."""
        cert = tmp_path / "c.crt"
        key = tmp_path / "c.key"
        ca = tmp_path / "ca.crt"
        cert.write_text("c")
        key.write_text("k")
        ca.write_text("ca")

        s = _make_settings(mtls_cert=cert, mtls_key=key, ca_bundle=ca)
        p = OllamaProvider(s, transport=CassetteTransport([]))
        assert p._client._transport is not None  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_retry_after_non_numeric_header(self) -> None:
        """429 response with non-numeric retry-after sets retry_after_s to None."""
        transport = CassetteTransport(
            [
                {
                    "request": {"method": "POST", "path": "/api/generate"},
                    "response": {
                        "status": 429,
                        "headers": {"retry-after": "not-a-number"},
                        "text": "rate limited",
                    },
                }
            ]
        )
        provider = OllamaProvider(_make_settings(), transport=transport)
        req = CompletionRequest(model="qwen2.5-coder:7b", prompt="hi")
        with pytest.raises(ProviderHTTPError) as exc_info:
            async for _ in provider.stream_complete(req):
                pass
        assert exc_info.value.status == 429
        assert exc_info.value.retry_after_s is None

    @pytest.mark.asyncio
    async def test_health_probe(self) -> None:
        """Probe Ollama daemon health against 200, 503, and timeout."""
        # Healthy 200 response
        healthy_transport = CassetteTransport(
            [
                {
                    "request": {"method": "GET", "path": "/api/tags"},
                    "response": {
                        "status": 200,
                        "json_body": {"models": [{"name": "qwen2.5-coder:7b"}]},
                    },
                }
            ]
        )
        p1 = OllamaProvider(_make_settings(), transport=healthy_transport)
        status1 = await p1.health_probe()
        assert status1.ok is True
        assert status1.latency_ms is not None
        assert status1.latency_ms >= 0.0
        assert "qwen2.5-coder:7b" in status1.models

        # Unhealthy 503 response
        unhealthy_transport = CassetteTransport(
            [{"request": {"method": "GET", "path": "/api/tags"}, "response": {"status": 503}}]
        )
        p2 = OllamaProvider(_make_settings(), transport=unhealthy_transport)
        status2 = await p2.health_probe()
        assert status2.ok is False

        # Transport timeout
        timeout_transport = CassetteTransport(
            [{"request": {"method": "GET", "path": "/api/tags"}, "fault": {"kind": "timeout"}}]
        )
        p3 = OllamaProvider(_make_settings(), transport=timeout_transport)
        status3 = await p3.health_probe()
        assert status3.ok is False

    @pytest.mark.asyncio
    async def test_trust_env_false_and_https_sni(self) -> None:
        """Verify trust_env=False and SNI hostname extension on HTTPS endpoints."""
        settings = _make_settings(base_url="https://ollama.internal:8443")

        async def mock_resolver(_h: str, _p: int) -> list[str]:
            return ["10.0.0.1"]

        provider = OllamaProvider(settings, resolver=mock_resolver)
        assert provider._client.trust_env is False  # noqa: SLF001

        url, headers, extensions = await provider._resolve_target("/api/generate")  # noqa: SLF001
        assert url == "https://10.0.0.1:8443/api/generate"
        assert headers["Host"] == "ollama.internal:8443"
        assert extensions["sni_hostname"] == "ollama.internal"


class TestRegistryBuildProvider:
    """Tests for build_provider factory in agent/providers/registry.py."""

    def test_build_ollama_from_settings(self) -> None:
        """Construct OllamaProvider from OllamaSettings instance."""
        settings = _make_settings()
        transport = CassetteTransport([])
        provider = build_provider("ollama", settings, transport=transport)
        assert isinstance(provider, OllamaProvider)

    def test_build_ollama_from_dict(self) -> None:
        """Construct OllamaProvider from raw dictionary."""
        d = {
            "base_url": "http://127.0.0.1:11434",
            "allowed_ollama_cidrs": ["127.0.0.0/8"],
            "model_allowlist": ["qwen2.5-coder:7b"],
        }
        transport = CassetteTransport([])
        provider = build_provider("ollama", d, transport=transport)
        assert isinstance(provider, OllamaProvider)

    def test_build_ollama_invalid_settings_type(self) -> None:
        """Non-settings/dict argument to build_provider('ollama') raises TypeError."""
        with pytest.raises(TypeError, match="OllamaSettings or dict"):
            build_provider("ollama", 12345)

    def test_build_fixture_provider(self) -> None:
        """Construct FixtureLLMProvider from YAML cassette path."""
        path = FIXTURES_DIR / "echo_stream_ok.yaml"
        provider = build_provider("fixture", path)
        assert isinstance(provider, FixtureLLMProvider)

    def test_build_fixture_invalid_type(self) -> None:
        """Invalid settings type to build_provider('fixture') raises TypeError."""
        with pytest.raises(TypeError, match="Cassette, str, Path, or list"):
            build_provider("fixture", 12345)

    def test_build_unknown_provider_raises(self) -> None:
        """Unknown provider kind raises ValueError."""
        with pytest.raises(ValueError, match="Unknown provider kind 'custom'"):
            build_provider("custom", {})
