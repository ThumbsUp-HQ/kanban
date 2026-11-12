# Copyright 2026 Kanban Platform Contributors
"""Unit tests for deterministic AI cassettes, FixtureLLMProvider, and FixtureCLIRunner."""

from __future__ import annotations

import asyncio
import json
import math
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel, Field

import agent.testing.fixtures as fixtures_mod
from agent.providers.base import (
    CLIRunner,
    CLIRunRequest,
    CompletionRequest,
    EmbedBatchRequest,
    LLMProvider,
    StructuredRequest,
)
from agent.providers.errors import (
    ProviderHTTPError,
    ProviderProtocolError,
    ProviderRefusal,
    ProviderSafetyBlock,
    ProviderSchemaError,
    ProviderTimeout,
    ProviderUnavailable,
)
from agent.testing.fixtures import (
    Cassette,
    CassetteMismatchError,
    CassetteValidationError,
    FixtureCLIRunner,
    FixtureLLMProvider,
    load_cassette,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

FIXTURES_DIR = Path(__file__).parents[3] / "tests" / "fixtures" / "ai"


class TransitionVerdict(BaseModel):
    """Pydantic model representing S15.2 transition verdict."""

    schema_: str = Field(alias="schema")
    decision: str
    reason_markdown: str
    field_updates: dict[str, Any]
    add_labels: list[str]


def test_fixture_llm_stream_replay() -> None:
    """Test streaming completion replay from echo_stream_ok.yaml."""

    async def _test() -> None:
        cassette_path = FIXTURES_DIR / "echo_stream_ok.yaml"
        provider = FixtureLLMProvider(cassette_path)

        assert provider.residency_tier == "fixture"
        assert isinstance(provider, LLMProvider)

        req = CompletionRequest(
            model="echo-model",
            prompt="Please hello and stream output",
        )

        chunks: list[str] = []
        first_chunk_ttft: float | None = None
        last_finish_reason: str | None = None
        last_prompt_tokens: int | None = None
        last_completion_tokens: int | None = None

        async for chunk in provider.stream_complete(req):
            if chunk.index == 0:
                first_chunk_ttft = chunk.ttft_ms
            if chunk.finish_reason is not None:
                last_finish_reason = chunk.finish_reason
                last_prompt_tokens = chunk.prompt_tokens
                last_completion_tokens = chunk.completion_tokens
            chunks.append(chunk.delta)

        assert "".join(chunks) == "Hello world!"
        assert first_chunk_ttft == 5.0
        assert last_finish_reason == "stop"
        assert last_prompt_tokens == 10
        assert last_completion_tokens == 5
        assert len(provider.call_log) == 1
        assert provider.call_log[0]["method"] == "stream_complete"

    asyncio.run(_test())


def test_fixture_llm_generate_structured() -> None:
    """Test structured verdict generation and tool trace from transition_rls_veto.yaml."""

    async def _test() -> None:
        cassette_path = FIXTURES_DIR / "transition_rls_veto.yaml"
        provider = FixtureLLMProvider(cassette_path)

        req = StructuredRequest(
            model="any-model",
            prompt="Audit KAN-142 for auth_provider_cards changes",
            response_model=TransitionVerdict,
            metadata={"agent_slug": "forensic-code-check", "transition_to": "Done"},
        )

        resp = await provider.generate_structured(req)

        assert resp.parsed.decision == "reject"
        assert "Missing `FORCE ROW LEVEL SECURITY`" in resp.parsed.reason_markdown
        assert resp.parsed.add_labels == ["qa-needs-work"]
        assert resp.ttft_ms == 18.0
        assert len(resp.tool_trace) == 2
        assert resp.tool_trace[0].tool == "read_ticket"
        assert resp.tool_trace[0].args == {"identifier": "KAN-100"}
        assert resp.tool_trace[1].tool == "repo_grep"
        assert resp.tool_trace[1].args == {
            "pattern": "FORCE ROW LEVEL SECURITY",
            "path": "database/",
        }

    asyncio.run(_test())


def test_fixture_llm_embed_batch_deterministic() -> None:
    """Test deterministic L2-normalized vector embedding generation."""

    async def _test() -> None:
        cassette_yaml = """
cassette_version: 1
matcher:
  model: embed-dim16
embeddings:
  dimension: 16
  seed: 42
"""
        cas = load_cassette_from_str(cassette_yaml)
        provider = FixtureLLMProvider(cas)

        req = EmbedBatchRequest(model="embed-dim16", inputs=("Alpha sentence", "Beta sentence"))
        vecs1 = await provider.embed_batch(req)
        vecs2 = await provider.embed_batch(req)

        # Identical across calls with same seed
        assert vecs1 == vecs2
        assert len(vecs1) == 2
        assert len(vecs1[0]) == 16
        assert len(vecs1[1]) == 16

        # Verify L2 normalization: norm == 1.0
        for vec in vecs1:
            norm = math.sqrt(sum(x * x for x in vec))
            assert math.isclose(norm, 1.0, rel_tol=1e-5)

    asyncio.run(_test())


def test_fixture_llm_embed_batch_static() -> None:
    """Test embedding batch with pre-configured static vectors."""

    async def _test() -> None:
        cassette_yaml = """
cassette_version: 1
matcher:
  model: embed-static
embeddings:
  - [0.1, 0.2, 0.3]
"""
        cas = load_cassette_from_str(cassette_yaml)
        provider = FixtureLLMProvider(cas)

        req = EmbedBatchRequest(model="embed-static", inputs=("Single input",))
        vecs = await provider.embed_batch(req)
        assert vecs == [[0.1, 0.2, 0.3]]

    asyncio.run(_test())


def test_fixture_cli_runner_positive() -> None:
    """Test FixtureCLIRunner replaying cli_agy_approve_ok.yaml."""

    async def _test() -> None:
        cassette_path = FIXTURES_DIR / "cli_agy_approve_ok.yaml"
        runner = FixtureCLIRunner(cassette_path)

        assert isinstance(runner, CLIRunner)

        req = CLIRunRequest(
            argv=("/usr/local/bin/agy", "-p"),
            stdin_bytes=b"review_request: ticket_id: KAN-142\n",
        )

        result = await runner.run(req)

        assert result.exit_code == 0
        assert result.duration_ms == 12.5
        parsed = json.loads(result.stdout.decode("utf-8"))
        assert parsed["verdict"] == "approved"
        assert len(runner.call_log) == 1

    asyncio.run(_test())


def test_fault_429_injection() -> None:
    """Test HTTP 429 fault injection with retry-after header."""

    async def _test() -> None:
        cassette_path = FIXTURES_DIR / "fault_429.yaml"
        provider = FixtureLLMProvider(cassette_path)

        req = CompletionRequest(
            model="test-429-model",
            prompt="Please simulate_429 now",
        )

        async def _consume() -> None:
            async for _ in provider.stream_complete(req):
                pass

        with pytest.raises(ProviderHTTPError) as exc_info:
            await _consume()

        assert exc_info.value.status == 429
        assert exc_info.value.retry_after_s == 30.0
        assert exc_info.value.code == "HTTP_ERROR"

    asyncio.run(_test())


def test_fault_malformed_stdout() -> None:
    """Test malformed stdout bytes from fault_malformed_stdout.yaml."""

    async def _test() -> None:
        cassette_path = FIXTURES_DIR / "fault_malformed_stdout.yaml"
        runner = FixtureCLIRunner(cassette_path)

        req = CLIRunRequest(
            argv=("/usr/local/bin/codex", "-p"),
            stdin_bytes=b"simulate_malformed task",
        )

        result = await runner.run(req)
        assert result.exit_code == 0
        # Output is unparseable non-JSON bytes
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.stdout.decode("utf-8", errors="replace"))

    asyncio.run(_test())


