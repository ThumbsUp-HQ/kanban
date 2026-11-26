# Copyright 2026 Kanban Platform Contributors
"""OllamaProvider adapter implementing LLMProvider protocol over httpx."""

from __future__ import annotations

import ipaddress
import json
import time
import urllib.parse
from ipaddress import (  # Runtime Pydantic field resolution
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
)
from pathlib import Path  # noqa: TC003  # Required at runtime for Pydantic field resolution
from typing import TYPE_CHECKING, Any, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

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
    ProviderHTTPError,
    ProviderPolicyError,
    ProviderProtocolError,
    ProviderSchemaError,
    ProviderTimeout,
    ProviderUnavailable,
)
from agent.providers.net_guard import Resolver, resolve_and_pin
from agent.providers.schema_utils import dereference_json_schema, strip_think_tags

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network

__all__ = [
    "OllamaProvider",
    "OllamaSettings",
]

T = TypeVar("T", bound=BaseModel)

_MAX_LINE_BYTES: int = 64 * 1024  # 64 KiB
_MAX_STREAM_BYTES: int = 8 * 1024 * 1024  # 8 MiB
_MAX_BATCH_SIZE: int = 64
_MAX_INPUT_CHARS: int = 8192

_HTTP_OK: int = 200
_HTTP_REDIRECT_MIN: int = 300
_HTTP_REDIRECT_MAX: int = 400
_HTTP_BAD_REQUEST: int = 400
_HTTP_TOO_MANY_REQUESTS: int = 429
_IPV4_VERSION: int = 4
_IPV6_VERSION: int = 6


