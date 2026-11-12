# Copyright 2026 Kanban Platform Contributors
"""GeminiProvider adapter implementing LLMProvider protocol over google-genai."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Literal, TypeVar

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

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
    ProviderSafetyBlock,
    ProviderSchemaError,
    ProviderTimeout,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from google.auth.credentials import Credentials

__all__ = [
    "DEFAULT_SAFETY_SETTINGS",
    "GeminiProvider",
    "GeminiSettings",
    "SafetySetting",
]

TModel = TypeVar("TModel", bound=BaseModel)

_MAX_BATCH_SIZE: int = 64
_MAX_INPUT_CHARS: int = 8192


class SafetySetting(BaseModel):
    """Explicit content safety threshold configuration for harm categories."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str
    threshold: str


DEFAULT_SAFETY_SETTINGS: tuple[SafetySetting, ...] = (
    SafetySetting(
        category="HARM_CATEGORY_HARASSMENT",
        threshold="BLOCK_MEDIUM_AND_ABOVE",
    ),
    SafetySetting(
        category="HARM_CATEGORY_HATE_SPEECH",
        threshold="BLOCK_MEDIUM_AND_ABOVE",
    ),
    SafetySetting(
        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
        threshold="BLOCK_MEDIUM_AND_ABOVE",
    ),
    SafetySetting(
        category="HARM_CATEGORY_DANGEROUS_CONTENT",
        threshold="BLOCK_MEDIUM_AND_ABOVE",
    ),
)