def test_miscellaneous_fault_injections() -> None:
    """Test http_500, http_503, timeout, ttft_sla_breach, safety_block, refusal, schema_error."""

    async def _test() -> None:
        fault_kinds = [
            ("http_500", ProviderHTTPError),
            ("http_503", ProviderHTTPError),
            ("timeout", ProviderTimeout),
            ("ttft_sla_breach", ProviderTimeout),
            ("unavailable", ProviderUnavailable),
            ("safety_block", ProviderSafetyBlock),
            ("refusal", ProviderRefusal),
            ("schema_error", ProviderSchemaError),
        ]

        for kind, expected_exc in fault_kinds:
            raw_yaml = f"""
cassette_version: 1
matcher:
  model: fault-model-{kind}
fault:
  kind: {kind}
"""
            cas = load_cassette_from_str(raw_yaml)
            provider = FixtureLLMProvider(cas)
            req = CompletionRequest(model=f"fault-model-{kind}", prompt="test prompt")

            async def _consume(stream: AsyncIterator[Any]) -> None:
                async for _ in stream:
                    pass

            with pytest.raises(expected_exc):
                await _consume(provider.stream_complete(req))

    asyncio.run(_test())


def test_stream_error_after_chunk() -> None:
    """Test stream_error_after_chunk emits initial chunks before raising ProviderProtocolError."""

    async def _test() -> None:
        raw_yaml = """
cassette_version: 1
matcher:
  model: stream-fault-model
stream_chunks:
  - "Chunk1"
  - "Chunk2"
  - "Chunk3"
fault:
  kind: stream_error_after_chunk
  after_chunks: 1
"""
        cas = load_cassette_from_str(raw_yaml)
        provider = FixtureLLMProvider(cas)
        req = CompletionRequest(model="stream-fault-model", prompt="stream test")

        chunks_seen: list[str] = []

        async def _consume() -> None:
            async for chunk in provider.stream_complete(req):
                chunks_seen.append(chunk.delta)  # noqa: PERF401  # Incremental append before stream error

        with pytest.raises(ProviderProtocolError):
            await _consume()

        assert chunks_seen == ["Chunk1"]

    asyncio.run(_test())


