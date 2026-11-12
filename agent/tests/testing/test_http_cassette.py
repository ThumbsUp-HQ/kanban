# Copyright 2026 Kanban Platform Contributors
"""Unit tests for CassetteTransport offline HTTP replay and cassette contract parity."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from agent.testing.fixtures import CassetteMismatchError, load_cassette
from agent.testing.http_cassette import CassetteTransport

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "ai"
TEST_BASE_URL = "http://127.0.0.1:11434"

ALL_OLLAMA_CASSETTES = [
    "ollama_fim_stream_ok.yaml",
    "ollama_chat_structured_ok.yaml",
    "ollama_chat_structured_invalid_json.yaml",
    "ollama_embed_ok.yaml",
    "ollama_fault_429.yaml",
    "ollama_fault_500.yaml",
    "ollama_fault_timeout.yaml",
    "ollama_fault_redirect_302.yaml",
    "ollama_fault_oversize_line.yaml",
]


class TestCassetteSchemaValidation:
    """Validate all Ollama cassette files against cassette.schema.json."""

    @pytest.mark.parametrize("cassette_name", ALL_OLLAMA_CASSETTES)
    def test_cassette_validates_against_schema(self, cassette_name: str) -> None:
        """Verify each pre-recorded Ollama cassette parses and satisfies schema."""
        path = FIXTURES_DIR / cassette_name
        assert path.exists(), f"Cassette file {path} must exist"
        data = load_cassette(path)
        assert data.cassette_version == 1
        assert data.http_exchanges is not None


class TestCassetteTransportReplay:
    """Test CassetteTransport matching, replay, and fault handling."""

    @pytest.mark.asyncio
    async def test_case_3_contract_parity_live_vs_cassette(self) -> None:
        """Case 3: Contract parity: CassetteTransport reproduces identical exchange as httpx."""
        cassette_data = {
            "http_exchanges": [
                {
                    "request": {
                        "method": "POST",
                        "path": "/api/test",
                        "json_contains": {"query": "hello"},
                    },
                    "response": {
                        "status": 200,
                        "headers": {"content-type": "application/json"},
                        "json_body": {"response": "world", "score": 0.95},
                    },
                }
            ]
        }
        transport = CassetteTransport(cassette_data)
        async with httpx.AsyncClient(transport=transport, base_url=TEST_BASE_URL) as client:
            resp = await client.post("/api/test", json={"query": "hello", "extra": 123})
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/json"
            data = resp.json()
            assert data == {"response": "world", "score": 0.95}
            assert transport.call_count == 1
            assert len(transport.requests) == 1

    @pytest.mark.asyncio
    async def test_method_mismatch_raises(self) -> None:
        """HTTP method mismatch raises CassetteMismatchError."""
        transport = CassetteTransport(
            [{"request": {"method": "GET", "path": "/test"}, "response": {"status": 200}}]
        )
        async with httpx.AsyncClient(transport=transport, base_url=TEST_BASE_URL) as client:
            with pytest.raises(CassetteMismatchError, match="HTTP method mismatch"):
                await client.post("/test")

    @pytest.mark.asyncio
    async def test_path_mismatch_raises(self) -> None:
        """HTTP path mismatch raises CassetteMismatchError."""
        transport = CassetteTransport(
            [{"request": {"method": "GET", "path": "/expected"}, "response": {"status": 200}}]
        )
        async with httpx.AsyncClient(transport=transport, base_url=TEST_BASE_URL) as client:
            with pytest.raises(CassetteMismatchError, match="HTTP path mismatch"):
                await client.get("/wrong")

    @pytest.mark.asyncio
    async def test_json_contains_mismatch_raises(self) -> None:
        """Request JSON not matching json_contains raises CassetteMismatchError."""
        transport = CassetteTransport(
            [
                {
                    "request": {
                        "method": "POST",
                        "path": "/test",
                        "json_contains": {"expected_key": "val"},
                    },
                    "response": {"status": 200},
                }
            ]
        )
        async with httpx.AsyncClient(transport=transport, base_url=TEST_BASE_URL) as client:
            with pytest.raises(CassetteMismatchError, match="JSON mismatch"):
                await client.post("/test", json={"expected_key": "different"})

    @pytest.mark.asyncio
    async def test_invalid_json_body_with_json_contains_raises(self) -> None:
        """Non-JSON body with json_contains predicate raises CassetteMismatchError."""
        transport = CassetteTransport(
            [
                {
                    "request": {
                        "method": "POST",
                        "path": "/test",
                        "json_contains": {"k": "v"},
                    },
                    "response": {"status": 200},
                }
            ]
        )
        async with httpx.AsyncClient(transport=transport, base_url=TEST_BASE_URL) as client:
            with pytest.raises(CassetteMismatchError, match="Failed to parse request JSON body"):
                await client.post("/test", content=b"invalid json {")

    @pytest.mark.asyncio
    async def test_exhausted_exchanges_raises(self) -> None:
        """Sending request after all exchanges exhausted raises CassetteMismatchError."""
        transport = CassetteTransport(
            [{"request": {"method": "GET", "path": "/test"}, "response": {"status": 200}}]
        )
        async with httpx.AsyncClient(transport=transport, base_url=TEST_BASE_URL) as client:
            await client.get("/test")
            with pytest.raises(CassetteMismatchError, match="No cassette exchange remaining"):
                await client.get("/test")

    @pytest.mark.asyncio
    async def test_fault_kinds(self) -> None:
        """Simulate and verify various fault injections."""
        # http_429
        t_429 = CassetteTransport(
            [{"request": {"method": "GET", "path": "/t"}, "fault": {"kind": "http_429"}}]
        )
        async with httpx.AsyncClient(transport=t_429, base_url=TEST_BASE_URL) as client:
            resp = await client.get("/t")
            assert resp.status_code == 429
            assert resp.headers.get("retry-after") == "30"

        # http_500
        t_500 = CassetteTransport(
            [{"request": {"method": "GET", "path": "/t"}, "fault": {"kind": "http_500"}}]
        )
        async with httpx.AsyncClient(transport=t_500, base_url=TEST_BASE_URL) as client:
            resp = await client.get("/t")
            assert resp.status_code == 500

        # timeout
        t_timeout = CassetteTransport(
            [{"request": {"method": "GET", "path": "/t"}, "fault": {"kind": "timeout"}}]
        )
        async with httpx.AsyncClient(transport=t_timeout, base_url=TEST_BASE_URL) as client:
            with pytest.raises(httpx.ReadTimeout):
                await client.get("/t")

        # connect_error
        t_conn = CassetteTransport(
            [{"request": {"method": "GET", "path": "/t"}, "fault": {"kind": "connect_error"}}]
        )
        async with httpx.AsyncClient(transport=t_conn, base_url=TEST_BASE_URL) as client:
            with pytest.raises(httpx.ConnectError):
                await client.get("/t")

        # malformed_body
        t_malformed = CassetteTransport(
            [{"request": {"method": "GET", "path": "/t"}, "fault": {"kind": "malformed_body"}}]
        )
        async with httpx.AsyncClient(transport=t_malformed, base_url=TEST_BASE_URL) as client:
            resp = await client.get("/t")
            assert resp.status_code == 200
            assert b"INVALID MALFORMED" in resp.content

        # oversize_line
        t_oversize = CassetteTransport(
            [{"request": {"method": "GET", "path": "/t"}, "fault": {"kind": "oversize_line"}}]
        )
        async with httpx.AsyncClient(transport=t_oversize, base_url=TEST_BASE_URL) as client:
            resp = await client.get("/t")
            assert resp.status_code == 200
            assert len(resp.content) > 64 * 1024

        # unknown fault
        t_unknown = CassetteTransport(
            [{"request": {"method": "GET", "path": "/t"}, "fault": {"kind": "bogus"}}]
        )
        async with httpx.AsyncClient(transport=t_unknown, base_url=TEST_BASE_URL) as client:
            with pytest.raises(ValueError, match="Unknown simulated fault kind"):
                await client.get("/t")

    @pytest.mark.asyncio
    async def test_response_renderers(self) -> None:
        """Verify NDJSON, SSE, custom JSON, and text responses."""
        # NDJSON chunks
        t_ndjson = CassetteTransport(
            [
                {
                    "request": {"method": "POST", "path": "/ndjson"},
                    "response": {"ndjson_chunks": [{"msg": "part1"}, {"msg": "part2"}]},
                }
            ]
        )
        async with httpx.AsyncClient(transport=t_ndjson, base_url=TEST_BASE_URL) as client:
            resp = await client.post("/ndjson")
            assert resp.headers["content-type"] == "application/x-ndjson"
            assert resp.text == '{"msg": "part1"}\n{"msg": "part2"}\n'

        # SSE chunks
        t_sse = CassetteTransport(
            [
                {
                    "request": {"method": "GET", "path": "/sse"},
                    "response": {
                        "headers": {"content-type": "text/event-stream; charset=utf-8"},
                        "sse_chunks": ["chunk1", "chunk2"],
                    },
                }
            ]
        )
        async with httpx.AsyncClient(transport=t_sse, base_url=TEST_BASE_URL) as client:
            resp = await client.get("/sse")
            assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"
            assert "data: chunk1\n\n" in resp.text

        # JSON body with explicit content-type
        t_json = CassetteTransport(
            [
                {
                    "request": {"method": "GET", "path": "/json"},
                    "response": {
                        "headers": {"content-type": "application/problem+json"},
                        "json_body": {"title": "Problem"},
                    },
                }
            ]
        )
        async with httpx.AsyncClient(transport=t_json, base_url=TEST_BASE_URL) as client:
            resp = await client.get("/json")
            assert resp.headers["content-type"] == "application/problem+json"
            assert resp.json() == {"title": "Problem"}

        # JSON body with default content-type
        t_json_default = CassetteTransport(
            [
                {
                    "request": {"method": "GET", "path": "/json_default"},
                    "response": {
                        "json_body": {"k": "v"},
                    },
                }
            ]
        )
        async with httpx.AsyncClient(transport=t_json_default, base_url=TEST_BASE_URL) as client:
            resp = await client.get("/json_default")
            assert resp.headers["content-type"] == "application/json"
            assert resp.json() == {"k": "v"}

        # Plain text
        t_text = CassetteTransport(
            [
                {
                    "request": {"method": "GET", "path": "/text"},
                    "response": {"text": "plain text response"},
                }
            ]
        )
        async with httpx.AsyncClient(transport=t_text, base_url=TEST_BASE_URL) as client:
            resp = await client.get("/text")
            assert resp.text == "plain text response"

    def test_init_from_file_path(self, tmp_path: Path) -> None:
        """Instantiate CassetteTransport from Path and string paths."""
        path = FIXTURES_DIR / "ollama_fim_stream_ok.yaml"
        t1 = CassetteTransport(path)
        assert t1.exchange_count >= 1

        t2 = CassetteTransport(str(path))
        assert t2.exchange_count >= 1

        # YAML file containing a list of exchanges directly
        list_yaml = tmp_path / "list_exchanges.yaml"
        list_yaml.write_text("- request:\n    method: GET\n    path: /list\n  response: {}\n")
        t3 = CassetteTransport(list_yaml)
        assert t3.exchange_count == 1

    def test_init_from_single_dict(self) -> None:
        """Instantiate CassetteTransport from single exchange dictionary."""
        t = CassetteTransport({"request": {"method": "GET", "path": "/"}, "response": {}})
        assert t.exchange_count == 1
