# Copyright 2026 Kanban Platform Contributors
"""Authenticated internal HTTP/2 client for communication between MCP and kanban-api."""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING, Any, Final, Self

import httpx

from mcp.errors import KbMcpError, McpErrorCode

if TYPE_CHECKING:
    import types

    from starlette.types import ASGIApp

    from mcp.settings import McpSettings

__all__ = [
    "KanbanApiClient",
]

_CONNECT_TIMEOUT_S: Final[float] = 2.0
_READ_TIMEOUT_S: Final[float] = 10.0
_WRITE_TIMEOUT_S: Final[float] = 10.0
_POOL_TIMEOUT_S: Final[float] = 2.0
_DEFAULT_BODY_LIMIT_BYTES: Final[int] = 8 * 1024 * 1024  # 8 MiB

_HTTP_BAD_REQUEST: Final[int] = 400
_HTTP_NOT_FOUND: Final[int] = 404
_HTTP_CONFLICT: Final[int] = 409
_HTTP_PRECONDITION_FAILED: Final[int] = 412
_HTTP_UNPROCESSABLE_ENTITY: Final[int] = 422
_HTTP_TOO_MANY_REQUESTS: Final[int] = 429
_HTTP_SERVER_ERROR_MIN: Final[int] = 500


class KanbanApiClient:
    """Internal HTTP/2 mTLS client connecting MCP server to kanban-api."""

    def __init__(
        self,
        settings: McpSettings,
        *,
        kanban_app: ASGIApp | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize client with mTLS certificates or in-process ASGI transport.

        Raises:
            ValueError: If plaintext http:// base URL is provided in mtls mode,
                or if kanban_app is omitted in standalone_inprocess mode.

        """
        self.settings: Final[McpSettings] = settings
        self.response_body_limit_bytes: Final[int] = settings.response_body_limit_bytes

        timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT_S,
            read=_READ_TIMEOUT_S,
            write=_WRITE_TIMEOUT_S,
            pool=_POOL_TIMEOUT_S,
        )

        if settings.mode == "standalone_inprocess":
            if transport is not None:
                active_transport = transport
            elif kanban_app is not None:
                active_transport = httpx.ASGITransport(app=kanban_app)
            else:
                msg = "kanban_app or transport is required in standalone_inprocess mode"
                raise ValueError(msg)
            self._client = httpx.AsyncClient(
                transport=active_transport,
                base_url="http://kanban.local",
                timeout=timeout,
            )
        else:
            # mTLS mode
            if settings.kanban_api_base_url.startswith("http://"):
                msg = (
                    f"Plaintext http:// base URL is strictly prohibited in mtls mode: "
                    f"'{settings.kanban_api_base_url}'"
                )
                raise ValueError(msg)

            verify: str | bool = (
                str(settings.internal_ca_path) if settings.internal_ca_path else True
            )
            cert = (
                (str(settings.client_cert_path), str(settings.client_key_path))
                if settings.client_cert_path and settings.client_key_path
                else None
            )

            if transport is not None:
                self._client = httpx.AsyncClient(
                    transport=transport,
                    base_url=settings.kanban_api_base_url,
                    timeout=timeout,
                )
            else:
                self._client = httpx.AsyncClient(
                    http2=True,
                    verify=verify,
                    cert=cert,
                    base_url=settings.kanban_api_base_url,
                    timeout=timeout,
                )

    async def aclose(self) -> None:
        """Close the underlying HTTP client session and connections."""
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def request(  # noqa: PLR0913
        self,
        method: str,
        path: str,
        *,
        subject_token: str | None = None,
        mcp_session_id: str | None = None,
        json_data: object = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> object:
        """Send authenticated internal request with identity forwarding and error mapping."""
        req_headers = dict(headers or {})
        if subject_token:
            req_headers["X-KB-Subject-Token"] = subject_token
        if mcp_session_id:
            req_headers["X-KB-MCP-Session"] = mcp_session_id

        try:
            req = self._client.build_request(
                method,
                path,
                json=json_data,
                params=params,
                headers=req_headers,
            )
            resp = await self._client.send(req, stream=True)
        except httpx.TransportError as exc:
            msg = f"Upstream communication failure: {exc}"
            raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg) from exc

        body_chunks: list[bytes] = []
        total_bytes = 0
        try:
            async for chunk in resp.aiter_bytes():
                total_bytes += len(chunk)
                if total_bytes > self.response_body_limit_bytes:
                    await resp.aclose()
                    msg = (
                        f"Response body size ({total_bytes} bytes) exceeds limit of "
                        f"{self.response_body_limit_bytes} bytes"
                    )
                    raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)
                body_chunks.append(chunk)
        finally:
            await resp.aclose()

        body_bytes = b"".join(body_chunks)

        if resp.status_code >= _HTTP_BAD_REQUEST:
            self._map_upstream_error(resp.status_code, body_bytes)

        if not body_bytes:
            return None

        try:
            return json.loads(body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return body_bytes.decode("utf-8", errors="replace")

    def _map_upstream_error(self, status_code: int, body_bytes: bytes) -> None:
        """Map RFC 7807 problem details or raw HTTP error status to McpErrorCode."""
        problem: dict[str, Any] = {}
        if body_bytes:
            with contextlib.suppress(json.JSONDecodeError, UnicodeDecodeError):
                loaded = json.loads(body_bytes.decode("utf-8"))
                if isinstance(loaded, dict):
                    problem = loaded

        prob_type = str(problem.get("type", ""))
        prob_title = str(problem.get("title", ""))
        prob_detail = str(problem.get("detail", ""))
        prob_code = str(problem.get("code", ""))
        prob_hint = problem.get("hint")
        prob_candidates = problem.get("candidates")
        error_message = prob_detail or prob_title or f"Upstream returned HTTP {status_code}"

        mapped_code = self._resolve_error_code(status_code, prob_type, prob_code)
        hint_str = str(prob_hint) if prob_hint is not None else None
        extra_layer = problem.get("layer") or (
            problem["extra"].get("layer") if isinstance(problem.get("extra"), dict) else None
        )
        if extra_layer:
            layer_text = f"layer: {extra_layer}"
            hint_str = f"{hint_str} ({layer_text})" if hint_str else layer_text

        candidates_list = (
            [dict(c) for c in prob_candidates] if isinstance(prob_candidates, list) else None
        )
        raise KbMcpError(mapped_code, error_message, hint=hint_str, candidates=candidates_list)

    @staticmethod
    def _resolve_conflict_code(prob_type: str, prob_code: str) -> McpErrorCode:  # noqa: PLR0911
        if prob_type.endswith("etag-mismatch"):
            return McpErrorCode.CONFLICT_ETAG
        if prob_type.endswith("ambiguous-identifier") or prob_code == "AMBIGUOUS_IDENTIFIER":
            return McpErrorCode.AMBIGUOUS_IDENTIFIER
        if prob_type.endswith("lockout-prevented") or prob_code == "LOCKOUT_PREVENTED":
            return McpErrorCode.LOCKOUT_PREVENTED
        if prob_type.endswith("plan-stale") or prob_code == "PLAN_STALE":
            return McpErrorCode.PLAN_STALE
        if prob_type.endswith("state-in-use") or prob_code == "STATE_IN_USE":
            return McpErrorCode.STATE_IN_USE
        if prob_type.endswith("priority-in-use") or prob_code == "PRIORITY_IN_USE":
            return McpErrorCode.PRIORITY_IN_USE
        if prob_type.endswith("invalid-transition") or prob_code in (
            "INVALID_TRANSITION",
            "INVALID_CYCLE_TRANSITION",
        ):
            return McpErrorCode.INVALID_TRANSITION
        return McpErrorCode.VALIDATION_FAILED

    @staticmethod
    def _resolve_error_code(  # noqa: PLR0911
        status_code: int,
        prob_type: str,
        prob_code: str = "",
    ) -> McpErrorCode:
        """Determine McpErrorCode from HTTP status and problem type."""
        if prob_code == "MODULES_DISABLED" or prob_type.endswith("modules-disabled"):
            return McpErrorCode.MODULES_DISABLED
        if prob_code == "CONFIRM_PHRASE_MISMATCH" or prob_type.endswith("confirm-phrase-mismatch"):
            return McpErrorCode.CONFIRM_PHRASE_MISMATCH
        if prob_code == "AAL2_REQUIRED" or prob_type.endswith("aal2-required"):
            return McpErrorCode.AAL2_REQUIRED
        if prob_code == "LOCKOUT_PREVENTED" or prob_type.endswith("lockout-prevented"):
            return McpErrorCode.LOCKOUT_PREVENTED

        direct_map = {
            _HTTP_NOT_FOUND: McpErrorCode.NOT_FOUND,
            _HTTP_PRECONDITION_FAILED: McpErrorCode.CONFLICT_ETAG,
            _HTTP_UNPROCESSABLE_ENTITY: McpErrorCode.VALIDATION_FAILED,
            _HTTP_TOO_MANY_REQUESTS: McpErrorCode.RATE_LIMITED,
        }
        if status_code in direct_map:
            return direct_map[status_code]
        if status_code == _HTTP_CONFLICT:
            return KanbanApiClient._resolve_conflict_code(prob_type, prob_code)
        if status_code >= _HTTP_SERVER_ERROR_MIN:
            return McpErrorCode.UPSTREAM_UNAVAILABLE
        return McpErrorCode.UPSTREAM_ERROR