class GeminiSettings(BaseModel):
    """Configuration settings for Gemini provider supporting Vertex AI and AI Studio."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["vertex", "ai_studio_paid"]
    api_key: SecretStr | None = None
    vertex_project: str | None = None
    vertex_location: str | None = None
    allowed_vertex_regions: tuple[str, ...] = ("europe-west4", "us-central1")
    model_allowlist: tuple[str, ...] = (
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "text-embedding-004",
    )
    safety_settings: tuple[SafetySetting, ...] = DEFAULT_SAFETY_SETTINGS
    timeout_s: float = Field(default=30.0, ge=1.0, le=300.0)

    def _validate_ai_studio(self) -> None:
        if not self.api_key or not self.api_key.get_secret_value().strip():
            msg = "api_key is required when mode is 'ai_studio_paid'"
            raise ValueError(msg)
        if self.vertex_project is not None or self.vertex_location is not None:
            msg = "vertex_project and vertex_location are forbidden when mode is 'ai_studio_paid'"
            raise ValueError(msg)

    def _validate_vertex(self) -> None:
        if self.api_key is not None:
            msg = "api_key is forbidden when mode is 'vertex'"
            raise ValueError(msg)
        if not self.vertex_project or not self.vertex_project.strip():
            msg = "vertex_project is required when mode is 'vertex'"
            raise ValueError(msg)
        if not self.vertex_location or not self.vertex_location.strip():
            msg = "vertex_location is required when mode is 'vertex'"
            raise ValueError(msg)
        if not self.allowed_vertex_regions:
            msg = "allowed_vertex_regions must contain at least one region"
            raise ValueError(msg)

        lowered_allowed = tuple(r.lower() for r in self.allowed_vertex_regions)
        if "global" in lowered_allowed or self.vertex_location.lower() == "global":
            msg = "'global' region is rejected for Vertex AI; regional pinning required"
            raise ValueError(msg)

        if self.vertex_location not in self.allowed_vertex_regions:
            msg = (
                f"vertex_location '{self.vertex_location}' is not permitted; "
                f"must be one of {self.allowed_vertex_regions}"
            )
            raise ValueError(msg)

    @model_validator(mode="after")
    def validate_gemini_settings(self) -> GeminiSettings:
        """Enforce strict isolation between Vertex and AI Studio and validate regions."""
        if not self.model_allowlist:
            msg = "model_allowlist must contain at least one model"
            raise ValueError(msg)

        if self.mode == "ai_studio_paid":
            self._validate_ai_studio()
        else:
            self._validate_vertex()

        return self


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider adapter wrapping google-genai SDK."""

    def __init__(
        self,
        settings: GeminiSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        credentials: Credentials | None = None,
    ) -> None:
        """Initialize provider with settings, optional transport, and credentials."""
        self._settings = settings

        async_client_args: dict[str, object] = {
            "trust_env": False,
        }
        if transport is not None:
            async_client_args["transport"] = transport

        http_options = types.HttpOptions(
            timeout=int(settings.timeout_s * 1000),
            async_client_args=async_client_args,
        )

        if settings.mode == "vertex":
            self._client = genai.Client(
                vertexai=True,
                project=settings.vertex_project,
                location=settings.vertex_location,
                credentials=credentials,
                http_options=http_options,
            )
        else:
            api_key_val = settings.api_key.get_secret_value() if settings.api_key else None
            self._client = genai.Client(
                api_key=api_key_val,
                http_options=http_options,
            )

    @property
    def residency_tier(self) -> str:
        """Return data residency tier identifier."""
        if self._settings.mode == "vertex":
            return f"gemini-vertex:{self._settings.vertex_location}"
        return "gemini-ai-studio-paid"

    def __repr__(self) -> str:
        """Return safe string representation without leaking secrets."""
        return (
            f"GeminiProvider(mode={self._settings.mode!r}, residency_tier={self.residency_tier!r})"
        )

    def __str__(self) -> str:
        """Return concise provider string identifier."""
        return f"GeminiProvider[{self.residency_tier}]"

    def _build_safety_settings(self) -> list[types.SafetySetting]:
        """Convert configured safety settings to google-genai SDK models."""
        return [
            types.SafetySetting(
                category=types.HarmCategory(s.category),
                threshold=types.HarmBlockThreshold(s.threshold),
            )
            for s in self._settings.safety_settings
        ]

    def _redact(self, message: str) -> str:
        """Redact configured API key if present in string message."""
        if self._settings.api_key is not None:
            return message.replace(self._settings.api_key.get_secret_value(), "[REDACTED]")
        return message

    def _translate_error(self, exc: Exception) -> Exception:
        """Map upstream SDK and network exceptions to typed ProviderError instances."""
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
            return ProviderTimeout(self._redact(str(exc)))
        if isinstance(exc, errors.APIError):
            status = int(exc.code) if exc.code else 500
            msg = exc.message or str(exc)
            return ProviderHTTPError(self._redact(msg), status=status)
        if isinstance(exc, httpx.HTTPStatusError):
            return ProviderHTTPError(
                self._redact(str(exc)),
                status=exc.response.status_code,
            )
        return ProviderProtocolError(self._redact(f"Unexpected provider error: {exc}"))

    def _check_safety(self, response: types.GenerateContentResponse) -> None:
        """Verify prompt feedback and candidates against safety triggers."""
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            msg = f"Prompt blocked by safety filters: {response.prompt_feedback.block_reason}"
            raise ProviderSafetyBlock(msg)

        if response.candidates:
            candidate = response.candidates[0]
            fr_val = getattr(candidate.finish_reason, "value", candidate.finish_reason)
            if fr_val == "SAFETY" or candidate.finish_reason == types.FinishReason.SAFETY:
                ratings_str = str(candidate.safety_ratings)
                msg = f"Generation blocked by safety filters: {ratings_str}"
                raise ProviderSafetyBlock(msg)

    def _extract_chunk(
        self,
        chunk: types.GenerateContentResponse,
        t0: float,
        chunk_idx: int,
    ) -> StreamChunk:
        """Extract typed StreamChunk from google-genai response chunk."""
        self._check_safety(chunk)

        delta = ""
        if chunk.candidates and chunk.candidates[0].content:
            parts = chunk.candidates[0].content.parts or []
            for part in parts:
                if part.text:
                    delta += part.text
        elif getattr(chunk, "text", None):
            delta = chunk.text or ""

        mapped_finish_reason: Literal["stop", "length", "tool_calls"] | None = None
        if chunk.candidates and chunk.candidates[0].finish_reason:
            fr = chunk.candidates[0].finish_reason
            fr_str = getattr(fr, "value", str(fr)).upper()
            if fr_str == "STOP" or fr == types.FinishReason.STOP:
                mapped_finish_reason = "stop"
            elif fr_str in ("MAX_TOKENS", "LENGTH") or fr == types.FinishReason.MAX_TOKENS:
                mapped_finish_reason = "length"

        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        if chunk.usage_metadata is not None:
            prompt_tokens = chunk.usage_metadata.prompt_token_count
            completion_tokens = chunk.usage_metadata.candidates_token_count

        ttft_ms = ((time.monotonic() - t0) * 1000.0) if chunk_idx == 0 else None

        return StreamChunk(
            delta=delta,
            index=chunk_idx,
            finish_reason=mapped_finish_reason,
            ttft_ms=ttft_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def stream_complete(self, req: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Stream token-by-token completion chunks from Gemini."""
        if req.model not in self._settings.model_allowlist:
            msg = f"Model '{req.model}' is not in allowed models: {self._settings.model_allowlist}"
            raise ProviderPolicyError(msg, code="MODEL_NOT_ALLOWED")

        config = types.GenerateContentConfig(
            temperature=req.temperature,
            max_output_tokens=req.max_output_tokens,
            safety_settings=self._build_safety_settings(),
            system_instruction=req.system_prompt or None,
        )

        t0 = time.monotonic()
        chunk_idx = 0

        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=req.model,
                contents=req.prompt,
                config=config,
            )
            async for chunk in stream:
                yield self._extract_chunk(chunk, t0, chunk_idx)
                chunk_idx += 1

        except Exception as exc:
            raise self._translate_error(exc) from exc

    async def generate_structured(
        self, req: StructuredRequest[TModel]
    ) -> StructuredResponse[TModel]:
        """Generate structured JSON output validated into req.response_model."""
        if req.model not in self._settings.model_allowlist:
            msg = f"Model '{req.model}' is not in allowed models: {self._settings.model_allowlist}"
            raise ProviderPolicyError(msg, code="MODEL_NOT_ALLOWED")

        config = types.GenerateContentConfig(
            temperature=req.temperature,
            max_output_tokens=req.max_output_tokens,
            response_mime_type="application/json",
            response_schema=req.response_model,
            safety_settings=self._build_safety_settings(),
            system_instruction=req.system_prompt or None,
        )

        t0 = time.monotonic()

        try:
            resp = await self._client.aio.models.generate_content(
                model=req.model,
                contents=req.prompt,
                config=config,
            )
        except Exception as exc:
            raise self._translate_error(exc) from exc

        total_latency_ms = (time.monotonic() - t0) * 1000.0

        self._check_safety(resp)

        raw_json = ""
        if resp.candidates and resp.candidates[0].content:
            parts = resp.candidates[0].content.parts or []
            for part in parts:
                if part.text:
                    raw_json += part.text
        elif getattr(resp, "text", None):
            raw_json = resp.text or ""

        try:
            parsed_model = req.response_model.model_validate_json(raw_json)
        except Exception as err:
            msg = f"Model output failed local schema validation: {err}"
            raise ProviderSchemaError(msg) from err

        prompt_tokens = 0
        completion_tokens = 0
        if resp.usage_metadata is not None:
            prompt_tokens = resp.usage_metadata.prompt_token_count or 0
            completion_tokens = resp.usage_metadata.candidates_token_count or 0

        return StructuredResponse(
            parsed=parsed_model,
            raw_json=raw_json,
            tool_trace=(),
            ttft_ms=total_latency_ms,
            total_latency_ms=total_latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def embed_batch(self, req: EmbedBatchRequest) -> list[list[float]]:
        """Generate batch vector embeddings with input length checks."""
        if req.model not in self._settings.model_allowlist:
            msg = f"Model '{req.model}' is not in allowed models: {self._settings.model_allowlist}"
            raise ProviderPolicyError(msg, code="MODEL_NOT_ALLOWED")

        if len(req.inputs) > _MAX_BATCH_SIZE:
            msg = f"Batch size {len(req.inputs)} exceeds maximum allowed {_MAX_BATCH_SIZE}"
            raise ProviderProtocolError(msg, code="BATCH_TOO_LARGE")

        for idx, text_input in enumerate(req.inputs):
            if len(text_input) > _MAX_INPUT_CHARS:
                msg = (
                    f"Input at index {idx} length {len(text_input)} exceeds "
                    f"maximum allowed {_MAX_INPUT_CHARS}"
                )
                raise ProviderProtocolError(msg, code="INPUT_TOO_LARGE")

        try:
            resp = await self._client.aio.models.embed_content(
                model=req.model,
                contents=list(req.inputs),
            )
        except Exception as exc:
            raise self._translate_error(exc) from exc

        if resp.embeddings:
            return [list(emb.values) if emb.values else [] for emb in resp.embeddings]

        return []

    async def health_probe(self) -> HealthStatus:
        """Probe upstream provider availability without raising exceptions."""
        start_time = time.monotonic()
        probe_model = (
            self._settings.model_allowlist[0]
            if self._settings.model_allowlist
            else "gemini-2.5-flash"
        )
        try:
            await self._client.aio.models.get(model=probe_model)
            latency_ms = (time.monotonic() - start_time) * 1000.0
            return HealthStatus(
                ok=True,
                latency_ms=latency_ms,
                models=self._settings.model_allowlist,
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = (time.monotonic() - start_time) * 1000.0
            err_msg = self._redact(str(exc))
            return HealthStatus(
                ok=False,
                latency_ms=latency_ms,
                models=(),
                detail=err_msg,
            )