def test_ttft_deadline_breach() -> None:
    """Test simulated TTFT breaching request ttft_deadline_ms raises ProviderTimeout."""

    async def _test() -> None:
        raw_yaml = """
cassette_version: 1
matcher:
  model: slow-model
simulated_ttft_ms: 100.0
stream_chunks: ["slow"]
"""
        cas = load_cassette_from_str(raw_yaml)
        provider = FixtureLLMProvider(cas)
        req = CompletionRequest(
            model="slow-model",
            prompt="run slow",
            ttft_deadline_ms=50,  # 100 > 50 -> SLA breach
        )

        async def _consume() -> None:
            async for _ in provider.stream_complete(req):
                pass

        with pytest.raises(ProviderTimeout, match="TTFT SLA breached"):
            await _consume()

    asyncio.run(_test())


def test_cli_runner_timeout_fault() -> None:
    """Test CLI runner fault timeout."""

    async def _test() -> None:
        raw_yaml = """
cassette_version: 1
matcher:
  argv_prefix: ["slow-cli"]
simulated_ttft_ms: 50.0
fault:
  kind: timeout
"""
        cas = load_cassette_from_str(raw_yaml)
        runner = FixtureCLIRunner(cas)
        req = CLIRunRequest(argv=("slow-cli", "arg"), stdin_bytes=b"")

        with pytest.raises(ProviderTimeout, match="Simulated CLI execution timeout"):
            await runner.run(req)

    asyncio.run(_test())


def test_cassette_security_and_validation(tmp_path: Path) -> None:
    """Test YAML safe_load attack resistance, file size checks, and schema validation."""
    # 1. Reject unsafe YAML tags
    unsafe_yaml = tmp_path / "unsafe.yaml"
    unsafe_yaml.write_text(
        "!!python/object/apply:os.system ['echo pwned']\n",
        encoding="utf-8",
    )
    with pytest.raises(CassetteValidationError, match="YAML safe_load failed"):
        load_cassette(unsafe_yaml)

    # 2. Reject files > 1 MiB
    large_yaml = tmp_path / "too_large.yaml"
    large_yaml.write_bytes(b"cassette_version: 1\n" + b" " * (1_048_576 + 1))
    with pytest.raises(CassetteValidationError, match="exceeds maximum allowed size"):
        load_cassette(large_yaml)

    # 3. Reject invalid UTF-8
    bad_utf8 = tmp_path / "bad_utf8.yaml"
    bad_utf8.write_bytes(b"\xff\xfe\x00\x00")
    with pytest.raises(CassetteValidationError, match="not valid UTF-8"):
        load_cassette(bad_utf8)

    # 4. Reject unknown version
    bad_ver = tmp_path / "bad_ver.yaml"
    bad_ver.write_text(
        "cassette_version: 2\nmatcher:\n  model: test\n",
        encoding="utf-8",
    )
    with pytest.raises(CassetteValidationError, match="schema validation failed"):
        load_cassette(bad_ver)

    # 5. Reject unknown fields (additionalProperties: false)
    unknown_field = tmp_path / "unknown_field.yaml"
    unknown_field.write_text(
        "cassette_version: 1\nmatcher:\n  model: test\nunexpected_extra: 123\n",
        encoding="utf-8",
    )
    with pytest.raises(CassetteValidationError, match="schema validation failed"):
        load_cassette(unknown_field)

    # 6. Reject non-dict top level
    list_yaml = tmp_path / "list.yaml"
    list_yaml.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(CassetteValidationError, match="must be a YAML mapping"):
        load_cassette(list_yaml)


