# Copyright 2026 Kanban Platform Contributors
"""Demo command validate-echo testing CLI report rendering against LLM providers."""

from __future__ import annotations

import ipaddress
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, HttpUrl, SecretStr

from agent.cli_report import (
    ContextScrubber,
    ExitCode,
    ReportMetrics,
    SchemaStatus,
    ValidationReport,
    default_context_scrubber,
    map_exception_to_exit_code,
)
from agent.providers.base import (
    CompletionRequest,
    LLMProvider,
    StructuredRequest,
)
from agent.providers.gemini import GeminiSettings
from agent.providers.ollama import OllamaSettings
from agent.providers.openai_provider import OpenAISettings
from agent.providers.registry import build_provider
from agent.testing.fixtures import (
    FixtureLLMProvider,
    load_cassette,
)
from agent.testing.http_cassette import CassetteTransport

if TYPE_CHECKING:
    import argparse

    import httpx

__all__ = [
    "EchoVerdict",
    "configure_validate_echo_parser",
    "handle_validate_echo",
]

_DEFAULT_CASSETTE: Path = Path("tests/fixtures/ai/echo_stream_ok.yaml")


class EchoVerdict(BaseModel):
    """Output schema for structured echo responses."""

    model_config = ConfigDict(extra="allow")

    echo: str = ""
    ok: bool = True


def configure_validate_echo_parser(parser: argparse.ArgumentParser) -> None:
    """Configure arguments and flags for validate-echo subcommand."""
    from agent.cli import add_common_agent_flags  # noqa: PLC0415  # Prevent circular import with agent.cli

    add_common_agent_flags(parser)
    parser.add_argument(
        "--prompt",
        type=str,
        default="Hello Sparkle",
        help="Input prompt text for completion or structured evaluation.",
    )
    parser.add_argument(
        "--mode",
        choices=("stream", "structured"),
        default="stream",
        help="Execution mode: token streaming or structured JSON output.",
    )
    parser.add_argument(
        "--ttft-deadline-ms",
        type=int,
        default=None,
        help="TTFT SLA deadline in milliseconds (1..60000).",
    )


def _resolve_ollama_provider(
    args: argparse.Namespace,
    prompt: str,
    model: str,
    metadata: dict[str, str],
) -> tuple[LLMProvider, str, str, dict[str, str]]:
    base_url_str = getattr(args, "base_url", None) or "http://127.0.0.1:11434"
    transport: httpx.AsyncBaseTransport | None = None
    http_cassette = getattr(args, "http_cassette", None)
    if http_cassette:
        transport = CassetteTransport(Path(http_cassette))

    allowed_cidrs = (
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("::1/128"),
    )
    settings = OllamaSettings(
        base_url=HttpUrl(base_url_str),
        allowed_ollama_cidrs=allowed_cidrs,
        model_allowlist=(args.model, "qwen2.5-coder:7b", "llama3.3", "fixture-echo-v1"),
    )
    provider = build_provider("ollama", settings, transport=transport)
    return provider, prompt, model, metadata


def _resolve_fixture_provider(
    args: argparse.Namespace,
    prompt: str,
    model: str,
    metadata: dict[str, str],
) -> tuple[LLMProvider, str, str, dict[str, str]]:
    cassette_path: Path | None = None
    if getattr(args, "cassette", None):
        cassette_path = Path(args.cassette)
    elif args.provider == "fixture":
        cassette_path = _DEFAULT_CASSETTE

    if cassette_path is not None and not cassette_path.exists():
        msg = f"Cassette file not found: {cassette_path}"
        raise FileNotFoundError(msg)

    if cassette_path is None:
        msg = "Non-fixture providers are not implemented in Phase 0."
        raise ValueError(msg)

    cas = load_cassette(cassette_path)
    provider = FixtureLLMProvider(cas)
    if args.prompt == "Hello Sparkle" and cas.matcher.prompt_contains:
        prompt = " ".join(cas.matcher.prompt_contains)
    if args.model == "fixture-echo-v1" and cas.matcher.model:
        model = cas.matcher.model
    if cas.matcher.agent_slug:
        metadata["agent_slug"] = cas.matcher.agent_slug
    if cas.matcher.transition_to:
        metadata["transition_to"] = cas.matcher.transition_to
    if cas.matcher.provider:
        metadata["provider"] = cas.matcher.provider

    return provider, prompt, model, metadata


def _resolve_gemini_provider(
    args: argparse.Namespace,
    prompt: str,
    model: str,
    metadata: dict[str, str],
) -> tuple[LLMProvider, str, str, dict[str, str]]:
    transport: httpx.AsyncBaseTransport | None = None
    http_cassette = getattr(args, "http_cassette", None)
    if http_cassette:
        transport = CassetteTransport(Path(http_cassette))

    api_key_str = getattr(args, "api_key", None) or "fake-gemini-key-for-test"
    settings = GeminiSettings(
        mode="ai_studio_paid",
        api_key=SecretStr(api_key_str),
        model_allowlist=(args.model, "gemini-2.5-flash", "gemini-2.5-pro", "text-embedding-004"),
    )
    provider = build_provider("gemini", settings, transport=transport)
    return provider, prompt, model, metadata


