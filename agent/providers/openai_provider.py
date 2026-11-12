# Copyright 2026 Kanban Platform Contributors
"""OpenAIProvider adapter implementing LLMProvider protocol over AsyncOpenAI."""

from __future__ import annotations

import contextlib
import json
import time
from typing import TYPE_CHECKING, Any, Literal, NoReturn, TypeVar

import httpx
import openai
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, model_validator

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

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

__all__ = [
    "OpenAIProvider",
    "OpenAISettings",
]

TModel = TypeVar("TModel", bound=BaseModel)

_LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "::1", "localhost"})
_HTTP_REDIRECT_MIN: int = 300
_HTTP_REDIRECT_MAX: int = 400
_HTTP_TOO_MANY_REQUESTS: int = 429
_HTTP_SERVER_ERROR_MIN: int = 500


class OpenAISettings(BaseModel):
    """Configuration settings for OpenAI provider with residency and URL controls."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    api_key: SecretStr
    base_url: HttpUrl | None = None
    base_url_kind: Literal["openai", "azure", "vllm", "litellm"] = "openai"
    model_allowlist: tuple[str, ...] = Field(min_length=1)
    organization: str | None = None
    timeout_s: float = Field(default=30.0, ge=1.0, le=300.0)
    residency_tier: str = "openai-zdr-us"

    @model_validator(mode="after")
    def validate_settings(self) -> OpenAISettings:
        """Validate base URL scheme, host, and absence of userinfo/query/fragment."""
        if self.base_url is not None:
            url = self.base_url
            if url.username or url.password:
                msg = "base_url must not contain userinfo"
                raise ValueError(msg)
            if url.query:
                msg = "base_url must not contain query parameters"
                raise ValueError(msg)
            if url.fragment:
                msg = "base_url must not contain fragment"
                raise ValueError(msg)

            host = (url.host or "").strip("[]")
            if url.scheme != "https" and host not in _LOOPBACK_HOSTS:
                msg = "base_url must use HTTPS unless targeting loopback (127.0.0.1, ::1)"
                raise ValueError(msg)
        return self


def _enforce_strict_dict(node: dict[str, Any]) -> None:
    """Enforce strict structured output rules on dictionary schema node."""
    if node.get("type") == "object" or "properties" in node:
        node["additionalProperties"] = False
        props = node.get("properties")
        if isinstance(props, dict):
            req_list = node.setdefault("required", [])
            for prop in props:
                if prop not in req_list:
                    req_list.append(prop)
    for v in node.values():
        _enforce_strict(v)


def _enforce_strict(node: object) -> None:
    """Recursively enforce additionalProperties=False and required fields."""
    if isinstance(node, dict):
        _enforce_strict_dict(node)
    elif isinstance(node, list):
        for item in node:
            _enforce_strict(item)


def _make_strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Generate OpenAI-compliant strict JSON schema with additionalProperties=False."""
    schema = model.model_json_schema()
    _enforce_strict(schema)
    return schema


def _raise_ttft_timeout(ttft_ms: float, deadline: int) -> NoReturn:
    """Raise ProviderTimeout for TTFT SLA breach."""
    msg = f"TTFT SLA breached: {ttft_ms:.1f}ms > {deadline}ms"
    raise ProviderTimeout(msg, code="TIMEOUT")


