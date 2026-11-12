# Copyright 2026 Kanban Platform Contributors
"""Vendor-neutral LLM provider protocol, DTOs, and CLI runner contracts."""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Protocol,
    TypeVar,
    runtime_checkable,
)

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
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
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

__all__ = [
    "AllProvidersUnavailable",
    "CLIRunRequest",
    "CLIRunResult",
    "CLIRunner",
    "CompletionRequest",
    "EgressDenied",
    "EmbedBatchRequest",
    "HealthStatus",
    "LLMProvider",
    "ProviderError",
    "ProviderHTTPError",
    "ProviderPolicyError",
    "ProviderProtocolError",
    "ProviderRefusal",
    "ProviderSafetyBlock",
    "ProviderSchemaError",
    "ProviderTimeout",
    "ProviderUnavailable",
    "StreamChunk",
    "StructuredRequest",
    "StructuredResponse",
    "ToolCallStep",
]

TModel = TypeVar("TModel", bound=BaseModel)

_MAX_BATCH_INPUTS: int = 64
_MAX_INPUT_CHARS: int = 8192

_FORBIDDEN_SHELL_BINARIES: frozenset[str] = frozenset(
    {
        "/bin/sh",
        "/bin/bash",
        "/usr/bin/sh",
        "/usr/bin/bash",
        "sh",
        "bash",
    }
)


class CompletionRequest(BaseModel):
    """Request DTO for streaming text completion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str
    prompt: str
    suffix: str | None = None
    system_prompt: str | None = None
    temperature: float = Field(default=0.15, ge=0.0, le=2.0)
    max_output_tokens: int = Field(
        default=256,
        ge=1,
        le=32768,
        validation_alias=AliasChoices("max_output_tokens", "max_tokens"),
    )
    ttft_deadline_ms: int | None = Field(default=None, ge=1, le=60000)
    metadata: dict[str, str] = Field(default_factory=dict)

    @property
    def max_tokens(self) -> int:
        """Return the maximum token budget for the completion."""
        return self.max_output_tokens


class StreamChunk(BaseModel):
    """Single token or delta emitted during completion streaming."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    delta: str
    index: int = Field(ge=0)
    finish_reason: Literal["stop", "length", "tool_calls"] | None = None
    ttft_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ToolCallStep(BaseModel):
    """Audit step representing a tool invocation during structured execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool: str
    args: dict[str, Any]
    result: dict[str, Any] | str | None = None


class StructuredRequest[TModel: BaseModel](BaseModel):
    """Request DTO for structured output parsed into a typed Pydantic model."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    model: str
    prompt: str
    response_model: type[TModel]
    system_prompt: str | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=1024, ge=1, le=32768)
    ttft_deadline_ms: int | None = Field(default=None, ge=1, le=60000)
    metadata: dict[str, str] = Field(default_factory=dict)


class StructuredResponse[TModel: BaseModel](BaseModel):
    """Response DTO carrying typed structured output and execution telemetry."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    parsed: TModel
    raw_json: str
    tool_trace: tuple[ToolCallStep, ...] = ()
    ttft_ms: float
    total_latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0


class EmbedBatchRequest(BaseModel):
    """Request DTO for batch vector embeddings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str
    inputs: tuple[str, ...]

    @field_validator("inputs", mode="before")
    @classmethod
    def _validate_inputs(cls, value: tuple[object, ...] | list[object]) -> tuple[str, ...]:
        tuple_val = tuple(value)
        if not (1 <= len(tuple_val) <= _MAX_BATCH_INPUTS):
            msg = f"inputs length must be between 1 and {_MAX_BATCH_INPUTS}, got {len(tuple_val)}"
            raise ValueError(msg)
        for idx, item in enumerate(tuple_val):
            if not isinstance(item, str):
                msg = f"input at index {idx} must be a string"
                raise ValueError(msg)  # noqa: TRY004  # ValueError mandated by KB-P0-12 spec
            if not (1 <= len(item) <= _MAX_INPUT_CHARS):
                msg = (
                    f"input at index {idx} length must be between 1 and {_MAX_INPUT_CHARS} "
                    f"characters, got {len(item)}"
                )
                raise ValueError(msg)
        return tuple(str(x) for x in tuple_val)


class HealthStatus(BaseModel):
    """Health status and latency report for an LLM provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    latency_ms: float
    models: tuple[str, ...] = ()
    detail: str | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """Vendor-neutral LLM provider protocol."""

    @property
    def residency_tier(self) -> str:
        """Return data residency tier identifier (e.g. 'local', 'cloud', 'fixture')."""
        ...

    def stream_complete(self, req: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Stream token-by-token completion chunks."""
        ...

    async def generate_structured(
        self, req: StructuredRequest[TModel]
    ) -> StructuredResponse[TModel]:
        """Generate typed structured output parsed into req.response_model."""
        ...

    async def embed_batch(self, req: EmbedBatchRequest) -> list[list[float]]:
        """Generate batch vector embeddings."""
        ...

    async def health_probe(self) -> HealthStatus:
        """Probe upstream provider availability and health."""
        ...


class CLIRunRequest(BaseModel):
    """Request DTO for executing zero-shell CLI pipe harnesses."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    argv: tuple[str, ...]
    stdin_bytes: bytes
    timeout_s: float = 30.0
    env_keys: tuple[str, ...] = ()

    @field_validator("argv", mode="before")
    @classmethod
    def _coerce_argv(cls, value: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        return tuple(value)

    @model_validator(mode="after")
    def _validate_cli_request(self) -> CLIRunRequest:
        if not self.argv:
            msg = "argv must not be empty"
            raise ValueError(msg)
        head = self.argv[0].strip().lower()
        if head in _FORBIDDEN_SHELL_BINARIES:
            msg = f"Shell wrapper '{head}' is forbidden; direct zero-shell execution required"
            raise ValueError(msg)
        if "-c" in self.argv:
            msg = "Shell invocation with '-c' wrapper is forbidden"
            raise ValueError(msg)
        return self


class CLIRunResult(BaseModel):
    """Result DTO of a completed zero-shell CLI invocation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stdout: bytes
    stderr: bytes
    exit_code: int
    duration_ms: float


@runtime_checkable
class CLIRunner(Protocol):
    """Zero-shell CLI harness protocol for transition interceptors."""

    async def run(self, req: CLIRunRequest) -> CLIRunResult:
        """Execute a CLI request returning raw stdout, stderr, and exit code."""
        ...