def test_cassette_mismatch_errors() -> None:
    """Test CassetteMismatchError when request doesn't match loaded predicates."""

    async def _test() -> None:
        raw_yaml = """
cassette_version: 1
matcher:
  model: expected-model
  prompt_contains: ["required_phrase"]
stream_chunks: ["matched"]
"""
        cas = load_cassette_from_str(raw_yaml)
        provider = FixtureLLMProvider(cas)

        # Unmatched prompt
        async def _consume_bad_prompt() -> None:
            req = CompletionRequest(model="expected-model", prompt="different phrase")
            async for _ in provider.stream_complete(req):
                pass

        with pytest.raises(CassetteMismatchError, match="No cassette matched LLM request"):
            await _consume_bad_prompt()

        # Unmatched model
        async def _consume_bad_model() -> None:
            req = CompletionRequest(model="other-model", prompt="required_phrase")
            async for _ in provider.stream_complete(req):
                pass

        with pytest.raises(CassetteMismatchError, match="No cassette matched LLM request"):
            await _consume_bad_model()

        # Unmatched CLI
        cli_yaml = """
cassette_version: 1
matcher:
  argv_prefix: ["target-bin"]
  stdin_contains: ["magic_token"]
cli_result:
  stdout: "ok"
  stderr: ""
  exit_code: 0
  duration_ms: 1.0
"""
        cli_cas = load_cassette_from_str(cli_yaml)
        runner = FixtureCLIRunner(cli_cas)

        with pytest.raises(CassetteMismatchError, match="No cassette matched CLI request"):
            await runner.run(CLIRunRequest(argv=("wrong-bin",), stdin_bytes=b"magic_token"))

        with pytest.raises(CassetteMismatchError, match="No cassette matched CLI request"):
            await runner.run(CLIRunRequest(argv=("target-bin",), stdin_bytes=b"other_token"))

    asyncio.run(_test())


def test_fixture_llm_structured_output_and_schema_error() -> None:
    """Test structured_output branch, schema validation failure, and missing output."""

    async def _test() -> None:
        # 1. structured_output branch
        yaml_structured = """
cassette_version: 1
matcher:
  model: model-struct
structured_output:
  schema: kb/v1
  decision: approve
  reason_markdown: "Looks great"
  field_updates: {}
  add_labels: ["qa-pass"]
"""
        cas1 = load_cassette_from_str(yaml_structured)
        prov1 = FixtureLLMProvider(cas1)
        resp1 = await prov1.generate_structured(
            StructuredRequest(model="model-struct", prompt="p", response_model=TransitionVerdict)
        )
        assert resp1.parsed.decision == "approve"

        # 2. Schema validation error
        yaml_invalid = """
cassette_version: 1
matcher:
  model: model-invalid
structured_output:
  unexpected: 123
"""
        cas2 = load_cassette_from_str(yaml_invalid)
        prov2 = FixtureLLMProvider(cas2)
        with pytest.raises(ProviderSchemaError, match="Failed to validate response"):
            await prov2.generate_structured(
                StructuredRequest(
                    model="model-invalid",
                    prompt="p",
                    response_model=TransitionVerdict,
                )
            )

        # 3. Neither final_verdict nor structured_output
        yaml_no_output = """
cassette_version: 1
matcher:
  model: model-no-out
simulated_ttft_ms: 1.0
"""
        cas3 = load_cassette_from_str(yaml_no_output)
        prov3 = FixtureLLMProvider(cas3)
        with pytest.raises(
            ProviderSchemaError,
            match="has neither final_verdict nor structured_output",
        ):
            await prov3.generate_structured(
                StructuredRequest(
                    model="model-no-out",
                    prompt="p",
                    response_model=TransitionVerdict,
                )
            )

        # 4. embed_batch with no embeddings
        with pytest.raises(ProviderSchemaError, match="has no embeddings configured"):
            await prov3.embed_batch(EmbedBatchRequest(model="model-no-out", inputs=("hi",)))

    asyncio.run(_test())


