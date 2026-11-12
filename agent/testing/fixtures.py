# Copyright 2026 Kanban Platform Contributors
"""Deterministic YAML cassette loader, FixtureLLMProvider, and FixtureCLIRunner."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
)

import jsonschema
import yaml
from pydantic import BaseModel, ConfigDict, Field

from agent.providers.base import (
    CLIRunRequest,
    CLIRunResult,
    CompletionRequest,
    EmbedBatchRequest,
    HealthStatus,
    StreamChunk,
    StructuredRequest,
    StructuredResponse,
    ToolCallStep,
)
from agent.providers.errors import (
    ProviderError,
    ProviderHTTPError,
    ProviderProtocolError,
    ProviderRefusal,
    ProviderSafetyBlock,
    ProviderSchemaError,
    ProviderTimeout,
    ProviderUnavailable,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

__all__ = [
    "MAX_CASSETTE_BYTES",
    "Cassette",
    "CassetteCLIResult",
    "CassetteEmbeddingsGen",
    "CassetteError",
    "CassetteFault",
    "CassetteMatcher",
    "CassetteMismatchError",
    "CassetteToolCall",
    "CassetteUsage",
    "CassetteValidationError",
    "FixtureCLIRunner",
    "FixtureLLMProvider",
    "load_cassette",
]

TModel = TypeVar("TModel", bound=BaseModel)

MAX_CASSETTE_BYTES: int = 1_048_576  # 1 MiB

_SCHEMA_PATH: Path = Path(__file__).parent / "cassette.schema.json"


class CassetteError(ProviderError):
    """Base error for cassette loading, schema validation, and replay."""

    def __init__(self, message: str, code: str = "CASSETTE_ERROR") -> None:
        """Initialize cassette error."""
        super().__init__(message, code=code)


class CassetteValidationError(CassetteError):
    """Raised when a cassette fails file size, YAML parsing, or schema validation."""

    def __init__(self, message: str, code: str = "CASSETTE_VALIDATION_ERROR") -> None:
        """Initialize cassette validation error."""
        super().__init__(message, code=code)


class CassetteMismatchError(CassetteError):
    """Raised when an incoming provider or CLI request matches no loaded cassette."""

    def __init__(self, message: str, code: str = "CASSETTE_MISMATCH_ERROR") -> None:
        """Initialize cassette mismatch error."""
        super().__init__(message, code=code)


class CassetteMatcher(BaseModel):
    """Matcher predicates for routing requests to cassettes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_slug: str | None = None
    provider: str | None = None
    model: str | None = None
    transition_to: str | None = None
    prompt_contains: list[str] = Field(default_factory=list)
    stdin_contains: list[str] = Field(default_factory=list)
    argv_prefix: list[str] = Field(default_factory=list)


class CassetteToolInvocation(BaseModel):
    """Single tool call specification inside tool_script."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool: str
    args: dict[str, Any]


class CassetteToolCall(BaseModel):
    """Tool call step with invocation args and optional mocked return."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    call: CassetteToolInvocation
    returns: Any = None


class CassetteUsage(BaseModel):
    """Simulated token usage counts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)


class CassetteEmbeddingsGen(BaseModel):
    """Deterministic embedding vector generator configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: int = Field(ge=1)
    seed: int


class CassetteCLIResult(BaseModel):
    """Simulated CLI runner process output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float = Field(ge=0.0)


class CassetteFault(BaseModel):
    """Fault injection specification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    retry_after_s: float | None = Field(default=None, ge=0.0)
    after_chunks: int | None = Field(default=None, ge=0)