class OllamaSettings(BaseModel):
    """Configuration settings for Ollama provider with CIDR and timeout controls."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: HttpUrl
    allowed_ollama_cidrs: tuple[IPv4Network | IPv6Network, ...] = Field(
        default_factory=tuple, min_length=1
    )
    model_allowlist: tuple[str, ...] = Field(min_length=1)
    keep_alive: str = "30m"
    connect_timeout_s: float = Field(default=2.0, ge=0.1, le=10.0)
    read_timeout_s: float = Field(default=30.0, ge=1.0, le=300.0)
    mtls_client_cert_path: Path | None = None
    mtls_client_key_path: Path | None = None
    ca_bundle_path: Path | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_default_cidrs(cls, data: Any) -> Any:  # noqa: ANN401
        """Auto-populate default allowed CIDR from admin-configured base_url host if omitted."""
        if isinstance(data, dict) and "allowed_ollama_cidrs" not in data:
            base_url_val = data.get("base_url")
            if base_url_val:
                try:
                    parsed = urllib.parse.urlsplit(str(base_url_val))
                    host_str = (parsed.hostname or "").strip("[]").lower()
                    if host_str:
                        if host_str in ("127.0.0.1", "::1", "localhost"):
                            data["allowed_ollama_cidrs"] = ["127.0.0.0/8", "::1/128"]
                        else:
                            ip = ipaddress.ip_address(host_str)
                            data["allowed_ollama_cidrs"] = [
                                f"{ip}/32" if ip.version == _IPV4_VERSION else f"{ip}/128"
                            ]
                except ValueError:
                    pass
        return data

    @model_validator(mode="after")
    def validate_settings(self) -> OllamaSettings:
        """Validate URL constraints and mTLS certificate/key pairing."""
        url = self.base_url
        if url.scheme not in ("http", "https"):
            msg = "base_url scheme must be 'http' or 'https'"
            raise ValueError(msg)
        if url.username or url.password:
            msg = "base_url must not contain userinfo"
            raise ValueError(msg)
        if url.query:
            msg = "base_url must not contain query parameters"
            raise ValueError(msg)
        if url.fragment:
            msg = "base_url must not contain fragment"
            raise ValueError(msg)

        has_cert = self.mtls_client_cert_path is not None
        has_key = self.mtls_client_key_path is not None
        if has_cert != has_key:
            msg = "Both mtls_client_cert_path and mtls_client_key_path must be provided, or neither"
            raise ValueError(msg)

        host_str = (url.host or "").strip("[]")
        try:
            ip = ipaddress.ip_address(host_str)
            if not any(ip in cidr for cidr in self.allowed_ollama_cidrs):
                host_net = ipaddress.ip_network(
                    f"{ip}/32" if ip.version == _IPV4_VERSION else f"{ip}/128"
                )
                object.__setattr__(
                    self, "allowed_ollama_cidrs", (*self.allowed_ollama_cidrs, host_net)
                )
        except ValueError:
            pass

        return self


def _parse_embeddings_data(embeddings_raw: object) -> list[list[float]]:
    if not isinstance(embeddings_raw, list):
        msg = "Ollama response missing 'embeddings' array"
        raise ProviderProtocolError(msg)

    embeddings: list[list[float]] = []
    expected_dim: int | None = None
    for row in embeddings_raw:
        if not isinstance(row, list):
            msg = "Embedding item is not a vector list"
            raise ProviderProtocolError(msg)
        if expected_dim is None:
            expected_dim = len(row)
        elif len(row) != expected_dim:
            msg = f"Embedding dimension mismatch: expected {expected_dim}, got {len(row)}"
            raise ProviderProtocolError(msg)
        embeddings.append([float(x) for x in row])

    return embeddings


class OllamaProvider(LLMProvider):
    """Provider adapter communicating with local or remote Ollama daemon."""

    def __init__(
        self,
        settings: OllamaSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        """Initialize OllamaProvider with hardened settings and optional test transport."""
        self._settings = settings
        self._resolver = resolver

        cert: tuple[str, str] | None = None
        if settings.mtls_client_cert_path and settings.mtls_client_key_path:
            cert = (str(settings.mtls_client_cert_path), str(settings.mtls_client_key_path))

        verify: str | bool = True
        if settings.ca_bundle_path is not None:
            verify = str(settings.ca_bundle_path)

        timeout = httpx.Timeout(
            connect=settings.connect_timeout_s,
            read=settings.read_timeout_s,
            write=5.0,
            pool=2.0,
        )

        self._client = httpx.AsyncClient(
            follow_redirects=False,
            trust_env=False,
            max_redirects=0,
            timeout=timeout,
            verify=verify,
            cert=cert,
            transport=transport,
        )

    @property
    def residency_tier(self) -> str:
        """Return data residency tier identifier."""
        return "ollama"

    def _format_target_url(self, ip: IPv4Address | IPv6Address, port: int, path: str) -> str:
        host_repr = f"[{ip}]" if ip.version == _IPV6_VERSION else str(ip)
        return f"{self._settings.base_url.scheme}://{host_repr}:{port}{path}"

    async def _resolve_target(self, path: str) -> tuple[str, dict[str, str], dict[str, Any]]:
        host = self._settings.base_url.host or "127.0.0.1"
        is_https = self._settings.base_url.scheme == "https"
        default_port = 443 if is_https else 80
        port = self._settings.base_url.port or default_port

        resolved_ip = await resolve_and_pin(
            host,
            port,
            self._settings.allowed_ollama_cidrs,
            resolver=self._resolver,
        )
        url = self._format_target_url(resolved_ip, port, path)
        headers = {"Host": f"{host}:{port}" if self._settings.base_url.port else host}
        extensions = {"sni_hostname": host} if is_https else {}
        return url, headers, extensions

    def _verify_model_allowed(self, model: str) -> None:
        if model not in self._settings.model_allowlist:
            models_str = ", ".join(self._settings.model_allowlist)
            msg = f"Model '{model}' is not in allowed Ollama models: ({models_str})"
            raise ProviderPolicyError(msg, code="MODEL_NOT_ALLOWED")

    def _handle_error_response(self, response: httpx.Response) -> None:
        if _HTTP_REDIRECT_MIN <= response.status_code < _HTTP_REDIRECT_MAX:
            msg = f"Unexpected redirect response {response.status_code} from Ollama"
            raise ProviderProtocolError(msg, code="REDIRECT_REFUSED")
        if response.status_code == _HTTP_TOO_MANY_REQUESTS:
            retry_s: float | None = None
            retry_hdr = response.headers.get("retry-after")
            if retry_hdr:
                try:
                    retry_s = float(retry_hdr)
                except ValueError:
                    retry_s = None
            msg = f"Ollama rate limit exceeded (HTTP 429): {response.text}"
            raise ProviderHTTPError(msg, status=_HTTP_TOO_MANY_REQUESTS, retry_after_s=retry_s)
        if response.status_code >= _HTTP_BAD_REQUEST:
            msg = f"Ollama returned HTTP {response.status_code}: {response.text}"
            raise ProviderHTTPError(msg, status=response.status_code)

    async def _process_stream_lines(
        self,
        response: httpx.Response,
        deadline_ms: int | None,
        t0: float,
    ) -> AsyncIterator[StreamChunk]:
        first_chunk = True
        total_bytes = 0
        chunk_idx = 0

        async for line in response.aiter_lines():
            line_bytes = len(line.encode())
            total_bytes += line_bytes
            if line_bytes > _MAX_LINE_BYTES:
                msg = f"Ollama line size ({line_bytes} B) exceeds limit ({_MAX_LINE_BYTES} B)"
                raise ProviderProtocolError(msg, code="LINE_TOO_LARGE")
            if total_bytes > _MAX_STREAM_BYTES:
                msg = f"Ollama total stream size exceeds limit ({_MAX_STREAM_BYTES} B)"
                raise ProviderProtocolError(msg, code="STREAM_TOO_LARGE")

            if not line.strip():
                continue

            ttft_ms: float | None = None
            if first_chunk:
                ttft_ms = (time.perf_counter() - t0) * 1000.0
                if deadline_ms is not None and ttft_ms > deadline_ms:
                    msg = f"TTFT SLA breached: {ttft_ms:.1f}ms > {deadline_ms}ms"
                    raise ProviderTimeout(msg, code="TIMEOUT")
                first_chunk = False

            try:
                data = json.loads(line)
            except json.JSONDecodeError as err:
                msg = f"Failed to parse Ollama NDJSON line: {line}"
                raise ProviderProtocolError(msg, code="PROTOCOL_ERROR") from err

            delta = str(data.get("response", ""))
            is_done = bool(data.get("done", False))

            prompt_tokens = int(data["prompt_eval_count"]) if "prompt_eval_count" in data else None
            completion_tokens = int(data["eval_count"]) if "eval_count" in data else None

            yield StreamChunk(
                delta=delta,
                index=chunk_idx,
                finish_reason="stop" if is_done else None,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                ttft_ms=ttft_ms,
            )
            chunk_idx += 1

    async def stream_complete(
        self,
        req: CompletionRequest,
    ) -> AsyncIterator[StreamChunk]:
        """Stream token chunks replayed from Ollama /api/generate endpoint."""
        self._verify_model_allowed(req.model)
        url, headers, extensions = await self._resolve_target("/api/generate")

        payload: dict[str, Any] = {
            "model": req.model,
            "prompt": req.prompt,
            "stream": True,
            "keep_alive": self._settings.keep_alive,
        }
        if req.suffix is not None:
            payload["suffix"] = req.suffix
        options: dict[str, Any] = {}
        if req.temperature is not None:
            options["temperature"] = req.temperature
        if req.max_output_tokens is not None:
            options["num_predict"] = req.max_output_tokens
        if options:
            payload["options"] = options

        t0 = time.perf_counter()
        req_timeout = req.ttft_deadline_ms / 1000.0 if req.ttft_deadline_ms is not None else None

        try:
            async with self._client.stream(
                "POST",
                url,
                json=payload,
                headers=headers,
                extensions=extensions,
                timeout=req_timeout,
            ) as response:
                self._handle_error_response(response)
                async for chunk in self._process_stream_lines(response, req.ttft_deadline_ms, t0):
                    yield chunk
        except httpx.TimeoutException as err:
            msg = f"Ollama request timed out: {err}"
            raise ProviderTimeout(msg) from err
        except httpx.ConnectError as err:
            msg = f"Failed to connect to Ollama: {err}"
            raise ProviderUnavailable(msg) from err
        except httpx.RequestError as err:
            msg = f"Ollama HTTP request failed: {err}"
            raise ProviderProtocolError(msg) from err

    async def generate_structured(
        self,
        req: StructuredRequest[T],
    ) -> StructuredResponse[T]:
        """Generate structured response validated against requested Pydantic model."""
        self._verify_model_allowed(req.model)
        url, headers, extensions = await self._resolve_target("/api/chat")

        messages: list[dict[str, str]] = []
        if req.system_prompt:
            messages.append({"role": "system", "content": req.system_prompt})
        messages.append({"role": "user", "content": req.prompt})

        schema = dereference_json_schema(req.response_model.model_json_schema())
        payload = {
            "model": req.model,
            "messages": messages,
            "format": schema,
            "options": {
                "temperature": req.temperature,
                "num_predict": req.max_output_tokens,
            },
            "stream": False,
            "keep_alive": self._settings.keep_alive,
        }

        t0 = time.perf_counter()
        req_timeout = req.ttft_deadline_ms / 1000.0 if req.ttft_deadline_ms is not None else None
        try:
            response = await self._client.post(
                url,
                json=payload,
                headers=headers,
                extensions=extensions,
                timeout=req_timeout,
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            self._handle_error_response(response)

            try:
                data = response.json()
            except Exception as err:
                msg = f"Ollama returned malformed JSON payload: {err}"
                raise ProviderProtocolError(msg) from err

            msg_obj = data.get("message", {})
            content_str = str(msg_obj.get("content", ""))
            cleaned_content = strip_think_tags(content_str)
            done_reason = data.get("done_reason")

            try:
                parsed_json = json.loads(cleaned_content)
            except json.JSONDecodeError as err:
                if done_reason == "length":
                    msg = (
                        f"Ollama structured output truncated: done_reason=length "
                        f"(truncated at num_predict={req.max_output_tokens}): {content_str!r}"
                    )
                    raise ProviderSchemaError(msg) from err
                msg = f"Ollama message content is not valid JSON: {content_str!r}"
                raise ProviderSchemaError(msg) from err

            try:
                parsed_model = req.response_model.model_validate(parsed_json)
            except Exception as err:
                name = req.response_model.__name__
                msg = f"Ollama output failed schema validation against {name}: {err}"
                raise ProviderSchemaError(msg) from err

            prompt_tokens = int(data.get("prompt_eval_count", 0))
            completion_tokens = int(data.get("eval_count", 0))

            return StructuredResponse(
                parsed=parsed_model,
                raw_json=cleaned_content,
                tool_trace=(),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                ttft_ms=latency_ms,
                total_latency_ms=latency_ms,
            )
        except httpx.TimeoutException as err:
            msg = f"Ollama structured request timed out: {err}"
            raise ProviderTimeout(msg) from err
        except httpx.ConnectError as err:
            msg = f"Failed to connect to Ollama: {err}"
            raise ProviderUnavailable(msg) from err
        except httpx.RequestError as err:
            msg = f"Ollama HTTP request failed: {err}"
            raise ProviderProtocolError(msg) from err

    async def embed_batch(
        self,
        req: EmbedBatchRequest,
    ) -> list[list[float]]:
        """Generate vector embeddings for a batch of text inputs."""
        if not req.inputs:
            msg = "Embed batch inputs must not be empty"
            raise ProviderProtocolError(msg)

        if len(req.inputs) > _MAX_BATCH_SIZE:
            msg = f"Embed batch size ({len(req.inputs)}) exceeds maximum limit of {_MAX_BATCH_SIZE}"
            raise ProviderProtocolError(msg, code="BATCH_TOO_LARGE")

        for idx, text in enumerate(req.inputs):
            if len(text) > _MAX_INPUT_CHARS:
                msg = f"Input text at index {idx} length ({len(text)}) exceeds {_MAX_INPUT_CHARS}"
                raise ProviderProtocolError(msg)

        self._verify_model_allowed(req.model)
        url, headers, extensions = await self._resolve_target("/api/embed")

        payload = {
            "model": req.model,
            "input": list(req.inputs),
            "keep_alive": self._settings.keep_alive,
        }

        try:
            response = await self._client.post(
                url,
                json=payload,
                headers=headers,
                extensions=extensions,
            )
            self._handle_error_response(response)

            try:
                data = response.json()
            except Exception as err:
                msg = f"Ollama returned malformed JSON payload: {err}"
                raise ProviderProtocolError(msg) from err

            return _parse_embeddings_data(data.get("embeddings"))
        except httpx.TimeoutException as err:
            msg = f"Ollama embed request timed out: {err}"
            raise ProviderTimeout(msg) from err
        except httpx.ConnectError as err:
            msg = f"Failed to connect to Ollama: {err}"
            raise ProviderUnavailable(msg) from err
        except httpx.RequestError as err:
            msg = f"Ollama HTTP request failed: {err}"
            raise ProviderProtocolError(msg) from err

    async def health_probe(self) -> HealthStatus:
        """Probe Ollama daemon health via GET /api/tags (never raises)."""
        t0 = time.perf_counter()
        try:
            url, headers, extensions = await self._resolve_target("/api/tags")
            response = await self._client.get(
                url,
                headers=headers,
                extensions=extensions,
                timeout=2.0,
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            if response.status_code == _HTTP_OK:
                data = response.json()
                models = tuple(str(m.get("name", "")) for m in data.get("models", []))
                return HealthStatus(ok=True, latency_ms=latency_ms, models=models)
            return HealthStatus(ok=False, latency_ms=latency_ms, models=())
        except Exception:  # noqa: BLE001  # Health probe must never raise
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return HealthStatus(ok=False, latency_ms=latency_ms, models=())