def test_fixture_sleep_hook_and_predicates() -> None:
    """Test sleep hook invocation and provider/transition_to matching."""

    async def _test() -> None:
        sleep_called: list[float] = []

        async def fake_sleep(duration: float) -> None:
            sleep_called.append(duration)

        yaml_predicates = """
cassette_version: 1
matcher:
  provider: custom-provider
  transition_to: Done
  model: predicate-model
simulated_ttft_ms: 20.0
stream_chunks: ["done"]
"""
        cas = load_cassette_from_str(yaml_predicates)
        prov = FixtureLLMProvider(cas, sleep_fn=fake_sleep)

        # Matching provider and transition_to
        req_ok = CompletionRequest(
            model="predicate-model",
            prompt="go",
            metadata={"provider": "custom-provider", "transition_to": "Done"},
        )
        async for chunk in prov.stream_complete(req_ok):
            assert chunk.delta == "done"
        assert len(sleep_called) == 1
        assert sleep_called[0] == 0.02

        # Mismatch provider
        req_bad_prov = CompletionRequest(
            model="predicate-model",
            prompt="go",
            metadata={"provider": "wrong-provider", "transition_to": "Done"},
        )
        with pytest.raises(CassetteMismatchError):
            async for _ in prov.stream_complete(req_bad_prov):
                pass

        # Mismatch transition_to
        req_bad_trans = CompletionRequest(
            model="predicate-model",
            prompt="go",
            metadata={"provider": "custom-provider", "transition_to": "Backlog"},
        )
        with pytest.raises(CassetteMismatchError):
            async for _ in prov.stream_complete(req_bad_trans):
                pass

    asyncio.run(_test())


def test_cli_runner_edge_cases() -> None:
    """Test CLI runner short argv, missing result/fault, and string paths."""

    async def _test() -> None:
        yaml_cli = """
cassette_version: 1
matcher:
  argv_prefix: ["tool", "subcmd", "extra"]
cli_result:
  stdout: "ok"
  stderr: ""
  exit_code: 0
  duration_ms: 1.0
"""
        cas = load_cassette_from_str(yaml_cli)
        runner = FixtureCLIRunner([cas])

        # Short argv < prefix length
        with pytest.raises(CassetteMismatchError):
            await runner.run(CLIRunRequest(argv=("tool",), stdin_bytes=b""))

        # Cassette without cli_result or fault
        yaml_no_cli = """
cassette_version: 1
matcher:
  argv_prefix: ["noop"]
"""
        cas_no_cli = load_cassette_from_str(yaml_no_cli)
        runner_empty = FixtureCLIRunner(cas_no_cli)
        with pytest.raises(CassetteMismatchError, match="neither cli_result nor supported fault"):
            await runner_empty.run(CLIRunRequest(argv=("noop",), stdin_bytes=b""))

    asyncio.run(_test())


def test_cassette_loader_file_errors(tmp_path: Path) -> None:
    """Test load_cassette with missing file."""
    with pytest.raises(CassetteValidationError, match="Cannot read cassette file"):
        load_cassette(tmp_path / "non_existent.yaml")


def test_schema_load_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test schema loading failure."""
    monkeypatch.setattr(fixtures_mod, "_COMPILED_SCHEMA", None)
    monkeypatch.setattr(fixtures_mod, "_SCHEMA_PATH", tmp_path / "non_existent_schema.json")
    with pytest.raises(CassetteValidationError, match="Failed to read cassette schema"):
        fixtures_mod._get_schema()  # noqa: SLF001  # Verifying schema loader failure branch


def test_cassette_model_construction_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test cassette model validation exception handling."""
    test_yaml = tmp_path / "valid.yaml"
    test_yaml.write_text("cassette_version: 1\nmatcher: {}\n", encoding="utf-8")

    def _fail_validate(_: object) -> object:
        msg = "Forced validation failure"
        raise ValueError(msg)

    monkeypatch.setattr(fixtures_mod.Cassette, "model_validate", _fail_validate)
    with pytest.raises(CassetteValidationError, match="Cassette model construction failed"):
        fixtures_mod.load_cassette(test_yaml)


def test_health_probe() -> None:
    """Test FixtureLLMProvider health probe."""

    async def _test() -> None:
        provider = FixtureLLMProvider([])
        status = await provider.health_probe()
        assert status.ok is True
        assert status.latency_ms > 0.0
        assert "fixture-model" in status.models

    asyncio.run(_test())


def load_cassette_from_str(yaml_str: str) -> Cassette:
    """Load a cassette from a raw YAML string."""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
        tf.write(yaml_str)
        tpath = Path(tf.name)
    try:
        return load_cassette(tpath)
    finally:
        tpath.unlink(missing_ok=True)