class OpenAIProvider(LLMProvider):
    """Vendor-neutral LLM provider adapter for OpenAI and compatible inference endpoints."""

    def __init__(
        self,
        settings: OpenAISettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize provider with validated settings and optional HTTP transport."""
        self._settings: OpenAISettings = settings
        self._transport: httpx.AsyncBaseTransport | None = transport
        base_url_str = (
            str(settings.base_url) if settings.base_url is not None else "https://api.openai.com/v1"
        )
        self._http_client: httpx.AsyncClient = httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
        )
        self._client: AsyncOpenAI = AsyncOpenAI(
            api_key=settings.api_key.get_secret_value(),
            base_url=base_url_str,
            organization=settings.organization,
            timeout=settings.timeout_s,
            max_retries=0,
            http_client=self._http_client,  # type: ignore[arg-type]
        )

    def __repr__(self) -> str:
        """Return safe developer-facing string with API key strictly excluded."""
        base_url = (
            str(self._settings.base_url) if self._settings.base_url else "https://api.openai.com/v1"
        )
        return (
            f"OpenAIProvider(base_url={base_url!r}, "
            f"models={self._settings.model_allowlist!r}, "
            f"residency_tier={self._settings.residency_tier!r})"
        )

    @property
    def residency_tier(self) -> str:
        """Return admin-configured data residency tier."""
        return self._settings.residency_tier

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Return underlying HTTPX async client instance."""
        return self._http_client

    def _chat_kwargs(
        self,
        req: CompletionRequest | StructuredRequest[Any],
        **extra: object,
    ) -> dict[str, Any]:
        """Construct validated chat parameters enforcing store=False and allowlist bounds."""
        if req.model not in self._settings.model_allowlist:
            msg = f"Model '{req.model}' is not in allowlist"
            raise ProviderPolicyError(msg, code="MODEL_NOT_ALLOWED")

        messages: list[dict[str, str]] = []
        if req.system_prompt:
            messages.append({"role": "system", "content": req.system_prompt})
        messages.append({"role": "user", "content": req.prompt})

        return {
            "model": req.model,
            "messages": messages,
            "store": False,
            "temperature": req.temperature,
            "max_tokens": req.max_output_tokens,
            **extra,
        }

    def _map_and_raise(self, exc: Exception) -> NoReturn:
        """Map upstream OpenAI SDK and HTTPX exceptions to typed ProviderError hierarchy."""
        if isinstance(exc, ProviderError):
            raise exc

        if isinstance(exc, openai.APIStatusError):
            status = exc.status_code
            if _HTTP_REDIRECT_MIN <= status < _HTTP_REDIRECT_MAX:
                msg = f"Redirect refused ({status})"
                raise ProviderProtocolError(msg, code="REDIRECT_REFUSED") from exc
            if status == _HTTP_TOO_MANY_REQUESTS:
                retry_after = None
                if hasattr(exc.response, "headers") and "retry-after" in exc.response.headers:
                    with contextlib.suppress(ValueError):
                        retry_after = float(exc.response.headers["retry-after"])
                raise ProviderHTTPError(
                    str(exc),
                    status=_HTTP_TOO_MANY_REQUESTS,
                    retry_after_s=retry_after,
                    code="RATE_LIMITED",
                ) from exc
            if status >= _HTTP_SERVER_ERROR_MIN:
                raise ProviderHTTPError(str(exc), status=status, code="UPSTREAM_5XX") from exc
            raise ProviderHTTPError(str(exc), status=status, code="HTTP_ERROR") from exc

        if isinstance(exc, (openai.APITimeoutError, httpx.TimeoutException)):
            raise ProviderTimeout(str(exc), code="TIMEOUT") from exc

        if isinstance(exc, (openai.APIConnectionError, httpx.ConnectError)):
            raise ProviderUnavailable(str(exc), code="UNAVAILABLE") from exc

        raise ProviderError(str(exc), code="PROVIDER_ERROR") from exc

    async def stream_complete(self, req: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Stream token-by-token completion chunks from OpenAI chat completion."""
        kwargs = self._chat_kwargs(req, stream=True, stream_options={"include_usage": True})
        t0 = time.perf_counter()
        index = 0
        first_chunk = True
        try:
            stream = await self._client.chat.completions.create(**kwargs)
            async for chunk in stream:
                delta = ""
                finish_reason: Literal["stop", "length", "tool_calls"] | None = None
                if chunk.choices:
                    choice = chunk.choices[0]
                    delta = choice.delta.content or ""
                    fr = choice.finish_reason
                    if fr in ("stop", "length", "tool_calls"):
                        finish_reason = fr

                ttft_ms = None
                if first_chunk:
                    ttft_ms = (time.perf_counter() - t0) * 1000.0
                    first_chunk = False
                    if req.ttft_deadline_ms is not None and ttft_ms > req.ttft_deadline_ms:
                        _raise_ttft_timeout(ttft_ms, req.ttft_deadline_ms)

                prompt_tokens = chunk.usage.prompt_tokens if chunk.usage else None
                completion_tokens = chunk.usage.completion_tokens if chunk.usage else None

                yield StreamChunk(
                    delta=delta,
                    index=index,
                    finish_reason=finish_reason,
                    ttft_ms=ttft_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
                index += 1
        except Exception as exc:  # noqa: BLE001  # Map all exceptions to ProviderError
            self._map_and_raise(exc)

    async def generate_structured(
        self, req: StructuredRequest[TModel]
    ) -> StructuredResponse[TModel]:
        """Generate typed structured output parsed and validated into req.response_model."""
        t0 = time.perf_counter()
        strict_schema = _make_strict_json_schema(req.response_model)
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": req.response_model.__name__,
                "strict": True,
                "schema": strict_schema,
            },
        }
        kwargs = self._chat_kwargs(req, response_format=response_format)
        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001  # Map all exceptions to ProviderError
            self._map_and_raise(exc)

        total_latency_ms = (time.perf_counter() - t0) * 1000.0
        if not resp.choices:
            msg = "OpenAI returned empty choices list"
            raise ProviderProtocolError(msg, code="PROTOCOL_ERROR")

        choice = resp.choices[0]
        if getattr(choice.message, "refusal", None):
            refusal_text = str(choice.message.refusal)
            raise ProviderRefusal(refusal_text, code="REFUSAL")

        content = choice.message.content or ""
        try:
            raw_data = json.loads(content)
            parsed = req.response_model.model_validate(raw_data)
        except Exception as exc:
            msg = f"Output validation failed against schema {req.response_model.__name__}: {exc}"
            raise ProviderSchemaError(msg, code="SCHEMA_ERROR") from exc

        prompt_tokens = resp.usage.prompt_tokens if resp.usage else 0
        completion_tokens = resp.usage.completion_tokens if resp.usage else 0

        return StructuredResponse(
            parsed=parsed,
            raw_json=content,
            tool_trace=(),
            ttft_ms=total_latency_ms,
            total_latency_ms=total_latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    async def embed_batch(self, req: EmbedBatchRequest) -> list[list[float]]:
        """Generate batch vector embeddings for up to 64 inputs."""
        if req.model not in self._settings.model_allowlist:
            msg = f"Model '{req.model}' is not in allowlist"
            raise ProviderPolicyError(msg, code="MODEL_NOT_ALLOWED")

        try:
            resp = await self._client.embeddings.create(
                model=req.model,
                input=list(req.inputs),
            )
        except Exception as exc:  # noqa: BLE001  # Map all exceptions to ProviderError
            self._map_and_raise(exc)

        return [item.embedding for item in resp.data]

    async def health_probe(self) -> HealthStatus:
        """Probe upstream availability by retrieving the first allowlisted model."""
        t0 = time.perf_counter()
        try:
            target_model = self._settings.model_allowlist[0]
            await self._client.models.retrieve(target_model)
            latency = (time.perf_counter() - t0) * 1000.0
            return HealthStatus(
                ok=True,
                latency_ms=latency,
                models=self._settings.model_allowlist,
            )
        except Exception as exc:  # noqa: BLE001  # Health probe must never raise
            latency = (time.perf_counter() - t0) * 1000.0
            return HealthStatus(
                ok=False,
                latency_ms=latency,
                models=(),
                detail=str(exc),
            )
