# Copyright 2026 Kanban Platform Contributors
"""Deterministic asynchronous HTTP transport for offline cassette replay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import yaml

from agent.testing.fixtures import CassetteMismatchError

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "CassetteTransport",
]

_OVERSIZE_BYTES: int = 70_000


class CassetteTransport(httpx.AsyncBaseTransport):
    """Asynchronous HTTP transport replaying pre-recorded cassette exchanges."""

    def __init__(
        self,
        cassette_or_exchanges: Path | str | dict[str, Any] | Sequence[dict[str, Any]],
    ) -> None:
        """Initialize transport with cassette path, raw dict, or exchange list."""
        self.call_count: int = 0
        self.requests: list[httpx.Request] = []
        self._exchanges: list[dict[str, Any]] = []

        if isinstance(cassette_or_exchanges, (Path, str)):
            path = Path(cassette_or_exchanges)
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if isinstance(data, dict) and "http_exchanges" in data:
                self._exchanges = list(data["http_exchanges"])
            elif isinstance(data, list):
                self._exchanges = list(data)
        elif isinstance(cassette_or_exchanges, dict):
            if "http_exchanges" in cassette_or_exchanges:
                self._exchanges = list(cassette_or_exchanges["http_exchanges"])
            else:
                self._exchanges = [cassette_or_exchanges]
        else:
            self._exchanges = list(cassette_or_exchanges)

    @property
    def exchange_count(self) -> int:
        """Return total number of loaded HTTP exchanges."""
        return len(self._exchanges)

    def _match_request(
        self,
        req_spec: dict[str, Any],
        request: httpx.Request,
        body_bytes: bytes,
    ) -> None:
        expected_method = str(req_spec.get("method", "")).upper()
        if request.method.upper() != expected_method:
            msg = f"HTTP method mismatch: expected {expected_method}, got {request.method.upper()}"
            raise CassetteMismatchError(msg)

        expected_path = str(req_spec.get("path", ""))
        if request.url.path != expected_path:
            msg = f"HTTP path mismatch: expected {expected_path}, got {request.url.path}"
            raise CassetteMismatchError(msg)

        if "json_contains" in req_spec:
            expected_json = req_spec["json_contains"]
            try:
                actual_json = json.loads(body_bytes.decode("utf-8"))
            except Exception as err:
                msg = f"Failed to parse request JSON body: {err}"
                raise CassetteMismatchError(msg) from err

            if isinstance(expected_json, dict) and isinstance(actual_json, dict):
                for k, v in expected_json.items():
                    actual_val = actual_json.get(k)
                    if actual_val != v:
                        msg = f"JSON mismatch for '{k}': expected {v!r}, got {actual_val!r}"
                        raise CassetteMismatchError(msg)

    def _render_fault(
        self,
        fault: dict[str, Any],
        request: httpx.Request,
    ) -> httpx.Response:
        kind = str(fault.get("kind", ""))
        if kind == "http_429":
            return httpx.Response(
                status_code=429,
                headers={"retry-after": "30", "content-type": "application/json"},
                json={"error": "rate limit exceeded"},
                request=request,
            )
        if kind == "http_500":
            return httpx.Response(
                status_code=500,
                headers={"content-type": "application/json"},
                json={"error": "internal server error"},
                request=request,
            )
        if kind == "timeout":
            msg = "Simulated read timeout"
            raise httpx.ReadTimeout(msg, request=request)
        if kind == "connect_error":
            msg = "Simulated connection error"
            raise httpx.ConnectError(msg, request=request)
        if kind == "malformed_body":
            return httpx.Response(
                status_code=200,
                content=b"INVALID MALFORMED NON-JSON GARBAGE {[\n",
                request=request,
            )
        if kind == "oversize_line":
            oversize_data = "x" * _OVERSIZE_BYTES
            content = f'{{"response": "{oversize_data}", "done": false}}\n'.encode()
            return httpx.Response(
                status_code=200,
                headers={"content-type": "application/x-ndjson"},
                content=content,
                request=request,
            )

        msg = f"Unknown simulated fault kind '{kind}'"
        raise ValueError(msg)

    def _render_response(
        self,
        resp_spec: dict[str, Any],
        request: httpx.Request,
    ) -> httpx.Response:
        status = int(resp_spec.get("status", 200))
        headers = {str(k).lower(): str(v) for k, v in resp_spec.get("headers", {}).items()}

        if "ndjson_chunks" in resp_spec:
            lines = [
                json.dumps(chunk) if isinstance(chunk, (dict, list)) else str(chunk)
                for chunk in resp_spec["ndjson_chunks"]
            ]
            content = ("\n".join(lines) + "\n").encode("utf-8")
            if "content-type" not in headers:
                headers["content-type"] = "application/x-ndjson"
            return httpx.Response(
                status_code=status,
                headers=headers,
                content=content,
                request=request,
            )

        if "sse_chunks" in resp_spec:
            chunks = [f"data: {c}\n\n" for c in resp_spec["sse_chunks"]]
            content = "".join(chunks).encode("utf-8")
            if "content-type" not in headers:
                headers["content-type"] = "text/event-stream"
            return httpx.Response(
                status_code=status,
                headers=headers,
                content=content,
                request=request,
            )

        if "json_body" in resp_spec:
            if "content-type" not in headers:
                headers["content-type"] = "application/json"
            return httpx.Response(
                status_code=status,
                headers=headers,
                json=resp_spec["json_body"],
                request=request,
            )

        text_content = str(resp_spec.get("text", ""))
        return httpx.Response(
            status_code=status,
            headers=headers,
            text=text_content,
            request=request,
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Handle incoming asynchronous HTTP request against recorded exchanges."""
        if self.call_count >= len(self._exchanges):
            msg = (
                f"No cassette exchange remaining for request {request.method} {request.url.path} "
                f"(handled {self.call_count}/{len(self._exchanges)} exchanges)"
            )
            raise CassetteMismatchError(msg)

        exchange = self._exchanges[self.call_count]
        req_spec = exchange.get("request", {})
        body_bytes = await request.aread()

        self._match_request(req_spec, request, body_bytes)
        self.call_count += 1
        self.requests.append(request)

        fault = exchange.get("fault")
        if fault is not None:
            return self._render_fault(fault, request)

        resp_spec = exchange.get("response", {})
        return self._render_response(resp_spec, request)