def _resolve_openai_provider(
    args: argparse.Namespace,
    prompt: str,
    model: str,
    metadata: dict[str, str],
) -> tuple[LLMProvider, str, str, dict[str, str]]:
    base_url_str = getattr(args, "base_url", None)
    base_url = HttpUrl(base_url_str) if base_url_str else None
    transport: httpx.AsyncBaseTransport | None = None
    http_cassette = getattr(args, "http_cassette", None)
    if http_cassette:
        transport = CassetteTransport(Path(http_cassette))

    api_key_str = os.environ.get("OPENAI_API_KEY", "sk-placeholder-test-key-00000000000000000000")
    settings = OpenAISettings(
        api_key=SecretStr(api_key_str),
        base_url=base_url,
        model_allowlist=(args.model, "gpt-4o-mini", "gpt-4.1", "o3-mini", "text-embedding-3-small"),
    )
    provider = build_provider("openai", settings, transport=transport)
    return provider, prompt, model, metadata


def _resolve_provider_and_params(
    args: argparse.Namespace,
) -> tuple[LLMProvider, str, str, dict[str, str]]:
    prompt = str(args.prompt)
    model = str(args.model)
    metadata: dict[str, str] = {}

    if args.provider == "ollama":
        return _resolve_ollama_provider(args, prompt, model, metadata)
    if args.provider == "openai":
        return _resolve_openai_provider(args, prompt, model, metadata)

    if args.provider == "gemini":
        return _resolve_gemini_provider(args, prompt, model, metadata)

    return _resolve_fixture_provider(args, prompt, model, metadata)


async def _stream_echo(
    provider: LLMProvider,
    req: CompletionRequest,
    rendered_context: str,
    t0: float,
) -> tuple[ValidationReport, ExitCode]:
    ttft_ms: float | None = None
    prompt_tokens = 0
    completion_tokens = 0
    try:
        async for chunk in provider.stream_complete(req):
            if chunk.index == 0:
                ttft_ms = chunk.ttft_ms
            if chunk.prompt_tokens is not None:
                prompt_tokens = chunk.prompt_tokens
            if chunk.completion_tokens is not None:
                completion_tokens = chunk.completion_tokens
    except Exception as err:  # noqa: BLE001  # Map provider exception to Section 4 details
        total_ms = (time.perf_counter() - t0) * 1000.0
        code = map_exception_to_exit_code(err)
        report = ValidationReport(
            command="validate-echo",
            rendered_context=rendered_context,
            tool_trace=(),
            metrics=ReportMetrics(
                ttft_ms=ttft_ms,
                total_latency_ms=total_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code=getattr(err, "code", type(err).__name__),
                detail=str(err),
            ),
        )
        return report, code

    total_ms = (time.perf_counter() - t0) * 1000.0
    report = ValidationReport(
        command="validate-echo",
        rendered_context=rendered_context,
        tool_trace=(),
        metrics=ReportMetrics(
            ttft_ms=ttft_ms,
            total_latency_ms=total_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
        schema_status=SchemaStatus(valid=True, status="ok"),
    )
    return report, ExitCode.OK


async def _structured_echo(
    provider: LLMProvider,
    req_struct: StructuredRequest[EchoVerdict],
    rendered_context: str,
    t0: float,
) -> tuple[ValidationReport, ExitCode]:
    try:
        resp = await provider.generate_structured(req_struct)
    except Exception as err:  # noqa: BLE001  # Map provider exception to Section 4 details
        total_ms = (time.perf_counter() - t0) * 1000.0
        code = map_exception_to_exit_code(err)
        report = ValidationReport(
            command="validate-echo",
            rendered_context=rendered_context,
            tool_trace=(),
            metrics=ReportMetrics(
                ttft_ms=None,
                total_latency_ms=total_ms,
            ),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code=getattr(err, "code", type(err).__name__),
                detail=str(err),
            ),
        )
        return report, code

    total_ms = (time.perf_counter() - t0) * 1000.0
    report = ValidationReport(
        command="validate-echo",
        rendered_context=rendered_context,
        tool_trace=resp.tool_trace,
        metrics=ReportMetrics(
            ttft_ms=resp.ttft_ms,
            total_latency_ms=total_ms,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
        ),
        schema_status=SchemaStatus(valid=True, status="ok"),
    )
    return report, ExitCode.OK


async def handle_validate_echo(
    args: argparse.Namespace,
    *,
    scrubber: ContextScrubber = default_context_scrubber,
) -> tuple[ValidationReport, ExitCode]:
    """Execute validate-echo against configured provider or fixture."""
    try:
        provider, prompt, model, metadata = _resolve_provider_and_params(args)
    except FileNotFoundError as err:
        rendered_context = scrubber(str(args.prompt))
        report = ValidationReport(
            command="validate-echo",
            rendered_context=rendered_context,
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=0.0),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code="FILE_NOT_FOUND",
                detail=str(err),
            ),
        )
        return report, ExitCode.RUNTIME_ERROR
    except Exception as err:  # noqa: BLE001  # Catch setup errors to format Section 4
        rendered_context = scrubber(str(args.prompt))
        code = map_exception_to_exit_code(err)
        report = ValidationReport(
            command="validate-echo",
            rendered_context=rendered_context,
            tool_trace=(),
            metrics=ReportMetrics(total_latency_ms=0.0),
            schema_status=SchemaStatus(
                valid=False,
                status="failed",
                error_code=getattr(err, "code", type(err).__name__),
                detail=str(err),
            ),
        )
        return report, code

    rendered_context = scrubber(prompt)
    t0 = time.perf_counter()

    if args.mode == "stream":
        req = CompletionRequest(
            model=model,
            prompt=prompt,
            metadata=metadata,
            ttft_deadline_ms=args.ttft_deadline_ms,
        )
        return await _stream_echo(provider, req, rendered_context, t0)

    req_struct = StructuredRequest(
        model=model,
        prompt=prompt,
        metadata=metadata,
        response_model=EchoVerdict,
        ttft_deadline_ms=args.ttft_deadline_ms,
    )
    return await _structured_echo(provider, req_struct, rendered_context, t0)