class Cassette(BaseModel):
    """Validated cassette holding deterministic responses and fault rules."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cassette_version: int = Field(default=1)
    matcher: CassetteMatcher
    tool_script: list[CassetteToolCall] | None = None
    simulated_ttft_ms: float = Field(default=5.0, ge=0.0)
    usage: CassetteUsage | None = None
    stream_chunks: list[str] | None = None
    final_verdict: dict[str, Any] | None = None
    structured_output: dict[str, Any] | None = None
    embeddings: list[list[float]] | CassetteEmbeddingsGen | None = None
    cli_result: CassetteCLIResult | None = None
    fault: CassetteFault | None = None


_COMPILED_SCHEMA: dict[str, Any] | None = None


def _get_schema() -> dict[str, Any]:
    global _COMPILED_SCHEMA  # noqa: PLW0603  # Cached compiled schema singleton
    if _COMPILED_SCHEMA is None:
        try:
            content = _SCHEMA_PATH.read_text(encoding="utf-8")
            _COMPILED_SCHEMA = json.loads(content)
        except OSError as err:
            msg = f"Failed to read cassette schema from {_SCHEMA_PATH}: {err}"
            raise CassetteValidationError(msg) from err
        except json.JSONDecodeError as err:
            msg = f"Failed to parse cassette schema JSON: {err}"
            raise CassetteValidationError(msg) from err
    return _COMPILED_SCHEMA


def load_cassette(path: Path | str) -> Cassette:
    """Load, size-check, parse, and validate an AI fixture cassette from YAML."""
    p = Path(path)
    try:
        raw_bytes = p.read_bytes()
    except OSError as err:
        msg = f"Cannot read cassette file '{p}': {err}"
        raise CassetteValidationError(msg) from err

    if len(raw_bytes) > MAX_CASSETTE_BYTES:
        msg = (
            f"Cassette file '{p}' size ({len(raw_bytes)} bytes) exceeds maximum "
            f"allowed size ({MAX_CASSETTE_BYTES} bytes)"
        )
        raise CassetteValidationError(msg)

    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as err:
        msg = f"Cassette file '{p}' is not valid UTF-8: {err}"
        raise CassetteValidationError(msg) from err

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as err:
        msg = f"YAML safe_load failed for '{p}': {err}"
        raise CassetteValidationError(msg) from err

    if not isinstance(data, dict):
        msg = f"Cassette root in '{p}' must be a YAML mapping (got {type(data).__name__})"
        raise CassetteValidationError(msg)

    schema = _get_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: str(e.path))
    if errors:
        details = "; ".join(
            f"{'/'.join(str(elem) for elem in err.path) or 'root'}: {err.message}" for err in errors
        )
        msg = f"Cassette schema validation failed for '{p}': {details}"
        raise CassetteValidationError(msg)

    try:
        return Cassette.model_validate(data)
    except Exception as err:
        msg = f"Cassette model construction failed for '{p}': {err}"
        raise CassetteValidationError(msg) from err


class FixtureLLMProvider:
    """Deterministic LLMProvider implementation replaying validated YAML cassettes."""

    def __init__(
        self,
        cassettes: Sequence[Cassette | Path | str] | Cassette | Path | str,
        sleep_fn: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize provider with one or more cassettes and optional sleep hook."""
        self.call_log: list[dict[str, Any]] = []
        self._sleep_fn: Callable[[float], Awaitable[None]] | None = sleep_fn
        self._cassettes: list[Cassette] = []

        items: Sequence[Cassette | Path | str] = (
            [cassettes] if isinstance(cassettes, (Cassette, Path, str)) else cassettes
        )

        for item in items:
            if isinstance(item, Cassette):
                self._cassettes.append(item)
            else:
                self._cassettes.append(load_cassette(item))

    @property
    def residency_tier(self) -> str:
        """Return residency tier identifier for fixtures."""
        return "fixture"

    def _matches_llm(
        self,
        matcher: CassetteMatcher,
        *,
        model: str,
        prompt: str,
        metadata: dict[str, str],
    ) -> bool:
        if matcher.model is not None and matcher.model != model:
            return False
        if matcher.agent_slug is not None:
            actual_slug = metadata.get("agent_slug") or metadata.get("agent")
            if actual_slug != matcher.agent_slug:
                return False
        if matcher.provider is not None:
            actual_provider = metadata.get("provider")
            if actual_provider != matcher.provider:
                return False
        if matcher.transition_to is not None:
            actual_transition = metadata.get("transition_to")
            if actual_transition != matcher.transition_to:
                return False
        return all(pattern in prompt for pattern in matcher.prompt_contains)

    def _find_matching_cassette(
        self,
        *,
        model: str,
        prompt: str,
        metadata: dict[str, str],
    ) -> Cassette:
        for cas in self._cassettes:
            if self._matches_llm(cas.matcher, model=model, prompt=prompt, metadata=metadata):
                return cas
        msg = (
            f"No cassette matched LLM request (model={model!r}, prompt={prompt!r}, "
            f"metadata={metadata!r})"
        )
        raise CassetteMismatchError(msg)

    async def _simulate_latency(self, ms: float) -> None:
        if self._sleep_fn is not None and ms > 0.0:
            await self._sleep_fn(ms / 1000.0)

    def _raise_fault(  # noqa: C901  # Exhaustive fault dispatch branch mapping
        self,
        cassette: Cassette,
        req_ttft_deadline_ms: int | None = None,
    ) -> None:
        fault = cassette.fault
        if fault is not None:
            kind = fault.kind
            if kind == "http_429":
                retry_after = fault.retry_after_s if fault.retry_after_s is not None else 30.0
                msg = "Simulated rate limit exceeded"
                raise ProviderHTTPError(msg, status=429, retry_after_s=retry_after)
            if kind == "http_500":
                msg = "Simulated server error"
                raise ProviderHTTPError(msg, status=500)
            if kind == "http_503":
                msg = "Simulated service unavailable"
                raise ProviderHTTPError(msg, status=503)
            if kind == "timeout":
                msg = "Simulated provider timeout"
                raise ProviderTimeout(msg)
            if kind == "ttft_sla_breach":
                msg = (
                    f"Simulated TTFT SLA breach ({cassette.simulated_ttft_ms}ms > "
                    f"{req_ttft_deadline_ms}ms)"
                )
                raise ProviderTimeout(msg)
            if kind == "unavailable":
                msg = "Simulated provider unavailable"
                raise ProviderUnavailable(msg)
            if kind == "schema_error":
                msg = "Simulated schema error"
                raise ProviderSchemaError(msg)
            if kind == "safety_block":
                msg = "Simulated content safety block"
                raise ProviderSafetyBlock(msg)
            if kind == "refusal":
                msg = "Simulated model refusal"
                raise ProviderRefusal(msg)

        if req_ttft_deadline_ms is not None and cassette.simulated_ttft_ms > float(
            req_ttft_deadline_ms
        ):
            msg = (
                f"TTFT SLA breached: simulated {cassette.simulated_ttft_ms}ms > "
                f"deadline {req_ttft_deadline_ms}ms"
            )
            raise ProviderTimeout(msg)

    async def stream_complete(self, req: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Stream chunks replayed from matching cassette."""
        cas = self._find_matching_cassette(
            model=req.model,
            prompt=req.prompt,
            metadata=req.metadata,
        )
        self.call_log.append(
            {
                "method": "stream_complete",
                "request": req.model_dump(),
                "matched_matcher": cas.matcher.model_dump(),
            }
        )

        await self._simulate_latency(cas.simulated_ttft_ms)

        if cas.fault is None or cas.fault.kind != "stream_error_after_chunk":
            self._raise_fault(cas, req.ttft_deadline_ms)

        chunks = cas.stream_chunks or []
        after_chunks = (
            cas.fault.after_chunks
            if (cas.fault and cas.fault.kind == "stream_error_after_chunk")
            else None
        )

        for idx, chunk in enumerate(chunks):
            if after_chunks is not None and idx >= after_chunks:
                msg = f"Simulated stream error after chunk {idx}"
                raise ProviderProtocolError(msg)

            is_last = idx == len(chunks) - 1
            yield StreamChunk(
                delta=chunk,
                index=idx,
                finish_reason="stop" if is_last else None,
                ttft_ms=cas.simulated_ttft_ms if idx == 0 else None,
                prompt_tokens=cas.usage.prompt_tokens if (cas.usage and is_last) else None,
                completion_tokens=cas.usage.completion_tokens if (cas.usage and is_last) else None,
            )

    async def generate_structured(
        self, req: StructuredRequest[TModel]
    ) -> StructuredResponse[TModel]:
        """Replay structured output and tool trace from matching cassette."""
        cas = self._find_matching_cassette(
            model=req.model,
            prompt=req.prompt,
            metadata=req.metadata,
        )
        self.call_log.append(
            {
                "method": "generate_structured",
                "request": req.model_dump(),
                "matched_matcher": cas.matcher.model_dump(),
            }
        )

        await self._simulate_latency(cas.simulated_ttft_ms)
        self._raise_fault(cas, req.ttft_deadline_ms)

        raw = cas.final_verdict if cas.final_verdict is not None else cas.structured_output
        if raw is None:
            msg = "Cassette has neither final_verdict nor structured_output configured"
            raise ProviderSchemaError(msg)

        try:
            parsed: TModel = req.response_model.model_validate(raw)
        except Exception as err:
            msg = f"Failed to validate response against {req.response_model.__name__}: {err}"
            raise ProviderSchemaError(msg) from err

        tool_trace: list[ToolCallStep] = []
        if cas.tool_script:
            tool_trace.extend(
                ToolCallStep(
                    tool=step.call.tool,
                    args=step.call.args,
                    result=step.returns,
                )
                for step in cas.tool_script
            )

        prompt_tokens = cas.usage.prompt_tokens if cas.usage else 0
        completion_tokens = cas.usage.completion_tokens if cas.usage else 0

        return StructuredResponse(
            parsed=parsed,
            raw_json=json.dumps(raw),
            tool_trace=tuple(tool_trace),
            ttft_ms=cas.simulated_ttft_ms,
            total_latency_ms=cas.simulated_ttft_ms + 2.0,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def embed_batch(self, req: EmbedBatchRequest) -> list[list[float]]:
        """Replay or generate deterministic L2-normalized vector embeddings."""
        cas = self._find_matching_cassette(
            model=req.model,
            prompt="",
            metadata={},
        )
        self.call_log.append(
            {
                "method": "embed_batch",
                "request": req.model_dump(),
                "matched_matcher": cas.matcher.model_dump(),
            }
        )

        await self._simulate_latency(cas.simulated_ttft_ms)
        self._raise_fault(cas)

        if cas.embeddings is None:
            msg = "Cassette has no embeddings configured"
            raise ProviderSchemaError(msg)

        if isinstance(cas.embeddings, list):
            return cas.embeddings

        rng = random.Random(cas.embeddings.seed)  # noqa: S311  # Deterministic test embeddings
        dim = cas.embeddings.dimension
        embeddings: list[list[float]] = []
        for _ in req.inputs:
            vec = [rng.gauss(0.0, 1.0) for _ in range(dim)]
            norm = math.sqrt(sum(x * x for x in vec))
            norm_factor = norm if norm > 0.0 else 1.0
            embeddings.append([x / norm_factor for x in vec])
        return embeddings

    async def health_probe(self) -> HealthStatus:
        """Return healthy status for fixture provider."""
        return HealthStatus(
            ok=True,
            latency_ms=1.0,
            models=("fixture-model",),
            detail="FixtureLLMProvider healthy",
        )


class FixtureCLIRunner:
    """Deterministic CLIRunner implementation replaying validated CLI cassettes."""

    def __init__(
        self,
        cassettes: Sequence[Cassette | Path | str] | Cassette | Path | str,
    ) -> None:
        """Initialize CLI runner with one or more cassettes."""
        self.call_log: list[dict[str, Any]] = []
        self._cassettes: list[Cassette] = []

        items: Sequence[Cassette | Path | str] = (
            [cassettes] if isinstance(cassettes, (Cassette, Path, str)) else cassettes
        )

        for item in items:
            if isinstance(item, Cassette):
                self._cassettes.append(item)
            else:
                self._cassettes.append(load_cassette(item))

    def _matches_cli(
        self,
        matcher: CassetteMatcher,
        *,
        argv: tuple[str, ...],
        stdin_str: str,
    ) -> bool:
        if matcher.argv_prefix:
            prefix_len = len(matcher.argv_prefix)
            if len(argv) < prefix_len or list(argv[:prefix_len]) != matcher.argv_prefix:
                return False
        return all(pattern in stdin_str for pattern in matcher.stdin_contains)

    def _find_matching_cassette(
        self,
        *,
        argv: tuple[str, ...],
        stdin_str: str,
    ) -> Cassette:
        for cas in self._cassettes:
            if self._matches_cli(cas.matcher, argv=argv, stdin_str=stdin_str):
                return cas
        msg = f"No cassette matched CLI request (argv={argv!r}, stdin_str={stdin_str!r})"
        raise CassetteMismatchError(msg)

    async def run(self, req: CLIRunRequest) -> CLIRunResult:
        """Simulate CLI process execution without spawning subprocesses."""
        stdin_str = req.stdin_bytes.decode("utf-8", errors="replace")
        cas = self._find_matching_cassette(argv=req.argv, stdin_str=stdin_str)

        self.call_log.append(
            {
                "method": "run",
                "request": req.model_dump(),
                "matched_matcher": cas.matcher.model_dump(),
            }
        )

        if cas.fault is not None:
            if cas.fault.kind == "timeout":
                msg = f"Simulated CLI execution timeout ({cas.simulated_ttft_ms}ms)"
                raise ProviderTimeout(msg)
            if cas.fault.kind == "malformed_stdout":
                return CLIRunResult(
                    stdout=b"INVALID MALFORMED NON-JSON GARBAGE \xff\xfe",
                    stderr=b"warning: non-json payload\n",
                    exit_code=0,
                    duration_ms=cas.simulated_ttft_ms,
                )

        if cas.cli_result is not None:
            return CLIRunResult(
                stdout=cas.cli_result.stdout.encode("utf-8"),
                stderr=cas.cli_result.stderr.encode("utf-8"),
                exit_code=cas.cli_result.exit_code,
                duration_ms=cas.cli_result.duration_ms,
            )

        msg = f"Cassette '{cas}' has neither cli_result nor supported fault"
        raise CassetteMismatchError(msg)
